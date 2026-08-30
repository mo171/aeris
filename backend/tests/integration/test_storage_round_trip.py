"""The Phase 0.4 gate: a file uploaded through a presigned URL reads back by key, and a browser at the configured origin is actually allowed to fetch it.

what  : Integration tests for `app/lib/storage.py` against a live MinIO. The presigned round trip, the CORS
        rules the globe and the figure panel depend on, and the error behaviour that separates storage from
        the Redis cache.
where : `tests/integration/`. Marked `integration`, so it needs `docker compose up -d`. Not skipped when the
        infrastructure is absent - it fails, because it is the evidence for a Phase 0 gate.
how   : The presigned tests deliberately do **not** use the S3 client to perform the upload. A presigned URL
        exists so that something with no credentials and no SDK - a browser - can PUT a multi-gigabyte scene
        straight at storage. Testing it through `aioboto3` would test the client that signed it. So the
        upload and the download run through plain `aiohttp` with no authentication of any kind, which is what
        the frontend's `uploadImageryFile` does.

        The CORS pair is the part worth reading. `test_an_unknown_origin_is_refused...` asserts something
        counter-intuitive on purpose: **a disallowed origin still gets HTTP 200 and the object's bytes.** CORS
        is enforced by the browser, not the server; the only difference on the wire is a missing
        `Access-Control-Allow-Origin`. A test written the obvious way - assert the status code - passes
        against a completely closed server, and that is precisely how CORS earns its reputation as the most
        common first-day failure (`api-contract.md` §8 rule 2).

        Every test names its objects with a fresh identifier and deletes them, so runs do not collide and
        nothing accumulates in the volume.
"""

from uuid import uuid4

import pytest
from aiohttp import ClientSession

from app.config import settings
from app.constants.storage import DEFAULT_CONTENT_TYPE, Bucket
from app.lib.exceptions import InvalidRequestError, ResourceNotFoundError
from app.lib.storage import (
    CrossOriginMechanism,
    bucket_name,
    check_cross_origin_access,
    check_health,
    configure_cross_origin_access,
    delete_object,
    ensure_buckets,
    get_object,
    object_exists,
    presigned_download_url,
    presigned_upload,
    put_object,
)

pytestmark = pytest.mark.integration

SCENE_BYTES = b"II*\x00" + b"not a real geotiff, but it is the same bytes coming back out" * 8


@pytest.fixture
def unique_key() -> str:
    """An object key no other test or previous run uses."""
    return f"tests/{uuid4().hex}.bin"


async def test_storage_is_reachable_with_all_five_buckets() -> None:
    """The precondition for everything else, and the row `aeris doctor` prints.

    `ensure_buckets()` is called first because provisioning is part of what this sub-phase delivers: the
    buckets are created by application code rather than by an `mc` command in an init container, so that the
    same path provisions a local MinIO and a real S3 account.
    """
    await ensure_buckets()
    health = await check_health()

    assert health.is_reachable, f"Storage unreachable: {health.failure_reason}"
    assert health.missing_buckets == ()
    assert len(health.present_buckets) == len(Bucket)
    assert health.failure_reason is None
    assert health.latency_ms is not None


async def test_ensure_buckets_is_idempotent() -> None:
    """It runs on every `aeris doctor` and every Phase 2 startup, so the second run must be a no-op."""
    await ensure_buckets()

    assert await ensure_buckets() == (), "a second call created buckets that already existed"


async def test_a_file_uploaded_through_a_presigned_url_is_readable_back_by_key(unique_key: str) -> None:
    """**The gate.** Upload with no credentials and no SDK, then read the same bytes back by key.

    The PUT goes through plain `aiohttp`, exactly as the browser's `uploadImageryFile` does. Using the S3
    client here would prove the client works, which was never in doubt; what is in doubt is whether a
    presigned URL is usable by something holding no credentials at all.
    """
    await ensure_buckets()
    ticket = await presigned_upload(Bucket.RAW, unique_key, content_type="image/tiff")

    async with ClientSession() as http_session:
        async with http_session.put(
            ticket.upload_url, data=SCENE_BYTES, headers=ticket.required_headers
        ) as response:
            assert response.status == 200, await response.text()

    try:
        assert await object_exists(Bucket.RAW, unique_key) is True
        assert await get_object(Bucket.RAW, unique_key) == SCENE_BYTES
    finally:
        await delete_object(Bucket.RAW, unique_key)

    assert await object_exists(Bucket.RAW, unique_key) is False


