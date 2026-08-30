"""Where the vendored frontend contracts live, and which backend vocabulary each one is the authority for.

what  : `CONTRACT_SCHEMAS_FILE`, and three maps - `SHARED_VOCABULARIES` (a backend enum the frontend also
        defines), `BACKEND_ONLY_VOCABULARIES` (ours alone, with the reason), and
        `FRONTEND_ONLY_VOCABULARIES` (theirs alone, with the phase that will meet it).
where : Read by `tests/contracts/`. Phase 2 will read it too, when a route serialises a payload that has to
        satisfy one of these schemas.
how   : `api-contract.md` §0 makes the frontend's Zod schemas authoritative and §7 names four vocabularies
        the backend **may not invent**. That is a rule no reviewer can enforce by reading - `changeformer`
        against `mdl_changeformer` looks fine in both files and only fails when someone tries to join them.
        These maps make it mechanical.

        **Every backend `StrEnum` appears in exactly one of the first two maps, and a test enforces that.**
        The point is not the pairing; it is that adding an enum forces a decision. Silence is the failure
        mode here - a vocabulary nobody classified is one nobody checked.

        `FRONTEND_ONLY_VOCABULARIES` is the same rule pointed the other way, and it is more useful than it
        looks: it is a list of contracts the frontend has already published that the backend has not met yet.
        Read down it and you are reading what Phase 1 still owes.

        The pairings below were **discovered by comparing value sets, not asserted by hand** - every entry
        was matched exactly before it was written here.
"""

from pathlib import Path
from typing import Final

# `app/constants/contracts.py` -> `app/constants` -> `app` -> `backend`. Resolved from `__file__` rather than
# the working directory so a test finds it whatever it was launched from. Not in `config.py`: this is a fixed
# fact about the repository's layout, not something that varies between machines, and `constants/` must not
# import `config` (`folder-archtecture.md` - the dependency runs the other way).
CONTRACTS_DIRECTORY: Final[Path] = Path(__file__).resolve().parent.parent.parent / "bcontext" / "contracts"
CONTRACT_SCHEMAS_FILE: Final[Path] = CONTRACTS_DIRECTORY / "schemas.json"

# Backend enum (`module.ClassName` under `app/constants/`) -> the frontend schema that defines it.
# The value is `(source module as it appears in schemas.json, exported schema name)`.
#
# Two backend enums map to *two* frontend schemas each, and that is the frontend's duplication rather than
# an error here: `SceneModality` is `acquisitionModalitySchema` in the investigation feature and
# `sensorModalitySchema` in mission command; `TraceStepState` is `traceStepStateSchema` on the analysis
# stream and `executionStepStateSchema` on the assistant stream. Both pairs are checked, so if the frontend
# ever lets the two drift apart the backend finds out.
SHARED_VOCABULARIES: Final[dict[str, tuple[str, str]]] = {
    "evidence.ClaimKind": ("features/investigation/schemas/evidence.schema.ts", "claimKindSchema"),
    "evidence.EvidenceKind": ("features/investigation/schemas/evidence.schema.ts", "evidenceKindSchema"),
    "evidence.MetricDirection": ("features/investigation/schemas/evidence.schema.ts", "metricDirectionSchema"),
    "intents.Intent": ("features/investigation/schemas/analysis.schema.ts", "analysisIntentSchema"),
    "investigations.WorkspaceMode": (
        "features/investigation/schemas/investigation.schema.ts",
        "workspaceModeSchema",
    ),
    "layers.LayerKind": ("features/investigation/schemas/layer.schema.ts", "layerKindSchema"),
    "layers.LayerRenderMode": ("features/investigation/schemas/layer.schema.ts", "layerRenderModeSchema"),
    "model_ids.ModelId": ("features/missionCommand/schemas/model.schema.ts", "modelIdSchema"),
    "reports.ReportSection": ("features/investigation/schemas/report.schema.ts", "reportSectionKindSchema"),
    "scenes.SceneModality": (
        "features/investigation/schemas/investigation.schema.ts",
        "acquisitionModalitySchema",
    ),
    "scenes.SceneRole": ("features/investigation/schemas/investigation.schema.ts", "sceneRoleSchema"),
    "scenes.TemporalRole": ("features/missionCommand/schemas/imagery.schema.ts", "temporalRoleSchema"),
    "stages.PipelineStage": ("features/investigation/schemas/analysis.schema.ts", "pipelineStageCodeSchema"),
    "statuses.AssistantMessageStatus": (
        "features/missionCommand/schemas/assistant.schema.ts",
        "assistantMessageStatusSchema",
    ),
    "statuses.InvestigationStatus": (
        "features/investigation/schemas/investigation.schema.ts",
        "investigationStatusSchema",
    ),
    "statuses.MissionStatus": ("features/missionCommand/schemas/mission.schema.ts", "missionStatusSchema"),
    "statuses.ModelHealth": ("features/missionCommand/schemas/model.schema.ts", "modelHealthSchema"),
    "statuses.RunStatus": ("features/investigation/schemas/analysis.schema.ts", "analysisRunStatusSchema"),
    "statuses.SceneProcessingState": (
        "features/missionCommand/schemas/imagery.schema.ts",
        "imageryProcessingStateSchema",
    ),
    "statuses.TraceStepState": ("features/investigation/schemas/analysis.schema.ts", "traceStepStateSchema"),
}

