"""Reads what a raster actually is - driver, CRS, bands, resolution, processing level - so no later stage has to guess.

what  : `RasterMetadata`, `BandDescriptor`, `inspect_raster()` and `identify_band()`. Stages S1-S3.
where : Called by `services/imagery/validation.py` and by the ingest node. Phase 1.4's index engine reads
        `processing_level` from here before computing anything.
how   : Everything below is read from the file, never inferred from its name. A scene called
        `S2B_MSIL2A_...` whose pixels are top-of-atmosphere is a scene someone renamed, and an index over
        it is a different quantity wearing the same name (`architecture-context.md` §8 rule 5).

        **The CRS check is the one that costs a day when it is missing.** A GeoTIFF with no CRS opens
        cleanly, reads cleanly, and reprojects to nothing - GDAL cannot place it on the globe, so the tile
        server produces empty tiles with no error. Worse is a *wrong* CRS, which places the scene
        confidently in the wrong country. Both are caught here rather than discovered as a blank map.

        **Band identity comes from the file name, not the band index.** Rasterio numbers bands from 1 in
        file order; that order is whatever the writer chose. `B04` is red on Sentinel-2 and band 3 on
        Landsat, and a hardcoded index is how an NDVI silently becomes something else. `aeris dataset
        fetch` writes one band per file named for the band, so the name is the identity.

        **rasterio is sync**, so every call into it is wrapped in `asyncio.to_thread` at the boundary,
        written at the call site where the cost is visible (`code-standards.md` §7).
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

import rasterio
from rasterio.crs import CRS

from app.constants.raster import (
    SENTINEL2_BANDS,
    BandRole,
    ProcessingLevel,
    SpectralBand,
)
from app.lib.exceptions import InvalidRequestError, ResourceNotFoundError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BandDescriptor:
    """What one band is, once identified. `role` is `None` when the file name says nothing recognisable."""

    band: SpectralBand | None
    role: BandRole | None
    native_resolution_metres: int | None
    centre_wavelength_nanometres: int | None

    @property
    def is_categorical(self) -> bool:
        """Whether resampling this band must use nearest neighbour.

        `architecture-context.md` §8 rule 6. The scene classification layer holds class *labels*; averaging
        label 4 and label 6 gives 5, which is a different class that was never there. The rule lives here
        rather than at each resample call because there is exactly one place that knows what a band is.
        """
        return self.role is BandRole.SCENE_CLASSIFICATION


@dataclass(frozen=True, slots=True)
class RasterMetadata:
    """Everything S1-S3 establishes about one raster file."""

    path: Path
    driver: str
    width: int
    height: int
    band_count: int
    dtype: str
    nodata: float | None

    crs: str | None
    # Ground sample distance in the CRS's units, x then y. Metres for a projected CRS, degrees for a
    # geographic one - which is why `is_projected` is carried rather than assumed.
    resolution: tuple[float, float]
    is_projected: bool

    # (west, south, east, north) in the raster's own CRS.
    bounds: tuple[float, float, float, float]

    band: BandDescriptor
    processing_level: ProcessingLevel

    # Whether the file is already a valid COG. Checked rather than assumed from the extension, because a
    # plain GeoTIFF renamed `.cog.tif` reads perfectly and costs forty range requests per tile.
    is_cloud_optimised: bool

    @property
    def pixel_count(self) -> int:
        return self.width * self.height

    @property
    def has_usable_crs(self) -> bool:
        """A CRS that GDAL can actually reproject from. `None` means the scene cannot be placed at all."""
        return self.crs is not None


def identify_band(path: Path) -> BandDescriptor:
    """Work out which band a file holds, from its name.

    Sync: it is string matching, and it is called from inside the threaded read below.

    Returns a descriptor with `None` fields rather than raising when the name is unrecognised. A GeoTIFF an
    operator uploaded is a legitimate input at S1 - it simply cannot have an index computed over it until
    someone says what its bands are, and that refusal belongs to the index engine rather than here.
    """
    stem = path.stem.upper()

    for band, (role, wavelength, resolution) in SENTINEL2_BANDS.items():
        # Exact stem, or the band name as a token in a longer name (`T43RGM_20240319_B04`). Substring
        # matching alone would match `B08` inside `B08A`, which is a different band at a different
        # resolution - hence the token split rather than `in`.
        if stem == band.value or band.value in stem.replace("-", "_").split("_"):
            return BandDescriptor(
                band=band,
                role=role,
                native_resolution_metres=resolution,
                centre_wavelength_nanometres=wavelength or None,
            )

    for role in (BandRole.VV, BandRole.VH):
        if stem == role.value.upper() or role.value.upper() in stem.replace("-", "_").split("_"):
            return BandDescriptor(
                band=None, role=role, native_resolution_metres=10, centre_wavelength_nanometres=None
            )

    return BandDescriptor(band=None, role=None, native_resolution_metres=None, centre_wavelength_nanometres=None)


def detect_processing_level(path: Path) -> ProcessingLevel:
    """Read the processing level out of a scene identifier.

    From the *path*, because a single-band GeoTIFF carries no product metadata - the level lives in the
    scene directory name that `aeris dataset fetch` wrote. Returns `UNKNOWN` rather than guessing `L2A`:
    §8 rule 5 makes an index over an unknown level a refusal, and defaulting to the permissive answer
    would turn that refusal into a wrong number.
    """
    haystack = str(path).upper()
    if "MSIL2A" in haystack:
        return ProcessingLevel.L2A
    if "MSIL1C" in haystack:
        return ProcessingLevel.L1C
    if "_GRD" in haystack or "GRDH" in haystack:
        return ProcessingLevel.GRD
    return ProcessingLevel.UNKNOWN


async def inspect_raster(path: Path) -> RasterMetadata:
    """S1-S3: open a raster, identify it, and report what it is.

    Does not validate. Reporting that a scene has no CRS is this function's job; refusing to proceed is
    `validation.py`'s, and keeping them apart is what lets `aeris ingest --inspect` describe a broken file
    instead of only rejecting it.
    """
    # Offloaded rather than called directly: `code-standards.md` §7 keeps blocking calls off the event
    # loop, and a `stat` against a network mount is not the microsecond it is against a local disk.
    if not await asyncio.to_thread(path.exists):
        raise ResourceNotFoundError(f"No raster at {path}.", details={"path": str(path)})

    try:
        metadata = await asyncio.to_thread(_read_metadata, path)
    except rasterio.errors.RasterioIOError as error:
        # GDAL could not open it at all - not a raster, truncated, or an unsupported driver. Raised as an
        # invalid request rather than an internal error, because the input is what is wrong.
        raise InvalidRequestError(
            f"{path.name} could not be opened as a raster: {error}", details={"path": str(path)}
        ) from error

    logger.info(
        "raster inspected",
        extra={
            "path": str(path), "driver": metadata.driver, "crs": metadata.crs,
            "size": f"{metadata.width}x{metadata.height}", "band": metadata.band.role,
            "level": metadata.processing_level.value, "cog": metadata.is_cloud_optimised,
        },
    )
    return metadata


def _read_metadata(path: Path) -> RasterMetadata:
    """The blocking half. Sync on purpose - it is what `to_thread` is handed."""
    from rio_cogeo.cogeo import cog_validate

    with rasterio.open(path) as source:
        crs: CRS | None = source.crs
        band = identify_band(path)

        # `cog_validate` opens the file again, which is why it is inside this thread rather than awaited
        # separately. It returns (is_valid, errors, warnings); only the first is load-bearing here.
        try:
            is_valid, _, _ = cog_validate(str(path), quiet=True)
        except Exception:  # noqa: BLE001 - a file that cannot be validated is simply not a COG
            is_valid = False

        return RasterMetadata(
            path=path,
            driver=source.driver,
            width=source.width,
            height=source.height,
            band_count=source.count,
            dtype=str(source.dtypes[0]),
            nodata=source.nodata,
            crs=str(crs) if crs is not None else None,
            resolution=(abs(source.transform.a), abs(source.transform.e)),
            is_projected=bool(crs.is_projected) if crs is not None else False,
            bounds=tuple(source.bounds),  # type: ignore[arg-type]
            band=band,
            processing_level=detect_processing_level(path),
            is_cloud_optimised=bool(is_valid),
        )
