"""Pure late-fusion rules: pair admissibility and spatial agreement partitions."""

from dataclasses import dataclass, replace
from datetime import datetime
from math import ceil
from typing import Literal

import numpy as np
from scipy import ndimage

from app.services.segmentation.math.vectorize import label_regions

type AgreementState = Literal["conflict", "corroborated", "optical-only", "radar-only"]
type AdvisoryVerdict = Literal["fair", "offset", "unusable"]
type LandcoverClass = Literal["water", "built_up"]

FAIR_OFFSET_DAYS = 12
MAXIMUM_OFFSET_DAYS = 30
MAXIMUM_REGISTRATION_PIXELS = 1.0


def minimum_region_pixels_for_hectares(hectares: float, *, resolution_metres: float) -> int:
    """Convert the ledger's material-ground threshold to its current analysis grid."""
    if hectares <= 0.0 or resolution_metres <= 0.0:
        raise ValueError("Material area and resolution must both be positive.")
    return max(1, ceil(hectares * 10_000.0 / resolution_metres**2))


@dataclass(frozen=True, slots=True)
class SensorFindingMasks:
    water: np.ndarray
    built_up: np.ndarray
    observed: np.ndarray
    obscured: np.ndarray
    water_confidence: float | None
    built_up_confidence: float | None


@dataclass(frozen=True, slots=True)
class AgreementFinding:
    label: str
    state: AgreementState
    reason: str
    mask: np.ndarray
    pixel_count: int
    optical_confidence: float | None
    radar_confidence: float | None
    row_start: int = 0
    column_start: int = 0
    optical_class: LandcoverClass | None = None
    radar_class: LandcoverClass | None = None


@dataclass(frozen=True, slots=True)
class PairAssessment:
    verdict: AdvisoryVerdict
    offset_days: int
    co_registration_pixels: float | None
    notes: tuple[str, ...]
    refusal: str | None


def assess_pair(optical_captured_at: datetime, radar_captured_at: datetime, residual_pixels: float | None) -> PairAssessment:
    offset = abs((optical_captured_at - radar_captured_at).total_seconds())
    offset_days = round(offset / 86_400)
    notes: list[str] = []
    verdict: AdvisoryVerdict = "fair"
    refusal: str | None = None
    if offset_days > MAXIMUM_OFFSET_DAYS:
        verdict, refusal = "unusable", "poor-co-registration"
        notes.append(f"{offset_days} days apart; the pair does not describe one ground state.")
    elif offset_days > FAIR_OFFSET_DAYS:
        verdict = "offset"
        notes.append(f"{offset_days} days apart; intervening ground change may appear as sensor disagreement.")
    else:
        notes.append(f"{offset_days} days apart, within the normal cross-sensor orbital offset.")
    if residual_pixels is None:
        verdict, refusal = "unusable", "poor-co-registration"
        notes.append("Cross-sensor registration could not be measured.")
    elif residual_pixels >= MAXIMUM_REGISTRATION_PIXELS:
        verdict, refusal = "unusable", "poor-co-registration"
        notes.append(f"Alignment residual is {residual_pixels:.2f} px; fusion requires a sub-pixel residual.")
    else:
        notes.append(f"Alignment residual is {residual_pixels:.2f} px, below one pixel.")
    return PairAssessment(verdict, offset_days, residual_pixels, tuple(notes), refusal)


def fused_confidence(optical: float | None, radar: float | None) -> float | None:
    stated = [value for value in (optical, radar) if value is not None]
    return min(stated) if stated else None


def build_agreement_findings(
    optical: SensorFindingMasks,
    radar: SensorFindingMasks,
    *,
    minimum_region_pixels: int = 1,
) -> list[AgreementFinding]:
    """Partition real masks into conflict, corroborated, and single-sensor connected regions."""
    shapes = {array.shape for array in (*_arrays(optical), *_arrays(radar))}
    if len(shapes) != 1:
        raise ValueError(f"Fusion masks must share one grid, got {sorted(shapes)}.")
    rows: list[AgreementFinding] = []
    conflicts = (optical.water & radar.built_up) | (optical.built_up & radar.water)
    for optical_class, radar_class, conflict_mask in (
        ("water", "built_up", optical.water & radar.built_up),
        ("built_up", "water", optical.built_up & radar.water),
    ):
        rows.extend(_components(
            f"Optical {_display_class(optical_class)} / radar {_display_class(radar_class)} conflict",
            "conflict", conflict_mask,
            _reason("conflict", False, False, optical_class, radar_class), None, None, minimum_region_pixels,
            optical_class=optical_class, radar_class=radar_class,
        ))
    for class_id, label, optical_mask, radar_mask, optical_confidence, radar_confidence in (
        ("built_up", "Built-up", optical.built_up, radar.built_up, optical.built_up_confidence, radar.built_up_confidence),
        ("water", "Water", optical.water, radar.water, optical.water_confidence, radar.water_confidence),
    ):
        optical_mask = optical_mask & ~conflicts
        radar_mask = radar_mask & ~conflicts
        overlap = optical_mask & radar_mask
        optical_only = optical_mask & ~radar_mask
        radar_only = radar_mask & ~optical_mask
        rows.extend(_components(
            label, "corroborated", overlap, _reason("corroborated", False, False),
            optical_confidence, radar_confidence, minimum_region_pixels,
            optical_class=class_id, radar_class=class_id,
        ))
        rows.extend(_single_sensor_components(
            label, "optical-only", optical_only, radar.obscured, optical_confidence, None,
            minimum_region_pixels, optical_class=class_id, radar_class=None,
        ))
        rows.extend(_single_sensor_components(
            label, "radar-only", radar_only, optical.obscured, None, radar_confidence,
            minimum_region_pixels, optical_class=None, radar_class=class_id,
        ))
    return _renumber_by_class(rows)


