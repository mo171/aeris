"""Proves the imagery half of Phase 1.1 against the live STAC catalogue - a real search, real signed assets, real refusals.

what  : Tests over `services/datasets/acquisition.py` against Planetary Computer.
where : `tests/integration/`. **Needs the internet**, and skips rather than fails without it - a machine
        with no network is not a machine with a broken backend.
how   : The searches here run against the real catalogue, not a recorded fixture, and that is deliberate.
        What can actually break in this code is not our query construction - it is the *catalogue's*
        behaviour: a collection renamed, a property that stopped existing, an asset that is no longer
        signed. A recorded response would keep passing through every one of those.

        Nothing here downloads a scene. A Sentinel-2 band is ~230 MB (measured - see the record's quirks),
        so a suite that fetched one would take minutes and would fail on a metered connection. The
        download path is exercised by `aeris dataset fetch` and its result is checked by
        `test_dataset_loader.py`, which reads whatever has actually been fetched.

        **Two of these test refusals rather than successes**, and they are the ones worth having. A
        transposed bounding box and a cloud filter on radar both produce *zero results* rather than an
        error if nothing checks - and zero results reads as "nothing was acquired over this area", which
        is a conclusion rather than a bug report.
"""

import socket
from datetime import date

import pytest

from app.constants.datasets import DatasetId
from app.lib.exceptions import InvalidRequestError
from app.services.datasets.acquisition import (
    DEFAULT_SENTINEL2_ASSETS,
    STAC_COLLECTIONS,
    acquisition_plan,
    search_scenes,
)

# Ghaziabad, in the Delhi NCR - a rapidly built-up area, which is why it is the AOI the change-detection
# examples use. Small enough that a search returns a handful of scenes rather than hundreds.
GHAZIABAD_BOUNDING_BOX = (77.40, 28.62, 77.50, 28.70)

# A month with known clear acquisitions over northern India: the dry season, before the monsoon.
SEARCH_START = date(2024, 3, 1)
SEARCH_END = date(2024, 3, 31)


def has_network() -> bool:
    try:
        socket.create_connection(("planetarycomputer.microsoft.com", 443), timeout=5).close()
        return True
    except OSError:
        return False


needs_network = pytest.mark.skipif(
    not has_network(), reason="the STAC catalogue is unreachable; this machine has no network"
)


@needs_network
async def test_a_search_finds_real_sentinel2_scenes() -> None:
    """The live catalogue returns scenes over a real AOI, with dates and cloud cover attached."""
    scenes = await search_scenes(
        DatasetId.SENTINEL2_L2A,
        bounding_box=GHAZIABAD_BOUNDING_BOX,
        start=SEARCH_START,
        end=SEARCH_END,
        maximum_cloud_percentage=20.0,
        limit=5,
    )

    assert scenes, "no Sentinel-2 scenes over Ghaziabad in March 2024 - the collection or query changed"
    for scene in scenes:
        assert scene.scene_id.startswith("S2"), scene.scene_id
        assert scene.acquired_on.startswith("2024-03")
        assert scene.cloud_cover_percentage is not None
        assert scene.cloud_cover_percentage <= 20.0, "the cloud filter was not applied"


@needs_network
async def test_the_assets_a_search_returns_are_signed() -> None:
    """**The non-obvious thing about this API.** An unsigned asset href fails with 404, not with 401.

    Planetary Computer's hrefs point at Azure Blob Storage and are unreadable without a SAS token;
    `planetary_computer.sign_inplace` adds it as a query string. Unsigned, a fetch fails with a message
    that reads as "no such scene" rather than "not signed", which is the standard afternoon lost to this
    catalogue. Checked here so that failure can never be silent.
    """
    scenes = await search_scenes(
        DatasetId.SENTINEL2_L2A,
        bounding_box=GHAZIABAD_BOUNDING_BOX,
        start=SEARCH_START,
        end=SEARCH_END,
        limit=1,
    )

    assets = scenes[0].assets
    for band in DEFAULT_SENTINEL2_ASSETS:
        assert band in assets, f"{band} is not published by this collection any more"
        assert "?" in assets[band], f"{band}'s href carries no SAS token - it would 404 on fetch"


