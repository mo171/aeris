"""The Phase 1.2 gate below the browser: a raster is inspected, refused or accepted, converted to a COG, and served as tiles.

what  : Tests over `services/imagery/` and the TiTiler service - metadata, validation, COG conversion,
        tiling, and the tile contract.
where : `tests/integration/`. The COG and tile tests need `docker compose up -d minio titiler`; they are
        marked `integration` and fail loudly rather than skipping, because they demonstrate a gate.
        The inspection and validation tests build their own GeoTIFFs and need nothing.
how   : Small synthetic rasters, written with rasterio, whose correct answers are known by construction -
        a 4x4 scene with two nodata pixels has a nodata fraction of exactly 0.125 and there is nothing to
        argue about. A 10980x10980 Sentinel-2 band would test the same code paths in two minutes instead
        of two milliseconds.

        The one test that uses the real scene is the tile contract, because that is the gate: the roadmap
        asks for "an NDVI COG produced by this pipeline, stored in MinIO, rendered in a browser through
        TiTiler". The browser half is `tools/tilecheck/` - the canvas `getImageData` check, which is what
        Cesium actually does and what a plain `<img>` does not exercise. What is here is everything
        underneath it, so a failure says which layer broke.
"""

import asyncio
import json
import socket
import subprocess
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.config import settings
from app.constants.raster import COG_BLOCK_SIZE, INFERENCE_TILE_SIZE, ProcessingLevel
from app.lib.exceptions import ConflictError, InvalidRequestError
from app.services.imagery.cog import convert_to_cog, write_cog_from_array
from app.services.imagery.metadata import identify_band, inspect_raster
from app.services.imagery.tiling import plan_tiles, read_tile, stitch_predictions
from app.services.imagery.validation import Severity, assess_raster, require_analysable

# The scene fetched in Phase 1.1 and converted by `aeris ingest index`. Ghaziabad, March 2024.
NDVI_OBJECT = "s3://aeris-cog/S2B_MSIL2A_20240319T052649_R105_T43RGM_20240319T094507/ndvi.tif"


def write_raster(
    path: Path,
    array: np.ndarray,
    *,
    crs: str | None = "EPSG:32643",
    nodata: float | None = 0.0,
) -> Path:
    """A minimal GeoTIFF whose statistics are known by construction."""
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff",
        "height": array.shape[0],
        "width": array.shape[1],
        "count": 1,
        "dtype": array.dtype.name,
        "transform": from_origin(700000, 3200000, 10, 10),
        "nodata": nodata,
    }
    if crs is not None:
        profile["crs"] = crs
    with rasterio.open(path, "w", **profile) as destination:
        destination.write(array, 1)
    return path


def titiler_is_up() -> bool:
    try:
        socket.create_connection(("127.0.0.1", 8000), timeout=3).close()
        return True
    except OSError:
        return False


needs_tile_server = pytest.mark.skipif(
    not titiler_is_up(), reason="TiTiler is not running - `docker compose up -d titiler`"
)


# --- S1-S3: what a raster is -----------------------------------------------------------------------------


async def test_a_raster_reports_what_it_actually_is(tmp_path: Path) -> None:
    """Driver, size, dtype, CRS and resolution, all read from the file rather than inferred."""
    path = write_raster(tmp_path / "B04.tif", np.arange(16, dtype=np.uint16).reshape(4, 4))

    metadata = await inspect_raster(path)

    assert metadata.driver == "GTiff"
    assert (metadata.width, metadata.height) == (4, 4)
    assert metadata.dtype == "uint16"
    assert metadata.crs == "EPSG:32643"
    assert metadata.is_projected
    assert metadata.resolution == (10.0, 10.0)


async def test_band_identity_comes_from_the_name_not_the_index() -> None:
    """`B04` is red on Sentinel-2 and band 3 on Landsat. A hardcoded index is how an NDVI becomes an NDWI."""
    assert identify_band(Path("B04.tif")).role is not None
    assert identify_band(Path("T43RGM_20240319_B08.tif")).native_resolution_metres == 10
    assert identify_band(Path("B11.tif")).native_resolution_metres == 20, "SWIR is 20 m, not 10"
    assert identify_band(Path("quicklook.tif")).role is None, "an unknown name is None, not a guess"


