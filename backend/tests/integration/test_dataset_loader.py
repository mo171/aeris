"""The Phase 1.1 gate: every dataset loads through one loader, and nothing trains on an unread licence.

what  : Tests over `services/datasets/loader.py` and `services/datasets/catalogue.py`, driven against
        synthetic directory trees built to each declared layout.
where : `tests/integration/`. **No Docker and no network** - it builds the layouts it reads. The one test
        that touches real data skips when that data is absent.
how   : Synthetic fixtures rather than a downloaded dataset, and that is the point rather than a
        compromise. LEVIR-CD is 2 GB and DOTA is 20 GB; a suite that needed them would be a suite nobody
        runs, and the thing being tested is *the layout declaration*, which a two-file directory exercises
        exactly as well as a 637-pair one.

        What the synthetic tree cannot prove is that the declared layout matches the real archive. Nothing
        can, short of downloading it - so the loader is written to **fail loudly** on a mismatch rather than
        return a short list, and `test_a_missing_pair_is_an_error_not_a_short_list` is the test that pins
        it. A change dataset with 637 images in `A`, 637 in `B` and 636 masks trains happily on 636 pairs
        and reports a number nobody can reproduce.

        The licence tests are the gate proper. `require_trainable` is where "recorded before any training
        begins" stops being a sentence in a roadmap and becomes something that raises.
"""

from pathlib import Path

import pytest

from app.constants.datasets import DATASET_CATALOGUE, DatasetId, DatasetSplit
from app.lib.exceptions import ConflictError, ResourceNotFoundError
from app.services.datasets.catalogue import Availability, inspect_dataset, require_trainable
from app.services.datasets.loader import count_samples, dataset_directory, load_samples


def write_image(path: Path) -> None:
    """A file that is an image only in the sense the loader cares about - its suffix.

    Enough because 1.1 enumerates rather than decodes: reading pixels is Phase 1.2's raster engine, and a
    loader test that needed valid GeoTIFFs would be testing rasterio.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not-a-real-image")


def build_paired_dataset(root: Path, dataset_id: DatasetId, split: DatasetSplit, names: list[str]) -> None:
    """A bi-temporal change dataset laid out exactly as its record declares."""
    layout = DATASET_CATALOGUE[dataset_id].layout
    split_root = root / dataset_id.value / layout.split_directories[split]
    for name in names:
        for image_directory in layout.image_directories:
            write_image(split_root / image_directory / f"{name}{layout.image_suffixes[0]}")
        if layout.label_directory:
            write_image(split_root / layout.label_directory / f"{name}{layout.image_suffixes[0]}")


def build_class_folder_dataset(root: Path, dataset_id: DatasetId, classes: dict[str, int]) -> None:
    """A class-folder dataset - EuroSAT's shape, where the directory name is the label."""
    layout = DATASET_CATALOGUE[dataset_id].layout
    split_root = root / dataset_id.value / layout.split_directories[DatasetSplit.ALL]
    for class_name, count in classes.items():
        for index in range(count):
            write_image(split_root / class_name / f"{class_name}_{index}{layout.image_suffixes[0]}")


# --- The single loader, across the layout kinds ------------------------------------------------------


async def test_a_paired_dataset_enumerates_its_pairs(isolated_dataset_root: Path) -> None:
    """`PAIRED_MASK`: two images and a mask per sample, matched by file name."""
    build_paired_dataset(
        isolated_dataset_root, DatasetId.LEVIR_CD, DatasetSplit.TRAIN, ["train_1", "train_2", "train_3"]
    )

    samples = list(load_samples(DatasetId.LEVIR_CD, DatasetSplit.TRAIN))

    assert [sample.sample_id for sample in samples] == ["train_1", "train_2", "train_3"]
    for sample in samples:
        assert len(sample.images) == 2, "a bi-temporal sample is a pair"
        # A is T1 and B is T2 - positional, and the order the record declares.
        assert sample.images[0].parent.name == "A"
        assert sample.images[1].parent.name == "B"
        assert sample.label is not None


async def test_a_class_folder_dataset_takes_its_label_from_the_directory(
    isolated_dataset_root: Path,
) -> None:
    """`CLASS_FOLDERS`: EuroSAT has no label file, because the directory is the label."""
    build_class_folder_dataset(
        isolated_dataset_root, DatasetId.EUROSAT, {"Forest": 2, "Highway": 3, "River": 1}
    )

    samples = list(load_samples(DatasetId.EUROSAT, DatasetSplit.ALL))

    assert len(samples) == 6
    assert {sample.class_name for sample in samples} == {"Forest", "Highway", "River"}
    assert all(sample.label is None for sample in samples)
    assert all(len(sample.images) == 1 for sample in samples)


