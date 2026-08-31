"""Declares the one object every pipeline node reads from and writes to, and how concurrent writes to it merge.

what  : `PipelineState`, the `TypedDict` LangGraph carries between nodes, and the reducers that decide what
        happens when two nodes update the same key.
where : The state schema of every graph in `services/pipeline/graphs/`. Nodes receive it and return a
        partial update of it; nothing else constructs one.
how   : **A `TypedDict`, not a Pydantic model.** LangGraph reads the annotations to build its channels, and
        a node returns a *partial* update - `{"answer_tokens": ["a"]}` - which a Pydantic model would
        reject for the fields it did not mention. `total=False` makes that partiality part of the type
        rather than something the reader has to know.

        **Reducers are the part worth reading carefully.** By default a key is last-write-wins, which is
        correct for a value one node owns and silently wrong for a list several nodes append to: two
        parallel branches each returning `{"trace_step_ids": [...]}` would leave only the one that
        happened to finish last, and the trace would be missing a stage with nothing to indicate it. The
        cross-modal graph (1.11) runs exactly that shape - two per-sensor branches converging - so the
        accumulating keys are annotated with `operator.add` now, while the graph that would expose the bug
        is still two phases away.

        **What is deliberately not here.** No service objects, no open file handles, no model instances,
        no database session. State is checkpointed after every node, so anything in it must survive being
        serialised and read back by a different process (`architecture-context.md`). A node reaches its
        dependencies through the modules that own them; the state carries identifiers and values.

        Phase 1.0 declares the keys the spine itself needs. Scene ids, arrays, evidence and claims arrive
        with the sub-phases that produce them - an unread key here is a claim about the pipeline that
        nothing verifies, the same rule `config.py` applies to settings.
"""

from operator import add
from typing import Annotated, NotRequired, TypedDict


class PipelineState(TypedDict, total=False):
    """The state one run carries from its first node to its last."""

    # --- Set once when the run starts, read by every node. -----------------------------------------------

    run_id: str

    # What the operator actually asked, unmodified. Kept verbatim because the report quotes it and because
    # a run that produced a surprising answer is diagnosed by re-reading the question first.
    query: str

    # One of `Intent`, stored as its **plain string value** rather than as the enum member. A node that
    # needs the enum writes `Intent(state["intent"])`.
    #
    # This is not fussiness. State is checkpointed after every node, and LangGraph serialises whatever it
    # is given: handing it an `Intent` writes the string `app.constants.intents.Intent` into the
    # checkpoint, so the persisted run now depends on our module layout. Rename that module and every
    # in-flight run becomes unresumable - and LangGraph itself warns on the way back in
    # ("Deserializing unregistered type ... will be blocked in a future version"), which is how this was
    # found rather than discovered later against a real pipeline.
    #
    # **The rule this stands for: a checkpoint holds data, never Python objects.** It applies to every key
    # added here from now on.
    #
    # Phase 1.8 replaces the operator's choice with a classifier's. It is in the state rather than
    # recomputed per node because routing reads it and the trace records it, and two derivations of the
    # same intent would eventually disagree.
    intent: str

    # --- Accumulated as the run proceeds. ----------------------------------------------------------------

    # The trace step ids emitted so far, in order. `add` rather than last-write-wins: parallel branches
    # each append, and the default reducer would keep only one branch's steps.
    trace_step_ids: Annotated[list[str], add]

    # The written answer, in the word-sized chunks that were streamed. Joined for the report; kept as
    # chunks so a replayed journal reproduces the same stream the operator saw.
    answer_tokens: Annotated[list[str], add]

    # --- Terminal. Set by at most one node. --------------------------------------------------------------

    # `None` means AERIS declines to state one, and is different from `0.0`, which claims no confidence.
    # `api-contract.md` §1 rule 2 - the frontend renders the two very differently.
    confidence: NotRequired[float | None]
