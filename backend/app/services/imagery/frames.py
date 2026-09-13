"""Says what the operator handed over and turns it into the one picture every specialist reads - a scene directory, a GeoTIFF or a plain photograph, through one door.

what  : `AnalysisInput` and `inspect_input()` - what an input *is* (kind, sensor, grid, resolution,
        bands); `RgbFrame` and `read_rgb_frame()` - the (H, W, 3) 8-bit picture the detector, the
        segmenter, the change model and the VLM are shown, with the pixels the run may not judge marked.
where : S1 (`pipeline/nodes/input_validation.py`) inspects; S13 and S14 read frames; `cli/ask.py` reads
        a frame for its no-run answer. One module, so a picture the agent counts on and a picture the
        operator asks about are made the same way.
how   : **Three kinds of input, one vocabulary.** A Sentinel-2 *scene directory* (band files, a grid, a
        CRS, a processing level); a georeferenced *raster* (a three-band GeoTIFF from a drone or a
        commercial product); a *picture* (PNG or JPEG: a benchmark crop, a screenshot) with no grid at
        all. The pipeline does not refuse the third - a count over a photograph is a real answer - but it
        never pretends: a picture gets figures and pixel-space claims, and nothing is placed on the globe,
        because there is no ground to place it on.

        **Resolution is measured or declared, never guessed** (§8 rule 5, the same rule as the processing
        level). A projected CRS states its metres per pixel; a picture states nothing, and an operator who
        knows the crop is 0.5 m says so with `--gsd`. `resolution_declared` travels with the number so
        every hectare computed from it is labelled nominal.

        **The picture is made with the fixed stretch the VLM adapter was trained on** (`vlm/math/
        rendering.py`), not a per-image percentile: the same ground renders the same on two dates, which
        is what makes a change model's input comparable and a reading reproducible. Pixels under cloud or
        shadow (S7) or nodata are `observed=False`; `for_model()` hands them to a specialist as NaN, which
        every adapter in `app/models/` reads as "not shown ground here".
"""

import asyncio
import logging
import warnings
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np
from rasterio.errors import NotGeoreferencedWarning

from app.constants.raster import BandRole, ProcessingLevel
from app.constants.scenes import SceneModality
from app.lib.exceptions import InvalidRequestError
from app.services.imagery.metadata import RasterMetadata, identify_band, inspect_raster
from app.services.preprocessing.cloud_masking import OpticalMaskResult
from app.services.spectral.indices import locate_bands, read_scene_bands
from app.services.vlm.math.rendering import S2_REFLECTANCE_WINDOW, render_s1_false_colour, render_s2_true_colour

logger = logging.getLogger(__name__)

type AffineTransform = tuple[float, float, float, float, float, float]

TRUE_COLOUR_ROLES: tuple[BandRole, ...] = (BandRole.RED, BandRole.GREEN, BandRole.BLUE)
SAR_ROLES: tuple[BandRole, ...] = (BandRole.VV, BandRole.VH)
PICTURE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp"})

# Surface reflectance is stored as an integer ten-thousandth; the fixed true-colour window is in those units.
REFLECTANCE_SCALE = 10_000.0


class InputKind(StrEnum):
    """What shape the operator's input takes."""

    SCENE_DIRECTORY = "scene-directory"
    RASTER = "raster"
    PICTURE = "picture"


class FrameStretch(StrEnum):
    """How an 8-bit picture was made from what was on disk - recorded so a render is reproducible."""

    S2_FIXED_WINDOW = "s2-fixed-window"
    S1_FALSE_COLOUR = "s1-false-colour"
    BYTES = "bytes"