async def test_a_scene_directory_dataset_enumerates_scenes_not_bands(
    isolated_dataset_root: Path,
) -> None:
    """`SCENE_DIRECTORIES`: one sample per scene, its bands as that sample's images.

    The distinction matters. Counting bands would report a two-band fetch of one scene as two samples,
    which is the number that would then appear in `aeris dataset list` and in any training log.
    """
    scene_root = isolated_dataset_root / DatasetId.SENTINEL2_L2A.value / "S2B_MSIL2A_20240319"
    for band in ("B04", "B08", "SCL"):
        write_image(scene_root / f"{band}.tif")

    samples = list(load_samples(DatasetId.SENTINEL2_L2A, DatasetSplit.ALL))

    assert len(samples) == 1
    assert samples[0].sample_id == "S2B_MSIL2A_20240319"
    assert len(samples[0].images) == 3


async def test_enumeration_is_ordered_the_same_way_on_every_machine(isolated_dataset_root: Path) -> None:
    """Sorted by name, always.

    `iterdir` returns whatever order the filesystem gives, which differs between machines and between a
    fresh copy and one that has been edited. A training run whose sample order depends on that is one
    whose results cannot be compared with a run on another machine.
    """
    build_paired_dataset(
        isolated_dataset_root, DatasetId.LEVIR_CD, DatasetSplit.TRAIN, ["c", "a", "b"]
    )

    first = [sample.sample_id for sample in load_samples(DatasetId.LEVIR_CD, DatasetSplit.TRAIN)]
    second = [sample.sample_id for sample in load_samples(DatasetId.LEVIR_CD, DatasetSplit.TRAIN)]

    assert first == ["a", "b", "c"] == second


# --- Failing loudly rather than short ----------------------------------------------------------------


async def test_a_missing_pair_is_an_error_not_a_short_list(isolated_dataset_root: Path) -> None:
    """**The check worth having.** An incomplete download must fail, not silently enumerate fewer samples.

    637 images in `A`, 636 in `B`, and a run that trains on 636 pairs and reports a number nobody can
    reproduce - with nothing anywhere saying a file was missing. The only useful moment to find that is
    before the run, which is why this raises rather than logs.
    """
    build_paired_dataset(
        isolated_dataset_root, DatasetId.LEVIR_CD, DatasetSplit.TRAIN, ["train_1", "train_2"]
    )
    layout = DATASET_CATALOGUE[DatasetId.LEVIR_CD].layout
    orphan = (
        isolated_dataset_root
        / DatasetId.LEVIR_CD.value
        / layout.split_directories[DatasetSplit.TRAIN]
        / layout.image_directories[1]
        / "train_2.png"
    )
    orphan.unlink()

    with pytest.raises(ResourceNotFoundError) as raised:
        list(load_samples(DatasetId.LEVIR_CD, DatasetSplit.TRAIN))

    # The message names what did not line up - a count alone would send someone to diff two directories
    # by hand.
    assert "train_2" in str(raised.value)


async def test_an_absent_dataset_says_where_to_get_it(isolated_dataset_root: Path) -> None:
    """The error an operator actually hits first, so it carries the source URL rather than a path."""
    with pytest.raises(ResourceNotFoundError) as raised:
        list(load_samples(DatasetId.DOTA, DatasetSplit.TRAIN))

    assert DATASET_CATALOGUE[DatasetId.DOTA].source_url in str(raised.value)


async def test_a_split_a_dataset_does_not_publish_is_refused(isolated_dataset_root: Path) -> None:
    """SECOND has no validation split. Asking for one must say so rather than return nothing.

    An empty list here would read as "the validation set is empty", and an evaluation reporting metrics
    over zero samples is worse than one that fails.
    """
    from app.lib.exceptions import InvalidRequestError

    with pytest.raises(InvalidRequestError) as raised:
        list(load_samples(DatasetId.SECOND, DatasetSplit.VALIDATION))

    assert "train" in str(raised.value)


# --- The catalogue report ----------------------------------------------------------------------------


