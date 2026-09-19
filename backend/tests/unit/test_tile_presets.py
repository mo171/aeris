"""Unit tests for raster tile presets and server-side band parameter resolution."""

import pytest

from app.constants.presets import BandPreset, resolve_preset_rendering
from app.constants.scenes import SceneModality


def test_preset_enum_values():
    assert BandPreset.TRUE_COLOR.value == "true_color"
    assert BandPreset.FALSE_COLOR_NIR.value == "false_color_nir"
    assert BandPreset.NDVI.value == "ndvi"
    assert BandPreset.NDWI.value == "ndwi"
    assert BandPreset.SAR_VV.value == "sar_vv"


def test_resolve_true_color_multispectral():
    # 4+ bands optical/multispectral (e.g. Sentinel-2: B4=Red, B3=Green, B2=Blue)
    params = resolve_preset_rendering(BandPreset.TRUE_COLOR, band_count=4, modality=SceneModality.MULTISPECTRAL)
    assert "bidx" in params
    assert params["bidx"] == "4,3,2"
    assert "rescale" in params


def test_resolve_true_color_rgb():
    # 3 bands standard RGB
    params = resolve_preset_rendering(BandPreset.TRUE_COLOR, band_count=3, modality=SceneModality.OPTICAL)
    assert params["bidx"] == "1,2,3"


def test_resolve_false_color_nir():
    params = resolve_preset_rendering(BandPreset.FALSE_COLOR_NIR, band_count=8, modality=SceneModality.MULTISPECTRAL)
    assert params["bidx"] == "8,4,3"


def test_resolve_ndvi_expression():
    params = resolve_preset_rendering(BandPreset.NDVI, band_count=8, modality=SceneModality.MULTISPECTRAL)
    assert "expression" in params
    assert "b8" in params["expression"] and "b4" in params["expression"]
    assert "colormap_name" in params
    assert "rescale" in params


def test_resolve_sar_vv():
    params = resolve_preset_rendering(BandPreset.SAR_VV, band_count=1, modality=SceneModality.SAR)
    assert params["bidx"] == "1"
    assert params.get("colormap_name") == "gray"


def test_invalid_preset_raises_error():
    with pytest.raises(ValueError):
        resolve_preset_rendering("invalid_preset", band_count=3, modality=SceneModality.OPTICAL)
