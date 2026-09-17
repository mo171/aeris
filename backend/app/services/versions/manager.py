"""Investigation workspace versioning and snapshot management.

what  : Save, retrieve, list, diff, and restore investigation workspace versions.
where : Called by investigation API routes, CLI, and workflow controllers.
how   : Persists version snapshots as immutable JSONB state rows linked to investigations,
        and logs version events in investigation_history.
"""

from datetime import datetime, timezone
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.history import InvestigationHistory, InvestigationVersion
from app.db.models.investigation import Investigation
from app.lib.exceptions import ResourceNotFoundError

logger = logging.getLogger(__name__)


async def save_version(
    session: AsyncSession,
    *,
    investigation_id: str,
    label: str,
    snapshot: dict[str, Any],
    actor: str = "operator",
    parent_version_id: str | None = None,
) -> dict[str, Any]:
    """Save an immutable version snapshot of an investigation workspace."""
    # Verify investigation exists
    investigation = await session.get(Investigation, investigation_id)
    if investigation is None:
        raise ResourceNotFoundError(
            f"Investigation {investigation_id} does not exist.",
            details={"investigationId": investigation_id},
        )

    # If parent_version_id is provided, verify it exists under this investigation
    if parent_version_id is not None:
        parent_stmt = select(InvestigationVersion).where(
            InvestigationVersion.id == parent_version_id,
            InvestigationVersion.investigation_id == investigation_id,
        )
        parent_result = await session.execute(parent_stmt)
        if parent_result.scalar_one_or_none() is None:
            raise ResourceNotFoundError(
                f"Parent version {parent_version_id} does not exist for investigation {investigation_id}.",
                details={"parentVersionId": parent_version_id},
            )

    now = datetime.now(timezone.utc)
    version_state = {
        "snapshot": snapshot,
        "actor": actor,
        "parentVersionId": parent_version_id,
        "label": label,
    }

    version = InvestigationVersion(
        investigation_id=investigation_id,
        name=label,
        state=version_state,
        created_at=now,
        updated_at=now,
    )
    session.add(version)

    # Log action to investigation history
    history_entry = InvestigationHistory(
        investigation_id=investigation_id,
        at=now,
        actor=actor,
        command_id="investigation.saveVersion",
        params={"versionId": version.id, "label": label, "parentVersionId": parent_version_id},
        summary=f"Saved version '{label}' ({version.id})",
    )
    session.add(history_entry)

    await session.commit()
    await session.refresh(version)

    return version.to_wire()


async def get_version(
    session: AsyncSession,
    *,
    investigation_id: str,
    version_id: str,
) -> dict[str, Any]:
    """Retrieve a single version snapshot by ID."""
    stmt = select(InvestigationVersion).where(
        InvestigationVersion.id == version_id,
        InvestigationVersion.investigation_id == investigation_id,
    )
    result = await session.execute(stmt)
    version = result.scalar_one_or_none()
    if version is None:
        raise ResourceNotFoundError(
            f"Version {version_id} not found in investigation {investigation_id}.",
            details={"investigationId": investigation_id, "versionId": version_id},
        )
    return version.to_wire()


async def list_versions(
    session: AsyncSession,
    *,
    investigation_id: str,
) -> list[dict[str, Any]]:
    """List all saved version snapshots for an investigation in descending chronological order."""
    stmt = (
        select(InvestigationVersion)
        .where(InvestigationVersion.investigation_id == investigation_id)
        .order_by(InvestigationVersion.created_at.desc())
    )
    result = await session.execute(stmt)
    versions = result.scalars().all()
    return [v.to_wire() for v in versions]


