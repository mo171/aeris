// lib/constants/commands.ts — canonical command identifiers for the agentic UI control layer.
//
// what  : Every command id the interface can execute, plus the palette group labels.
// where : Used when defining commands in features/&ast;/hooks/use-&ast;-commands.ts and when dispatching from
//         buttons, shortcuts or (in a later phase) a voice/agent intent.
// how   : Ids are namespaced `domain.action`. They are a public contract: the agent layer will reference
//         these strings, so renaming one is a breaking change and must be done here only.

export const COMMAND_IDS = {
  navigation: {
    goto: "nav.goto",
  },
  interface: {
    openPalette: "interface.openCommandPalette",
    toggleDataPanel: "interface.toggleDataPanel",
    toggleAssistantPanel: "interface.toggleAssistantPanel",
    toggleNavigationRail: "interface.toggleNavigationRail",
  },
  globe: {
    flyTo: "globe.flyTo",
    resetView: "globe.resetView",
    toggleLayer: "globe.toggleLayer",
    toggleAutoRotate: "globe.toggleAutoRotate",
  },
  imagery: {
    openUpload: "imagery.openUpload",
    select: "imagery.select",
    clearSelection: "imagery.clearSelection",
    search: "imagery.search",
  },
  missions: {
    open: "missions.open",
  },
  investigation: {
    create: "investigation.create",
    open: "investigation.open",
    ask: "investigation.ask",
    runOperation: "investigation.runOperation",
    toggleLayer: "investigation.toggleLayer",
    setLayerOpacity: "investigation.setLayerOpacity",
    soloLayer: "investigation.soloLayer",
    setSplitPosition: "investigation.setSplitPosition",
    sweepSplit: "investigation.sweepSplit",
    setComparator: "investigation.setComparator",
    togglePlayback: "investigation.togglePlayback",
    toggleVolumetric: "investigation.toggleVolumetric",
    spotlightClaim: "investigation.spotlightClaim",
    inspectFeature: "investigation.inspectFeature",
    clearSpotlight: "investigation.clearSpotlight",
    focusEvidence: "investigation.focusEvidence",
    peekArtefact: "investigation.peekArtefact",
    clearArtefact: "investigation.clearArtefact",
    selectDrawTool: "investigation.selectDrawTool",
    completeDraw: "investigation.completeDraw",
    undoVertex: "investigation.undoVertex",
    cancelDraw: "investigation.cancelDraw",
    clearRegions: "investigation.clearRegions",
    setProjection: "investigation.setProjection",
    setTilt: "investigation.setTilt",
    orbit: "investigation.orbit",
    setBuildingMode: "investigation.setBuildingMode",
    setTerrainExaggeration: "investigation.setTerrainExaggeration",
    scrubTo: "investigation.scrubTo",
    stepAcquisition: "investigation.stepAcquisition",
    toggleTimelinePlayback: "investigation.toggleTimelinePlayback",
    setCloudCeiling: "investigation.setCloudCeiling",
    runAutonomous: "investigation.runAutonomous",
    togglePresentMode: "investigation.togglePresentMode",
    toggleTrace: "investigation.toggleTrace",
    openReport: "investigation.openReport",
    saveAsMission: "investigation.saveAsMission",
    saveCameraView: "investigation.saveCameraView",
    resetView: "investigation.resetView",
  },
  assistant: {
    ask: "assistant.ask",
    clear: "assistant.clear",
    stop: "assistant.stop",
    focusComposer: "assistant.focusComposer",
  },
} as const;

export const COMMAND_GROUP_LABEL = {
  navigation: "Navigate",
  interface: "Interface",
  globe: "Globe",
  imagery: "Imagery",
  missions: "Missions",
  investigation: "Investigation",
  assistant: "Assistant",
} as const;

export type CommandGroup = keyof typeof COMMAND_GROUP_LABEL;