@dataclass(frozen=True, slots=True)
class AnalysisInput:
    """One thing the operator handed over, and everything S1 established about it."""

    path: Path
    scene_id: str
    kind: InputKind
    modality: SceneModality
    width: int
    height: int
    crs: str | None
    transform: AffineTransform
    # Metres per pixel: from the grid when the CRS is projected, from the operator when declared, else None.
    resolution_metres: float | None
    resolution_declared: bool
    band_ids: tuple[str, ...]
    processing_level: ProcessingLevel
    # The raster the grid is taken from - what `store_artefact` georeferences a computed array against.
    reference: RasterMetadata
    # Every file the input consists of: the band files of a scene directory, or the one image file.
    files: tuple[Path, ...] = ()

    @property
    def georeferenced(self) -> bool:
        return self.crs is not None

    @property
    def shape(self) -> tuple[int, int]:
        return (self.height, self.width)

    def to_wire(self) -> dict[str, Any]:
        return {
            "path": str(self.path), "sceneId": self.scene_id, "kind": self.kind.value, "modality": self.modality.value,
            "width": self.width, "height": self.height, "crs": self.crs, "georeferenced": self.georeferenced,
            "resolutionMetres": self.resolution_metres, "resolutionDeclared": self.resolution_declared,
            "bandIds": list(self.band_ids), "processingLevel": self.processing_level.value,
        }

    def describe(self) -> str:
        """The line the trace shows: "optical scene 1066x1120 at 10 m, EPSG:32643, B02 B03 B04 B08"."""
        resolution = (
            f"{self.resolution_metres:g} m" + (" (declared)" if self.resolution_declared else "")
            if self.resolution_metres is not None else "unknown resolution"
        )
        place = self.crs if self.crs else "no georeference"
        return f"{self.modality.value} {self.kind.value} {self.width}x{self.height} at {resolution}, {place}, {' '.join(self.band_ids)}"


async def inspect_input(path: Path, *, declared_resolution_metres: float | None = None, is_sar: bool = False) -> AnalysisInput:
    """What the input is. Raises `InvalidRequestError` for a path that holds nothing analysable."""
    if declared_resolution_metres is not None and declared_resolution_metres <= 0:
        raise InvalidRequestError("A declared ground sample distance must be positive metres per pixel.", details={"gsd": declared_resolution_metres})
    if await asyncio.to_thread(path.is_dir):
        return await _inspect_directory(path, declared_resolution_metres)
    if not await asyncio.to_thread(path.is_file):
        raise InvalidRequestError(f"{path} is neither a scene directory nor an image file.", details={"path": str(path)})
    return await _inspect_file(path, declared_resolution_metres, is_sar)


async def _inspect_directory(path: Path, declared: float | None) -> AnalysisInput:
    located = await locate_bands(path)
    if not located:
        raise InvalidRequestError(
            f"{path.name} holds no band file this backend recognises (B02..B12, SCL, vv, vh).", details={"path": str(path)},
        )
    sar = [role for role in SAR_ROLES if role in located]
    optical = [role for role in located if role not in SAR_ROLES and role is not BandRole.SCENE_CLASSIFICATION]
    modality = SceneModality.SAR if sar and not optical else SceneModality.OPTICAL
    # The finest band present is the grid every other band is brought onto (`analysis_grid`).
    finest = min(
        (located[role] for role in (optical or sar)),
        key=lambda band: identify_band(band).native_resolution_metres or 0,
    )
    reference = await inspect_raster(finest)
    band_ids = tuple(sorted(
        (identify_band(located[role]).band.value if identify_band(located[role]).band else role.value)
        for role in located if role is not BandRole.SCENE_CLASSIFICATION
    ))
    resolution, declared_flag = _resolution(reference, declared)
    return AnalysisInput(
        path=path, scene_id=path.name, kind=InputKind.SCENE_DIRECTORY, modality=modality, width=reference.width,
        height=reference.height, crs=reference.crs, transform=reference.transform, resolution_metres=resolution,
        resolution_declared=declared_flag, band_ids=band_ids, processing_level=reference.processing_level, reference=reference,
        files=tuple(sorted(located.values())),
    )


