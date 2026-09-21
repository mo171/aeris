"""The interface commands the agent may ask the frontend to run - the frontend's command registry, mirrored.

what  : `UiCommand`, every id in `frontend/lib/constants/commands.ts`, and `AGENT_UI_COMMANDS`, the subset
        the agent is allowed to emit.
where : `agents/tools/interface_tools.py` binds the allowed subset as tools; `schemas/events/ui_command.py`
        carries one on the wire. A test parses `commands.ts` and fails if the two lists drift.
how   : The frontend declares its commands as a `const` object, not a Zod schema, so the contract exporter
        never sees them and they are transcribed here (the same situation as `SpectralIndex`). Ids are
        `domain.action` and are a public contract on the frontend side: renaming one there is a breaking
        change made in one file, and this file is that change's mirror.

        The agent's subset is deliberately small and *verifiable*: each command it emits names a claim,
        evidence item or layer that exists in the run it just made, so a hallucinated id is dropped before
        it reaches the wire. Commands that move the camera or toggle panels are the operator's, and a model
        that could fire them would be a model that could hide what it does not want seen.
"""

from enum import StrEnum
from typing import Final


class UiCommand(StrEnum):
    NAV_GOTO = "nav.goto"
    INTERFACE_OPEN_PALETTE = "interface.openCommandPalette"
    INTERFACE_TOGGLE_DATA_PANEL = "interface.toggleDataPanel"
    INTERFACE_TOGGLE_ASSISTANT_PANEL = "interface.toggleAssistantPanel"
    INTERFACE_TOGGLE_NAVIGATION_RAIL = "interface.toggleNavigationRail"
    GLOBE_FLY_TO = "globe.flyTo"
    GLOBE_RESET_VIEW = "globe.resetView"
    GLOBE_TOGGLE_LAYER = "globe.toggleLayer"
    GLOBE_TOGGLE_AUTO_ROTATE = "globe.toggleAutoRotate"
    IMAGERY_OPEN_UPLOAD = "imagery.openUpload"
    IMAGERY_SELECT = "imagery.select"
    IMAGERY_CLEAR_SELECTION = "imagery.clearSelection"
    IMAGERY_SEARCH = "imagery.search"
    MISSIONS_OPEN = "missions.open"
    MISSIONS_CREATE = "missions.create"
    INVESTIGATION_CREATE = "investigation.create"
    INVESTIGATION_OPEN = "investigation.open"
    INVESTIGATION_ASK = "investigation.ask"
    INVESTIGATION_RUN_OPERATION = "investigation.runOperation"
    INVESTIGATION_TOGGLE_LAYER = "investigation.toggleLayer"
    INVESTIGATION_SET_LAYER_OPACITY = "investigation.setLayerOpacity"
    INVESTIGATION_SOLO_LAYER = "investigation.soloLayer"
    INVESTIGATION_SET_SPLIT_POSITION = "investigation.setSplitPosition"
    INVESTIGATION_SWEEP_SPLIT = "investigation.sweepSplit"
    INVESTIGATION_SET_COMPARATOR = "investigation.setComparator"
    INVESTIGATION_TOGGLE_PLAYBACK = "investigation.togglePlayback"
    INVESTIGATION_TOGGLE_VOLUMETRIC = "investigation.toggleVolumetric"
    INVESTIGATION_SPOTLIGHT_CLAIM = "investigation.spotlightClaim"
    INVESTIGATION_INSPECT_FEATURE = "investigation.inspectFeature"
    INVESTIGATION_CLEAR_SPOTLIGHT = "investigation.clearSpotlight"
    INVESTIGATION_FOCUS_EVIDENCE = "investigation.focusEvidence"
    INVESTIGATION_PEEK_ARTEFACT = "investigation.peekArtefact"
    INVESTIGATION_CLEAR_ARTEFACT = "investigation.clearArtefact"
    INVESTIGATION_SELECT_DRAW_TOOL = "investigation.selectDrawTool"
    INVESTIGATION_COMPLETE_DRAW = "investigation.completeDraw"
    INVESTIGATION_UNDO_VERTEX = "investigation.undoVertex"
    INVESTIGATION_CANCEL_DRAW = "investigation.cancelDraw"
    INVESTIGATION_CLEAR_REGIONS = "investigation.clearRegions"
    INVESTIGATION_SET_PROJECTION = "investigation.setProjection"
    INVESTIGATION_SET_TILT = "investigation.setTilt"
    INVESTIGATION_ORBIT = "investigation.orbit"
    INVESTIGATION_SET_BUILDING_MODE = "investigation.setBuildingMode"
    INVESTIGATION_SET_TERRAIN_EXAGGERATION = "investigation.setTerrainExaggeration"
    INVESTIGATION_SCRUB_TO = "investigation.scrubTo"
    INVESTIGATION_STEP_ACQUISITION = "investigation.stepAcquisition"
    INVESTIGATION_TOGGLE_TIMELINE_PLAYBACK = "investigation.toggleTimelinePlayback"
    INVESTIGATION_SET_CLOUD_CEILING = "investigation.setCloudCeiling"
    INVESTIGATION_RUN_AUTONOMOUS = "investigation.runAutonomous"
    INVESTIGATION_TOGGLE_PRESENT_MODE = "investigation.togglePresentMode"
    INVESTIGATION_TOGGLE_TRACE = "investigation.toggleTrace"
    INVESTIGATION_OPEN_REPORT = "investigation.openReport"
    INVESTIGATION_SET_LEFT_TAB = "investigation.setLeftTab"
    INVESTIGATION_SET_RIGHT_TAB = "investigation.setRightTab"
    INVESTIGATION_SAVE_AS_MISSION = "investigation.saveAsMission"
    INVESTIGATION_SAVE_CAMERA_VIEW = "investigation.saveCameraView"
    INVESTIGATION_RESET_VIEW = "investigation.resetView"
    INVESTIGATION_TOGGLE_CANVAS = "investigation.toggleCanvas"
    INVESTIGATION_SELECT_NODE = "investigation.selectNode"
    INVESTIGATION_RERUN_STEP = "investigation.rerunStep"
    INVESTIGATION_SAVE_VERSION = "investigation.saveVersion"
    INVESTIGATION_COMPARE_VERSIONS = "investigation.compareVersions"
    INVESTIGATION_RESTORE_VERSION = "investigation.restoreVersion"
    INVESTIGATION_FOCUS_NODE = "investigation.focusNode"
    INVESTIGATION_MOVE_TO_PROJECT = "investigation.moveToProject"
    PROJECTS_OPEN = "projects.open"
    PROJECTS_CREATE = "projects.create"
    ASSISTANT_ASK = "assistant.ask"
    ASSISTANT_CLEAR = "assistant.clear"
    ASSISTANT_STOP = "assistant.stop"
    ASSISTANT_FOCUS_COMPOSER = "assistant.focusComposer"


# What the agent may emit, and the id each command must name so it can be checked against the run.
AGENT_UI_COMMANDS: Final[dict[UiCommand, str]] = {
    UiCommand.INVESTIGATION_SPOTLIGHT_CLAIM: "claimId",
    UiCommand.INVESTIGATION_FOCUS_EVIDENCE: "evidenceId",
    UiCommand.INVESTIGATION_TOGGLE_LAYER: "layerId",
    UiCommand.INVESTIGATION_TOGGLE_TRACE: "",
    # The model receives these opaque handles; resolvers compose the frontend's actual params.
    UiCommand.GLOBE_FLY_TO: "cameraTargetId",
    UiCommand.INVESTIGATION_OPEN_REPORT: "reportId",
}
