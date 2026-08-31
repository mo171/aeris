"""Holds the dataset catalogue to the rule the roadmap's 1.1 gate is actually about: no training on data whose terms nobody read.

what  : Tests over `constants/datasets.py` and `constants/licences.py`. No disk, no network - these are
        statements about the catalogue itself.
where : `tests/unit/`.
how   : The gate says "licences are recorded **before any training begins**, not after". That is a claim
        about sequence, and the way it fails is not dramatic: someone adds a dataset in a hurry, leaves the
        licence blank or optimistic, trains on it, and the problem surfaces when the work is being
        published. Every test here exists to make that fail early and loudly instead.

        Two of them matter more than the rest.

        `test_an_unverified_licence_permits_nothing` pins the design decision that an unknown licence is
        **not** a permissive one. If `Licence.UNVERIFIED` ever gained `training_permitted=True` - which is
        one careless edit - every other check here would still pass while the gate silently stopped
        existing.

        `test_no_record_claims_a_verified_unverified_licence` catches the contradiction that reads as fine
        in a diff: `licence=Licence.UNVERIFIED, licence_verified=True` is someone ticking a box without
        changing the licence, and it would make a dataset trainable on the strength of nothing.
"""

import re

import pytest

from app.constants.datasets import (
    DATASET_CATALOGUE,
    DatasetId,
    DatasetSplit,
    LayoutKind,
)
from app.constants.licences import LICENCE_TERMS, CommercialUse, Licence, Redistribution, terms_for

# Sub-phases as `roadmap.md` numbers them. Checked as a shape rather than against a list of known phases,
# because the roadmap grows and a test that has to be edited every time it does gets deleted instead.
PHASE_PATTERN = re.compile(r"^\d+\.\d+(\.\d+)?$")

ACQUISITION_ROUTES = {"stac", "download", "manual"}


async def test_every_dataset_id_has_a_record() -> None:
    """The enum and the catalogue are one thing; an id with no record is a dataset nothing can describe."""
    missing = sorted(set(DatasetId) - set(DATASET_CATALOGUE))
    assert not missing, f"These DatasetIds have no record in DATASET_CATALOGUE: {missing}."


async def test_every_record_is_filed_under_its_own_id() -> None:
    """A record filed under the wrong key would load a different dataset's directory and licence."""
    for key, record in DATASET_CATALOGUE.items():
        assert record.dataset_id is key, f"{key} holds the record for {record.dataset_id}."


async def test_an_unverified_licence_permits_nothing() -> None:
    """**The load-bearing test.** An unknown licence must deny everything, not default to permissive.

    If this ever passes with `training_permitted=True`, every other check in this file keeps passing while
    the gate stops existing - because `require_trainable` would wave through any dataset nobody had read
    the terms for. The whole design rests on unknown and permissive being different states.
    """
    unverified = terms_for(Licence.UNVERIFIED)

    assert unverified.training_permitted is False
    assert unverified.redistribution is Redistribution.FORBIDDEN
    assert unverified.commercial_use is CommercialUse.FORBIDDEN


async def test_no_record_claims_a_verified_unverified_licence() -> None:
    """`licence=UNVERIFIED, licence_verified=True` is a contradiction that reads as fine in a diff.

    It is what "I ticked the box" looks like when nobody changed the licence itself, and it would make a
    dataset trainable on the strength of nothing at all.
    """
    contradictions = [
        record.dataset_id.value
        for record in DATASET_CATALOGUE.values()
        if record.licence is Licence.UNVERIFIED and record.licence_verified
    ]
    assert not contradictions, (
        f"These are marked verified while their licence is UNVERIFIED: {contradictions}. "
        "Read the terms and record the real licence, or leave both unverified."
    )


@pytest.mark.parametrize("dataset_id", sorted(DATASET_CATALOGUE))
async def test_a_record_names_a_licence_with_known_terms(dataset_id: DatasetId) -> None:
    """Every licence used must have terms, or nothing can answer what the dataset permits."""
    record = DATASET_CATALOGUE[dataset_id]
    assert record.licence in LICENCE_TERMS, f"{dataset_id.value} names {record.licence}, which has no terms."


