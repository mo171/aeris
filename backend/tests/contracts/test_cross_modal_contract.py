"""Phase 1.11's backend result must be accepted by the frontend's exported Zod schema."""

import json
from datetime import UTC, datetime

from jsonschema import Draft202012Validator

from app.constants.contracts import CONTRACT_SCHEMAS_FILE
from app.schemas.cross_modal import (
    AgreementRow,
    CrossModalResult,
    FusionVerdict,
    ModalityAdvisory,
    SensorRun,
)


def _sensor(sensor: str) -> SensorRun:
    return SensorRun(
        sensor=sensor,
        scene_id=f"{sensor}-scene",
        captured_at=datetime(2026, 3, 8, tzinfo=UTC),
        platform="Sentinel-2" if sensor == "optical" else "Sentinel-1",
        polarisation=None if sensor == "optical" else "VV",
        look_azimuth_degrees=None if sensor == "optical" else 347.2,
        incidence_angle_degrees=None if sensor == "optical" else 39.1,
        layers=[],
        evidence=[],
        claims=[],
        model_id="index-engine" if sensor == "optical" else "sar-preprocess",
        model_version="1.0.0",
        confidence=0.82,
        obscured_fraction=0.04,
    )


async def test_cross_modal_result_validates_against_frontend_contract() -> None:
    result = CrossModalResult(
        investigation_id="run_01TEST",
        run_id="run_01TEST",
        optical=_sensor("optical"),
        radar=_sensor("radar"),
        advisory=ModalityAdvisory(
            verdict="fair", offset_days=1, co_registration_pixels=0.42,
            notes=["One day apart and aligned below one pixel."],
        ),
        verdict=FusionVerdict(
            headline="One water region is corroborated by both sensors.",
            confidence=0.82,
            refused_because=None,
            blocked_by_conflict=None,
            rows=[AgreementRow(
                id="feature_01ROW", label="Water region 1", state="corroborated",
                reason="Both sensors independently identify smooth open water.",
                optical_feature_ids=["feature_01OPT"], radar_feature_ids=["feature_01SAR"],
                optical_confidence=0.87, radar_confidence=0.82, area_hectares=4.2,
            )],
        ),
        generated_at=datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
    )
    contracts = json.loads(CONTRACT_SCHEMAS_FILE.read_text(encoding="utf-8"))
    schema = contracts["features/crossModal/schemas/cross-modal.schema.ts"]["crossModalResultSchema"]

    payload = result.to_wire()
    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(payload)

    assert payload["optical"]["capturedAt"] == "2026-03-08T00:00:00Z"
    assert payload["verdict"]["rows"][0]["opticalFeatureIds"] == ["feature_01OPT"]


async def test_refused_fusion_keeps_both_sensor_runs_and_no_headline() -> None:
    result = CrossModalResult(
        investigation_id="run_01TEST",
        run_id="run_01TEST",
        optical=_sensor("optical"),
        radar=_sensor("radar"),
        advisory=ModalityAdvisory(
            verdict="unusable", offset_days=2, co_registration_pixels=1.0,
            notes=["Alignment residual is not sub-pixel."],
        ),
        verdict=FusionVerdict(
            headline=None, confidence=None, refused_because="poor-co-registration",
            blocked_by_conflict=None, rows=[],
        ),
        generated_at=datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
    )

    assert result.optical.scene_id == "optical-scene"
    assert result.radar is not None and result.radar.scene_id == "radar-scene"
    assert result.verdict is not None and result.verdict.headline is None