async def test_an_absent_dataset_reports_absent_rather_than_empty(isolated_dataset_root: Path) -> None:
    """`aeris dataset list` distinguishes "not downloaded" from "downloaded and broken"."""
    status = inspect_dataset(DatasetId.LEVIR_CD)

    assert status.availability is Availability.ABSENT
    assert status.size_bytes == 0
    assert not status.is_trainable(DatasetSplit.TRAIN)


async def test_a_partly_downloaded_dataset_is_partial_rather_than_broken(
    isolated_dataset_root: Path,
) -> None:
    """Train downloaded, test not, is an ordinary situation - and it is not "malformed".

    Added after this distinction was got wrong: reporting it as malformed sends an operator to check how
    the archive unpacked, when what they need to do is finish downloading. The states exist to prescribe
    different actions, so conflating two of them removes the reason to have either.
    """
    build_paired_dataset(isolated_dataset_root, DatasetId.LEVIR_CD, DatasetSplit.TRAIN, ["a", "b"])

    status = inspect_dataset(DatasetId.LEVIR_CD)

    assert status.availability is Availability.PARTIAL
    assert status.has(DatasetSplit.TRAIN)
    assert set(status.missing_splits) == {DatasetSplit.VALIDATION, DatasetSplit.TEST}
    assert "val" in (status.problem or "")


async def test_training_is_refused_when_the_split_it_needs_is_the_missing_one(
    isolated_dataset_root: Path,
) -> None:
    """Permission is per split. A test split that is absent must not be borrowed from the train split.

    The failure without this is an evaluation that silently runs on training data, which produces a number
    that looks excellent and means nothing.
    """
    build_paired_dataset(isolated_dataset_root, DatasetId.LEVIR_CD, DatasetSplit.TRAIN, ["a", "b"])

    with pytest.raises(ConflictError) as raised:
        require_trainable(DatasetId.LEVIR_CD, DatasetSplit.TEST)

    assert "test" in str(raised.value)


async def test_a_directory_that_exists_but_holds_nothing_is_malformed(
    isolated_dataset_root: Path,
) -> None:
    """The two need opposite responses, which is why they are different states.

    Absent means download it. Malformed means the archive unpacked to a different shape and downloading it
    again will not help - the commonest real failure, because several of these expand to a top-level
    directory that is not their name.
    """
    (isolated_dataset_root / DatasetId.LEVIR_CD.value / "train").mkdir(parents=True)

    status = inspect_dataset(DatasetId.LEVIR_CD)

    assert status.availability is Availability.MALFORMED
    assert status.problem


async def test_size_is_measured_from_disk_not_taken_from_the_record(
    isolated_dataset_root: Path,
) -> None:
    """A half-finished download is the case the whole command exists to make visible.

    The record's `approximate_size` is the published figure; trusting it would make a 4 GB fragment of a
    10 GB dataset look complete. Measured here on a tree whose byte count is known exactly.
    """
    build_class_folder_dataset(isolated_dataset_root, DatasetId.EUROSAT, {"Forest": 4})

    status = inspect_dataset(DatasetId.EUROSAT)

    assert status.size_bytes == 4 * len(b"not-a-real-image")
    assert status.sample_counts[DatasetSplit.ALL] == 4


async def test_count_samples_counts_rather_than_reading_the_published_figure(
    isolated_dataset_root: Path,
) -> None:
    """The published scale is what a complete download *should* hold, which is not the question."""
    build_paired_dataset(
        isolated_dataset_root, DatasetId.LEVIR_CD, DatasetSplit.TRAIN, ["a", "b", "c", "d"]
    )

    assert count_samples(DatasetId.LEVIR_CD, DatasetSplit.TRAIN) == 4
    assert "637" in DATASET_CATALOGUE[DatasetId.LEVIR_CD].scale, "the published figure is unrelated"


# --- The licence gate --------------------------------------------------------------------------------


async def test_training_is_refused_on_a_dataset_whose_licence_nobody_read(
    isolated_dataset_root: Path,
) -> None:
    """**The gate.** "Licences are recorded before any training begins, not after."

    A rule about sequence needs something that refuses at the right moment. LEVIR-CD is present, complete
    and perfectly loadable here - and training on it still raises, because nobody has read its terms. That
    is the entire point: availability and permission are different questions.
    """
    build_paired_dataset(
        isolated_dataset_root, DatasetId.LEVIR_CD, DatasetSplit.TRAIN, ["a", "b"]
    )
    # Present and readable - only the train split was built, so the dataset is partial rather than ready,
    # which is exactly the situation someone training would be in.
    assert inspect_dataset(DatasetId.LEVIR_CD).has(DatasetSplit.TRAIN)

    with pytest.raises(ConflictError) as raised:
        require_trainable(DatasetId.LEVIR_CD)

    assert DATASET_CATALOGUE[DatasetId.LEVIR_CD].licence_url in str(raised.value)
    assert "licence_verified" in str(raised.value), "the error must say what to do about it"


