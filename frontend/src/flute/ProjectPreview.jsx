"use client";
import React from "react";
import { ProjectPreview } from "@webprodigies/flute/preview";
import { sceneModules } from "./catalog";
// Host-owned development flag: no process, Vite or Electron globals in this adapter.
export function FluteProjectPreview({ children, enabled, active, ...props }) {
  if (!enabled) return children;
  return <ProjectPreview {...props} projectId="87e12401-03f1-45a7-8c04-860e26ccd5af" enabled={enabled} active={active} sceneModules={sceneModules}>{children}</ProjectPreview>;
}
