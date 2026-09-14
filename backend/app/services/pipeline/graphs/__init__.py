"""Selects a graph by name, so the CLI validates the choice at its argument rather than three layers down.

what  : `GRAPH_BUILDERS`, mapping `GraphName` to the function that builds that graph.
where : Read by `cli/run.py` and `services/pipeline/runner.py`. 1.10 added `single-image` and `temporal`;
        1.11 adds `cross-modal`.
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
from app.services.pipeline.graphs.cross_modal import build_cross_modal_graph
from app.services.pipeline.graphs.probe import build_probe_graph
from app.services.pipeline.graphs.single_image import build_single_image_graph
from app.services.pipeline.graphs.temporal import build_temporal_graph

GRAPH_BUILDERS: Final[dict[GraphName, Callable[[], StateGraph]]] = {
    GraphName.PROBE: build_probe_graph,
    GraphName.SINGLE_IMAGE: build_single_image_graph,
    GraphName.TEMPORAL: build_temporal_graph,
    GraphName.CROSS_MODAL: build_cross_modal_graph,
}