async def _inspect_file(path: Path, declared: float | None, is_sar: bool) -> AnalysisInput:
    with warnings.catch_warnings():
        # A photograph has no geotransform, and this module knows that; the warning is for code that assumes one.
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        reference = await inspect_raster(path)
    kind = InputKind.PICTURE if path.suffix.lower() in PICTURE_SUFFIXES or reference.crs is None else InputKind.RASTER
    role = reference.band.role
    modality = SceneModality.SAR if is_sar or role in SAR_ROLES else SceneModality.OPTICAL
    if reference.band.band is not None:
        band_ids: tuple[str, ...] = (reference.band.band.value,)
    elif role is not None:
        band_ids = (role.value,)
    else:
        band_ids = ("red", "green", "blue")[: reference.band_count] if reference.band_count >= 3 else ("grey",)
    resolution, declared_flag = _resolution(reference, declared)
    return AnalysisInput(
        path=path, scene_id=path.stem, kind=kind, modality=modality, width=reference.width, height=reference.height,
        crs=reference.crs, transform=reference.transform, resolution_metres=resolution, resolution_declared=declared_flag,
        band_ids=band_ids, processing_level=reference.processing_level, reference=reference, files=(path,),
    )


def _resolution(reference: RasterMetadata, declared: float | None) -> tuple[float | None, bool]:
    """Metres per pixel from a projected grid; the operator's word otherwise; `None` rather than a guess."""
    if reference.crs is not None and reference.is_projected:
        return float(reference.resolution[0]), False
    if declared is not None:
        return float(declared), True
    return None, False


# --- The picture ------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RgbFrame:
    """The 8-bit picture a specialist is shown, and which of its pixels were actually observed."""

    source: AnalysisInput
    rgb: np.ndarray
    observed: np.ndarray
    band_ids: tuple[str, ...]
    stretch: FrameStretch
    # The files the pixels came from, in `band_ids` order: what a stage records as read (PDF §21.2).
    files: tuple[Path, ...] = ()

    async def input_records(self) -> list[dict[str, Any]]:
        """`InputFileRecord`s in wire form for every file this frame was read from, hashed by content."""
        from app.services.evidence.trace import InputFileRecord, hash_file

        records = []
        # One file holding three channels is one record ("rgb"); one file per band is one record each.
        band_ids = self.band_ids if len(self.band_ids) == len(self.files) else tuple("rgb" for _ in self.files)
        for path, band_id in zip(self.files, band_ids, strict=True):
            descriptor = identify_band(path)
            records.append(InputFileRecord(
                path=str(path), band_id=band_id, role=descriptor.role.value if descriptor.role else "rgb", sha256=await hash_file(path),
                crs=self.source.crs, processing_level=self.source.processing_level.value, width=self.source.width, height=self.source.height,
                resolution_metres=self.source.resolution_metres if self.source.resolution_metres is not None else 0.0,
            ).to_wire())
        return records

    @property
    def shape(self) -> tuple[int, int]:
        return self.rgb.shape[:2]

    @property
    def observed_fraction(self) -> float:
        return float(self.observed.mean()) if self.observed.size else 0.0

    def for_model(self) -> np.ndarray:
        """Float32 pixels with NaN where nothing was observed - what every adapter reads as 'not shown'."""
        pixels = self.rgb.astype(np.float32)
        pixels[~self.observed] = np.nan
        return pixels


async def read_rgb_frame(
    source: AnalysisInput, *, declared_level: ProcessingLevel | None = None, mask: OpticalMaskResult | None = None,
) -> RgbFrame:
    """The picture of one input. A scene directory is rendered from its bands with the fixed stretch; a
    raster or picture is read as it is. `mask` (S7) marks cloud and shadow unobserved."""
    if source.kind is InputKind.SCENE_DIRECTORY:
        frame = await _frame_from_scene(source, declared_level)
    else:
        frame = await asyncio.to_thread(_frame_from_file, source)
    if mask is not None:
        if mask.exclusion_mask.shape != frame.shape:
            raise InvalidRequestError(
                f"The cloud mask is {mask.exclusion_mask.shape} and the picture {frame.shape}; one grid only.",
                details={"maskShape": list(mask.exclusion_mask.shape), "frameShape": list(frame.shape)},
            )
        observed = frame.observed & ~mask.exclusion_mask
        frame = RgbFrame(frame.source, frame.rgb, observed, frame.band_ids, frame.stretch, frame.files)
    logger.info(
        "rgb frame read",
        extra={"scene": source.scene_id, "kind": source.kind.value, "shape": list(frame.shape), "observed": frame.observed_fraction, "stretch": frame.stretch.value},
    )
    return frame