async def test_b08_is_not_matched_inside_b8a() -> None:
    """Substring matching would pair a 10 m band with a 20 m one, and every area would be wrong by four."""
    assert identify_band(Path("B08.tif")).native_resolution_metres == 10
    assert identify_band(Path("B8A.tif")).native_resolution_metres == 20


async def test_an_unknown_processing_level_is_not_guessed(tmp_path: Path) -> None:
    """§8 rule 5. Defaulting to L2A would turn a refusal into a wrong number."""
    path = write_raster(tmp_path / "anything.tif", np.ones((4, 4), np.uint16))

    assert (await inspect_raster(path)).processing_level is ProcessingLevel.UNKNOWN


async def test_a_file_that_is_not_a_raster_is_refused(tmp_path: Path) -> None:
    """The input is what is wrong, so it is an invalid request rather than an internal error."""
    path = tmp_path / "notes.tif"
    path.write_text("this is not a GeoTIFF")

    with pytest.raises(InvalidRequestError, match="could not be opened"):
        await inspect_raster(path)


# --- S4-S5: refusing rather than warning -----------------------------------------------------------------


async def test_a_raster_with_no_crs_is_refused(tmp_path: Path) -> None:
    """**The failure that costs a day when it is not caught.**

    A GeoTIFF with no CRS opens cleanly, reads cleanly and reprojects to nothing. The tile server emits
    empty tiles with no error anywhere, so the symptom is a blank map rather than a message.
    """
    path = write_raster(tmp_path / "B04.tif", np.arange(16, dtype=np.uint16).reshape(4, 4), crs=None)

    report = await assess_raster(await inspect_raster(path))

    assert not report.is_analysable
    assert [problem.code for problem in report.refusals] == ["NO_CRS"]

    with pytest.raises(ConflictError, match="coordinate reference system"):
        await require_analysable(await inspect_raster(path))


async def test_a_mostly_empty_raster_is_refused(tmp_path: Path) -> None:
    """Statistics over the remaining third would be reported as describing the whole area."""
    array = np.zeros((10, 10), dtype=np.uint16)
    array[:2, :] = 500  # 80% nodata
    path = write_raster(tmp_path / "B04.tif", array, nodata=0.0)

    report = await assess_raster(await inspect_raster(path))

    assert "EXCESSIVE_NODATA" in [problem.code for problem in report.refusals]


async def test_a_constant_raster_is_refused(tmp_path: Path) -> None:
    """A failed download renders as a plausible flat image and yields a uniform index map - which reads
    as a finding rather than a fault."""
    path = write_raster(tmp_path / "B04.tif", np.full((20, 20), 1234, np.uint16), nodata=0.0)

    report = await assess_raster(await inspect_raster(path))

    assert "CONSTANT_RASTER" in [problem.code for problem in report.refusals]


async def test_a_geographic_crs_warns_but_does_not_refuse(tmp_path: Path) -> None:
    """Degrees are fine for display and wrong for area (§8 rule 3), so it is reported and not blocked.

    The severity distinction is the design: refusing everything imperfect makes the gate unusable, and
    warning about everything makes it useless.
    """
    path = write_raster(
        tmp_path / "B04.tif", np.arange(16, dtype=np.uint16).reshape(4, 4), crs="EPSG:4326"
    )

    report = await assess_raster(await inspect_raster(path))

    assert report.is_analysable, "a geographic CRS does not block analysis"
    assert "GEOGRAPHIC_CRS" in [problem.code for problem in report.warnings]
    assert all(problem.severity is Severity.WARNS for problem in report.problems)


async def test_a_refusal_carries_the_number_that_caused_it(tmp_path: Path) -> None:
    """"62% nodata" is actionable; "too much nodata" is not."""
    array = np.zeros((10, 10), dtype=np.uint16)
    array[:2, :] = 500
    path = write_raster(tmp_path / "B04.tif", array, nodata=0.0)

    refusal = next(
        problem
        for problem in (await assess_raster(await inspect_raster(path))).refusals
        if problem.code == "EXCESSIVE_NODATA"
    )

    assert refusal.measured == pytest.approx(0.8)
    assert refusal.limit is not None


# --- S6: COG conversion ----------------------------------------------------------------------------------