@pytest.mark.parametrize("dataset_id", sorted(DATASET_CATALOGUE))
async def test_a_record_says_where_its_terms_are_published(dataset_id: DatasetId) -> None:
    """Including the verified ones. "Verified" means a human read a page, and this is that page.

    Without it, re-checking a licence years later - which is what a change of terms requires - starts with
    a search rather than a link.
    """
    record = DATASET_CATALOGUE[dataset_id]
    assert record.licence_url.startswith("http"), f"{dataset_id.value} has no licence page."
    assert record.source_url.startswith("http"), f"{dataset_id.value} has no source."


@pytest.mark.parametrize("dataset_id", sorted(DATASET_CATALOGUE))
async def test_a_record_names_the_phase_that_unlocks_it(dataset_id: DatasetId) -> None:
    """Read down `unlocked_in` and it is the acquisition schedule - so it has to be a real phase number.

    It matters because several of these are tens of gigabytes: knowing that SEN12MS is not needed until
    1.11 is what stops it being downloaded in week one on a laptop.
    """
    record = DATASET_CATALOGUE[dataset_id]
    assert PHASE_PATTERN.match(record.unlocked_in), (
        f"{dataset_id.value} is unlocked in {record.unlocked_in!r}, which is not a roadmap phase number."
    )


@pytest.mark.parametrize("dataset_id", sorted(DATASET_CATALOGUE))
async def test_a_record_declares_how_it_is_acquired(dataset_id: DatasetId) -> None:
    """One of three routes, because `aeris dataset fetch` branches on exactly these and nothing else.

    An unrecognised route would fall through the CLI's branches and do nothing at all - a fetch that exits
    zero and downloads nothing, which is the worst available outcome.
    """
    record = DATASET_CATALOGUE[dataset_id]
    assert record.acquisition in ACQUISITION_ROUTES, (
        f"{dataset_id.value} declares acquisition={record.acquisition!r}, not one of {ACQUISITION_ROUTES}."
    )


@pytest.mark.parametrize("dataset_id", sorted(DATASET_CATALOGUE))
async def test_a_layout_is_loadable(dataset_id: DatasetId) -> None:
    """Every layout has at least one split and at least one image directory.

    A layout declaring neither is a dataset the single loader cannot read, and the failure would arrive as
    an empty enumeration - which looks exactly like an absent download.
    """
    layout = DATASET_CATALOGUE[dataset_id].layout

    assert layout.split_directories, f"{dataset_id.value} declares no splits."
    assert layout.image_directories, f"{dataset_id.value} declares no image directory."
    assert layout.image_suffixes, f"{dataset_id.value} declares no image suffixes."


@pytest.mark.parametrize(
    "dataset_id",
    sorted(
        dataset_id
        for dataset_id, record in DATASET_CATALOGUE.items()
        if record.layout.kind is LayoutKind.PAIRED_MASK
    ),
)
async def test_a_bitemporal_layout_declares_exactly_two_image_directories(dataset_id: DatasetId) -> None:
    """A change dataset has T1 and T2, and the order is meaningful.

    One directory would silently enumerate half the pairs; three would pair the wrong images. Both produce
    a change map rather than an error, which is why this is checked here rather than discovered in 1.6.
    """
    layout = DATASET_CATALOGUE[dataset_id].layout
    assert len(layout.image_directories) == 2, (
        f"{dataset_id.value} is a paired-mask dataset with {len(layout.image_directories)} image "
        "directories. Bi-temporal means exactly two, first is T1."
    )
    assert layout.label_directory, f"{dataset_id.value} is a change dataset with no mask directory."