async def _frame_from_scene(source: AnalysisInput, declared_level: ProcessingLevel | None) -> RgbFrame:
    if source.modality is SceneModality.SAR:
        located = await locate_bands(source.path)
        vv = await asyncio.to_thread(_read_first_band, located[BandRole.VV])
        vh = await asyncio.to_thread(_read_first_band, located[BandRole.VH]) if BandRole.VH in located else vv
        observed = np.isfinite(vv) & np.isfinite(vh)
        rgb = await asyncio.to_thread(render_s1_false_colour, vv, vh, already_decibels=bool(np.nanmax(vv) <= 0))
        present = tuple(role for role in SAR_ROLES if role in located)
        return RgbFrame(source, rgb, observed, tuple(role.value for role in present), FrameStretch.S1_FALSE_COLOUR, tuple(located[role] for role in present))

    bands = await read_scene_bands(source.path, TRUE_COLOUR_ROLES, declared_level=declared_level)
    red, green, blue = (bands.bands[role].reflectance for role in TRUE_COLOUR_ROLES)
    observed = np.isfinite(red) & np.isfinite(green) & np.isfinite(blue)
    rgb = await asyncio.to_thread(
        render_s2_true_colour, red * REFLECTANCE_SCALE, green * REFLECTANCE_SCALE, blue * REFLECTANCE_SCALE
    )
    return RgbFrame(
        source, rgb, observed, tuple(bands.bands[role].band_id for role in TRUE_COLOUR_ROLES), FrameStretch.S2_FIXED_WINDOW,
        tuple(bands.bands[role].source.path for role in TRUE_COLOUR_ROLES),
    )


def _frame_from_file(source: AnalysisInput) -> RgbFrame:
    """Sync. A picture as its bytes; a raster's first three bands, stretched when they are reflectance."""
    if source.kind is InputKind.PICTURE and source.path.suffix.lower() in PICTURE_SUFFIXES:
        from PIL import Image

        rgb = np.asarray(Image.open(source.path).convert("RGB"))
        return RgbFrame(source, rgb, np.ones(rgb.shape[:2], dtype=bool), source.band_ids, FrameStretch.BYTES, (source.path,))

    import rasterio

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with rasterio.open(source.path) as dataset:
            bands = dataset.read(list(range(1, min(dataset.count, 3) + 1))).astype(np.float32)
            nodata = dataset.nodata
    if nodata is not None:
        bands[bands == nodata] = np.nan
    observed = np.isfinite(bands).all(axis=0)
    if source.modality is SceneModality.SAR:
        vv = bands[0]
        vh = bands[1] if bands.shape[0] > 1 else bands[0]
        return RgbFrame(source, render_s1_false_colour(vv, vh, already_decibels=bool(np.nanmax(vv) <= 0)), observed, source.band_ids, FrameStretch.S1_FALSE_COLOUR, (source.path,))
    if bands.shape[0] < 3:
        bands = np.repeat(bands[:1], 3, axis=0)
    peak = float(np.nanmax(bands)) if observed.any() else 0.0
    if peak > 255 or peak <= S2_REFLECTANCE_WINDOW[1] / REFLECTANCE_SCALE:
        # Reflectance, as a ten-thousandth or on [0, 1]: the fixed window, the same one the scene path uses.
        scale = REFLECTANCE_SCALE if peak <= 1.0 else 1.0
        rgb = render_s2_true_colour(bands[0] * scale, bands[1] * scale, bands[2] * scale)
        return RgbFrame(source, rgb, observed, source.band_ids, FrameStretch.S2_FIXED_WINDOW, (source.path,))
    rgb = np.moveaxis(np.nan_to_num(bands, nan=0.0), 0, -1).clip(0, 255).astype(np.uint8)
    return RgbFrame(source, rgb, observed, source.band_ids, FrameStretch.BYTES, (source.path,))


def _read_first_band(path: Path) -> np.ndarray:
    import rasterio

    with rasterio.open(path) as dataset:
        values = dataset.read(1).astype(np.float32)
        if dataset.nodata is not None:
            values[values == dataset.nodata] = np.nan
    return values
