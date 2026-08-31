"""Turns a raster into a Cloud-Optimised GeoTIFF in object storage, which is what makes a 120-megapixel scene drawable on a globe.

what  : `CogResult`, `convert_to_cog()`, `upload_cog()` and `write_cog_from_array()`. Stage S6.
where : Called by the ingest node, and from 1.4 by the index engine, which writes its NDVI array through
        `write_cog_from_array` and hands the object key to TiTiler.
how   : **What a COG actually is, because every constant in `constants/raster.py` follows from it.** An
        ordinary GeoTIFF stores its pixels in scanline order with its index at the end, so reading one
        512x512 patch means reading most of the file. A COG stores pixels in internal tiles, keeps
        overviews inside the same file, and puts the offsets in the header - so a reader that can do HTTP
        range requests fetches exactly the bytes for the tile it wants. That is the entire difference
        between a globe that pans and one that hangs.

        Both files open identically in QGIS, which is why `metadata.is_cloud_optimised` *validates* rather
        than trusting an extension. A plain GeoTIFF renamed `.cog.tif` works perfectly and costs forty
        range requests per tile.

        **The predictor is chosen by dtype, and getting it wrong corrupts the file.** `PREDICTOR=2` is
        horizontal differencing for integers; floating point needs `PREDICTOR=3`, which is a different
        algorithm. Applying 2 to float32 produces a file that writes without error and decompresses to
        noise.

        **Overview resampling is chosen by what the band *is*** - `architecture-context.md` §8 rule 6.
        Averaging a scene-classification layer blends class 4 and class 6 into class 5, which is a class
        that was never there, and the operator sees it at low zoom only.

        **rio-cogeo is sync**, so every call is wrapped in `asyncio.to_thread` at the call site.
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rio_cogeo.cogeo import cog_translate, cog_validate
from rio_cogeo.profiles import cog_profiles

from app.constants.raster import (
    COG_BLOCK_SIZE,
    COG_COMPRESSION,
    COG_OVERVIEW_LEVELS,
    COG_OVERVIEW_RESAMPLING,
    COG_OVERVIEW_RESAMPLING_CATEGORICAL,
    COG_PREDICTOR_FLOAT,
    COG_PREDICTOR_INTEGER,
    NODATA_FLOAT,
)
from app.constants.storage import Bucket
from app.lib import storage
from app.lib.exceptions import InternalError
from app.services.imagery.metadata import RasterMetadata

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CogResult:
    """A COG that exists, where it is, and what it cost."""

    local_path: Path
    bucket: Bucket
    object_key: str
    size_bytes: int
    is_valid_cog: bool

    @property
    def storage_uri(self) -> str:
        """The `s3://` URI GDAL and TiTiler read the object through.

        The form matters: TiTiler is given this string and opens it with GDAL's `/vsis3/` driver, which is
        configured by the `AWS_S3_ENDPOINT` the compose file sets. A `http://` URL would work too and
        would bypass the credential path entirely, which is exactly the difference between a public bucket
        and a private one - so `s3://` is the form that keeps the objects private.
        """
        return f"s3://{self.bucket_name}/{self.object_key}"

    @property
    def bucket_name(self) -> str:
        from app.config import settings

        return f"{settings.storage_bucket_prefix}-{self.bucket.value}"


def _predictor_for(dtype: str) -> int:
    """The compression predictor a dtype requires.

    `PREDICTOR=2` is horizontal differencing over integers. Floating point needs `PREDICTOR=3`, which is a
    genuinely different algorithm that reorders the bytes of each float. Applying 2 to float32 writes
    without error and decompresses to noise, which is why this is a function rather than a constant.
    """
    return COG_PREDICTOR_FLOAT if np.dtype(dtype).kind == "f" else COG_PREDICTOR_INTEGER


def _cog_profile(dtype: str) -> dict[str, object]:
    """The creation options every COG this project writes is built with."""
    profile = dict(cog_profiles.get("deflate"))
    profile.update(
        {
            "blockxsize": COG_BLOCK_SIZE,
            "blockysize": COG_BLOCK_SIZE,
            "compress": COG_COMPRESSION,
            "predictor": _predictor_for(dtype),
        }
    )
    return profile


async def convert_to_cog(metadata: RasterMetadata, destination: Path) -> Path:
    """S6: rewrite a raster as a valid COG on local disk.

    Local first, then uploaded, rather than streamed straight into object storage. `cog_translate` needs to
    seek while building overviews, and a multipart upload cannot be seeked - so a direct-to-S3 write would
    mean either buffering the whole file in memory (240 MB for one band) or producing a file whose
    overviews are wrong.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    resampling = (
        COG_OVERVIEW_RESAMPLING_CATEGORICAL if metadata.band.is_categorical else COG_OVERVIEW_RESAMPLING
    )

    size_bytes = await asyncio.to_thread(
        _translate, metadata.path, destination, metadata.dtype, resampling
    )

    is_valid, errors, _ = await asyncio.to_thread(cog_validate, str(destination), quiet=True)
    if not is_valid:
        # Ours to fix, not the operator's - the profile above is what produced this file.
        raise InternalError(
            f"Wrote {destination.name} but it is not a valid COG: {errors}. "
            "The creation profile in constants/raster.py is wrong for this input.",
            details={"path": str(destination)},
        )

    logger.info(
        "cog written",
        extra={
            "source": str(metadata.path), "destination": str(destination),
            "resampling": resampling, "size_bytes": size_bytes,
        },
    )
    return destination


