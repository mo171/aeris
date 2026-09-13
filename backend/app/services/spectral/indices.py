"""Decides which index a question needs, gets the right bands onto one grid, masks them, and only then lets the arithmetic run.

what  : `resolve_index_target()` - phrase to index and range; `read_scene_bands()` - bands by role, on the
        analysis grid, as surface reflectance; `read_scene_classification()` - the SCL on that grid;
        `compute_index()` - the cloud mask applied to the *inputs*, then the formula.
where : S12. Called by `services/pipeline/nodes/feature_extraction.py` and by `cli/figures.py`. The
        formulae are in `math/index_formulae.py` and this file contains none of them.
how   : This is the reference example of `architecture-context.md` §12: the service holds every decision
        and the `math/` module holds every equation. Four decisions live here, each a §8 boundary:

        - **Which band is red** (rule 5's cousin). Bands are located by role through
          `imagery/metadata.identify_band`, never by file position, and the formula is handed roles.
        - **Surface reflectance or refuse** (rule 5). An index over L1C or an unknown level is a different
          quantity wearing the same name. A human may *declare* the level; the code never guesses it.
        - **One grid before any arithmetic** (rule 6). A 20 m SWIR band is resampled onto the 10 m
          analysis grid, bilinear because reflectance is continuous, before it meets a 10 m band. The
          analysis grid is the finest native resolution among the bands the index needs.
        - **The mask reaches the bands, not the result** (rule 1). `compute_index` takes the mask and
          applies it to every input before the formula sees them. There is no code path that computes
          first and masks after, which is the structural form of "never after".

        `unphysical_fraction` is the share of pixels the formula itself refused - observed in every band,
        NaN in the result. It is reported rather than absorbed, because a scene where EVI masked 30% of
        the ground is a scene where EVI was the wrong index.
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio

from app.config import settings
from app.constants.raster import BandRole, ProcessingLevel
from app.constants.spectral import INDEX_BAND_ROLES, INDEX_NAMES, QUERY_TARGETS, SpectralIndex
from app.lib.exceptions import ConflictError, InvalidRequestError
from app.services.imagery.math.indices import to_surface_reflectance
from app.services.imagery.metadata import RasterMetadata, identify_band, inspect_raster
from app.services.imagery.validation import require_analysable
from app.services.preprocessing.cloud_masking import OpticalMaskResult, apply_optical_mask
from app.services.preprocessing.math.grid_alignment import GridDefinition, grids_match
from app.services.preprocessing.reprojection import reproject_to_reference_grid
from app.services.spectral.math.index_formulae import FORMULAE

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IndexTarget:
    """What a question asks for: an index, and the value range that answers it - or no range, for a map."""

    index: SpectralIndex
    lower: float | None
    upper: float | None
    label: str
    phrase: str

    @property
    def has_range(self) -> bool:
        return self.lower is not None and self.upper is not None


async def resolve_index_target(query: str) -> IndexTarget:
    """The deterministic half of routing (PDF p.24): a phrase chooses from a table.

    Longest matching phrase wins, so "unhealthy vegetation" is not answered as "vegetation". A bare index
    name draws the map with no range. Nothing matching is a refusal that names the phrases it knows, not a
    guess at what was meant.
    """
    lowered = query.lower()
    for phrase in sorted(QUERY_TARGETS, key=len, reverse=True):
        if _contains_phrase(lowered, phrase):
            target = QUERY_TARGETS[phrase]
            return IndexTarget(target.index, target.lower, target.upper, target.label, phrase)
    for name, index in INDEX_NAMES.items():
        if _contains_phrase(lowered, name):
            return IndexTarget(index, None, None, index.value.upper(), name)
    raise InvalidRequestError(
        f"No spectral index answers {query!r}. Phase 1.4 answers questions about: "
        f"{', '.join(sorted(QUERY_TARGETS))}; or names an index: {', '.join(INDEX_NAMES)}.",
        details={"query": query},
    )


def _contains_phrase(text: str, phrase: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None


@dataclass(frozen=True, slots=True)
class BandOnGrid:
    """One band, as surface reflectance on the analysis grid."""

    role: BandRole
    band_id: str
    reflectance: np.ndarray
    native_resolution_metres: int | None
    resampled: bool
    # The file the values were read from, before any resampling: what provenance hashes.
    source: RasterMetadata


@dataclass(frozen=True, slots=True)
class SceneBands:
    """Every band an index needs, read from one scene directory onto one grid."""

    scene_directory: Path
    reference: RasterMetadata
    bands: dict[BandRole, BandOnGrid]
    processing_level: ProcessingLevel

    @property
    def scene_id(self) -> str:
        return self.scene_directory.name

    @property
    def transform(self) -> tuple[float, float, float, float, float, float]:
        return self.reference_grid.transform

    @property
    def reference_grid(self) -> GridDefinition:
        return _grid_of(self.reference)


async def finest_resolution(scene_directory: Path) -> float | None:
    """Metres per pixel of the finest band present - the router's resolution gate; `None` if unreadable.
    A scene the graph cannot read is the graph's to refuse with its own message; routing needs a hint."""
    try:
        bands = await locate_bands(scene_directory)
        resolutions = [(await inspect_raster(path)).resolution[0] for path in bands.values()]
    except Exception:  # noqa: BLE001 - see above
        return None
    return min(resolutions) if resolutions else None


