// app/scene/[sceneId]/page.tsx — the detached scene inspector window.
//
// what  : Routes "/scene/:sceneId" to a standalone view of one acquisition.
// where : Opened as a separate browser window from the Investigation Workspace, and shareable as a URL.
// how   : Deliberately OUTSIDE the (geospatial) route group. That group mounts the shared Cesium stage,
//         and a window whose only job is to show one picture must not boot a WebGL globe to do it.
//
//         `params` is a promise in this version of Next.js and must be awaited before the id is read.

import type { Metadata } from "next";

import { SceneInspectorScreen } from "@/features/sceneInspector/components/SceneInspectorScreen";

interface ScenePageProps {
  params: Promise<{ sceneId: string }>;
}

export async function generateMetadata({ params }: ScenePageProps): Promise<Metadata> {
  const { sceneId } = await params;

  return {
    title: `Scene ${sceneId}`,
    description: "Acquisition quicklook, metadata and band detail for a single satellite scene.",
  };
}

export default async function ScenePage({ params }: ScenePageProps) {
  const { sceneId } = await params;

  return <SceneInspectorScreen sceneId={sceneId} />;
}
