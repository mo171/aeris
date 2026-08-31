"""The one loader every dataset goes through, so eighteen datasets do not become eighteen bespoke readers that disagree.

what  : `DatasetSample`, `load_samples()` and `count_samples()` - enumeration of a dataset's samples from
        its declared layout.
where : Called by `services/datasets/catalogue.py` (which reports counts), by `aeris dataset show`, and
        from Phase 1.6 onwards by everything that trains or evaluates.
how   : The roadmap's gate says "every one loads through a single loader", and this is it. It works
        because `constants/datasets.py` declares each dataset's `DatasetLayout` rather than hiding it in
        code: six layout shapes cover the whole of the PDF's Table 5, so this file reads a declaration
        instead of carrying a branch per dataset.

        **A sample is paths and identity, not parsed labels, and that boundary is deliberate.** A LEVIR-CD
        mask, a DOTA oriented bounding box and an RSVQA question have nothing in common; a loader
        returning all three would return `Any`, which is a loader that has stopped promising anything. So
        1.1 owes acquisition, licensing, cataloguing and **enumeration**, and label parsing belongs to the
        phase that has a model to feed - 1.6 for boxes and masks, 1.7 for questions.

        Enumeration is not a placeholder for that. It is what answers the questions actually worth asking
        now: is this download complete, do the pairs line up, how many samples are really in this split.

        **Pairing is by file name, and an unmatched file is an error rather than a skip.** A bi-temporal
        dataset with 637 images in `A`, 637 in `B` and 636 masks is a dataset that will silently train on
        636 pairs and report a number nobody can reproduce. `load_samples` raises with the names that did
        not match, because the only useful moment to find that out is before the training run.
"""

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.constants.datasets import (
    DATASET_CATALOGUE,
    DatasetId,
    DatasetLayout,
    DatasetSplit,
    LayoutKind,
)
from app.lib.exceptions import InvalidRequestError, ResourceNotFoundError

logger = logging.getLogger(__name__)

# How many unmatched names to name in an error before giving up on listing them. Enough to see the pattern
# - a suffix mismatch, an off-by-one in a split - without printing six hundred lines at someone.
UNMATCHED_NAMES_REPORTED = 10


@dataclass(frozen=True, slots=True)
class DatasetSample:
    """One sample: which dataset and split it belongs to, and the files that make it up.

    `images` is a tuple because a bi-temporal sample has two and the order is meaningful - the first is T1.
    A tuple rather than two named fields so that single-image and paired datasets are the same type, which
    is what lets one loader serve both.
    """

    dataset_id: DatasetId
    split: DatasetSplit
    sample_id: str
    images: tuple[Path, ...]

    # The mask or per-image annotation, where the layout has one. `None` for class-folder and sidecar
    # layouts, whose labels are the directory name and a shared file respectively.
    label: Path | None = None

    # The class name, for `CLASS_FOLDERS` layouts where the directory *is* the label.
    class_name: str | None = None


def dataset_directory(dataset_id: DatasetId) -> Path:
    """Where one dataset lives on disk. The id is the directory name - no manifest to fall out of date."""
    return settings.dataset_root / dataset_id.value


def split_directory(dataset_id: DatasetId, split: DatasetSplit) -> Path:
    """The directory holding one split, resolved through the dataset's declared layout."""
    layout = DATASET_CATALOGUE[dataset_id].layout
    if split not in layout.split_directories:
        available = ", ".join(sorted(existing.value for existing in layout.split_directories))
        raise InvalidRequestError(
            f"{dataset_id.value} has no {split.value} split. It publishes: {available}.",
            details={"datasetId": dataset_id.value, "split": split.value},
        )
    return dataset_directory(dataset_id) / layout.split_directories[split]


def load_samples(dataset_id: DatasetId, split: DatasetSplit) -> Iterator[DatasetSample]:
    """Enumerate one split of one dataset, in a stable order.

    A generator, because several of these have hundreds of thousands of samples and the caller usually
    wants to iterate rather than materialise. Sync: it walks a local directory tree, and the phase that
    reads pixels does so through `rasterio`, which is sync too (`code-standards.md` §7).

    Sorted by name, always. An unsorted `iterdir` gives whatever order the filesystem returns, which
    differs between machines - and a training run that is not reproducible across machines is one whose
    results cannot be compared with anything.
    """
    record = DATASET_CATALOGUE[dataset_id]
    root = split_directory(dataset_id, split)

    if not root.exists():
        raise ResourceNotFoundError(
            f"{record.title} is not on disk. Expected {root}. "
            f"Get it from {record.source_url} - `aeris dataset show {dataset_id.value}` has the details.",
            details={"datasetId": dataset_id.value, "expectedPath": str(root)},
        )

    match record.layout.kind:
        case LayoutKind.CLASS_FOLDERS:
            yield from _load_class_folders(dataset_id, split, root, record.layout)
        case LayoutKind.SCENE_DIRECTORIES:
            yield from _load_scene_directories(dataset_id, split, root, record.layout)
        case _:
            yield from _load_parallel_directories(dataset_id, split, root, record.layout)


def count_samples(dataset_id: DatasetId, split: DatasetSplit) -> int:
    """How many samples a split actually holds.

    The number the catalogue reports, and it is counted rather than read from the record's `scale` field -
    which is the published figure and is exactly what an incomplete download will not match.
    """
    return sum(1 for _ in load_samples(dataset_id, split))


