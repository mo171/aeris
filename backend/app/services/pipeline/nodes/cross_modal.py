"""S1/S9 and independent optical/SAR branches joined by the Phase 1.11 late-fusion ledger."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from affine import Affine

from app.constants.evidence import (
    COUNT_PRECISION,
    DETECTION_MASK_DETECTED,
    DETECTION_MASK_NOT_DETECTED,
    DETECTION_MASK_UNOBSERVED,
    ClaimKind,
    EvidenceKind,
    MetricDirection,
)
from app.constants.fleet import FLEET
from app.constants.model_ids import ModelId
from app.constants.raster import BandRole, ProcessingLevel
from app.constants.scenes import Polarisation, SceneModality
from app.constants.spectral import INDEX_ENGINE_VERSION
from app.constants.stages import PipelineStage
from app.db.identifiers import IdentifierPrefix, new_identifier
from app.lib.exceptions import InvalidRequestError
from app.schemas.cross_modal import (
    AgreementRow,
    CrossModalResult,
    FusionVerdict,
    ModalityAdvisory,
    SensorRun,
)
from app.schemas.events import Claim, ClaimEvent, ClaimMetric, LayerReadyEvent
from app.services.evidence.artefacts import read_artefact, store_artefact, store_json_artefact
from app.services.evidence.builder import build_region_evidence
from app.services.evidence.spatial import measure_mask_on_grid
from app.services.evidence.trace import ArtefactRecord, ModelRecord
from app.services.imagery.frames import InputKind, inspect_input, read_rgb_frame
from app.services.optical_sar.math.fusion_rules import (
    SensorFindingMasks,
    assess_pair,
    build_agreement_findings,
    fused_confidence,
    minimum_region_pixels_for_hectares,
    source_feature_ids_for_component,
)
from app.services.optical_sar.math.indices import optical_landcover_masks
from app.services.optical_sar.math.sar_masks import sar_landcover_masks
from app.services.optical_sar.metadata import sentinel_metadata
from app.services.pipeline.node import current_trace_step_id, describe_trace_step, pipeline_node
from app.services.pipeline.state import AnalysisState
from app.services.pipeline.stream import emit
from app.services.preprocessing.cloud_masking import mask_from_scene_classification
from app.services.preprocessing.elevation import elevation_on_grid
from app.services.preprocessing.sar_calibration import preprocess_sar
from app.services.rendering.figures import render_cross_modal_overlay, render_mask_overlay
from app.services.spectral.indices import locate_bands, read_scene_bands, read_scene_classification

OPTICAL_ROLES = (BandRole.GREEN, BandRole.NEAR_INFRARED, BandRole.SHORTWAVE_INFRARED_1)
RADAR_ROLES = (BandRole.VV, BandRole.VH)
# Sentinel-1 nominal mid-swath incidence angle (IW mode: 29.1° - 46.0°, nominal center ~39.0°)
RADAR_NOMINAL_INCIDENCE_DEGREES = 39.0
# Sentinel-1 descending pass look azimuth (nominally ~280.0° for right-looking SAR)
RADAR_NOMINAL_LOOK_AZIMUTH_DEGREES = 280.0
# Backward-compatibility aliases
RADAR_INCIDENCE_DEGREES = RADAR_NOMINAL_INCIDENCE_DEGREES
RADAR_LOOK_AZIMUTH_DEGREES = RADAR_NOMINAL_LOOK_AZIMUTH_DEGREES
# At Sentinel's 10 m grid this is 500 pixels. The ledger is an operator-facing catalogue of material
# regions; complete per-pixel masks remain retained in the sensor artefacts.
MINIMUM_LEDGER_REGION_HECTARES = 5.0


@pipeline_node(PipelineStage.S1, detail="Validating one optical and one SAR acquisition")
async def validate_cross_modal_inputs(state: AnalysisState) -> dict[str, object]:
    if not state.get("reference_directory"):
        raise InvalidRequestError("CROSS_MODAL needs one optical and one SAR acquisition; only one was given.")
    declared = state.get("declared_resolution_metres")
    primary = await inspect_input(Path(state["scene_directory"]), declared_resolution_metres=declared, is_sar=bool(state.get("is_sar")))
    reference = await inspect_input(
        Path(state["reference_directory"]), declared_resolution_metres=declared,
        is_sar=bool(state.get("reference_is_sar")),
    )
    by_modality = {primary.modality: primary, reference.modality: reference}
    if set(by_modality) != {SceneModality.OPTICAL, SceneModality.SAR}:
        raise InvalidRequestError(
            "CROSS_MODAL needs exactly one optical and one SAR acquisition.",
            details={"modalities": [reference.modality.value, primary.modality.value]},
        )
    optical, radar = by_modality[SceneModality.OPTICAL], by_modality[SceneModality.SAR]
    if optical.kind is not InputKind.SCENE_DIRECTORY or radar.kind is not InputKind.SCENE_DIRECTORY:
        raise InvalidRequestError("CROSS_MODAL land-cover fusion needs scene directories with named optical and VV/VH bands.")
    if not optical.georeferenced or not radar.georeferenced:
        raise InvalidRequestError("CROSS_MODAL fusion needs both acquisitions georeferenced.")
    _require_common_grid(optical, radar)
    describe_trace_step(f"optical: {optical.describe()}; radar: {radar.describe()}; roles normalized from inspected bands")
    return {
        "scene_directory": str(optical.path), "scene_id": optical.scene_id, "is_sar": False,
        "reference_directory": str(radar.path), "reference_scene_id": radar.scene_id, "reference_is_sar": True,
        "optical_directory": str(optical.path), "radar_directory": str(radar.path),
        "optical_scene_id": optical.scene_id, "radar_scene_id": radar.scene_id,
        "input_records": [optical.to_wire(), radar.to_wire()], "georeferenced": True,
        "crs": optical.crs, "transform": list(optical.transform), "resolution_metres": optical.resolution_metres,
        "resolution_declared": optical.resolution_declared, "input_kind": optical.kind.value,
        "modality": SceneModality.OPTICAL.value,
    }


def _require_common_grid(optical: Any, radar: Any) -> None:
    if optical.shape != radar.shape or optical.crs != radar.crs:
        raise InvalidRequestError(
            "The optical and SAR acquisitions are not on one grid. Reproject the SAR bands onto the optical grid first.",
            details={"opticalShape": list(optical.shape), "radarShape": list(radar.shape), "opticalCrs": optical.crs, "radarCrs": radar.crs},
        )
    scale = max(abs(optical.transform[0]), abs(optical.transform[4]), 1e-12)
    residual = max(abs(left - right) for left, right in zip(optical.transform, radar.transform, strict=True)) / scale
    if residual >= 1.0:
        raise InvalidRequestError(
            f"Cross-modal affine-grid residual is {residual:.2f} px; fusion requires a sub-pixel grid.",
            details={"residualPixels": residual},
        )


@pipeline_node(
    PipelineStage.S9, detail="Measuring cross-sensor grid registration",
    model_id=ModelId.CO_REGISTRATION, model_version=FLEET[ModelId.CO_REGISTRATION].version,
)
async def coregister_modalities(state: AnalysisState) -> dict[str, object]:
    optical = await inspect_input(Path(state["optical_directory"]))
    radar = await inspect_input(Path(state["radar_directory"]), is_sar=True)
    scale = max(abs(optical.transform[0]), abs(optical.transform[4]), 1e-12)
    residual = max(abs(left - right) for left, right in zip(optical.transform, radar.transform, strict=True)) / scale
    record = {
        "method": "affine-grid", "residualPixels": residual, "tolerancePixels": 1.0,
        "accepted": residual < 1.0, "declaredRegistered": bool(state.get("declared_registered")),
    }
    artefact = await store_json_artefact(record, run_id=state["run_id"], stage=PipelineStage.S9, name="cross-modal-registration.json")
    record.update({"artefactPath": str(artefact.path), "artefactObjectKey": artefact.object_key, "artefactStorageUri": artefact.storage_uri})
    if not record["accepted"]:
        raise InvalidRequestError(f"Cross-modal fusion refused at {residual:.2f} px; registration must be sub-pixel.")
    describe_trace_step(f"common affine grid residual {residual:.2f} px (limit < 1.00 px)")
    return {
        "registration": record,
        "stage_models": [ModelRecord(
            stage=PipelineStage.S9, model_id=ModelId.CO_REGISTRATION.value,
            model_version=FLEET[ModelId.CO_REGISTRATION].version,
        ).to_wire()],
        "artefact_records": [ArtefactRecord(
            stage=PipelineStage.S9, name=artefact.path.name, object_key=artefact.object_key,
            storage_uri=artefact.storage_uri, local_path=str(artefact.path), layer_id=None,
        ).to_wire()],
    }


@pipeline_node(
    PipelineStage.S12, detail="Measuring cloud-masked optical water and built-up signatures",
    model_id=ModelId.INDEX_ENGINE, model_version=INDEX_ENGINE_VERSION,
)
async def analyse_optical(state: AnalysisState) -> dict[str, object]:
    path = Path(state["optical_directory"])
    source = await inspect_input(path)
    level = ProcessingLevel(state["declared_level"]) if state.get("declared_level") else None
    bands = await read_scene_bands(path, OPTICAL_ROLES, declared_level=level)
    scl = await read_scene_classification(path, bands.reference)
    cloud_mask = await mask_from_scene_classification(scl) if scl is not None else None
    observed = np.ones(source.shape, dtype=bool) if cloud_mask is None else ~cloud_mask.exclusion_mask
    result = await asyncio.to_thread(
        optical_landcover_masks,
        bands.bands[BandRole.GREEN].reflectance,
        bands.bands[BandRole.NEAR_INFRARED].reflectance,
        bands.bands[BandRole.SHORTWAVE_INFRARED_1].reflectance,
        observed,
    )
    frame = await read_rgb_frame(source, declared_level=level, mask=cloud_mask)
    metadata = sentinel_metadata(source.scene_id)
    branch = await _build_sensor_branch(
        state, source, frame, sensor="optical", platform=metadata.platform, captured_at=metadata.captured_at,
        masks=result, values={"water": result.mndwi, "built_up": result.ndbi},
        confidences={"water": result.water_confidence, "built_up": result.built_up_confidence},
        model_id=ModelId.INDEX_ENGINE, model_version=INDEX_ENGINE_VERSION,
        obscured=~result.observed, polarisation=None, look_azimuth=None, incidence=None,
        quantity={"water": "MNDWI > 0.15", "built_up": "NDBI > 0.05"},
    )
    describe_trace_step(
        f"MNDWI/NDBI on {result.observed.mean():.1%} observed ground; water {result.water.mean():.1%}, "
        f"built-up {result.built_up.mean():.1%}; informative={result.informative}"
    )
    sensor_masks = branch.pop("sensor_masks")
    sensor_run = branch.pop("sensor_run")
    return {**branch, "optical_informative": result.informative, "optical_masks": sensor_masks, "optical_sensor_run": sensor_run}


@pipeline_node(
    PipelineStage.S10, detail="Preprocessing VV/VH and measuring radar water and built-up signatures",
    model_id=ModelId.SAR_PREPROCESS, model_version=FLEET[ModelId.SAR_PREPROCESS].version,
)
async def analyse_radar(state: AnalysisState) -> dict[str, object]:
    path = Path(state["radar_directory"])
    source = await inspect_input(path, is_sar=True)
    located = await locate_bands(path)
    missing = [role for role in RADAR_ROLES if role not in located]
    if missing:
        raise InvalidRequestError(f"{source.scene_id} has no {', '.join(role.value for role in missing)} band.")
    vv = await asyncio.to_thread(_read_radar_band, located[BandRole.VV])
    vh = await asyncio.to_thread(_read_radar_band, located[BandRole.VH])
    # Planetary Computer backscatter windows and the synthetic gate are linear power; accept dB only when
    # every finite sample is non-positive, and record the conversion in the stage detail.
    vv_power, vv_was_db = _as_linear_power(vv)
    vh_power, vh_was_db = _as_linear_power(vh)
    elevation = await elevation_on_grid(located[BandRole.VV])
    incidence = float(state.get("radar_incidence_degrees") or RADAR_NOMINAL_INCIDENCE_DEGREES)
    look_azimuth = float(state.get("radar_look_azimuth_degrees") or RADAR_NOMINAL_LOOK_AZIMUTH_DEGREES)
    vv_processed, vh_processed = await asyncio.gather(
        preprocess_sar(
            vv_power, elevation, polarisation=Polarisation.VV, calibration_factor=None,
            incidence_angle_degrees=incidence, radar_azimuth_degrees=look_azimuth,
            pixel_size_metres=float(source.resolution_metres or 10.0),
        ),
        preprocess_sar(
            vh_power, elevation, polarisation=Polarisation.VH, calibration_factor=None,
            incidence_angle_degrees=incidence, radar_azimuth_degrees=look_azimuth,
            pixel_size_metres=float(source.resolution_metres or 10.0),
        ),
    )
    obscured = vv_processed.obscured_mask | vh_processed.obscured_mask
    observed = np.isfinite(vv_processed.terrain_corrected_power) & np.isfinite(vh_processed.terrain_corrected_power) & ~obscured
    result = await asyncio.to_thread(
        sar_landcover_masks, vv_processed.terrain_corrected_power, vh_processed.terrain_corrected_power, observed
    )
    frame = await read_rgb_frame(source)
    metadata = sentinel_metadata(source.scene_id)
    version = FLEET[ModelId.SAR_PREPROCESS].version
    branch = await _build_sensor_branch(
        state, source, frame, sensor="radar", platform=metadata.platform, captured_at=metadata.captured_at,
        masks=result, values={"water": result.vv_decibels, "built_up": result.vv_decibels},
        confidences={"water": result.water_confidence, "built_up": result.built_up_confidence},
        model_id=ModelId.SAR_PREPROCESS, model_version=version, obscured=~result.observed,
        polarisation="ratio", look_azimuth=look_azimuth, incidence=incidence,
        quantity={"water": "VV <= -17 dB and VH <= -22 dB", "built_up": "VV >= -8 dB and VH >= -15 dB"},
    )
    describe_trace_step(
        f"calibrate/pass-through -> Lee -> terrain flatten; input {'dB converted to power' if vv_was_db or vh_was_db else 'linear power'}; "
        f"{result.observed.mean():.1%} observable, water {result.water.mean():.1%}, built-up {result.built_up.mean():.1%}; "
        f"informative={result.informative}"
    )
    sensor_masks = branch.pop("sensor_masks")
    sensor_run = branch.pop("sensor_run")
    return {**branch, "radar_informative": result.informative, "radar_masks": sensor_masks, "radar_sensor_run": sensor_run}


async def _build_sensor_branch(
    state: AnalysisState,
    source: Any,
    frame: Any,
    *,
    sensor: str,
    platform: str,
    captured_at: datetime,
    masks: Any,
    values: dict[str, np.ndarray],
    confidences: dict[str, float | None],
    model_id: ModelId,
    model_version: str,
    obscured: np.ndarray,
    polarisation: str | None,
    look_azimuth: float | None,
    incidence: float | None,
    quantity: dict[str, str],
) -> dict[str, Any]:
    run_id, step_id = state["run_id"], current_trace_step_id()
    layers: list[dict[str, Any]] = []
    evidence_items: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    artefacts: list[dict[str, Any]] = []
    figures: list[str] = []
    mask_state: dict[str, Any] = {}
    feature_ids_by_region_label: dict[str, dict[str, str]] = {}
    base_rgba = np.dstack([frame.rgb, np.where(frame.observed, 255, 0).astype(np.uint8)])
    for key, label in (("built_up", "Built-up"), ("water", "Water")):
        detected = getattr(masks, key)
        observed = masks.observed
        encoded = np.full(detected.shape, DETECTION_MASK_NOT_DETECTED, dtype=np.uint8)
        encoded[detected] = DETECTION_MASK_DETECTED
        encoded[~observed] = DETECTION_MASK_UNOBSERVED
        stored = await store_artefact(
            encoded, run_id=run_id, stage=PipelineStage.S12 if sensor == "optical" else PipelineStage.S10,
            name=f"{sensor}-{key.replace('_', '-')}.tif", reference=source.reference,
            nodata=DETECTION_MASK_UNOBSERVED, categorical=True,
        )
        statistics = await measure_mask_on_grid(
            detected, observed, transform=source.transform, crs=source.crs,
            resolution_metres=source.resolution_metres, resolution_declared=source.resolution_declared,
        )
        region = await build_region_evidence(
            detected, values[key], statistics=statistics, transform=source.transform, crs=source.crs,
            resolution_metres=source.resolution_metres, run_id=run_id, trace_step_id=step_id,
            scene_id=source.scene_id, mask_storage_uri=stored.storage_uri, index_label=label,
            quantity_label=quantity[key], region_label=f"{sensor.title()} {label}", lower=-30.0 if sensor == "radar" else -1.0,
            upper=5.0 if sensor == "radar" else 1.0, obscured_fraction=float(obscured.mean()),
            unphysical_fraction=0.0, model_id=model_id, model_version=model_version,
            confidence=confidences[key], evidence_kind=EvidenceKind.CROSS_MODAL,
        )
        for layer in region.layers:
            emit(LayerReadyEvent(run_id=run_id, layer=layer, evidence=region.evidence if layer is region.vector_layer else []))
            layers.append(layer.to_wire())
        branch_claims: list[Claim] = []
        for claim in region.claims:
            wire = claim.to_wire()
            wire["isPrimary"] = False
            validated = Claim.model_validate(wire)
            emit(ClaimEvent(run_id=run_id, claim=validated))
            branch_claims.append(validated)
            claims.append(validated.to_wire())
        evidence_items.extend(item.to_wire() for item in region.evidence)
        feature_ids_by_region_label[key] = {
            str(label): feature_id for label, feature_id in region.feature_ids_by_region_label.items()
        }
        overlay = await render_mask_overlay(
            detected, base_rgba, run_id=run_id, trace_step_id=step_id,
            title=f"{sensor.title()} {label} - {source.scene_id}", label=f"{sensor.title()} {label}",
            scene_ids=[source.scene_id], crs=source.crs, claim_ids=[claim.id for claim in branch_claims],
            caption=f"{label} derived independently from {sensor} evidence; unobserved ground is transparent.",
        )
        emit(overlay.event)
        figures.append(overlay.event.figure_id)
        artefacts.append(ArtefactRecord(
            stage=PipelineStage.S12 if sensor == "optical" else PipelineStage.S10,
            name=stored.path.name, object_key=stored.object_key, storage_uri=stored.storage_uri,
            local_path=str(stored.path), layer_id=region.raster_layer.id if region.raster_layer else None,
        ).to_wire())
        mask_state[key] = {"path": str(stored.path), "key": stored.object_key}
    stated = [value for value in confidences.values() if value is not None]
    sensor_run = SensorRun(
        sensor=sensor, scene_id=source.scene_id, captured_at=captured_at, platform=platform,
        polarisation=polarisation, look_azimuth_degrees=look_azimuth, incidence_angle_degrees=incidence,
        layers=layers, evidence=evidence_items, claims=claims, model_id=model_id.value,
        model_version=model_version, confidence=min(stated) if stated else None,
        obscured_fraction=float(obscured.mean()),
    )
    mask_state.update({"featureIdsByRegionLabel": feature_ids_by_region_label, "confidences": confidences})
    return {
        "sensor_run": sensor_run.to_wire(), "sensor_masks": mask_state,
        "layers": layers, "evidence_items": evidence_items, "claims": claims,
        "artefact_records": artefacts, "figure_ids": figures, "input_files": await frame.input_records(),
        "stage_models": [ModelRecord(
            stage=PipelineStage.S12 if sensor == "optical" else PipelineStage.S10,
            model_id=model_id.value, model_version=model_version, confidence=sensor_run.confidence,
        ).to_wire()],
    }


@pipeline_node(
    PipelineStage.S15, detail="Building the optical/SAR agreement ledger",
    model_id=ModelId.OPTICAL_SAR_FUSION, model_version=FLEET[ModelId.OPTICAL_SAR_FUSION].version,
)
async def fuse_modalities(state: AnalysisState) -> dict[str, object]:
    optical_masks = await _restore_sensor_masks(state["optical_masks"])
    radar_masks = await _restore_sensor_masks(state["radar_masks"])
    source = await inspect_input(Path(state["optical_directory"]))
    findings = await asyncio.to_thread(
        build_agreement_findings,
        optical_masks,
        radar_masks,
        minimum_region_pixels=minimum_region_pixels_for_hectares(
            MINIMUM_LEDGER_REGION_HECTARES, resolution_metres=float(source.resolution_metres or 10.0)
        ),
    )
    optical_run = SensorRun.model_validate(state["optical_sensor_run"])
    radar_run = SensorRun.model_validate(state["radar_sensor_run"])
    optical_meta = sentinel_metadata(optical_run.scene_id)
    radar_meta = sentinel_metadata(radar_run.scene_id)
    residual = float(state["registration"]["residualPixels"])
    assessment = assess_pair(optical_meta.captured_at, radar_meta.captured_at, residual)
    advisory = ModalityAdvisory(
        verdict=assessment.verdict, offset_days=assessment.offset_days,
        co_registration_pixels=assessment.co_registration_pixels, notes=list(assessment.notes),
    )
    rows: list[AgreementRow] = []
    for finding in findings:
        cropped_transform = tuple(
            Affine(*source.transform) @ Affine.translation(finding.column_start, finding.row_start)
        )[:6]
        statistics = await measure_mask_on_grid(
            finding.mask, np.ones(finding.mask.shape, dtype=bool), transform=cropped_transform,
            crs=source.crs, resolution_metres=source.resolution_metres, resolution_declared=source.resolution_declared,
        )
        rows.append(AgreementRow(
            id=new_identifier(IdentifierPrefix.FEATURE), label=finding.label, state=finding.state,
            reason=finding.reason,
            optical_feature_ids=_finding_feature_ids(
                state["optical_masks"], getattr(optical_masks, finding.optical_class), finding, finding.optical_class,
            ) if finding.optical_class is not None else [],
            radar_feature_ids=_finding_feature_ids(
                state["radar_masks"], getattr(radar_masks, finding.radar_class), finding, finding.radar_class,
            ) if finding.radar_class is not None else [],
            optical_confidence=finding.optical_confidence, radar_confidence=finding.radar_confidence,
            area_hectares=statistics.detected.hectares,
        ))
    conflicts = [row for row in rows if row.state == "conflict"]
    refused = assessment.refusal
    informative = bool(state.get("optical_informative")) and bool(state.get("radar_informative"))
    if refused:
        verdict = FusionVerdict(headline=None, confidence=None, refused_because=refused, blocked_by_conflict=None, rows=rows)
    elif conflicts:
        verdict = FusionVerdict(
            headline=None, confidence=None, refused_because=None,
            blocked_by_conflict=f"{len(conflicts)} region(s) carry opposing physical classes; acquire a third observation.", rows=rows,
        )
    elif not informative:
        advisory.notes.append("At least one sensor lacked enough dynamic range for silence to count as evidence; no fused verdict was produced.")
        verdict = None
    else:
        corroborated = sum(row.state == "corroborated" for row in rows)
        optical_only = sum(row.state == "optical-only" for row in rows)
        radar_only = sum(row.state == "radar-only" for row in rows)
        headline = f"{corroborated} of {len(rows)} regions are corroborated; {optical_only} optical-only and {radar_only} radar-only."
        verdict = FusionVerdict(
            headline=headline, confidence=fused_confidence(optical_run.confidence, radar_run.confidence),
            refused_because=None, blocked_by_conflict=None, rows=rows,
        )
    new_claims: list[dict[str, Any]] = []
    evidence_ids = [item.id for item in optical_run.evidence + radar_run.evidence]
    claim_text: str | None = None
    claim_confidence: float | None = None
    claim_metrics: list[ClaimMetric] = []
    if verdict is not None and verdict.headline is not None:
        claim_text = verdict.headline
        claim_confidence = verdict.confidence
        claim_metrics = [ClaimMetric(
            label="Corroborated regions", value=float(sum(row.state == "corroborated" for row in rows)),
            unit="", direction=MetricDirection.NEUTRAL, precision=COUNT_PRECISION,
        )]
    elif verdict is not None and verdict.blocked_by_conflict is not None:
        claim_text = (
            "AERIS cannot produce a fused conclusion: "
            f"{len(conflicts)} material optical/SAR conflict requires a third observation."
        )
        claim_metrics = [ClaimMetric(
            label="Material optical/SAR conflicts", value=float(len(conflicts)), unit="",
            direction=MetricDirection.NEUTRAL, precision=COUNT_PRECISION,
        )]
    elif verdict is not None and verdict.refused_because is not None:
        claim_text = f"AERIS cannot produce a fused conclusion: {verdict.refused_because}"
    else:
        claim_text = (
            "AERIS cannot produce a fused conclusion because at least one sensor lacks sufficient "
            "dynamic range; acquire informative optical and SAR observations."
        )
    claim = Claim(
        id=new_identifier(IdentifierPrefix.CLAIM), run_id=state["run_id"], text=claim_text,
        kind=ClaimKind.CATEGORICAL, confidence=claim_confidence, metrics=claim_metrics,
        evidence_ids=evidence_ids, model_id=ModelId.OPTICAL_SAR_FUSION,
        model_version=FLEET[ModelId.OPTICAL_SAR_FUSION].version,
        trace_step_id=current_trace_step_id(), is_primary=True,
    )
    emit(ClaimEvent(run_id=state["run_id"], claim=claim))
    new_claims.append(claim.to_wire())
    level = ProcessingLevel(state["declared_level"]) if state.get("declared_level") else None
    frame = await read_rgb_frame(source, declared_level=level)
    base_rgba = np.dstack([
        frame.rgb,
        np.where(optical_masks.observed | radar_masks.observed, 255, 0).astype(np.uint8),
    ])
    fusion_figure = await render_cross_modal_overlay(
        optical_masks.water, optical_masks.built_up, radar_masks.water, radar_masks.built_up, base_rgba,
        run_id=state["run_id"], trace_step_id=current_trace_step_id(),
        title=f"Optical/SAR agreement - {optical_run.scene_id}",
        scene_ids=[optical_run.scene_id, radar_run.scene_id], crs=source.crs,
        observed=optical_masks.observed | radar_masks.observed,
        caption=(
            f"Late-fusion partition for material regions of at least {MINIMUM_LEDGER_REGION_HECTARES:g} ha; "
            "conflict requires a third observation."
        ),
        claim_ids=[claim["id"] for claim in new_claims], is_primary=bool(new_claims),
    )
    emit(fusion_figure.event)
    result = CrossModalResult(
        investigation_id=state["run_id"], run_id=state["run_id"], optical=optical_run, radar=radar_run,
        advisory=advisory, verdict=verdict, generated_at=datetime.now(UTC),
    )
    result_artefact = await store_json_artefact(
        result.to_wire(), run_id=state["run_id"], stage=PipelineStage.S15, name="cross-modal-result.json"
    )
    describe_trace_step(
        f"{len(rows)} spatial rows: {sum(row.state == 'corroborated' for row in rows)} corroborated, "
        f"{sum(row.state != 'corroborated' for row in rows)} disagreement/single-sensor; "
        + ("fused" if verdict and verdict.headline else "no fused headline")
    )
    return {
        "cross_modal_result": result.to_wire(), "cross_modal_result_path": str(result_artefact.path),
        "claims": new_claims,
        "primary_figure_id": fusion_figure.event.figure_id if new_claims else None,
        "figure_ids": [fusion_figure.event.figure_id],
        "artefact_records": [ArtefactRecord(
            stage=PipelineStage.S15, name=result_artefact.path.name, object_key=result_artefact.object_key,
            storage_uri=result_artefact.storage_uri, local_path=str(result_artefact.path), layer_id=None,
        ).to_wire()],
        "stage_models": [ModelRecord(
            stage=PipelineStage.S15, model_id=ModelId.OPTICAL_SAR_FUSION.value,
            model_version=FLEET[ModelId.OPTICAL_SAR_FUSION].version,
            confidence=verdict.confidence if verdict else None,
        ).to_wire()],
    }


async def _restore_sensor_masks(record: dict[str, Any]) -> SensorFindingMasks:
    arrays: dict[str, np.ndarray] = {}
    observed: np.ndarray | None = None
    for key in ("water", "built_up"):
        encoded = await read_artefact(Path(record[key]["path"]), record[key]["key"])
        arrays[key] = encoded == DETECTION_MASK_DETECTED
        one_observed = encoded != DETECTION_MASK_UNOBSERVED
        observed = one_observed if observed is None else observed & one_observed
    assert observed is not None
    confidences = record.get("confidences", {})
    return SensorFindingMasks(
        water=arrays["water"], built_up=arrays["built_up"], observed=observed, obscured=~observed,
        water_confidence=confidences.get("water"), built_up_confidence=confidences.get("built_up"),
    )


def _finding_feature_ids(
    mask_record: dict[str, Any], source_mask: np.ndarray, finding: Any, class_id: str,
) -> list[str]:
    mapping = {
        int(label): feature_id
        for label, feature_id in mask_record.get("featureIdsByRegionLabel", {}).get(class_id, {}).items()
    }
    return source_feature_ids_for_component(
        source_mask, finding.mask, row_start=finding.row_start, column_start=finding.column_start,
        feature_ids_by_region_label=mapping,
    )


def _read_radar_band(path: Path) -> np.ndarray:
    with rasterio.open(path) as dataset:
        values = dataset.read(1).astype(np.float32)
        if dataset.nodata is not None:
            values[values == dataset.nodata] = np.nan
    return values


def _as_linear_power(values: np.ndarray) -> tuple[np.ndarray, bool]:
    finite = values[np.isfinite(values)]
    was_db = bool(finite.size and np.nanmax(finite) <= 0.0)
    return (np.power(10.0, values / 10.0).astype(np.float32), True) if was_db else (values, False)