async def locate_bands(scene_directory: Path) -> dict[BandRole, Path]:
    """Every recognisable band in a scene directory, by role.

    By role rather than by file position: `B04` is red on Sentinel-2 and band 3 on Landsat, and a
    positional read is how a true-colour composite silently becomes a false-colour one.
    """
    candidates = await asyncio.to_thread(lambda: sorted(scene_directory.glob("*.tif")))
    found: dict[BandRole, Path] = {}
    for candidate in candidates:
        role = identify_band(candidate).role
        if role is not None:
            found[role] = candidate
    return found


async def require_surface_reflectance(
    metadata: RasterMetadata, declared_level: ProcessingLevel | None = None
) -> ProcessingLevel:
    """§8 rule 5. A declared level is a human's statement; a detected one is read from the path.

    Neither is guessed. A band extracted into a research directory has lost its product name, and the
    only honest options are a human saying what it is or a refusal.
    """
    level = declared_level or metadata.processing_level
    if level is not ProcessingLevel.L2A:
        raise ConflictError(
            f"This scene reads as {level.value}, and an index needs surface reflectance (L2A). If you know "
            "what it is, say so with --level; the code will not assume it "
            "(architecture-context.md §8 rule 5).",
            details={"level": level.value, "path": str(metadata.path)},
        )
    return level


async def analysis_grid(scene_directory: Path, roles: tuple[BandRole, ...]) -> RasterMetadata:
    """The grid every band is brought onto: the finest native resolution among the roles, formula order
    breaking ties. Both S7 and S12 derive it from the same inputs, so they cannot disagree."""
    located = await locate_bands(scene_directory)
    missing = [role for role in roles if role not in located]
    if missing:
        raise InvalidRequestError(
            f"{scene_directory.name} has no {', '.join(role.value for role in missing)} band. "
            f"Present: {', '.join(sorted(role.value for role in located)) or 'nothing recognisable'}.",
            details={"sceneDirectory": str(scene_directory), "missing": [role.value for role in missing]},
        )
    finest = min(roles, key=lambda role: (identify_band(located[role]).native_resolution_metres or 0))
    return await inspect_raster(located[finest])


async def read_scene_bands(
    scene_directory: Path,
    roles: tuple[BandRole, ...],
    *,
    declared_level: ProcessingLevel | None = None,
) -> SceneBands:
    """Read the named roles as surface reflectance on the analysis grid, refusing what §8 forbids."""
    located = await locate_bands(scene_directory)
    reference = await analysis_grid(scene_directory, roles)
    level = await require_surface_reflectance(reference, declared_level)
    await require_analysable(reference)

    bands: dict[BandRole, BandOnGrid] = {}
    for role in roles:
        metadata = await inspect_raster(located[role])
        await require_analysable(metadata)
        source_path, resampled = await _on_reference_grid(metadata, reference, scene_directory)
        raw = await asyncio.to_thread(_read_band, source_path)
        reflectance = await asyncio.to_thread(to_surface_reflectance, raw, nodata=metadata.nodata)
        bands[role] = BandOnGrid(
            role=role,
            band_id=metadata.band.band.value if metadata.band.band else role.value,
            reflectance=reflectance,
            native_resolution_metres=metadata.band.native_resolution_metres,
            resampled=resampled,
            source=metadata,
        )

    logger.info(
        "scene bands read",
        extra={
            "scene": scene_directory.name, "roles": [role.value for role in roles],
            "grid": f"{reference.width}x{reference.height}",
            "resampled": [band.band_id for band in bands.values() if band.resampled],
        },
    )
    return SceneBands(scene_directory=scene_directory, reference=reference, bands=bands, processing_level=level)


