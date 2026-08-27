// features/sceneInspector/scene-popout-messages.ts — the contract between the workspace and its pop-out windows.
//
// what  : The message type and payload a detached scene window sends back to the window that opened it.
// where : Sent by SceneInspectorScreen, received by features/investigation/hooks/use-scene-popout.ts.
// how   : A detached window has its own JavaScript context, so it shares no stores, no query cache and no
//         module state with the workspace. postMessage is the only channel, and it is deliberately narrow:
//         one message type carrying an investigation, a scene and a role.
//
//         Both ends check the origin and the shape. A window handle is not a reason to trust what arrives
//         through it — any page the operator has open could post to this window, so the payload is treated
//         as untrusted input exactly like an HTTP response.

export const SCENE_ROLE_ASSIGNMENT_MESSAGE = "aeris:scene-role-assignment" as const;

export interface SceneRoleAssignment {
  type: typeof SCENE_ROLE_ASSIGNMENT_MESSAGE;
  investigationId: string;
  sceneId: string;
  role: "t0" | "t1" | "sar";
}

/** Narrows an unknown postMessage payload. Returns null for anything that is not ours. */
export function parseSceneRoleAssignment(payload: unknown): SceneRoleAssignment | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }

  const candidate = payload as Partial<SceneRoleAssignment>;
  if (
    candidate.type !== SCENE_ROLE_ASSIGNMENT_MESSAGE ||
    typeof candidate.investigationId !== "string" ||
    typeof candidate.sceneId !== "string" ||
    (candidate.role !== "t0" && candidate.role !== "t1" && candidate.role !== "sar")
  ) {
    return null;
  }

  return {
    type: SCENE_ROLE_ASSIGNMENT_MESSAGE,
    investigationId: candidate.investigationId,
    sceneId: candidate.sceneId,
    role: candidate.role,
  };
}