async def test_the_signed_content_type_is_a_commitment_not_a_hint(unique_key: str) -> None:
    """Sending a different `Content-Type` than the ticket names fails the upload.

    Worth pinning because the failure is so unhelpful in a browser: the content type is part of what was
    signed, so a mismatch is a *signature* error, and it arrives as an opaque 403 at the end of a long
    upload rather than as anything naming the header. `required_headers` exists so the caller never has to
    know this.
    """
    await ensure_buckets()
    ticket = await presigned_upload(Bucket.RAW, unique_key, content_type="image/tiff")

    assert ticket.required_headers == {"Content-Type": "image/tiff"}

    async with ClientSession() as http_session:
        async with http_session.put(
            ticket.upload_url, data=SCENE_BYTES, headers={"Content-Type": "text/plain"}
        ) as response:
            assert response.status == 403

    assert await object_exists(Bucket.RAW, unique_key) is False


async def test_an_uningestible_upload_is_refused_before_the_url_is_issued(unique_key: str) -> None:
    """A scene the pipeline cannot read is rejected at ticket time, not after the upload.

    The alternative is the expensive ordering: issue the URL, let the operator push several gigabytes, accept
    it, and fail at S2 with a GDAL message about an unrecognised driver. The refusal costs one round trip and
    names the formats that would have worked.

    Only `raw` is guarded. The other buckets hold artefacts this backend wrote, so their content types are
    not a caller's to get wrong.
    """
    with pytest.raises(InvalidRequestError) as raised:
        await presigned_upload(Bucket.RAW, unique_key, content_type="text/html")

    assert raised.value.status == 400
    assert raised.value.details is not None
    assert "image/tiff" in raised.value.details["accepted"]

    # The same content type is fine for a bucket whose contents are ours.
    ticket = await presigned_upload(Bucket.REPORTS, unique_key, content_type="text/html")
    assert ticket.required_headers == {"Content-Type": "text/html"}


async def test_a_presigned_download_serves_the_bytes_without_credentials(unique_key: str) -> None:
    """The read half. A figure URL handed to a browser must work with no auth attached to it."""
    await ensure_buckets()
    await put_object(Bucket.FIGURES, unique_key, SCENE_BYTES, content_type=DEFAULT_CONTENT_TYPE)

    try:
        url = await presigned_download_url(Bucket.FIGURES, unique_key)
        async with ClientSession() as http_session:
            async with http_session.get(url) as response:
                assert response.status == 200
                assert await response.read() == SCENE_BYTES
    finally:
        await delete_object(Bucket.FIGURES, unique_key)


async def test_presigned_urls_are_signed_against_the_browser_facing_endpoint(unique_key: str) -> None:
    """The URL must address the host a *browser* can reach, not the one this process uses.

    They are the same today. They stop being the same the moment the backend moves into the compose network,
    and the failure then is not obvious: the signature covers the host, so a URL signed for `http://minio:9000`
    cannot be repaired by substituting `localhost` into it afterwards. It has to be signed correctly, which
    is what `storage_signing_endpoint` is for.
    """
    await ensure_buckets()
    url = await presigned_download_url(Bucket.FIGURES, unique_key)

    assert url.startswith(settings.storage_signing_endpoint)


async def test_the_browser_origin_is_allowed_to_read_from_storage() -> None:
    """**The other half of the gate.** A preflight from the configured origin comes back allowed.

    Without this header the browser fetches a figure or a tile, receives it, and refuses to hand it to the
    page - the globe renders nothing and no error appears anywhere.
    """
    access = await check_cross_origin_access()

    assert access.is_allowed, access.failure_reason
    assert access.origin == settings.storage_browser_origin_header
    assert access.allowed_origin_header in {settings.storage_browser_origin_header, "*"}
    assert access.allowed_methods_header is not None


async def test_an_unknown_origin_is_refused_and_the_status_code_does_not_say_so() -> None:
    """The counter-intuitive half, asserted so nobody rewrites the check above against a status code.

    A disallowed origin still receives HTTP 200 and, on a GET, the object's bytes. CORS is enforced by the
    browser; the server's only signal is the *absence* of `Access-Control-Allow-Origin`. So this test asserts
    both halves: our probe says refused, and the raw HTTP status says nothing at all.
    """
    access = await check_cross_origin_access("https://evil.example.invalid")

    assert access.is_allowed is False
    assert access.allowed_origin_header is None
    assert access.failure_reason is not None

    # The same preflight, unfiltered. A test that asserted on this would have passed against a closed server.
    probe_url = f"{settings.storage_signing_endpoint}/{await bucket_name(Bucket.FIGURES)}/"
    async with ClientSession() as http_session:
        async with http_session.options(
            probe_url,
            headers={
                "Origin": "https://evil.example.invalid",
                "Access-Control-Request-Method": "GET",
            },
        ) as response:
            assert response.status < 400, (
                "MinIO rejected the preflight outright. That would make the status code a usable CORS "
                "signal, and this test exists because it is not one - re-check the claim before relying on it."
            )
            assert "Access-Control-Allow-Origin" not in response.headers