def _images_in(directory: Path, layout: DatasetLayout) -> dict[str, Path]:
    """Every image in a directory, keyed by stem so parallel directories can be matched by name."""
    if not directory.exists():
        return {}
    return {
        path.stem: path
        for path in sorted(directory.iterdir())
        if path.is_file() and path.suffix.lower() in layout.image_suffixes
    }


def _load_parallel_directories(
    dataset_id: DatasetId, split: DatasetSplit, root: Path, layout: DatasetLayout
) -> Iterator[DatasetSample]:
    """`PAIRED_MASK`, `IMAGE_MASK`, `IMAGE_ANNOTATION` and `IMAGE_SIDECAR` - directories matched by stem.

    One function for four layout kinds because they differ only in how many image directories there are
    and whether a label directory exists beside them. Writing four near-identical functions is how three
    of them come to handle a missing file differently.
    """
    image_sets = [_images_in(root / directory, layout) for directory in layout.image_directories]

    if not image_sets or not image_sets[0]:
        raise ResourceNotFoundError(
            f"No images under {root / layout.image_directories[0]}. The download looks incomplete, or the "
            f"archive unpacked to a different layout than {dataset_id.value} declares.",
            details={"datasetId": dataset_id.value, "path": str(root)},
        )

    primary_stems = set(image_sets[0])
    _require_matching_stems(dataset_id, split, root, layout, image_sets, primary_stems)

    labels = _images_in(root / layout.label_directory, layout) if layout.label_directory else {}
    # An annotation directory holds `.txt` or `.xml`, which `_images_in` filters out by suffix, so it is
    # read by stem across every file instead.
    if layout.label_directory and not labels:
        label_root = root / layout.label_directory
        labels = {
            path.stem: path for path in sorted(label_root.iterdir()) if path.is_file()
        } if label_root.exists() else {}

    for stem in sorted(primary_stems):
        yield DatasetSample(
            dataset_id=dataset_id,
            split=split,
            sample_id=stem,
            images=tuple(images[stem] for images in image_sets),
            label=labels.get(stem),
        )


def _require_matching_stems(
    dataset_id: DatasetId,
    split: DatasetSplit,
    root: Path,
    layout: DatasetLayout,
    image_sets: list[dict[str, Path]],
    primary_stems: set[str],
) -> None:
    """Every image directory must hold the same sample names. Raises naming what did not line up.

    **This is the check worth having.** A bi-temporal dataset with 637 images in `A`, 637 in `B` and 636
    masks trains happily on 636 pairs and reports a number nobody can reproduce, because nothing anywhere
    said a file was missing. The only useful moment to discover it is before the run.
    """
    for directory, images in zip(layout.image_directories[1:], image_sets[1:], strict=True):
        missing = sorted(primary_stems - set(images))
        extra = sorted(set(images) - primary_stems)
        if missing or extra:
            raise ResourceNotFoundError(
                f"{dataset_id.value} {split.value}: {root / layout.image_directories[0]} and "
                f"{root / directory} do not hold the same samples. "
                f"{len(missing)} missing from {directory} (e.g. {missing[:UNMATCHED_NAMES_REPORTED]}), "
                f"{len(extra)} only in {directory} (e.g. {extra[:UNMATCHED_NAMES_REPORTED]}). "
                "The download is incomplete or was unpacked wrongly.",
                details={
                    "datasetId": dataset_id.value,
                    "split": split.value,
                    "missingCount": len(missing),
                    "extraCount": len(extra),
                },
            )


def _load_class_folders(
    dataset_id: DatasetId, split: DatasetSplit, root: Path, layout: DatasetLayout
) -> Iterator[DatasetSample]:
    """`CLASS_FOLDERS` - EuroSAT. The directory name is the label, so there is no label file to match."""
    class_directories = sorted(path for path in root.iterdir() if path.is_dir())
    if not class_directories:
        raise ResourceNotFoundError(
            f"No class directories under {root}. {dataset_id.value} expects one directory per class.",
            details={"datasetId": dataset_id.value, "path": str(root)},
        )

    for class_directory in class_directories:
        for image in sorted(class_directory.iterdir()):
            if image.is_file() and image.suffix.lower() in layout.image_suffixes:
                yield DatasetSample(
                    dataset_id=dataset_id,
                    split=split,
                    sample_id=image.stem,
                    images=(image,),
                    class_name=class_directory.name,
                )


def _load_scene_directories(
    dataset_id: DatasetId, split: DatasetSplit, root: Path, layout: DatasetLayout
) -> Iterator[DatasetSample]:
    """`SCENE_DIRECTORIES` - one directory per scene, holding its bands.

    The layout `aeris dataset fetch` writes for Sentinel scenes, and the one SEN12MS and BigEarthNet use.
    A sample is a whole scene and its images are its bands, so the tuple is longer than two and its order
    is the sorted band order - which the caller must not rely on for band identity. Band identity comes
    from the file name, and Phase 1.2 reads it there.
    """
    for scene in sorted(path for path in root.iterdir() if path.is_dir()):
        bands = tuple(
            path
            for path in sorted(scene.rglob("*"))
            if path.is_file() and path.suffix.lower() in layout.image_suffixes
        )
        if bands:
            yield DatasetSample(
                dataset_id=dataset_id, split=split, sample_id=scene.name, images=bands
            )
