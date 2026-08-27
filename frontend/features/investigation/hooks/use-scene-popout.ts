// features/investigation/hooks/use-scene-popout.ts — opening scenes in detached windows, and hearing back.
//
// what  : Opens a scene inspector in its own browser window, tracks which ones are open, and receives the
//         role assignments those windows send back.
// where : Called once by InvestigationScreen; the open action is passed down to the scene and acquisition
//         lists.
// how   : Detached windows rather than modals because that is what the work needs. Comparing four
//         candidate acquisitions means having four visible at once, on a second monitor if there is one.
//         A modal shows exactly one and covers the map while doing it.
//
//         One window per scene, reused on a second click. Opening a fresh window each time buries the
//         operator in duplicates of the same picture; naming the window after the scene makes the browser
//         focus the existing one instead.
//
//         Messages from those windows are validated and origin-checked. A window handle is not a reason
//         to trust what arrives through it — any page the operator has open can post to this one, so the
//         payload is treated as untrusted input exactly like an HTTP response.

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { parseSceneRoleAssignment } from "@/features/sceneInspector/scene-popout-messages";
import { SCENE_POPOUT_WINDOW } from "@/lib/constants/investigation";

interface ScenePopoutOptions {
  investigationId: string;
  /** Called when a detached window asks for a scene to be bound into a role. */
  onAssignRole: (sceneId: string, role: "t0" | "t1" | "sar") => void;
}

interface ScenePopoutControls {
  openScene: (sceneId: string) => void;
  /** Scene ids with a window currently open, so the list can show which are already detached. */
  openSceneIds: readonly string[];
}

export function useScenePopout({
  investigationId,
  onAssignRole,
}: ScenePopoutOptions): ScenePopoutControls {
  const windowsRef = useRef(new Map<string, Window>());
  const [openSceneIds, setOpenSceneIds] = useState<string[]>([]);

  const onAssignRoleRef = useRef(onAssignRole);
  useEffect(() => {
    onAssignRoleRef.current = onAssignRole;
  }, [onAssignRole]);

  const openScene = useCallback((sceneId: string) => {
    const existing = windowsRef.current.get(sceneId);
    if (existing && !existing.closed) {
      existing.focus();
      return;
    }

    const features = [
      `width=${SCENE_POPOUT_WINDOW.widthPx}`,
      `height=${SCENE_POPOUT_WINDOW.heightPx}`,
      "menubar=no",
      "toolbar=no",
      "location=no",
      "status=no",
    ].join(",");

    // Named after the scene so a second click focuses the window that is already showing it rather than
    // opening a duplicate.
    const opened = window.open(`/scene/${encodeURIComponent(sceneId)}`, `aeris-scene-${sceneId}`, features);
    if (!opened) {
      // Popup blocked. Falling back to a tab is better than doing nothing silently, and the operator's
      // blocker will usually offer to allow it next time.
      window.open(`/scene/${encodeURIComponent(sceneId)}`, "_blank", "noopener");
      return;
    }

    windowsRef.current.set(sceneId, opened);
    setOpenSceneIds((current) => (current.includes(sceneId) ? current : [...current, sceneId]));
  }, []);

  // Windows are closed by the operator, not by us, so their state is polled rather than pushed. A
  // detached window has no close event the opener can subscribe to.
  useEffect(() => {
    const intervalId = window.setInterval(() => {
      let didClose = false;
      for (const [sceneId, popout] of windowsRef.current) {
        if (popout.closed) {
          windowsRef.current.delete(sceneId);
          didClose = true;
        }
      }
      if (didClose) {
        setOpenSceneIds([...windowsRef.current.keys()]);
      }
    }, SCENE_POPOUT_WINDOW.closePollIntervalMs);

    return () => window.clearInterval(intervalId);
  }, []);

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) {
        return;
      }

      const assignment = parseSceneRoleAssignment(event.data);
      if (!assignment || assignment.investigationId !== investigationId) {
        return;
      }

      onAssignRoleRef.current(assignment.sceneId, assignment.role);
    };

    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [investigationId]);

  // Leaving the workspace closes the windows it opened. Orphaned inspectors pointing at an investigation
  // the operator has left are clutter they then have to tidy up by hand.
  useEffect(() => {
    const openWindows = windowsRef.current;
    return () => {
      for (const popout of openWindows.values()) {
        popout.close();
      }
      openWindows.clear();
    };
  }, []);

  return { openScene, openSceneIds };
}