# The same vocabulary under a second frontend name. Checked as well, so a divergence between two frontend
# schemas that mean the same thing surfaces here rather than as a payload one surface accepts and another
# rejects.
SHARED_VOCABULARY_ALIASES: Final[dict[str, tuple[str, str]]] = {
    "scenes.SceneModality": ("features/missionCommand/schemas/imagery.schema.ts", "sensorModalitySchema"),
    "statuses.TraceStepState": (
        "features/missionCommand/schemas/assistant.schema.ts",
        "executionStepStateSchema",
    ),
}

# Backend enums with no frontend counterpart, and why each one is allowed not to have one. A reason, not a
# waiver: "it does not have one yet" and "it never will" are different situations, and only the first is
# something to come back to.
BACKEND_ONLY_VOCABULARIES: Final[dict[str, str]] = {
    "errors.ErrorCode": (
        "The frontend's `ApiErrorPayload` types `code` as a plain string rather than an enum, so there is "
        "nothing to compare against. The codes are still a contract - `api-contract.md` says a client "
        "branches on them - so this is a candidate for a frontend schema, not an internal vocabulary."
    ),
    "figure_kinds.FigureKind": (
        "`figure-ready` is agreed and NOT YET IMPLEMENTED on the frontend (`api-contract.md` §6). When it "
        "lands, this becomes a shared vocabulary and moves up - the test will start matching."
    ),
    "figure_kinds.LegendKind": "Same as FigureKind: agreed in api-contract.md §6, not yet on the frontend.",
    "model_ids.ModelCapability": (
        "Authored copy in `frontend/lib/constants/models.ts`, deliberately not on the wire - the payload "
        "carries the id and the live numbers only (`model.schema.ts`)."
    ),
    "redis_keys.KeyNamespace": "Internal. A Redis key prefix never crosses the boundary.",
    "storage.Bucket": "Internal. A bucket role never crosses the boundary; the frontend sees signed URLs.",
    "tasks.EventName": "Internal. Inngest event names are between the backend and Inngest.",
}

# Frontend vocabularies the backend has not met yet, each with the sub-phase that will meet it. This is a
# list of what is still owed, kept here because it is the one place that can be checked mechanically: a new
# frontend enum has to be classified before the contract test passes again.
FRONTEND_ONLY_VOCABULARIES: Final[dict[str, str]] = {
    "agreementStateSchema": "Phase 1.11 - the cross-modal agreement ledger.",
    "fusionRefusalIdSchema": "Phase 1.11 - the stated reasons fusion refuses.",
    "polarisationSchema": "Phase 1.3 - the SAR branch.",
    "sensorIdSchema": "Phase 1.11 - names a sensor within a cross-modal comparison.",
    "colorRampIdSchema": "Phase 1.2.1 - becomes `app/constants/color_ramps.py`.",
    "comparatorSideSchema": "Interface state. The backend has no opinion on which pane a layer is drawn in.",
    "reportExportFormatSchema": "Phase 1.12 - JSON and GeoJSON; PDF is deferred to Phase 2.",
    "assistantRoleSchema": "Phase 1.13 - the spoken loop's turn-taking.",
    "missionAnalysisKindSchema": "Deferred with continuous monitoring (`roadmap.md`, explicitly deferred).",
}