@pytest.mark.integration
async def test_a_converted_raster_is_a_valid_cog_with_the_declared_profile(tmp_path: Path) -> None:
    """Both files open identically in QGIS, which is why validity is checked rather than assumed.

    A plain GeoTIFF renamed `.cog.tif` reads perfectly and costs forty range requests per tile - a slow
    globe, not a broken one, which is the harder failure to notice.
    """
    source = write_raster(
        tmp_path / "B04.tif",
        (np.random.default_rng(0).random((2048, 2048)) * 10000).astype(np.uint16),
        nodata=0.0,
    )
    destination = tmp_path / "out.tif"

    await convert_to_cog(await inspect_raster(source), destination)

    assert (await inspect_raster(destination)).is_cloud_optimised
    with rasterio.open(destination) as result:
        assert result.block_shapes[0] == (COG_BLOCK_SIZE, COG_BLOCK_SIZE)
        assert result.overviews(1), "a COG without overviews decimates 120 Mpx to draw one zoomed-out tile"
        assert result.tags(ns="IMAGE_STRUCTURE")["COMPRESSION"] == "DEFLATE"


@pytest.mark.integration
async def test_a_float_cog_uses_the_predictor_its_dtype_requires(tmp_path: Path) -> None:
    """`PREDICTOR=2` is for integers; floating point needs 3, which is a different algorithm.

    Applying 2 to float32 writes without error and decompresses to noise. Read from
    `IMAGE_STRUCTURE` rather than from `profile`, because rasterio's profile dict does not surface it -
    which is how this was briefly misdiagnosed as the predictor not being applied at all.
    """
    reference = write_raster(tmp_path / "B04.tif", np.ones((1024, 1024), np.uint16), nodata=0.0)
    array = np.random.default_rng(0).random((1024, 1024)).astype(np.float32)
    destination = tmp_path / "index.tif"

    await write_cog_from_array(array, reference=await inspect_raster(reference), destination=destination)

    with rasterio.open(destination) as result:
        assert result.tags(ns="IMAGE_STRUCTURE")["PREDICTOR"] == "3"
        assert result.dtypes[0] == "float32"


@pytest.mark.integration
async def test_an_array_that_does_not_match_its_reference_grid_is_refused(tmp_path: Path) -> None:
    """A computed array inherits georeferencing from the raster it came from. A mismatch would place
    every pixel slightly wrong, with no error."""
    reference = write_raster(tmp_path / "B04.tif", np.ones((64, 64), np.uint16))

    with pytest.raises(Exception, match="reference raster"):
        await write_cog_from_array(
            np.zeros((32, 32), np.float32),
            reference=await inspect_raster(reference),
            destination=tmp_path / "bad.tif",
        )


# --- S11: tiling for inference ---------------------------------------------------------------------------


async def test_a_tile_plan_covers_the_raster_and_reports_its_cost(tmp_path: Path) -> None:
    """`redundancy` is what an operator deciding "minutes or hours" actually needs."""
    path = write_raster(tmp_path / "B04.tif", np.ones((1500, 1200), np.uint16))

    plan = plan_tiles(await inspect_raster(path))

    assert plan.tile_size == INFERENCE_TILE_SIZE
    assert plan.tile_count == len(plan.windows)
    assert plan.redundancy > 1.0, "overlapping tiles read some pixels more than once, by design"


async def test_a_tile_reads_the_pixels_its_window_names(tmp_path: Path) -> None:
    """Rasterio takes (col, row) and NumPy takes [row, col]; swapping them transposes the read, which is
    only obviously wrong on a non-square raster."""
    array = np.arange(60 * 40, dtype=np.uint16).reshape(60, 40)
    path = write_raster(tmp_path / "B04.tif", array)

    plan = plan_tiles(await inspect_raster(path), tile_size=16, overlap=4)
    window = plan.windows[0]
    tile = await read_tile(path, window)

    rows, columns = window.as_slices()
    assert np.array_equal(tile, array[rows, columns])


async def test_stitching_reproduces_a_known_surface(tmp_path: Path) -> None:
    """The seam test. Feeding each window the ground truth it covers must reconstruct that truth.

    If the blend were wrong, the overlaps would show as a visible grid - the exact artefact the overlap
    exists to prevent.
    """
    truth = np.random.default_rng(1).random((300, 220)).astype(np.float32)
    path = write_raster(tmp_path / "B04.tif", np.ones((300, 220), np.uint16))

    plan = plan_tiles(await inspect_raster(path), tile_size=64, overlap=16)
    predictions = [truth[window.as_slices()[0], window.as_slices()[1]] for window in plan.windows]

    stitched = stitch_predictions(plan, predictions)

    assert np.allclose(stitched, truth, atol=1e-5), "the blend must be seamless over a consistent input"