async def test_the_provider_reports_which_cors_mechanism_it_uses() -> None:
    """MinIO answers `NotImplemented` to `PutBucketCors`, and that is handled rather than fatal.

    Asserted as `SERVER_LEVEL` rather than "either value" on purpose. Two useful things then happen: on this
    provider a regression that turned `NotImplemented` back into an exception fails here, and if MinIO ever
    *does* implement the API this test fails and says the compose-level workaround can go.
    """
    await ensure_buckets()

    assert await configure_cross_origin_access() is CrossOriginMechanism.SERVER_LEVEL


async def test_a_missing_object_raises_rather_than_reading_as_empty(unique_key: str) -> None:
    """Storage raises where the Redis cache degrades, and the asymmetry is deliberate.

    A cache miss costs a recomputation. A missing artefact is a broken provenance chain: a caller that
    treated absence as empty bytes would render a blank figure and attach it to a claim, which is a
    confidently wrong answer - the failure this whole product is built not to produce.
    """
    await ensure_buckets()

    with pytest.raises(ResourceNotFoundError) as raised:
        await get_object(Bucket.ARTEFACTS, unique_key)

    assert raised.value.status == 404
    assert raised.value.details is not None
    assert raised.value.details["key"] == unique_key


async def test_bucket_names_carry_the_configured_prefix() -> None:
    """One S3 account may host several deployments, so the prefix is what keeps them apart."""
    assert await bucket_name(Bucket.FIGURES) == f"{settings.storage_bucket_prefix}-figures"
    assert await bucket_name(Bucket.COG) == f"{settings.storage_bucket_prefix}-cog"


# --- Recorded run ----------------------------------------------------------------------------------------
#
# $ uv run pytest tests/integration/test_storage_round_trip.py -q               2026-08-31
#
#   ............                                                             [100%]
#   12 passed in 3.31s
#
# Against MinIO RELEASE.2025-09-07T16-13-09Z in the `aeris-minio` container, five buckets provisioned by
# `ensure_buckets()`, MINIO_API_CORS_ALLOW_ORIGIN=http://localhost:3000.
#
# Checked by mutation - each claim broken, and the intended test confirmed to catch it:
#
#   CORS judged by status code, not the header  -> test_an_unknown_origin_is_refused_...        FAILED
#   `get_object` returns b"" for a missing key  -> test_a_missing_object_raises_...             FAILED
#   `NotImplemented` treated as a hard failure  -> test_the_provider_reports_which_cors_...     FAILED
#
# Each mutation was reverted and the file byte-compared against its pre-mutation copy.
#
# --- The gate, in a real browser -------------------------------------------------------------------------
#
# These tests assert on response headers, which is correct but is not the same as a browser succeeding. So a
# page was served at the configured origin and asked to load a real PNG from the `figures` bucket three
# ways. From http://localhost:3000, the allowed origin:
#
#   { "origin": "http://localhost:3000",
#     "plainImage":     "loaded (64x64)",
#     "corsFetch":      "ok (185 bytes, image/png)",
#     "canvasReadback": "ok - read pixel rgba(16,185,129,255)" }
#
# and from http://127.0.0.1:3000, which is a *different origin* to a browser and is not allowed:
#
#   { "origin": "http://127.0.0.1:3000",
#     "plainImage":     "loaded (64x64)",          <-- note
#     "corsFetch":      "FAILED: Failed to fetch",
#     "canvasReadback": "FAILED to load with crossOrigin=anonymous" }
#
# The plain <img> loads in BOTH cases. Images are exempt from CORS unless the page reads their pixels back,
# so "the picture shows up" proves nothing - and checking it that way is how a broken configuration ships.
# What actually breaks without CORS is `fetch()` and `crossOrigin="anonymous"` -> canvas -> getImageData,
# which is precisely the path Cesium takes for every tile. That is why the assertions above are written
# against `Access-Control-Allow-Origin` and never against a status code or a rendered image.
