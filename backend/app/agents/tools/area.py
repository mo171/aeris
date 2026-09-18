from typing import Any
import numpy as np

from app.schemas.orchestration import TaskSpec
from app.services.evidence.spatial import measure_mask_nominal, measure_mask_pixels


async def execute_area(
    task: TaskSpec,
    pictures: list[np.ndarray] | None = None,
    resolution_metres: float | None = 10.0,
) -> dict[str, Any]:
    """Execute spatial area measurement over detected mask or picture."""
    target = task.target or "observed_area"
    if not pictures or len(pictures) == 0:
        return {
            "type": "area",
            "target": target,
            "value": "0.00 ha",
            "hectares": 0.0,
            "unit": "ha",
            "region_count": 0,
            "coverage_fraction": 0.0,
        }

    pic = pictures[0]
    if pic.ndim == 3:
        detected = np.any(pic > 0, axis=-1)
    else:
        detected = pic.astype(bool)

    observed = np.ones(detected.shape, dtype=bool)

    if resolution_metres is not None and resolution_metres > 0:
        stats = await measure_mask_nominal(detected, observed, resolution_metres=resolution_metres)
        hectares = stats.detected.hectares
        unit = "ha"
        display_val = f"{hectares:,.2f} ha"
    else:
        stats = await measure_mask_pixels(detected, observed)
        hectares = float(stats.detected.pixel_count)
        unit = "px"
        display_val = f"{int(hectares):d} px"

    return {
        "type": "area",
        "target": target,
        "value": display_val,
        "hectares": hectares,
        "unit": unit,
        "region_count": stats.regions.region_count,
        "coverage_fraction": stats.coverage_fraction,
    }