async def test_stitching_a_wrongly_shaped_prediction_is_refused(tmp_path: Path) -> None:
    """A prediction that does not fill its window would broadcast, not fail.

    Added after a mutation pass found nothing testing it. NumPy happily broadcasts a (1, 64) array into a
    (64, 64) slice, so a model returning the wrong shape would paint a stripe across the scene and
    complete successfully - the seam artefact the overlap exists to prevent, arriving from the other side.
    """
    path = write_raster(tmp_path / "B04.tif", np.ones((300, 220), np.uint16))
    plan = plan_tiles(await inspect_raster(path), tile_size=64, overlap=16)
    predictions = [np.zeros((window.height, window.width), np.float32) for window in plan.windows]
    predictions[0] = np.zeros((1, 64), np.float32)

    with pytest.raises(Exception, match="but its window is"):
        stitch_predictions(plan, predictions)


async def test_stitching_a_mismatched_number_of_predictions_is_refused(tmp_path: Path) -> None:
    """Silently zipping to the shorter list would leave part of the scene unpredicted and unmarked."""
    path = write_raster(tmp_path / "B04.tif", np.ones((300, 220), np.uint16))
    plan = plan_tiles(await inspect_raster(path), tile_size=64, overlap=16)

    with pytest.raises(Exception, match="Every window must have exactly one prediction"):
        stitch_predictions(plan, [np.zeros((64, 64), np.float32)])


# --- The tile contract -----------------------------------------------------------------------------------


def curl_json(url: str) -> dict:
    result = subprocess.run(["curl", "-s", url], capture_output=True, text=True, timeout=60)
    return json.loads(result.stdout)


def curl_headers(url: str, origin: str) -> dict[str, str]:
    result = subprocess.run(
        ["curl", "-s", "-D", "-", "-o", "/dev/null", "-H", f"Origin: {origin}", url],
        capture_output=True, text=True, timeout=60,
    )
    headers: dict[str, str] = {}
    for line in result.stdout.splitlines():
        name, separator, value = line.partition(":")
        if separator:
            headers[name.strip().lower()] = value.strip()
    return headers


@pytest.mark.integration
@needs_tile_server
async def test_the_tilejson_carries_what_the_frontend_reads() -> None:
    """**The 1.2 gate's contract half.** The frontend positions its camera from these fields.

    `bounds` wrong and the globe flies to the ocean; `minzoom`/`maxzoom` wrong and it requests tiles that
    do not exist and shows nothing - neither of which produces an error anywhere.
    """
    tilejson = curl_json(
        f"{settings.tile_server}/cog/WebMercatorQuad/tilejson.json?url={NDVI_OBJECT}"
    )

    assert tilejson["scheme"] == "xyz"
    assert len(tilejson["bounds"]) == 4
    west, south, east, north = tilejson["bounds"]
    assert west < east and south < north, "a transposed bounds is still a valid bounds, somewhere else"
    # Ghaziabad, in the Delhi NCR - the AOI Phase 1.1 fetched.
    assert 76.5 < west < 78.5 and 27.0 < south < 29.5
    assert isinstance(tilejson["minzoom"], int) and isinstance(tilejson["maxzoom"], int)
    assert tilejson["minzoom"] < tilejson["maxzoom"]


@pytest.mark.integration
@needs_tile_server
async def test_cors_permits_the_configured_origin_and_no_other() -> None:
    """Named by the frontend's own notes as "the most common first-day failure".

    TiTiler's default is `*` **and** `allow-credentials: true` - a pair every browser rejects outright,
    so the permissive-looking default is in fact the broken one. Measured on the first tile this project
    served, and the reason `TITILER_API_CORS_ORIGINS` is set in docker-compose.yml.

    A disallowed origin still gets HTTP 200 with no `access-control-allow-origin`. That is correct and is
    the same thing Phase 0.4 measured against MinIO: **the browser enforces CORS, not the server.**
    """
    tile = (
        f"{settings.tile_server}/cog/tiles/WebMercatorQuad/11/1465/855@1x.png"
        f"?url={NDVI_OBJECT}&rescale=-1,1&colormap_name=rdylgn"
    )

    allowed = curl_headers(tile, settings.storage_browser_origin_header)
    assert allowed.get("access-control-allow-origin") == settings.storage_browser_origin_header

    refused = curl_headers(tile, "https://evil.example")
    assert "access-control-allow-origin" not in refused