async def restore_version(
    session: AsyncSession,
    *,
    investigation_id: str,
    version_id: str,
    actor: str = "operator",
) -> dict[str, Any]:
    """Restore an investigation workspace to a previous version snapshot."""
    version_wire = await get_version(session, investigation_id=investigation_id, version_id=version_id)
    snapshot = version_wire.get("snapshot") or {}

    now = datetime.now(timezone.utc)
    label = version_wire.get("label", version_id)

    # Log the restore event to history
    history_entry = InvestigationHistory(
        investigation_id=investigation_id,
        at=now,
        actor=actor,
        command_id="investigation.restoreVersion",
        params={"versionId": version_id, "label": label},
        summary=f"Restored workspace to version '{label}' ({version_id})",
    )
    session.add(history_entry)
    await session.commit()

    return {
        "versionId": version_id,
        "restoredAt": now.isoformat(),
        "snapshot": snapshot,
    }


def compare_version_snapshots(
    version_a: dict[str, Any],
    version_b: dict[str, Any],
) -> dict[str, Any]:
    """Compute structured semantic differences between two version snapshots.
    
    Examines:
    - Step parameter changes (e.g. threshold 0.5 vs 0.7)
    - Claim metrics differences (area, count, magnitude)
    - Timeline scene pair differences
    - Added and removed layer IDs
    """
    snap_a = version_a.get("snapshot", version_a)
    snap_b = version_b.get("snapshot", version_b)

    # 1. Compare timeline scene slots
    timeline_a = snap_a.get("timelinePair") or {}
    timeline_b = snap_b.get("timelinePair") or {}
    timeline_diff = {
        "baselineChanged": timeline_a.get("baselineSceneId") != timeline_b.get("baselineSceneId"),
        "comparisonChanged": timeline_a.get("comparisonSceneId") != timeline_b.get("comparisonSceneId"),
        "a": timeline_a,
        "b": timeline_b,
    }

    # 2. Compare step parameters
    steps_a = {s.get("operationId") or s.get("stageCode") or s.get("id"): s for s in snap_a.get("steps", [])}
    steps_b = {s.get("operationId") or s.get("stageCode") or s.get("id"): s for s in snap_b.get("steps", [])}

    parameter_diffs: dict[str, dict[str, tuple[Any, Any]]] = {}
    for op_id, step_b in steps_b.items():
        step_a = steps_a.get(op_id)
        params_b = step_b.get("parameters") or {}
        params_a = step_a.get("parameters") if step_a else {}
        for param_key, val_b in params_b.items():
            val_a = (params_a or {}).get(param_key)
            if val_a != val_b:
                if op_id not in parameter_diffs:
                    parameter_diffs[op_id] = {}
                parameter_diffs[op_id][param_key] = (val_a, val_b)

    # 3. Compare claim metrics
    summary_a = snap_a.get("resultSummary") or {}
    summary_b = snap_b.get("resultSummary") or {}
    metrics_a = {m.get("label"): m.get("value") for m in summary_a.get("claimMetrics", []) if isinstance(m, dict)}
    metrics_b = {m.get("label"): m.get("value") for m in summary_b.get("claimMetrics", []) if isinstance(m, dict)}

    metric_diffs: dict[str, dict[str, Any]] = {}
    for label, val_b in metrics_b.items():
        val_a = metrics_a.get(label)
        if val_a != val_b:
            metric_diffs[label] = {
                "before": val_a,
                "after": val_b,
                "delta": (val_b - val_a) if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)) else None,
            }

    # 4. Compare layer IDs
    layers_a = set(snap_a.get("layerIds") or [])
    layers_b = set(snap_b.get("layerIds") or [])

    return {
        "versionAId": version_a.get("id"),
        "versionBId": version_b.get("id"),
        "timeline": timeline_diff,
        "parameterDiffs": parameter_diffs,
        "metricDiffs": metric_diffs,
        "layers": {
            "added": sorted(layers_b - layers_a),
            "removed": sorted(layers_a - layers_b),
            "shared": sorted(layers_a & layers_b),
        },
        "confidenceDelta": (
            (summary_b.get("confidence") - summary_a.get("confidence"))
            if summary_a.get("confidence") is not None and summary_b.get("confidence") is not None
            else None
        ),
    }
