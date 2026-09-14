"""Gets imagery onto the machine: a STAC search and fetch for Sentinel scenes, an archive download for the rest.

what  : `search_scenes()`, `fetch_scene()`, `download_archive()`, and `AcquisitionPlan` - what the CLI
        prints for a dataset it cannot fetch itself.
where : Called by `aeris dataset fetch`. Phase 1.2's catalogue search reuses `search_scenes` directly -
        the STAC query behind `POST /catalogue/search` is this one.
how   : Four acquisition routes, named on each record in `constants/datasets.py`, because they are
        genuinely different problems and pretending otherwise produces a `fetch` that lies:

        - **`stac`** - Sentinel-1 and Sentinel-2, searched and fetched from a STAC API. Real, and the only
          imagery this project acquires rather than downloads.
        - **`download`** - a direct archive URL. Real.
        - **`huggingface`** (1.6) - a benchmark republished on the Hub as parquet. One file per split,
          the image columns written out into the record's declared layout, so the single loader and the
          enumeration behind `aeris dataset list` serve it like anything unpacked by hand.
        - **`manual`** - behind a registration form, a Google Drive link or an email request. **The CLI
          prints instructions and does not pretend.** Roughly half of the PDF's Table 5 is in this state,
          and a `fetch` command that silently did nothing for those would be worse than one that refuses.

        **Planetary Computer assets need signing, and this is the one non-obvious thing about STAC here.**
        A search returns asset hrefs pointing at Azure Blob Storage that are unreadable without a SAS
        token; `planetary_computer.sign()` adds it. An unsigned href fails with 404, which reads as "no
        such scene" rather than "not signed" and is the standard afternoon lost to this API.

        **pystac-client is sync**, so every call into it is wrapped in `asyncio.to_thread` at the boundary
        (`code-standards.md` §7). Written here at the call site rather than hidden, so the cost is visible.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import aiohttp

from app.config import settings
from app.constants.datasets import (
    DATASET_CATALOGUE,
    DOWNLOAD_ATTEMPTS,
    DOWNLOAD_RETRY_BACKOFF_SECONDS,
    DatasetId,
    DatasetSplit,
)
from app.lib.exceptions import InvalidRequestError, UpstreamUnavailableError
from app.services.datasets.loader import dataset_directory, split_directory

logger = logging.getLogger(__name__)

# The STAC collection each dataset id corresponds to on Planetary Computer. Here rather than in
# `constants/datasets.py` because it is specific to this provider - a different STAC API names its
# collections differently, and the record stays provider-neutral.
STAC_COLLECTIONS: dict[DatasetId, str] = {
    DatasetId.SENTINEL2_L2A: "sentinel-2-l2a",
    # The catalogue record promises radiometrically terrain-corrected linear power. The similarly named
    # `sentinel-1-grd` collection publishes unsigned amplitudes and cannot support physical dB thresholds.
    DatasetId.SENTINEL1_GRD: "sentinel-1-rtc",
}

# The Sentinel-2 assets worth fetching by default: the four 10 m bands plus the scene classification layer.
# Not every band, because a full L2A scene is over a gigabyte and Phase 1.2's first index needs red, NIR
# and the cloud mask. `--asset` overrides this.
DEFAULT_SENTINEL2_ASSETS: tuple[str, ...] = ("B02", "B03", "B04", "B08", "SCL")

# Sentinel-1 GRD publishes one asset per polarisation. VV and VH are the pair the fusion phase compares.
DEFAULT_SENTINEL1_ASSETS: tuple[str, ...] = ("vv", "vh")

DOWNLOAD_CHUNK_BYTES = 1 << 20


@dataclass(frozen=True, slots=True)
class SceneMatch:
    """One scene a STAC search found, reduced to what the operator needs to choose between them."""

    scene_id: str
    collection: str
    acquired_on: str
    cloud_cover_percentage: float | None
    assets: dict[str, str]
    # Some Sentinel-1 assets omit CRS from the GeoTIFF header while the STAC item correctly carries
    # `proj:code`. Keep that boundary metadata rather than making the downloader rediscover it.
    source_crs: str | None = None
    source_transform: tuple[float, float, float, float, float, float] | None = None

    @property
    def summary(self) -> str:
        cloud = "n/a (SAR)" if self.cloud_cover_percentage is None else f"{self.cloud_cover_percentage:.1f}%"
        return f"{self.acquired_on}  cloud {cloud}"


@dataclass(frozen=True, slots=True)
class AcquisitionPlan:
    """What to do about a dataset this tool cannot fetch. Printed by `aeris dataset fetch` for `manual`."""

    dataset_id: DatasetId
    instructions: str


async def search_scenes(
    dataset_id: DatasetId,
    *,
    bounding_box: tuple[float, float, float, float],
    start: date,
    end: date,
    maximum_cloud_percentage: float | None = None,
    limit: int = 10,
) -> list[SceneMatch]:
    """Find scenes over an area and a date range.

    `bounding_box` is `(west, south, east, north)` in EPSG:4326 - the order STAC and GeoJSON both use, and
    the one that is silently wrong if swapped, because a transposed box is usually still a valid box
    somewhere in the ocean.
    """
    collection = STAC_COLLECTIONS.get(dataset_id)
    if collection is None:
        raise InvalidRequestError(
            f"{dataset_id.value} is not fetched from STAC. `aeris dataset show {dataset_id.value}` says how.",
            details={"datasetId": dataset_id.value},
        )

    query: dict[str, Any] = {}
    if maximum_cloud_percentage is not None:
        if dataset_id is DatasetId.SENTINEL1_GRD:
            # SAR sees through cloud, so the property does not exist on the collection and filtering on it
            # would return nothing at all - which reads as "no scenes here" (api-contract.md §1 rule 3 is
            # the same mistake on the wire).
            raise InvalidRequestError(
                "Sentinel-1 is radar and carries no cloud cover. Filtering it by cloud returns nothing.",
                details={"datasetId": dataset_id.value},
            )
        query["eo:cloud_cover"] = {"lt": maximum_cloud_percentage}

    try:
        items = await asyncio.to_thread(
            _search_stac_synchronously,
            collection=collection,
            bounding_box=bounding_box,
            start=start,
            end=end,
            query=query,
            limit=limit,
        )
    except Exception as error:
        raise UpstreamUnavailableError(
            f"The STAC catalogue at {settings.stac_api_url} could not be searched: {error}",
            details={"stacApiUrl": str(settings.stac_api_url)},
        ) from error

    logger.info(
        "stac search returned scenes",
        extra={"dataset_id": dataset_id.value, "count": len(items), "collection": collection},
    )
    return items


def _search_stac_synchronously(
    *,
    collection: str,
    bounding_box: tuple[float, float, float, float],
    start: date,
    end: date,
    query: dict[str, Any],
    limit: int,
) -> list[SceneMatch]:
    """The blocking half of the search. Sync on purpose - it is what `to_thread` is given.

    Assets are signed here, inside the thread, because `planetary_computer.sign` makes its own HTTP call
    for the token. Signing after the fact at the call site would put that call back on the event loop.
    """
    import planetary_computer
    import pystac_client

    catalogue = pystac_client.Client.open(
        str(settings.stac_api_url), modifier=planetary_computer.sign_inplace
    )
    search = catalogue.search(
        collections=[collection],
        bbox=bounding_box,
        datetime=f"{start.isoformat()}/{end.isoformat()}",
        query=query or None,
        max_items=limit,
    )

    matches: list[SceneMatch] = []
    for item in search.items():
        matches.append(
            SceneMatch(
                scene_id=item.id,
                collection=collection,
                acquired_on=str(item.datetime.date()) if item.datetime else "unknown",
                cloud_cover_percentage=item.properties.get("eo:cloud_cover"),
                assets={name: asset.href for name, asset in item.assets.items()},
                source_crs=item.properties.get("proj:code") or item.properties.get("proj:epsg"),
                source_transform=(
                    tuple(item.properties["proj:transform"][:6])
                    if item.properties.get("proj:transform") else None
                ),
            )
        )
    return matches


async def fetch_scene(
    dataset_id: DatasetId, scene: SceneMatch, *, asset_names: tuple[str, ...] | None = None
) -> Path:
    """Download one scene's assets into `<datasets>/<dataset_id>/<scene_id>/`.

    That directory shape is the `SCENE_DIRECTORIES` layout the record declares, so a fetched scene is
    immediately visible to `aeris dataset list` and loadable through the same loader as everything else.
    Nothing about a fetched scene is special-cased downstream, which is the point of writing it here.
    """
    if asset_names is None:
        asset_names = (
            DEFAULT_SENTINEL1_ASSETS if dataset_id is DatasetId.SENTINEL1_GRD else DEFAULT_SENTINEL2_ASSETS
        )

    destination = dataset_directory(dataset_id) / scene.scene_id
    destination.mkdir(parents=True, exist_ok=True)

    missing = [name for name in asset_names if name not in scene.assets]
    if missing:
        raise InvalidRequestError(
            f"{scene.scene_id} has no assets named {missing}. It publishes: {sorted(scene.assets)}.",
            details={"sceneId": scene.scene_id, "missing": missing},
        )

    timeout = aiohttp.ClientTimeout(total=settings.dataset_download_timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for name in asset_names:
            await _download_to(session, scene.assets[name], destination / f"{name}.tif")

    logger.info(
        "scene fetched",
        extra={"dataset_id": dataset_id.value, "scene_id": scene.scene_id, "assets": len(asset_names)},
    )
    return destination


async def fetch_scene_window(
    dataset_id: DatasetId,
    scene: SceneMatch,
    *,
    bounding_box: tuple[float, float, float, float],
    asset_names: tuple[str, ...] | None = None,
    name: str | None = None,
) -> Path:
    """Fetch only the part of each asset that covers `bounding_box`, as a GeoTIFF per band (1.10).

    A Sentinel-2 tile is 110 km across and a question is usually about a town. The assets are COGs, so a
    windowed read over the signed href moves the tiles that cover the box and nothing else - measured:
    ten megabytes for a 10 km subset of five bands against half a gigabyte for the same bands whole. The
    grid is the asset's own (no reprojection, no resampling: the window is aligned to the asset's pixels),
    which is what lets a second date land on the first date's grid when the two are the same tile - the
    property the temporal graph's S1 checks and the S9 gate measures.

    `name` is the directory the subset is written to under the dataset's root; the scene id otherwise.
    """
    if asset_names is None:
        asset_names = DEFAULT_SENTINEL1_ASSETS if dataset_id is DatasetId.SENTINEL1_GRD else DEFAULT_SENTINEL2_ASSETS
    missing = [asset for asset in asset_names if asset not in scene.assets]
    if missing:
        raise InvalidRequestError(
            f"{scene.scene_id} has no assets named {missing}. It publishes: {sorted(scene.assets)}.",
            details={"sceneId": scene.scene_id, "missing": missing},
        )
    destination = dataset_directory(dataset_id) / (name or scene.scene_id)
    await asyncio.to_thread(destination.mkdir, parents=True, exist_ok=True)
    for asset in asset_names:
        await asyncio.to_thread(
            _window_asset, scene.assets[asset], bounding_box, destination / f"{asset}.tif",
            source_crs=scene.source_crs, source_transform=scene.source_transform,
        )
    logger.info(
        "scene window fetched",
        extra={"dataset_id": dataset_id.value, "scene_id": scene.scene_id, "assets": len(asset_names), "bbox": list(bounding_box)},
    )
    return destination


def _window_asset(
    href: str,
    bounding_box: tuple[float, float, float, float],
    destination: Path,
    *,
    source_crs: str | int | None = None,
    source_transform: Any | None = None,
) -> None:
    """Read the window of one remote COG that covers the geographic box and write it locally. Sync."""
    import rasterio
    from affine import Affine
    from rasterio.warp import transform_bounds
    from rasterio.windows import Window, from_bounds
    from rasterio.windows import transform as window_transform

    with rasterio.open(href) as source:
        effective_crs = source.crs or source_crs
        if effective_crs is None:
            raise InvalidRequestError(
                "The imagery asset and its STAC item provide no coordinate reference system; it cannot be clipped by geographic bounds.",
                details={"href": href.split("?", maxsplit=1)[0]},
            )
        effective_transform = (
            source.transform
            if source.crs is not None or source_transform is None
            else Affine(*tuple(source_transform)[:6])
        )
        west, south, east, north = transform_bounds("EPSG:4326", effective_crs, *bounding_box)
        window = from_bounds(west, south, east, north, transform=effective_transform).round_offsets().round_lengths()
        window = window.intersection(Window(0, 0, source.width, source.height))
        if window.width <= 0 or window.height <= 0:
            raise InvalidRequestError(f"{href} does not cover the requested box.", details={"bbox": list(bounding_box)})
        data = source.read(window=window)
        profile = source.profile.copy()
        profile.update(
            driver="GTiff", height=int(window.height), width=int(window.width), transform=window_transform(window, effective_transform),
            crs=effective_crs, compress="deflate", tiled=True, blockxsize=256, blockysize=256,
        )
        profile.pop("blocksize", None)
    with rasterio.open(destination, "w", **profile) as sink:
        sink.write(data)


async def download_archive(dataset_id: DatasetId) -> Path:
    """Download a dataset published as a single archive at a stable URL.

    Only the `download` route. The archive is left compressed and **not** unpacked: several of these expand
    to a different top-level directory than their name suggests, and guessing wrongly produces a nested
    mess that looks like a corrupt download. The CLI prints where it landed and what to unpack it to.
    """
    record = DATASET_CATALOGUE[dataset_id]
    if record.acquisition != "download":
        raise InvalidRequestError(
            f"{dataset_id.value} is acquired by '{record.acquisition}', not by direct download.",
            details={"datasetId": dataset_id.value, "acquisition": record.acquisition},
        )

    destination_directory = dataset_directory(dataset_id)
    destination_directory.mkdir(parents=True, exist_ok=True)
    destination = destination_directory / record.source_url.rsplit("/", 1)[-1]

    timeout = aiohttp.ClientTimeout(total=settings.dataset_download_timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        await _download_to(session, record.source_url, destination)

    return destination


async def _download_to(session: aiohttp.ClientSession, url: str, destination: Path) -> None:
    """Stream one URL to a file, retrying a transfer the remote end drops.

    Written to a `.partial` and renamed on success, so an interrupted download never leaves a file that
    looks complete. `aeris dataset list` measures what is on disk, and a truncated GeoTIFF reporting the
    right size is exactly the failure that check exists to catch.

    **Retried, because a long download being reset is normal rather than exceptional.** Measured: a 245 MB
    band was cut off by the remote host after four minutes and 375 KB of a 239 MB body, failing the whole
    fetch. A client that cannot survive that cannot acquire a scene reliably.

    Each attempt restarts from zero rather than resuming with a `Range` header. Resuming would be faster
    and would need the server's `ETag` to prove the object had not changed underneath us - and a scene
    silently stitched from two versions of a file is a worse failure than a slow retry.
    """
    partial = destination.with_suffix(destination.suffix + ".partial")
    last_error: Exception | None = None

    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            async with session.get(url) as response:
                response.raise_for_status()
                with partial.open("wb") as handle:
                    async for chunk in response.content.iter_chunked(DOWNLOAD_CHUNK_BYTES):
                        handle.write(chunk)
            partial.replace(destination)
            return
        except (aiohttp.ClientError, TimeoutError) as error:
            last_error = error
            partial.unlink(missing_ok=True)
            if attempt < DOWNLOAD_ATTEMPTS:
                logger.warning(
                    "download failed; retrying",
                    extra={"url": url, "attempt": attempt, "of": DOWNLOAD_ATTEMPTS, "error": str(error)},
                )
                await asyncio.sleep(DOWNLOAD_RETRY_BACKOFF_SECONDS * attempt)

    raise UpstreamUnavailableError(
        f"Could not download {url} after {DOWNLOAD_ATTEMPTS} attempts: {last_error}",
        details={"url": url, "attempts": DOWNLOAD_ATTEMPTS},
    ) from last_error


def acquisition_plan(dataset_id: DatasetId) -> AcquisitionPlan:
    """What a human has to do for a dataset this tool cannot fetch.

    Returned rather than raised, because "you have to go and get this one yourself" is an answer, not a
    failure - and the operator asking is entitled to the URL and the expected directory rather than a
    stack trace.
    """
    record = DATASET_CATALOGUE[dataset_id]
    return AcquisitionPlan(
        dataset_id=dataset_id,
        instructions=(
            f"{record.title} is behind a registration form or a hosted drive and cannot be fetched here.\n"
            f"  1. Get it from {record.source_url}\n"
            f"  2. Check the licence at {record.licence_url}\n"
            f"  3. Unpack it to {dataset_directory(dataset_id)}\n"
            f"     so that {record.layout.kind.value} layout holds - "
            f"`aeris dataset show {dataset_id.value}` prints the expected directories.\n"
            f"  4. Set `licence_verified=True` in app/constants/datasets.py once you have read the terms.\n"
            f"  Approximate size: {record.approximate_size}"
        ),
    )


async def fetch_hub_split(dataset_id: DatasetId, split: DatasetSplit) -> Path:
    """Fetch one split of a Hub parquet mirror and write its images into the declared layout.

    Returns the split directory. Idempotent: a split already on disk with the expected count is left alone,
    so re-running `fetch` is cheap and a partial write is finished rather than duplicated.
    """
    record = DATASET_CATALOGUE[dataset_id]
    mirror = record.hub_parquet
    if mirror is None or split not in mirror.files:
        raise InvalidRequestError(
            f"{record.title} has no Hub parquet for its {split.value} split.",
            details={"datasetId": dataset_id.value, "split": split.value},
        )
    destination = split_directory(dataset_id, split)
    parquet = await asyncio.to_thread(_download_hub_file, mirror.repository, mirror.files[split], mirror.revision)
    written = await asyncio.to_thread(_materialise_parquet, parquet, destination, mirror.columns, record.layout.image_suffixes[0])
    logger.info(
        "hub split materialised",
        extra={"dataset_id": dataset_id.value, "split": split.value, "samples": written, "directory": str(destination)},
    )
    return destination


def _download_hub_file(repository: str, filename: str, revision: str) -> Path:
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import HfHubHTTPError

    try:
        return Path(
            hf_hub_download(
                repo_id=repository, filename=filename, revision=revision, repo_type="dataset",
                cache_dir=settings.model_weights_path,
            )
        )
    except (HfHubHTTPError, OSError) as error:
        raise UpstreamUnavailableError(
            f"Could not fetch {filename} from {repository}: {error}",
            details={"upstream": "huggingface-hub", "repository": repository},
        ) from error


def _materialise_parquet(parquet: Path, destination: Path, columns: dict[str, str], suffix: str) -> int:
    """Write each image column of the parquet into its layout directory, one file per row, zero-padded."""
    import pyarrow.parquet as pq

    table = pq.read_table(parquet, columns=list(columns))
    for directory in columns.values():
        (destination / directory).mkdir(parents=True, exist_ok=True)
    row_count = table.num_rows
    width = len(str(row_count))
    for column, directory in columns.items():
        values = table.column(column).to_pylist()
        for index, value in enumerate(values):
            # The `image` feature is a struct of `bytes` and `path`; the bytes are the encoded PNG as-is.
            payload = value["bytes"] if isinstance(value, dict) else value
            target = destination / directory / f"{index:0{width}d}{suffix}"
            if not target.exists():
                target.write_bytes(payload)
    return row_count
