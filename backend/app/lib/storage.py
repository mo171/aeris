"""Object storage over the S3 API: the one client, the presigned URLs a browser uses, and the CORS check that proves the browser can actually read what we wrote.

what  : `get_client()`, `ensure_buckets()`, byte-level `put_object`/`get_object`/`delete_object`/`object_exists`,
        `presigned_upload()` and `presigned_download_url()`, `check_health()` and `check_cross_origin_access()`
        for `aeris doctor`, and `close_client()` for shutdown.
where : The only module that talks to object storage. Shaped like `app/lib/database.py` and
        `app/lib/redis.py` - lazy singleton, never-raising health probe, `require_healthy_*` gate - so the
        third dependency is the same shape as the first two rather than a third thing to learn.
how   : **Written against the S3 API, never against MinIO.** MinIO is what runs locally; S3, R2 or Supabase
        Storage is what runs deployed, and the only line that knows the difference is
        `storage_addressing_style` in `config.py`. That is the whole reason for using `aioboto3` here rather
        than MinIO's own SDK, which would have tied Phase 1 to a local development choice.

        **Storage failures raise.** Unlike the Redis cache, which degrades to a miss, a missing object is a
        broken provenance chain: a claim that cannot resolve to the pixels it was read from is not a slower
        answer, it is an unsupportable one. Missing objects raise `ResourceNotFoundError`; an unreachable
        provider raises `UpstreamUnavailableError`.

        **The two CORS facts this file exists to encode.** They are the difference between a globe that draws
        and a globe that silently renders nothing (`api-contract.md` §8 rule 2):

        1. **MinIO does not implement `PutBucketCors`** - measured, not assumed: it answers `NotImplemented`,
           and `GetBucketCors` answers `NoSuchCORSConfiguration`. It is configured server-wide instead, with
           `MINIO_API_CORS_ALLOW_ORIGIN`, which `docker-compose.yml` sets. Real S3 *does* implement the API
           and starts with **no** CORS at all, so `configure_cross_origin_access()` applies the rules where
           they are supported and reports the server-level requirement where they are not. Neither provider
           is the special case.
        2. **A CORS failure is invisible to anything but a browser.** A request from a disallowed origin
           still returns `200` with the object's bytes; the only difference is a missing
           `Access-Control-Allow-Origin` header, and it is the *browser* that refuses to hand those bytes to
           the page. So `check_cross_origin_access()` asserts on the header and never on the status code - a
           check written the obvious way would pass against a completely closed server.
"""

import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from time import perf_counter
from typing import Any

import aioboto3
from aiohttp import ClientError as HttpClientError
from aiohttp import ClientSession, ClientTimeout
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.config import settings
from app.constants.storage import (
    BROWSER_ALLOWED_METHODS,
    BROWSER_EXPOSED_HEADERS,
    BROWSER_FACING_BUCKETS,
    BROWSER_PREFLIGHT_CACHE_SECONDS,
    DEFAULT_CONTENT_TYPE,
    INGESTIBLE_CONTENT_TYPES,
    Bucket,
)
from app.lib.exceptions import (
    InvalidRequestError,
    ResourceNotFoundError,
    UpstreamUnavailableError,
)

logger = logging.getLogger(__name__)

# aioboto3 hands out clients as async context managers, so the singleton is a stack holding one open rather
# than a bare object. Same intent as the engine in `database.py`: one connection pool per process.
_exit_stack: AsyncExitStack | None = None
_client: Any = None
_signing_client: Any = None

# The S3 error codes that mean "this object or bucket is not here", as opposed to "storage is broken".
# `404` appears for HeadObject, which returns a bare status rather than a named code.
_NOT_FOUND_CODES = frozenset({"NoSuchKey", "NoSuchBucket", "NotFound", "404"})


class CrossOriginMechanism(StrEnum):
    """How CORS is configured on the provider in front of us. Reported by `aeris doctor`."""

    # Real S3: the rules were applied per bucket through `PutBucketCors`, and we can read them back.
    PER_BUCKET = "per-bucket"
    # MinIO: `PutBucketCors` answers NotImplemented. The server is configured with a single allowed origin
    # through `MINIO_API_CORS_ALLOW_ORIGIN`, which is docker-compose.yml's job rather than ours.
    SERVER_LEVEL = "server-level"