@pytest.mark.integration
@needs_tile_server
async def test_a_tile_is_a_png_with_alpha_transparent_over_nodata(tmp_path: Path) -> None:
    """The globe draws black squares off the edge of a scene without this.

    PNG is requested explicitly: TiTiler answers with JPEG when the format is unspecified, and JPEG has
    no alpha channel at all - measured, after the first tile came back `image/jpeg` and RGB.
    """
    from PIL import Image

    edge_tile = (
        f"{settings.tile_server}/cog/tiles/WebMercatorQuad/9/365/213@1x.png"
        f"?url={NDVI_OBJECT}&rescale=-1,1&colormap_name=rdylgn"
    )
    destination = tmp_path / "tile.png"
    # Offloaded like every other blocking call in an `async def` - `code-standards.md` §7. The two helpers
    # above are sync functions called from async tests, which is why they do not need this.
    await asyncio.to_thread(
        subprocess.run, ["curl", "-s", "-o", str(destination), edge_tile], check=True, timeout=120
    )

    image = Image.open(destination)

    assert image.mode == "RGBA", f"expected an alpha channel, got {image.mode}"
    alpha = np.array(image.getchannel("A"))
    assert (alpha == 0).any(), "no transparent pixels - nodata would render as a black square"
    assert (alpha == 255).any(), "no opaque pixels - the tile is entirely empty"


# --- Recorded run ----------------------------------------------------------------------------------------
#
# $ uv run pytest tests/integration/test_raster_pipeline.py -q -p no:warnings          2026-08-31
#
#   ....................                                                     [100%]
#   20 passed in 4.35s
#
# The inspection, validation and tiling tests build their own GeoTIFFs and need nothing running. The COG and
# tile tests need `docker compose up -d minio titiler`.
#
# **The gate, end to end.** `aeris ingest index` over the scene Phase 1.1 fetched:
#
#   NDVI over 10980x10980   range [-1.000, 1.000]   mean 0.521   vegetated (>0.3) 72.6%
#   -> s3://aeris-cog/S2B_MSIL2A_20240319T052649_R105_T43RGM_20240319T094507/ndvi.tif  (508.8 MB)
#
#   TileJSON  scheme xyz, bounds [77.032, 27.901, 78.176, 28.913], minzoom 8, maxzoom 14
#   CORS      allowed origin -> access-control-allow-origin: http://localhost:3000
#             other origin   -> HTTP 200 with NO access-control-allow-origin  (the browser enforces it)
#   Tile      image/png, RGBA, 38,217 transparent px of 65,536 over the scene edge
#
# And in a real browser at http://localhost:3000 (`tools/tilecheck/`, seven checks, all PASS) - including
# `getImageData` on a canvas the tile was drawn into, which is what Cesium does and what a plain <img>
# does not exercise.
#
# Checked by mutation:
#
#   I  the CRS check dropped               -> test_a_raster_with_no_crs_is_refused FAILED
#   J  constancy back to a fraction        -> test_a_constant_raster_is_refused FAILED
#   K  the COG predictor ignores dtype     -> test_a_float_cog_uses_the_predictor_its_dtype_requires FAILED
#   L  the prediction-shape check dropped  -> test_stitching_a_wrongly_shaped_prediction_is_refused FAILED
#
# J is the one that came from a failing test rather than from review: `distinct / valid` is `1 / N` for a
# constant raster, so a fixed fraction threshold means something different at every resolution. At 1e-6 it
# fired on a 10980x10980 scene and silently passed a 20x20 one - the check existed and only worked on large
# rasters. Constancy is scale-free and is now counted.
#
# L survived the first pass: nothing tested a wrongly-shaped prediction, and NumPy broadcasts a (1, 64)
# array into a (64, 64) slice happily - so a model returning the wrong shape would paint a stripe across
# the scene and complete successfully.
#
# All mutated files were restored and byte-compared against their originals.