async def read_scene_classification(
    scene_directory: Path, reference: RasterMetadata
) -> np.ndarray | None:
    """The L2A scene classification layer on the analysis grid, or `None` when the scene has none.

    Nearest neighbour, and it must be (§8 rule 6): the SCL holds class labels, and an averaged label is a
    class that does not exist.
    """
    located = await locate_bands(scene_directory)
    path = located.get(BandRole.SCENE_CLASSIFICATION)
    if path is None:
        return None
    metadata = await inspect_raster(path)
    source_path, _ = await _on_reference_grid(metadata, reference, scene_directory)
    return await asyncio.to_thread(_read_band, source_path)


async def _on_reference_grid(
    metadata: RasterMetadata, reference: RasterMetadata, scene_directory: Path
) -> tuple[Path, bool]:
    """The band's path on the analysis grid - itself when it already is, a resampled copy when not."""
    if grids_match(_grid_of(metadata), _grid_of(reference)):
        return metadata.path, False
    destination = (
        settings.cog_working_directory_path.parent
        / f"{scene_directory.name}__{metadata.path.stem}_on_{reference.path.stem}.tif"
    )
    result = await reproject_to_reference_grid(
        metadata.path, reference.path, destination, categorical=metadata.band.is_categorical
    )
    logger.info(
        "band resampled onto the analysis grid",
        extra={"band": metadata.path.name, "onto": reference.path.name, "resampling": result.resampling},
    )
    return result.path, True


def _grid_of(metadata: RasterMetadata) -> GridDefinition:
    return GridDefinition(
        width=metadata.width, height=metadata.height, crs=metadata.crs or "", transform=metadata.transform
    )


def _read_band(path: Path) -> np.ndarray:
    with rasterio.open(path) as dataset:
        return dataset.read(1)


@dataclass(frozen=True, slots=True)
class IndexResult:
    """One index over one scene, with everything a figure, a claim or a report needs to say about it."""

    index: SpectralIndex
    values: np.ndarray
    band_ids: list[str]
    resampled_band_ids: list[str]
    mask_applied: bool
    # `None` when no mask was applied - not `0.0`, which would claim a cloud-free scene.
    obscured_fraction: float | None
    # Observed in every band, refused by the formula. Large means the wrong index for this ground.
    unphysical_fraction: float
    scene_id: str
    reference: RasterMetadata
    transform: tuple[float, float, float, float, float, float]

    @property
    def observed(self) -> np.ndarray:
        return np.isfinite(self.values)

    @property
    def crs(self) -> str:
        return self.reference.crs or ""


async def compute_index(
    bands: SceneBands, index: SpectralIndex, *, mask: OpticalMaskResult | None
) -> IndexResult:
    """S12. The mask is applied to every input band, then the formula runs. In that order, only."""
    roles = INDEX_BAND_ROLES[index]
    missing = [role for role in roles if role not in bands.bands]
    if missing:
        raise InvalidRequestError(
            f"{index.value.upper()} needs {', '.join(role.value for role in roles)}; the scene bands read "
            f"lack {', '.join(role.value for role in missing)}.",
            details={"index": index.value, "missing": [role.value for role in missing]},
        )

    inputs = [bands.bands[role].reflectance for role in roles]
    if mask is not None:
        inputs = [await apply_optical_mask(values, mask) for values in inputs]

    values = await asyncio.to_thread(FORMULAE[index], *inputs)

    observed_in_every_band = np.logical_and.reduce([np.isfinite(band) for band in inputs])
    refused = observed_in_every_band & ~np.isfinite(values)
    unphysical_fraction = float(refused.sum() / observed_in_every_band.sum()) if observed_in_every_band.any() else 0.0

    return IndexResult(
        index=index,
        values=values,
        band_ids=[bands.bands[role].band_id for role in roles],
        resampled_band_ids=[bands.bands[role].band_id for role in roles if bands.bands[role].resampled],
        mask_applied=mask is not None,
        obscured_fraction=mask.obscured_fraction if mask is not None else None,
        unphysical_fraction=unphysical_fraction,
        scene_id=bands.scene_id,
        reference=bands.reference,
        transform=bands.transform,
    )
