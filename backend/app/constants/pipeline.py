"""Fixed facts about how a run is identified, checkpointed and remembered - the values that are not machine-dependent.

what  : `GraphName`, the memory namespace root, the journal file suffix, and the node-boundary trace
        defaults.
where : Read by `app/services/pipeline/`, `app/services/sessions/` and the CLI renderers. Paths and
        timeouts are **not** here - those vary between machines and live in `config.py` (code-standards.md
        §4). What is here is the vocabulary, which does not.
how   : `GraphName` exists with one member on purpose. Phase 1.10 adds `single_image`, `temporal` and
        `cross_modal`; the probe graph is the throwaway that proves the spine before any of them exist. A
        named set rather than a free string means `aeris run --graph typo` fails at the argument rather
        than at a lookup three layers down, and it is the seam 1.10 extends instead of redesigns.

        `MEMORY_NAMESPACE_ROOT` is the prefix of every long-term memory key. LangGraph's `BaseStore`
        namespaces are tuples, and a shared prefix means one deployment's memories can be listed, exported
        or deleted as a unit - the same reasoning as `KEY_PREFIX` in `redis_keys.py`, for the same reason:
        a store with no namespace convention cannot be cleaned up without knowing every writer.
"""

from enum import StrEnum
from typing import Final


class GraphName(StrEnum):
    """Every `StateGraph` this backend can run, by the name the CLI accepts."""

    # The two-node graph that exercises checkpointing, streaming, cancellation and the renderers without
    # touching imagery. It is deliberately not deleted when the real graphs land: it stays as the thing to
    # run when the question is "is the spine broken, or is my pipeline broken?".
    PROBE = "probe"


# The first element of every long-term memory namespace: `("aeris", "memory", <scope>, ...)`.
MEMORY_NAMESPACE_ROOT: Final[tuple[str, ...]] = ("aeris", "memory")

# Memories that belong to the operator rather than to one investigation. Phase 1.9 adds investigation-scoped
# namespaces beside this one; 1.0 only has to prove that a namespace is carried, not populate it.
MEMORY_SCOPE_OPERATOR: Final[str] = "operator"

# One JSON object per line, appended as the event is emitted. Not `.json`: a run that is killed halfway
# leaves a readable, replayable journal rather than an unclosed array.
JOURNAL_FILE_SUFFIX: Final[str] = ".jsonl"