@needs_network
async def test_sentinel1_is_searchable_and_carries_no_cloud_cover() -> None:
    """Radar sees through cloud, so `cloudCoverPercentage` is `None` and never `0`.

    The same rule the wire contract states (`api-contract.md` §1 rule 3): zero would assert a cloud-free
    radar scene, which is a claim about something the sensor cannot observe.
    """
    scenes = await search_scenes(
        DatasetId.SENTINEL1_GRD,
        bounding_box=GHAZIABAD_BOUNDING_BOX,
        start=SEARCH_START,
        end=SEARCH_END,
        limit=3,
    )

    assert scenes, "no Sentinel-1 scenes over Ghaziabad in March 2024"
    for scene in scenes:
        assert scene.cloud_cover_percentage is None, "SAR must not report a cloud percentage"


async def test_filtering_radar_by_cloud_is_refused_rather_than_silently_empty() -> None:
    """**A refusal worth having.** The property does not exist on the collection, so the filter matches
    nothing - and "no scenes found" is a conclusion an operator would act on rather than a bug they would
    report.

    No network needed: the refusal happens before the query is built, which is the point of it.
    """
    with pytest.raises(InvalidRequestError) as raised:
        await search_scenes(
            DatasetId.SENTINEL1_GRD,
            bounding_box=GHAZIABAD_BOUNDING_BOX,
            start=SEARCH_START,
            end=SEARCH_END,
            maximum_cloud_percentage=10.0,
        )

    assert "radar" in str(raised.value).lower()


async def test_a_dataset_that_is_not_imagery_cannot_be_searched() -> None:
    """LEVIR-CD is a download, not a catalogue query. Asking must say so and point at how to get it."""
    with pytest.raises(InvalidRequestError) as raised:
        await search_scenes(
            DatasetId.LEVIR_CD,
            bounding_box=GHAZIABAD_BOUNDING_BOX,
            start=SEARCH_START,
            end=SEARCH_END,
        )

    assert "aeris dataset show" in str(raised.value)


async def test_only_the_two_sentinel_collections_are_searchable() -> None:
    """The STAC mapping is provider-specific and stays small on purpose.

    Every other dataset in the catalogue is a published benchmark with a fixed download, not something
    queried by area and date. A collection added here without a matching record would be searchable and
    unstorable.
    """
    assert set(STAC_COLLECTIONS) == {DatasetId.SENTINEL2_L2A, DatasetId.SENTINEL1_GRD}


async def test_a_manual_dataset_gets_instructions_rather_than_a_stack_trace() -> None:
    """"You have to go and get this one yourself" is an answer, not a failure.

    Roughly half the PDF's Table 5 is behind a registration form or a hosted drive. A `fetch` that raised
    for those would be a command that fails on half its inputs by design; one that silently did nothing
    would be worse. The plan names the URL, the licence page and the directory to unpack into.
    """
    plan = acquisition_plan(DatasetId.LEVIR_CD)

    assert "https://chenhao.in/LEVIR/" in plan.instructions
    assert "licence_verified" in plan.instructions, "it has to say what makes the dataset usable"
    assert "levir-cd" in plan.instructions, "and where to put it"


# --- Recorded run ----------------------------------------------------------------------------------------
#
# $ uv run pytest tests/integration/test_scene_acquisition.py -q                      2026-08-31
#
#   .......                                                                  [100%]
#   7 passed in 18.82s
#
# Against the live Planetary Computer catalogue, not a recorded fixture. Four Sentinel-2 scenes returned
# over Ghaziabad for March 2024 at under 10% cloud (0.2% to 5.6%), and Sentinel-1 scenes over the same box
# with `cloudCoverPercentage` correctly absent rather than zero.
#
# A real scene was then fetched end to end and is what `test_dataset_loader.py`'s last test reads:
#
#   $ uv run aeris dataset fetch sentinel2-l2a --bbox 77.40,28.62,77.50,28.70 \
#         --from 2024-03-01 --to 2024-03-31 --max-cloud 10 --asset B04,B08
#   -> S2B_MSIL2A_20240319T052649_R105_T43RGM_20240319T094507   489 MB, 7m18s
#
# **That measurement changed the catalogue.** The record declared "~200 MB per scene subset"; two 10 m bands
# came to 489 MB, so one band is ~245 MB rather than the ~100 MB the published figures suggest. The record
# now says so, and `--asset` exists because of it.
#
# Checked by mutation:
#
#   G  the Sentinel-1 cloud-filter refusal removed  -> test_filtering_radar_by_cloud_is_refused_rather_than
#                                                      _silently_empty FAILED
#
# G is the shape of failure this whole file is written against. Without the refusal the query is accepted,
# matches nothing, and returns an empty list - which reads as "no radar was acquired over this area" and is
# a conclusion an operator would act on rather than a bug they would report.