async def test_the_datasets_the_roadmap_names_are_all_catalogued() -> None:
    """The roadmap's 1.1 table names these by name, so their absence here is a gap in the plan.

    Spelled out rather than derived, because this is the one place the catalogue is checked against the
    document that commissioned it - and a dataset quietly dropped from the catalogue would otherwise be
    invisible until the phase that needed it.
    """
    required = {
        DatasetId.SENTINEL2_L2A, DatasetId.SENTINEL1_GRD, DatasetId.LEVIR_CD, DatasetId.S2LOOKING,
        DatasetId.SECOND, DatasetId.DOTA, DatasetId.DIOR, DatasetId.LOVEDA, DatasetId.OPEN_EARTH_MAP,
        DatasetId.RSVQA_LR, DatasetId.RSVQA_HR, DatasetId.VRSBENCH, DatasetId.DIOR_RSVG,
        DatasetId.RRSIS_D, DatasetId.SEN12MS, DatasetId.BIGEARTHNET_MM, DatasetId.EUROSAT,
    }
    assert required <= set(DATASET_CATALOGUE), (
        f"roadmap.md 1.1 names these and the catalogue lacks them: {sorted(required - set(DATASET_CATALOGUE))}"
    )


async def test_the_sentinel_licences_are_the_ones_that_are_actually_verified() -> None:
    """Copernicus is open and unambiguous; everything else is somebody's research licence until read.

    Asserted as a *fact about the current state*, so that marking something verified is a deliberate act
    that fails this test and makes the author write down what they checked. Loosening it is fine; doing so
    silently is not.
    """
    verified = {
        record.dataset_id for record in DATASET_CATALOGUE.values() if record.licence_verified
    }
    assert verified == {DatasetId.SENTINEL2_L2A, DatasetId.SENTINEL1_GRD}, (
        "The set of verified licences changed. If someone read a licence page and confirmed the terms, "
        "update this test and say which page and when. If not, the record is wrong."
    )


async def test_every_split_directory_is_relative() -> None:
    """An absolute split path would escape the datasets root and read someone else's disk."""
    for dataset_id, record in DATASET_CATALOGUE.items():
        for split, directory in record.layout.split_directories.items():
            assert not directory.startswith(("/", "\\")) and ":" not in directory, (
                f"{dataset_id.value}'s {split.value} split is an absolute path: {directory!r}."
            )


async def test_scene_directory_datasets_publish_one_undivided_split() -> None:
    """Imagery we acquire ourselves has no train/test split, and pretending otherwise would invent one.

    A published benchmark's splits are part of its definition and comparability; a scene we fetched has
    none, and `DatasetSplit.ALL` says that rather than defaulting to `TRAIN`.
    """
    for record in DATASET_CATALOGUE.values():
        if record.layout.kind is LayoutKind.SCENE_DIRECTORIES:
            assert DatasetSplit.ALL in record.layout.split_directories, (
                f"{record.dataset_id.value} holds scenes but declares splits it does not have."
            )


# --- Recorded run ----------------------------------------------------------------------------------------
#
# $ uv run pytest tests/unit/test_dataset_catalogue.py -q                             2026-08-31
#
#   ........................................................................ [ 70%]
#   ..............................                                           [100%]
#   102 passed in 0.30s
#
# 18 datasets catalogued from the PDF's Table 5 (pp.21-24). Two licences verified - Sentinel-1 and
# Sentinel-2, both Copernicus open data. **Sixteen are not**, which is the honest state of a catalogue
# assembled from published papers rather than from reading sixteen licence pages, and it is why
# `Licence.UNVERIFIED` denies everything rather than defaulting to permissive.
#
# Checked by mutation:
#
#   A  `Licence.UNVERIFIED` gains `training_permitted=True`  -> test_an_unverified_licence_permits_nothing
#                                                               FAILED
#   D  LEVIR-CD marked `licence_verified=True` with nobody   -> 3 tests FAILED:
#      having read its terms                                    test_no_record_claims_a_verified_unverified
#                                                               _licence, test_the_sentinel_licences_are_the
#                                                               _ones_that_are_actually_verified, and
#                                                               test_training_is_refused_on_a_dataset_whose
#                                                               _licence_nobody_read
#
# A is the one the whole design rests on. If it ever passes, every other test in this file keeps passing
# while the gate silently stops existing - `require_trainable` would wave through any dataset nobody had
# read the terms for, because unknown and permissive would have become the same state.
#
# D is the human version of the same failure: ticking a box without changing the licence. Three separate
# tests catch it, which is the level of redundancy that particular mistake deserves.
