"""Page sizes for cursor pagination. Numbers that will be tuned, so they are not typed into a route signature.

what  : `DEFAULT_PAGE_SIZE`, `MAXIMUM_PAGE_SIZE`.
where : Read by `app/lib/responses.py` (`CursorPageRequest`) and by every paginated query built on it.
how   : Offset pagination is forbidden by `api-contract.md` §1 rule 5 - the catalogue is unbounded and ingest is
        concurrent, so offsets skip and duplicate rows while the operator scrolls.

        `MAXIMUM_PAGE_SIZE` is a clamp, not a suggestion: a client asking for fifty thousand imagery rows gets
        one hundred. The imagery list renders thumbnails, so a page is bounded by what a human can look at
        rather than by what the database can return.
"""

from typing import Final

DEFAULT_PAGE_SIZE: Final[int] = 25
MAXIMUM_PAGE_SIZE: Final[int] = 100