@dataclass(frozen=True, slots=True)
class PresignedUpload:
    """One direct-to-storage upload ticket.

    The field names are the frontend's, from `imageryUploadTicketSchema`: `uploadUrl`, `expiresAt`,
    `requiredHeaders`. Phase 2.2 adds a `sceneId` and serialises this straight out - the shape is settled
    here so that the endpoint is wiring rather than design.

    `required_headers` is not advice. The content type is signed *into* the URL, so a browser that sends a
    different one gets a signature mismatch, which surfaces in the console as an opaque 403 long after the
    upload has begun.
    """

    upload_url: str
    expires_at: datetime
    required_headers: dict[str, str]


@dataclass(frozen=True, slots=True)
class StorageHealth:
    """What `aeris doctor` prints for the storage row."""

    is_reachable: bool
    present_buckets: tuple[str, ...]
    missing_buckets: tuple[str, ...]
    latency_ms: float | None
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class CrossOriginAccess:
    """The result of asking storage, as a browser would, whether it may read an object.

    Carries the origin that was tested because "CORS is fine" is meaningless without it - the answer differs
    per origin, and the whole class of failure here is a rule that allows an origin nobody uses.
    """

    origin: str
    is_allowed: bool
    allowed_origin_header: str | None
    allowed_methods_header: str | None
    failure_reason: str | None


async def get_client() -> Any:
    """Return the process-wide S3 client, creating it on first call."""
    global _exit_stack, _client
    if _client is None:
        _exit_stack = AsyncExitStack()
        _client = await _exit_stack.enter_async_context(await _open_client(settings.storage_endpoint))
    return _client


async def _get_signing_client() -> Any:
    """The client presigned URLs are signed with - bound to the browser-facing endpoint.

    Usually the same object as `get_client()`. It is a second client only when the browser reaches storage at
    a different address than this process does, because a presigned URL's signature covers the host: a URL
    signed for `http://minio:9000` cannot be repaired by string-substituting `localhost` into it afterwards.
    Signing performs no I/O, so the extra client costs a few objects and no connections.
    """
    global _signing_client
    if settings.storage_signing_endpoint == settings.storage_endpoint:
        return await get_client()
    if _signing_client is None:
        await get_client()  # ensures the exit stack exists
        assert _exit_stack is not None
        _signing_client = await _exit_stack.enter_async_context(
            await _open_client(settings.storage_signing_endpoint)
        )
    return _signing_client


