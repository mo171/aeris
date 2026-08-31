"""Selects a graph by name, so the CLI validates the choice at its argument rather than three layers down.

what  : `GRAPH_BUILDERS`, mapping `GraphName` to the function that builds that graph.
where : Read by `cli/run.py`. Phase 1.10 adds `single_image`, `temporal` and `cross_modal` entries.
how   : A mapping rather than an `if` chain, and keyed by the enum rather than by a string, so adding a
        graph is one line here and no change at the call site. `folder-archtecture.md` puts routing
        *between stages* in a `StateGraph`; this is the level above - which graph runs at all - and it is a
        lookup because the deterministic-routing principle (PDF p.24) applies here too: a model may choose
        an intent, a table chooses the graph.
"""

from collections.abc import Callable
from typing import Final

from langgraph.graph import StateGraph

from app.constants.pipeline import GraphName
from app.services.pipeline.graphs.probe import build_probe_graph

GRAPH_BUILDERS: Final[dict[GraphName, Callable[[], StateGraph]]] = {
    GraphName.PROBE: build_probe_graph,
}
