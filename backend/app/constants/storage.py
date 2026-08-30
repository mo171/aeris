"""The five buckets AERIS writes to, and which of them a browser reads directly - which is the only reason CORS matters.

what  : `Bucket` (the five logical roles), `BROWSER_FACING_BUCKETS`, the CORS rule this project needs, and
        the small content-type vocabulary the presigned-upload path validates against.
where : Read by `app/lib/storage.py`, which is the only module that talks to object storage, and later by
        `services/rendering/figures.py` and the ingest pipeline when they choose where to put something.
how   : A bucket here is a **role**, not a name. The name is `{storage_bucket_prefix}-{role}` and the prefix
        is configuration (`code-standards.md` §4), so one S3 account can host several deployments; the set of
        roles is a fixed vocabulary and lives here. Five settings that had to be kept in step with a five-
        member enum would be the same decision written twice.

        The split that actually matters is `BROWSER_FACING_BUCKETS`. Two of the five are fetched by the
        browser directly - `figures` as `<img>` and into a canvas, `cog` as tiles onto Cesium's WebGL context
        - and those are the ones where a missing `Access-Control-Allow-Origin` makes the interface render
        nothing at all, with no error anywhere (`api-contract.md` §8 rule 2). The other three are only ever
        read server-side. Naming the distinction here means the CORS configuration is derived from it rather
        than from someone remembering which buckets were which.

        There are deliberately **no object-key builders here.** What a scene's key looks like is Phase 1.2's
        decision and nothing has made it yet; inventing a layout now would be a claim about the system that
        no code verifies.
"""

from enum import StrEnum
from typing import Final


class Bucket(StrEnum):
    """The five storage roles. The value is the suffix; the full name comes from `config.storage_bucket_prefix`."""

    # Exactly what was uploaded, never modified. The input side of the provenance chain: every claim traces
    # back to bytes here, so nothing in this bucket is ever rewritten in place.
    RAW = "raw"
    # Cloud-Optimised GeoTIFFs produced from `raw` (Phase 1.2). Read by TiTiler over HTTP range requests,
    # which is why it is browser-facing - the tiles Cesium draws are served from these.
    COG = "cog"
    # Pipeline intermediates a trace step points at: cloud masks, registration residuals, index arrays.
    # Server-side only; the interface reaches them through a trace step, never by URL.
    ARTEFACTS = "artefacts"
    # Rendered figures (Phase 1.2.1, `api-contract.md` §6). Loaded by the browser as images.
    FIGURES = "figures"
    # Generated reports, exported as JSON and GeoJSON.
    REPORTS = "reports"


# The buckets a browser fetches directly. CORS is configured for exactly these, and for nothing else - an
# allowance granted to a bucket no browser reads is a permission with no purpose.
BROWSER_FACING_BUCKETS: Final[frozenset[Bucket]] = frozenset({Bucket.COG, Bucket.FIGURES})

# The methods a browser needs. `PUT` is here for the direct-to-storage upload of `api-contract.md` §2 - the
# browser PUTs a multi-gigabyte scene straight at storage, so the preflight has to allow it. `HEAD` is what
# a range-reading tiler issues before it reads.
BROWSER_ALLOWED_METHODS: Final[tuple[str, ...]] = ("GET", "PUT", "HEAD")

# `ETag` is the one response header a browser needs to read back: the upload path uses it to confirm the
# object it just PUT is the object it meant to. Without an explicit expose-list a browser can read almost
# none of the response headers, whatever the server sent.
BROWSER_EXPOSED_HEADERS: Final[tuple[str, ...]] = ("ETag", "Content-Length", "Content-Type")

# How long a browser may cache a preflight result. Ten minutes: long enough that a multipart upload does not
# re-preflight every part, short enough that a corrected CORS rule takes effect while someone is still
# looking at the tab.
BROWSER_PREFLIGHT_CACHE_SECONDS: Final[int] = 600

# What a presigned upload is allowed to declare. The content type is signed into the URL, so it is a
# commitment rather than a hint: the PUT fails unless the browser sends exactly this. Kept small on purpose -
# these are the formats Phase 1.2 can actually ingest, and a scene arriving as something else should be
# refused when the ticket is issued, not four stages later inside rasterio.
INGESTIBLE_CONTENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "image/tiff",
        "application/octet-stream",
        "application/zip",
        "application/x-netcdf",
    }
)

# The fallback when a caller does not know. S3 defaults to this too; naming it means the default is a
# decision rather than an accident.
DEFAULT_CONTENT_TYPE: Final[str] = "application/octet-stream"