async def _open_client(endpoint: str) -> Any:
    """Build an S3 client context manager against one endpoint."""
    session = aioboto3.Session(
        aws_access_key_id=settings.storage_access_key.get_secret_value(),
        aws_secret_access_key=settings.storage_secret_key.get_secret_value(),
        region_name=settings.storage_region,
    )
    return session.client(
        "s3",
        endpoint_url=endpoint,
        config=Config(
            # SigV4 explicitly. Botocore picks it for real S3 anyway, but a custom endpoint can fall back to
            # the deprecated SigV2, which MinIO rejects with a signature error that names nothing useful.
            signature_version="s3v4",
            s3={"addressing_style": settings.storage_addressing_style},
            connect_timeout=settings.storage_connect_timeout_seconds,
            read_timeout=settings.storage_read_timeout_seconds,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


async def bucket_name(bucket: Bucket) -> str:
    """`aeris-figures` from `Bucket.FIGURES`. The only place a bucket name is assembled."""
    return f"{settings.storage_bucket_prefix}-{bucket.value}"


# --- Provisioning -----------------------------------------------------------------------------------------


async def ensure_buckets() -> tuple[str, ...]:
    """Create any of the five buckets that do not exist. Returns the ones it created.

    Idempotent, and written in Python rather than as an `mc` command in an init container so that the same
    code provisions a local MinIO and a real S3 account. `BucketAlreadyOwnedByYou` is swallowed because two
    processes starting at once is normal, not an error.
    """
    client = await get_client()
    created: list[str] = []

    for bucket in Bucket:
        name = await bucket_name(bucket)
        try:
            await client.head_bucket(Bucket=name)
        except ClientError as error:
            if _error_code(error) not in _NOT_FOUND_CODES:
                raise _as_upstream_error(error, f"checking bucket {name}") from error
            try:
                await client.create_bucket(Bucket=name)
                created.append(name)
            except ClientError as create_error:
                if _error_code(create_error) not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
                    raise _as_upstream_error(create_error, f"creating bucket {name}") from create_error

    if created:
        logger.info("created storage buckets", extra={"buckets": created})
    return tuple(created)


async def configure_cross_origin_access() -> CrossOriginMechanism:
    """Apply CORS rules to the browser-facing buckets, and report which mechanism the provider uses.

    On S3 this writes the rules and they take effect. On MinIO `PutBucketCors` answers `NotImplemented` -
    verified against RELEASE.2025-09-07 - so nothing is written and CORS comes from the server's
    `MINIO_API_CORS_ALLOW_ORIGIN`, which `docker-compose.yml` sets from the same
    `STORAGE_BROWSER_ORIGIN` this would have used.

    `NotImplemented` is a fact about the provider, not a failure, so it is returned rather than raised.
    Whether the result is actually correct is `check_cross_origin_access()`'s question - and that one asks a
    browser's question instead of the server's.
    """
    client = await get_client()
    rules = {
        "CORSRules": [
            {
                "AllowedOrigins": [settings.storage_browser_origin_header],
                "AllowedMethods": list(BROWSER_ALLOWED_METHODS),
                # The browser's preflight names the headers it intends to send; the upload path sends
                # `Content-Type` and whatever the ticket required, so the list is not knowable here.
                "AllowedHeaders": ["*"],
                "ExposeHeaders": list(BROWSER_EXPOSED_HEADERS),
                "MaxAgeSeconds": BROWSER_PREFLIGHT_CACHE_SECONDS,
            }
        ]
    }

    for bucket in BROWSER_FACING_BUCKETS:
        name = await bucket_name(bucket)
        try:
            await client.put_bucket_cors(Bucket=name, CORSConfiguration=rules)
        except ClientError as error:
            if _error_code(error) == "NotImplemented":
                logger.info(
                    "provider does not implement per-bucket CORS; relying on its server-level setting",
                    extra={"bucket": name, "allowed_origin": settings.storage_browser_origin_header},
                )
                return CrossOriginMechanism.SERVER_LEVEL
            raise _as_upstream_error(error, f"configuring CORS on {name}") from error

    return CrossOriginMechanism.PER_BUCKET


# --- Objects ----------------------------------------------------------------------------------------------


async def put_object(bucket: Bucket, key: str, data: bytes, content_type: str = DEFAULT_CONTENT_TYPE) -> str:
    """Write bytes and return the object's ETag. For anything a pipeline stage produces server-side."""
    client = await get_client()
    name = await bucket_name(bucket)
    try:
        response = await client.put_object(Bucket=name, Key=key, Body=data, ContentType=content_type)
    except ClientError as error:
        raise _as_upstream_error(error, f"writing {name}/{key}") from error
    return str(response["ETag"]).strip('"')


async def get_object(bucket: Bucket, key: str) -> bytes:
    """Read an object's bytes. Raises `ResourceNotFoundError` when the key is not there.

    Raising rather than returning `None` is the §9 rule, and it earns its keep here: a caller that treated a
    missing artefact as an empty one would render a blank figure and attach it to a claim.
    """
    client = await get_client()
    name = await bucket_name(bucket)
    try:
        response = await client.get_object(Bucket=name, Key=key)
        async with response["Body"] as stream:
            return await stream.read()
    except ClientError as error:
        if _error_code(error) in _NOT_FOUND_CODES:
            raise ResourceNotFoundError(
                f"No object at {name}/{key}.", details={"bucket": name, "key": key}
            ) from error
        raise _as_upstream_error(error, f"reading {name}/{key}") from error


async def object_exists(bucket: Bucket, key: str) -> bool:
    """Whether a key is present. A boolean, not an exception, because absence is the question being asked."""
    client = await get_client()
    name = await bucket_name(bucket)
    try:
        await client.head_object(Bucket=name, Key=key)
        return True
    except ClientError as error:
        if _error_code(error) in _NOT_FOUND_CODES:
            return False
        raise _as_upstream_error(error, f"heading {name}/{key}") from error


async def delete_object(bucket: Bucket, key: str) -> None:
    """Remove an object. Deleting a key that is not there is not an error, in S3 or here."""
    client = await get_client()
    name = await bucket_name(bucket)
    try:
        await client.delete_object(Bucket=name, Key=key)
    except ClientError as error:
        raise _as_upstream_error(error, f"deleting {name}/{key}") from error


# --- Presigned URLs ---------------------------------------------------------------------------------------


async def presigned_upload(
    bucket: Bucket,
    key: str,
    content_type: str = DEFAULT_CONTENT_TYPE,
    expiry_seconds: int | None = None,
) -> PresignedUpload:
    """A ticket letting a browser PUT straight at storage, never through this process.

    This is what keeps a multi-gigabyte scene out of the app server's memory and off its event loop
    (`roadmap.md` 2.2). The content type is part of the signature, so it comes back in `required_headers`
    rather than being left to the caller to remember.

    An upload into `raw` is checked against `INGESTIBLE_CONTENT_TYPES` **before the URL is issued**. Refusing
    here costs the operator one immediate error; refusing later costs them the whole upload first, and then
    fails inside rasterio with a message about an unrecognised driver rather than about the file they chose.
    Only `raw` is checked - the other four buckets hold things this backend produced, and their content types
    are ours rather than a caller's.
    """
    if bucket is Bucket.RAW and content_type not in INGESTIBLE_CONTENT_TYPES:
        raise InvalidRequestError(
            f"{content_type!r} is not a format this pipeline can ingest.",
            details={"content_type": content_type, "accepted": sorted(INGESTIBLE_CONTENT_TYPES)},
        )

    signing_client = await _get_signing_client()
    seconds = settings.storage_presigned_put_expiry_seconds if expiry_seconds is None else expiry_seconds
    name = await bucket_name(bucket)

    try:
        url = await signing_client.generate_presigned_url(
            "put_object",
            Params={"Bucket": name, "Key": key, "ContentType": content_type},
            ExpiresIn=seconds,
        )
    except (BotoCoreError, ClientError) as error:
        raise _as_upstream_error(error, f"signing an upload for {name}/{key}") from error

    return PresignedUpload(
        upload_url=url,
        # Timezone-aware, because it crosses the wire as an ISO-8601 timestamp the frontend parses
        # (`isoTimestampSchema`), and a naive one there is an hour wrong twice a year.
        expires_at=datetime.now(UTC) + timedelta(seconds=seconds),
        required_headers={"Content-Type": content_type},
    )


async def presigned_download_url(bucket: Bucket, key: str, expiry_seconds: int | None = None) -> str:
    """A time-limited URL a browser can GET without credentials.

    Used for figures and reports. The URL grants access to whoever holds it until it expires and cannot be
    revoked before then, which is why the default lifetime in `config.py` is an hour rather than a day.
    """
    signing_client = await _get_signing_client()
    seconds = settings.storage_presigned_get_expiry_seconds if expiry_seconds is None else expiry_seconds
    name = await bucket_name(bucket)

    try:
        return str(
            await signing_client.generate_presigned_url(
                "get_object", Params={"Bucket": name, "Key": key}, ExpiresIn=seconds
            )
        )
    except (BotoCoreError, ClientError) as error:
        raise _as_upstream_error(error, f"signing a download for {name}/{key}") from error


# --- Health -----------------------------------------------------------------------------------------------


async def check_health() -> StorageHealth:
    """Probe storage and report which of the five buckets exist. Never raises."""
    started_at = perf_counter()
    try:
        client = await get_client()
        response = await client.list_buckets()
        latency_ms = (perf_counter() - started_at) * 1000
    except Exception as error:
        return StorageHealth(
            is_reachable=False,
            present_buckets=(),
            missing_buckets=(),
            latency_ms=None,
            failure_reason=f"{type(error).__name__}: {error}",
        )

    existing = {entry["Name"] for entry in response.get("Buckets", [])}
    expected = {await bucket_name(bucket) for bucket in Bucket}
    missing = tuple(sorted(expected - existing))

    return StorageHealth(
        is_reachable=True,
        present_buckets=tuple(sorted(expected & existing)),
        missing_buckets=missing,
        latency_ms=round(latency_ms, 2),
        failure_reason=(
            None
            if not missing
            else f"Reachable, but {len(missing)} of {len(expected)} buckets do not exist: "
            f"{', '.join(missing)}. Run `ensure_buckets()`, which `aeris doctor` will do for you."
        ),
    )


async def check_cross_origin_access(origin: str | None = None) -> CrossOriginAccess:
    """Ask storage the question a browser asks: may this origin read from you? Never raises.

    Sends a real preflight `OPTIONS` rather than inspecting configuration, because the configuration is not
    where the answer lives - on MinIO it is a server setting this process cannot read, and on S3 a rule can
    be present and still not match the origin in use.

    **Asserts on the header, never on the status code.** A disallowed origin gets `200` and the object's
    bytes; only the absent `Access-Control-Allow-Origin` stops the browser handing them to the page. A check
    written against the status code passes against a completely closed server, which is the shape of the
    "CORS is the most common first-day failure" bug.
    """
    tested_origin = origin or settings.storage_browser_origin_header
    endpoint = settings.storage_signing_endpoint
    probe_url = f"{endpoint}/{await bucket_name(Bucket.FIGURES)}/"

    try:
        timeout = ClientTimeout(total=settings.storage_connect_timeout_seconds)
        async with ClientSession(timeout=timeout) as http_session:
            async with http_session.options(
                probe_url,
                headers={
                    "Origin": tested_origin,
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "content-type",
                },
            ) as response:
                allowed_origin = response.headers.get("Access-Control-Allow-Origin")
                allowed_methods = response.headers.get("Access-Control-Allow-Methods")
    except (HttpClientError, TimeoutError, OSError) as error:
        return CrossOriginAccess(
            origin=tested_origin,
            is_allowed=False,
            allowed_origin_header=None,
            allowed_methods_header=None,
            failure_reason=f"Could not reach storage to run a preflight: {type(error).__name__}: {error}",
        )

    # A wildcard is a valid allowance and a bad one: paired with credentials a browser rejects it outright,
    # and on its own it lets any page on the internet read the objects. Accepted, and reported.
    is_allowed = allowed_origin in {tested_origin, "*"}

    return CrossOriginAccess(
        origin=tested_origin,
        is_allowed=is_allowed,
        allowed_origin_header=allowed_origin,
        allowed_methods_header=allowed_methods,
        failure_reason=(
            None
            if is_allowed
            else f"Storage did not allow {tested_origin!r}: Access-Control-Allow-Origin was "
            f"{allowed_origin!r}. The browser will fetch the bytes and refuse to hand them to the page, so "
            "figures and tiles render as nothing with no error. Set MINIO_API_CORS_ALLOW_ORIGIN (MinIO) or "
            "the bucket's CORS rules (S3) to this origin."
        ),
    )


async def require_healthy_storage() -> None:
    """Raise `UpstreamUnavailableError` unless storage is reachable with all five buckets present.

    CORS is deliberately *not* checked here. A run writes figures server-side and succeeds whether or not a
    browser could read them; failing the run would turn a display problem into a lost analysis. It is a
    `aeris doctor` row instead, which is where a configuration problem belongs.
    """
    health = await check_health()
    if not health.is_reachable or health.missing_buckets:
        raise UpstreamUnavailableError(
            "Object storage is not available.",
            details={
                "upstream": "storage",
                "missing_buckets": list(health.missing_buckets),
                "reason": health.failure_reason,
            },
        )


async def close_client() -> None:
    """Close the client and its connection pool. Called on CLI exit and, in Phase 2, on shutdown."""
    global _exit_stack, _client, _signing_client
    if _exit_stack is not None:
        await _exit_stack.aclose()
    _exit_stack = None
    _client = None
    _signing_client = None


# --- Error mapping ----------------------------------------------------------------------------------------


def _error_code(error: ClientError) -> str:
    """The S3 error code from a botocore exception.

    One of the two sync functions in this module, and it is sync for the reason `code-standards.md` §7 names:
    it maps fields already in memory and is called from `except` blocks, where an `await` would be a
    liability. It performs no I/O and there is no version of it that could.
    """
    response = getattr(error, "response", {}) or {}
    return str(response.get("Error", {}).get("Code", ""))


def _as_upstream_error(error: Exception, while_doing: str) -> UpstreamUnavailableError:
    """Turn a botocore failure into the project's one retryable error, naming what we were attempting.

    Returned rather than raised, so call sites read `raise _as_upstream_error(...) from error`: the `raise`
    and the `from` both stay visible where control actually leaves, instead of being hidden in a helper.

    The second of this module's two sync functions, for the same `code-standards.md` §7 reason as
    `_error_code` above - it maps values already in memory and is only ever called from an `except` block,
    where an `await` would be a liability.
    """
    code = _error_code(error) if isinstance(error, ClientError) else type(error).__name__
    return UpstreamUnavailableError(
        f"Object storage failed while {while_doing}.",
        details={"upstream": "storage", "operation": while_doing, "code": code, "reason": str(error)},
    )