def _single_sensor_components(
    label: str,
    state: AgreementState,
    mask: np.ndarray,
    other_obscured: np.ndarray,
    optical_confidence: float | None,
    radar_confidence: float | None,
    minimum_region_pixels: int,
    *,
    optical_class: LandcoverClass | None,
    radar_class: LandcoverClass | None,
) -> list[AgreementFinding]:
    labelled, _ = label_regions(mask)
    rows: list[AgreementFinding] = []
    for number, window in enumerate(ndimage.find_objects(labelled), start=1):
        if window is None:
            continue
        component = labelled[window] == number
        pixel_count = int(component.sum())
        if pixel_count < minimum_region_pixels:
            continue
        obscured = bool(other_obscured[window][component].any())
        rows.append(AgreementFinding(
            label=f"{label} region {number}", state=state, reason=_reason(state, obscured, label == "Water"),
            mask=component, pixel_count=pixel_count, optical_confidence=optical_confidence,
            radar_confidence=radar_confidence, row_start=window[0].start or 0, column_start=window[1].start or 0,
            optical_class=optical_class, radar_class=radar_class,
        ))
    return rows


def _components(
    label: str,
    state: AgreementState,
    mask: np.ndarray,
    reason: str,
    optical_confidence: float | None,
    radar_confidence: float | None,
    minimum_region_pixels: int,
    *,
    optical_class: LandcoverClass | None,
    radar_class: LandcoverClass | None,
) -> list[AgreementFinding]:
    labelled, _ = label_regions(mask)
    rows: list[AgreementFinding] = []
    for number, window in enumerate(ndimage.find_objects(labelled), start=1):
        if window is None:
            continue
        component = labelled[window] == number
        pixel_count = int(component.sum())
        if pixel_count < minimum_region_pixels:
            continue
        rows.append(AgreementFinding(
            label=f"{label} region {number}", state=state, reason=reason, mask=component,
            pixel_count=pixel_count, optical_confidence=optical_confidence,
            radar_confidence=radar_confidence, row_start=window[0].start or 0, column_start=window[1].start or 0,
            optical_class=optical_class, radar_class=radar_class,
        ))
    return rows


def _reason(
    state: AgreementState,
    obscured: bool,
    water: bool,
    optical_class: LandcoverClass | None = None,
    radar_class: LandcoverClass | None = None,
) -> str:
    if state == "conflict":
        return (
            f"Both sensors observed this ground but optical {_display_class(optical_class)} and "
            f"radar {_display_class(radar_class)} assign opposing physical classes; a third observation is required."
        )
    if state == "corroborated":
        return "Optical spectral evidence and independent radar structure/backscatter evidence support the same class."
    if state == "optical-only":
        if obscured:
            return "Radar could not see this region because it falls in layover or shadow; its silence is not disagreement."
        return "Optical found a spectral signature without matching radar structure or backscatter evidence."
    if obscured:
        return "Optical imagery was obscured here, so only radar could observe this region."
    return (
        "Radar found a smooth dark-water return without a matching optical spectral signature."
        if water else "Radar found structural backscatter without a matching optical spectral signature."
    )


def _display_class(class_id: LandcoverClass | None) -> str:
    return "built-up" if class_id == "built_up" else "water"


def _arrays(sensor: SensorFindingMasks) -> tuple[np.ndarray, ...]:
    return sensor.water, sensor.built_up, sensor.observed, sensor.obscured


def _renumber_by_class(rows: list[AgreementFinding]) -> list[AgreementFinding]:
    """Keep labels stable and unique when one class has rows from several agreement partitions."""
    counters: dict[str, int] = {}
    numbered: list[AgreementFinding] = []
    for row in rows:
        class_label = row.label.split(" region", maxsplit=1)[0]
        counters[class_label] = counters.get(class_label, 0) + 1
        numbered.append(replace(row, label=f"{class_label} region {counters[class_label]}"))
    return numbered


def source_feature_ids_for_component(
    source_mask: np.ndarray,
    component_mask: np.ndarray,
    *,
    row_start: int,
    column_start: int,
    feature_ids_by_region_label: dict[int, str],
) -> list[str]:
    """Return only the source-vector features whose labelled pixels overlap a ledger component."""
    row_stop = row_start + component_mask.shape[0]
    column_stop = column_start + component_mask.shape[1]
    if (
        row_start < 0 or column_start < 0 or row_stop > source_mask.shape[0]
        or column_stop > source_mask.shape[1]
    ):
        raise ValueError("Fusion component lies outside its source mask.")
    labels, _ = label_regions(source_mask)
    source_labels = np.unique(labels[row_start:row_stop, column_start:column_stop][component_mask])
    return [feature_ids_by_region_label[label] for label in source_labels if label in feature_ids_by_region_label]
