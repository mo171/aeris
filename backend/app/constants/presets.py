"""Visualization presets and server-side band selection / stretch rules (Phase 2.6).

what  : `BandPreset`, standard presets for satellite imagery visualization, and
        `resolve_preset_rendering()` which maps a preset to TiTiler query parameters.
where : Called by `tiles_controller.py` to ensure all band math, colormap lookup,
        and contrast stretching happen strictly on the server side.
how   : Conforms to `api-contract.md` §8 rule 5: the browser never does band math.
"""

from enum import StrEnum
from typing import Any

from app.constants.scenes import SceneModality


class BandPreset(StrEnum):
    """Supported server-side visualization presets."""

    TRUE_COLOR = "true_color"
    FALSE_COLOR_NIR = "false_color_nir"
    NDVI = "ndvi"
    NDWI = "ndwi"
    SAR_VV = "sar_vv"
    GRAYSCALE = "grayscale"



def resolve_preset_rendering(
    preset: BandPreset | str,
    band_count: int = 3,
    modality: SceneModality = SceneModality.OPTICAL,
) -> dict[str, str]:
    """Translate a high-level preset into TiTiler query parameters.

    Returns dict of query arguments (e.g. `bidx`, `rescale`, `colormap_name`, `expression`).
    """
    if isinstance(preset, str):
        try:
            preset = BandPreset(preset)
        except ValueError:
            raise ValueError(f"Unknown preset: {preset}. Valid presets are {[p.value for p in BandPreset]}")

    if preset is BandPreset.TRUE_COLOR:
        # If Sentinel-2 multispectral with 4+ bands: B4 (Red), B3 (Green), B2 (Blue)
        if band_count >= 4 and modality in (SceneModality.MULTISPECTRAL, SceneModality.HYPERSPECTRAL):
            return {"bidx": "4,3,2", "rescale": "0,3000"}
        # Standard RGB 3-band
        return {"bidx": "1,2,3", "rescale": "0,255" if band_count <= 3 else "0,3000"}

    elif preset is BandPreset.FALSE_COLOR_NIR:
        # Near-Infrared false color: NIR (B8), Red (B4), Green (B3)
        if band_count >= 8:
            return {"bidx": "8,4,3", "rescale": "0,3500"}
        elif band_count >= 4:
            return {"bidx": "4,3,2", "rescale": "0,3500"}
        return {"bidx": "1,2,3", "rescale": "0,3500"}

    elif preset is BandPreset.NDVI:
        # (B8 - B4) / (B8 + B4)
        if band_count >= 8:
            return {
                "expression": "(b8-b4)/(b8+b4)",
                "rescale": "-0.2,0.8",
                "colormap_name": "rdylgn",
            }
        # Fallback for single-band pre-computed index or standard 4-band
        elif band_count >= 4:
            return {
                "expression": "(b4-b3)/(b4+b3)",
                "rescale": "-0.2,0.8",
                "colormap_name": "rdylgn",
            }
        return {
            "bidx": "1",
            "rescale": "-1,1",
            "colormap_name": "rdylgn",
        }

    elif preset is BandPreset.NDWI:
        # (B3 - B8) / (B3 + B8)
        if band_count >= 8:
            return {
                "expression": "(b3-b8)/(b3+b8)",
                "rescale": "-0.5,0.5",
                "colormap_name": "blues",
            }
        return {
            "bidx": "1",
            "rescale": "-1,1",
            "colormap_name": "blues",
        }

    elif preset is BandPreset.SAR_VV:
        return {
            "bidx": "1",
            "rescale": "0,0.5",
            "colormap_name": "gray",
        }

    elif preset is BandPreset.GRAYSCALE:
        return {
            "bidx": "1",
            "rescale": "0,3000" if band_count == 1 else "0,255",
            "colormap_name": "gray",
        }

    raise ValueError(f"Unhandled preset: {preset}")