def _translate(source: Path, destination: Path, dtype: str, resampling: str) -> int:
    """The blocking conversion. Sync - it is what `to_thread` is handed. Returns the bytes written.

    The size is returned rather than stat-ed by the caller so the whole filesystem interaction stays in
    this thread; an `await`ing caller reaching back for `.stat()` would put a blocking syscall on the loop.
    """
    cog_translate(
        str(source),
        str(destination),
        _cog_profile(dtype),
        overview_level=COG_OVERVIEW_LEVELS,
        overview_resampling=resampling,
        # `web_optimized=False`: the COG stays in its native CRS and TiTiler reprojects per request. The
        # alternative bakes EPSG:3857 into the file, which is faster to serve and destroys the pixel grid
        # every measurement in this project depends on - an area computed from a reprojected raster is
        # computed from resampled pixels (§8 rule 3).
        web_optimized=False,
        quiet=True,
    )
    return destination.stat().st_size


async def write_cog_from_array(
    array: np.ndarray,
    *,
    reference: RasterMetadata,
    destination: Path,
    nodata: float = NODATA_FLOAT,
) -> Path:
    """Write a computed array - an index map, a mask - as a COG, georeferenced from the raster it came from.

    The path Phase 1.4 takes: NDVI is computed into a float32 array and has to become something the globe
    can draw. It inherits its CRS and transform from `reference`, because a computed array carries no
    georeferencing of its own and inventing one would place the result somewhere plausible and wrong.

    NaN as nodata, never a sentinel like -9999: a sentinel is a real number that survives arithmetic and
    can be averaged into a mean, whereas NaN propagates (§8 rule 4).
    """
    if array.shape != (reference.height, reference.width):
        raise InternalError(
            f"Array is {array.shape} but its reference raster is "
            f"{(reference.height, reference.width)}. A computed array must match the grid it inherits its "
            "georeferencing from, or every pixel is placed slightly wrong.",
            details={"arrayShape": list(array.shape)},
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(_write_array, array, reference, destination, nodata)

    is_valid, errors, _ = await asyncio.to_thread(cog_validate, str(destination), quiet=True)
    if not is_valid:
        raise InternalError(
            f"Wrote {destination.name} from an array but it is not a valid COG: {errors}",
            details={"path": str(destination)},
        )
    return destination


def _write_array(
    array: np.ndarray, reference: RasterMetadata, destination: Path, nodata: float
) -> None:
    """Georeference an array and translate it to a COG. Sync."""
    with rasterio.open(reference.path) as source:
        profile = source.profile.copy()

    profile.update(
        {
            "driver": "GTiff",
            "dtype": array.dtype.name,
            "count": 1,
            "nodata": nodata,
            "height": array.shape[0],
            "width": array.shape[1],
        }
    )

    # Written through a MemoryFile rather than to a temporary path: `cog_translate` needs a readable
    # source, and going via memory avoids leaving a non-COG GeoTIFF on disk that something could pick up
    # and serve. The array is already in memory, so this costs nothing extra.
    with MemoryFile() as memory:
        with memory.open(**profile) as temporary:
            temporary.write(array, 1)
        cog_translate(
            memory.name,
            str(destination),
            _cog_profile(array.dtype.name),
            overview_level=COG_OVERVIEW_LEVELS,
            overview_resampling=COG_OVERVIEW_RESAMPLING,
            web_optimized=False,
            quiet=True,
            in_memory=True,
        )


async def upload_cog(
    path: Path, *, object_key: str, bucket: Bucket = Bucket.COG
) -> CogResult:
    """Put a COG into object storage and report where it landed.

    The `cog` bucket, which `constants/storage.py` marks browser-facing: TiTiler reads it over `/vsis3/`
    and the browser then loads tiles from TiTiler, so the CORS configuration proven in Phase 0.4 is what
    makes the 1.2 gate possible at all.
    """
    payload = await asyncio.to_thread(path.read_bytes)
    await storage.put_object(bucket, object_key, payload, content_type="image/tiff")

    result = CogResult(
        local_path=path,
        bucket=bucket,
        object_key=object_key,
        size_bytes=len(payload),
        is_valid_cog=True,
    )
    logger.info(
        "cog uploaded",
        extra={"object_key": object_key, "bucket": bucket.value, "size_bytes": result.size_bytes},
    )
    return result
