"""Strict Sentinel scene-id metadata parsing for an auditable pair advisory."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from app.lib.exceptions import InvalidRequestError

_SENTINEL = re.compile(r"^(S[12])([AB])_.*?(\d{8}T\d{6})")


@dataclass(frozen=True, slots=True)
class SceneMetadata:
    platform: str
    captured_at: datetime


def sentinel_metadata(scene_id: str) -> SceneMetadata:
    match = _SENTINEL.match(scene_id)
    if match is None:
        raise InvalidRequestError(
            f"{scene_id!r} does not carry a standard Sentinel platform and capture timestamp.",
            details={"sceneId": scene_id},
        )
    mission, spacecraft, timestamp = match.groups()
    captured_at = datetime.strptime(timestamp, "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
    return SceneMetadata(platform=f"Sentinel-{mission[1]}{spacecraft}", captured_at=captured_at)