async def test_training_is_refused_on_a_dataset_that_is_not_there(isolated_dataset_root: Path) -> None:
    """The other half: permission is not enough if the data is absent."""
    with pytest.raises(ConflictError) as raised:
        require_trainable(DatasetId.SENTINEL2_L2A, DatasetSplit.ALL)

    assert "absent" in str(raised.value)


async def test_a_verified_open_dataset_is_trainable(isolated_dataset_root: Path) -> None:
    """The positive case, so the gate is not passing by refusing everything.

    Sentinel-2 is Copernicus open data and its licence *has* been read, so once a scene is on disk nothing
    stands in the way. A gate that refused this too would be a gate nobody could get past, which is
    indistinguishable from a broken one.
    """
    scene = isolated_dataset_root / DatasetId.SENTINEL2_L2A.value / "S2B_MSIL2A_20240319"
    write_image(scene / "B04.tif")

    status = require_trainable(DatasetId.SENTINEL2_L2A, DatasetSplit.ALL)

    assert status.is_trainable(DatasetSplit.ALL)
    assert status.terms.training_permitted


# --- Against the real thing --------------------------------------------------------------------------


async def test_the_real_fetched_scene_loads_if_one_has_been_fetched() -> None:
    """The synthetic trees prove the layout logic; this proves the layout is the one on disk.

    Skipped rather than failed when no scene has been fetched, because acquiring 466 MB is not something a
    test suite should do on its own - but when a scene *is* there, the claim `aeris dataset fetch` makes
    about where it puts things is worth checking rather than assuming.
    """
    directory = dataset_directory(DatasetId.SENTINEL2_L2A)
    if not directory.exists() or not any(directory.iterdir()):
        pytest.skip("no Sentinel-2 scene fetched; run `aeris dataset fetch sentinel2-l2a --bbox ...`")

    samples = list(load_samples(DatasetId.SENTINEL2_L2A, DatasetSplit.ALL))

    assert samples, "a fetched scene must be enumerable through the same loader as everything else"
    for sample in samples:
        assert sample.images, f"{sample.sample_id} holds no bands"
        assert all(path.suffix == ".tif" for path in sample.images)
        assert all(path.stat().st_size > 0 for path in sample.images)


# --- Recorded run ----------------------------------------------------------------------------------------
#
# $ uv run pytest tests/integration/test_dataset_loader.py -q                         2026-08-31
#
#   .................                                                        [100%]
#   17 passed in 0.52s
#
# No Docker, no network. Sixteen tests build the layout they read; the seventeenth loads the real fetched
# Sentinel-2 scene and skips when none has been fetched.
#
# **A design bug was found here rather than by reading.** The first version of `inspect_dataset` reported a
# dataset with its train split downloaded and its test split not as `MALFORMED`, because it enumerated every
# declared split and the first missing one set the error. That is wrong in a way that matters: malformed
# sends an operator to check how the archive unpacked, when what they need to do is finish downloading.
# `Availability.PARTIAL` was added, and `require_trainable` became per-split - because permission and
# presence are both per-split questions, and an absent test split must never be quietly satisfied by a
# present train split.
#
# Checked by mutation:
#
#   B  `require_trainable` stops checking `licence_verified` -> test_training_is_refused_on_a_dataset_whose
#                                                               _licence_nobody_read FAILED
#   C  a mismatched pair is skipped instead of raising        -> test_a_missing_pair_is_an_error_not_a_short
#                                                               _list FAILED
#   E  enumeration stops sorting                              -> 2 tests FAILED, including
#                                                               test_enumeration_is_ordered_the_same_way_on
#                                                               _every_machine
#   F  size read from the record instead of measured          -> test_size_is_measured_from_disk_not_taken
#                                                               _from_the_record FAILED
#   H  scene enumeration counts bands as samples              -> test_a_scene_directory_dataset_enumerates
#                                                               _scenes_not_bands FAILED
#
# B is the gate. C is the one that would otherwise cost the most: a change dataset missing one mask trains
# on 636 pairs instead of 637 and reports a number nobody can reproduce, with nothing anywhere saying a file
# was missing.
