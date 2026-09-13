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
from typing import Annotated, Any, NotRequired, TypedDict


def unique_by_path(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reducer for `input_files`: every stage that reads a file records it, and a file read by two
    stages (the red band, by S12 for an index and by S13 for a picture) is recorded once."""
    merged = list(left)
    known = {record.get("path") for record in merged}
    for record in right:
        if record.get("path") not in known:
            merged.append(record)
            known.add(record.get("path"))
    return merged


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
    # `vlm` or `template`: which generator phrased the claims (S16), and whether the S14 reading was spoken.
    answer_source: str
    reading_spoken: bool

    # --- Terminal. Set by at most one node. --------------------------------------------------------------

    # `None` means AERIS declines to state one, and is different from `0.0`, which claims no confidence.
    # `api-contract.md` §1 rule 2 - the frontend renders the two very differently.
    confidence: NotRequired[float | None]


class MeasurementState(TypedDict):
    """What S15 measured, as the numbers a claim will carry. Keys are the wire's names (camelCase), because
    1.5 lifts this dictionary into claim metrics and a rename across that boundary is the bug
    `code-standards.md` §3 forbids."""

    # `None` over a picture with no grid and no declared pixel size: pixels were counted, ground was not.
    areaHectares: float | None
    observedHectares: float | None
    coverageFraction: float
    pixelCount: int
    regionCount: int
    regionDensityPerSquareKilometre: float
    largestRegionPixels: int
    equalAreaCrs: str


class IndexQueryState(PipelineState, total=False):
    """`PipelineState` plus what an index query carries between S7, S12, S15, S16, S18 and S19.

    Every value is data: paths and object keys stand in for arrays, which are read back through
    `services/evidence/artefacts.py`. That is what makes a resumed S15 see the same index S12 wrote.
    Layers, evidence and claims are carried in their **wire form** - the camelCase dictionaries
    `serialise_event` produces - because S16 reads a claim's text, S19 writes them into the evidence
    graph unchanged, and a checkpoint that held the Pydantic objects would depend on our module layout.
    """

    # Set by the caller.
    scene_directory: str
    scene_id: str
    # A `ProcessingLevel` value, or `None` to trust what the scene path says. A human's statement, never a
    # guess (§8 rule 5).
    declared_level: str | None
    # A `SpectralIndex` value and the target range resolved from the question. `None` bounds mean a map
    # with no mask was asked for.
    index: str
    target_lower: float | None
    target_upper: float | None
    target_label: str
    target_phrase: str

    # S7. `None` paths mean no mask source was available, which the trace states and S12 records.
    cloud_mask_path: str | None
    cloud_mask_object_key: str | None
    cloud_mask_storage_uri: str | None
    obscured_fraction: float | None

    # S12.
    index_path: str
    index_object_key: str
    index_storage_uri: str
    index_band_ids: list[str]
    index_mask_applied: bool
    index_unphysical_fraction: float
    index_figure_id: str
    # The tile layer over the index artefact - what the S12 trace step's `artefactLayerId` names.
    index_layer_id: str
    # `InputFileRecord`s in wire form: every file a stage read, with its hash (PDF §21.2). Accumulated by
    # the stages that read - S7 the classification layer, S12 the index bands, S13/S14 the picture's
    # bands or file - and never by a stage that only looked at a header.
    input_files: Annotated[list[dict[str, Any]], unique_by_path]

    # S15.
    mask_path: str | None
    mask_object_key: str | None
    mask_storage_uri: str | None
    # The raster-mask layer over the mask artefact; the polygon layer is what the trace step names.
    mask_layer_id: str | None
    measurement: MeasurementState | None
    band_fractions: dict[str, float]
    composite_figure_id: str | None
    mask_figure_id: str | None

    # S14. The model's reading of the evidence figure, labelled as its own; `None` when skipped.
    reading_text: str | None
    reading_prompt: str | None
    reading_figure_id: str | None
    reading_confidence: float | None

    # --- Accumulated across stages, in wire form. `add`, because S12 and S15 each contribute. -------------
    layers: Annotated[list[dict[str, Any]], add]
    evidence_items: Annotated[list[dict[str, Any]], add]
    claims: Annotated[list[dict[str, Any]], add]
    # `ModelRecord`s: which engine ran at which stage and what confidence it stated, for S18 and S19.
    stage_models: Annotated[list[dict[str, Any]], add]

    # S18 and S19.
    confidence_aggregation_rule: str
    provenance_path: str
    evidence_graph_path: str


class AnalysisState(IndexQueryState, total=False):
    """`IndexQueryState` plus what the 1.10 graphs carry: what was handed in (S1), and what the detector,
    the segmenter and the change model produced (S13) for S15 to bind to ground.

    The index-query keys are inherited unchanged - `scene_directory`, `scene_id`, `declared_level`, the
    target - because the single-image graph *is* the index-query graph when the intent is an index, and
    one state means one set of nodes. Every key below is read by a node or by S19; the rule from the
    header holds: data only, wire form for anything a record copies.
    """

    # --- Set by the caller. --------------------------------------------------------------------------------
    # The operator's declared pixel size for a picture with no grid, metres; `None` means not declared.
    declared_resolution_metres: float | None
    # Whether the primary input is radar (a picture cannot say so itself).
    is_sar: bool
    # The earlier date of a pair (temporal graph): a scene directory or an image file, and its flags.
    reference_directory: str
    reference_scene_id: str
    reference_is_sar: bool
    # The operator's word that the pair is co-registered (a benchmark its authors aligned): S9 measures
    # and records regardless, and admits the pair on the declaration when the measurement cannot.
    declared_registered: bool
    # The specialist the router chose (a `ModelId` value): GROUND goes to the detector for a class it
    # knows and to the VLM for a phrase it does not, and the graph's edge reads this to tell them apart.
    tool: str | None
    # What the question asked for, from the router's entities: the detector classes, and whether a
    # location was wanted (S15 then states where the best-scoring one is).
    objects: list[str]
    wants_location: bool
    # The land-cover class names the question resolved to (SEGMENT); empty means every class.
    classes: list[str]

    # --- S1. `AnalysisInput.to_wire()` per input, primary first; the primary's grid facts for S13/S15. ------
    input_records: list[dict[str, Any]]
    georeferenced: bool
    crs: str | None
    transform: list[float]
    resolution_metres: float | None
    resolution_declared: bool
    # `InputKind` value of the primary input: a scene directory runs S7, a picture does not.
    input_kind: str
    modality: str

    # --- S7 over the reference date (temporal graph); the primary date uses the inherited keys. -------------
    reference_cloud_mask_path: str | None
    reference_cloud_mask_object_key: str | None
    reference_obscured_fraction: float | None

    # --- S13 detection. Boxes in wire form: class name, score, four pixel corners. ---------------------------
    detections: list[dict[str, Any]]
    detections_path: str
    detections_object_key: str
    detections_storage_uri: str
    detection_figure_id: str | None
    detection_layer_id: str | None
    detection_counts: dict[str, int]
    # Boxes S15 left out of the claims because their class cannot span enough pixels at this resolution.
    detections_below_resolution: dict[str, int]
    detection_score_threshold: float
    frame_observed_fraction: float
    frame_figure_id: str | None

    # --- S13 segmentation. The class map and the model's per-pixel confidence, both retained. ----------------
    class_map_path: str
    class_map_object_key: str
    class_map_storage_uri: str
    class_confidence_path: str
    class_confidence_object_key: str
    class_confidence_storage_uri: str
    class_names: list[str]
    # Share of observed pixels per class name, and the mean confidence per class.
    class_fractions: dict[str, float]
    class_mean_confidence: dict[str, float]
    class_confidence_layer_id: str | None
    class_confidence_figure_id: str | None
    segmentation_confidence: float | None

    # --- S9 (temporal). The co-registration measurement in wire form, and whether it admitted the pair. ------
    registration: dict[str, Any]

    # --- S13 change. -----------------------------------------------------------------------------------------
    change_probability_path: str
    change_probability_object_key: str
    change_probability_storage_uri: str
    change_mask_path: str
    change_mask_object_key: str
    change_mask_storage_uri: str
    change_threshold: float
    change_confidence: float | None
    change_model_id: str
    change_model_version: str
    changed_fraction: float
    change_probability_figure_id: str | None
    comparison_figure_id: str | None
    change_layer_id: str | None

    # --- S15, any branch: which figure the run stands behind, for S14 to read and the record to name. --------
    primary_figure_id: str | None
    # Artefacts a stage retained beyond the named keys above - one mask per land-cover class, say - as
    # `ArtefactRecord`s in wire form, for S19. `add`, because a stage may retain several.
    artefact_records: Annotated[list[dict[str, Any]], add]
    # Figures in the order they were drawn, for S19; every renderer's id lands here.
    figure_ids: Annotated[list[str], add]
