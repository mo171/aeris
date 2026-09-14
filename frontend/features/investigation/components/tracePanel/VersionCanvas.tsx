"use client";

import React, { useMemo } from "react";
import { GitGraphCanvas, type GitGraphNode } from "@/components/sharedUI/gitGraphCanvas";
import { useInvestigationStore } from "../../store/investigation-store";
import type { InvestigationVersion } from "../../types/version.types";
import { ChevronDown, ChevronRight, Hash, User, Calendar } from "lucide-react";

interface VersionCanvasProps {
  versions: InvestigationVersion[];
}

export function VersionCanvas({ versions }: VersionCanvasProps) {
  const setSelectedNodeId = useInvestigationStore((state) => state.setSelectedNodeId);

  const nodes = useMemo<GitGraphNode[]>(() => {
    if (!versions || versions.length === 0) return [];

    // Sort versions by createdAt descending (newest first)
    const sortedVersions = [...versions].sort(
      (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
    );

    return sortedVersions.map((version) => {
      const date = new Date(version.createdAt);
      
      return {
        id: version.id,
        parents: version.parentVersionId ? [version.parentVersionId] : [],
        renderRow: (node, isExpanded, toggleExpand) => (
          <div className="flex items-center justify-between py-1">
            <div className="flex items-center gap-3">
              {isExpanded ? (
                <ChevronDown className="w-4 h-4 text-muted-foreground" />
              ) : (
                <ChevronRight className="w-4 h-4 text-muted-foreground" />
              )}
              <span className="font-semibold text-sm text-zinc-100 truncate max-w-[400px]">
                {version.label || "Version Snapshot"}
              </span>
            </div>
            <div className="flex items-center gap-6 text-xs text-zinc-400">
              <span className="font-mono">
                {version.authorName || version.authorId || "Unknown User"}
              </span>
              <span className="font-mono text-zinc-500">
                {date.toLocaleString(undefined, {
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
              <span className="font-mono bg-[#09090b] px-2 py-0.5 rounded text-[10px] text-zinc-300 border border-zinc-800">
                {version.id.substring(0, 8)}
              </span>
            </div>
          </div>
        ),
        renderDetails: () => (
          <div className="flex flex-col gap-3 text-sm text-zinc-300">
            {version.description && (
              <div>
                <strong className="text-zinc-100 text-[10px] uppercase tracking-widest block mb-1">Description</strong>
                <span className="text-zinc-400">{version.description}</span>
              </div>
            )}
            <div className="grid grid-cols-3 gap-4 mt-2 p-3 bg-[#09090b] rounded-md border border-zinc-800">
              <div className="flex flex-col gap-1">
                <span className="text-[10px] uppercase tracking-widest text-zinc-500 flex items-center gap-1"><Hash className="w-3 h-3"/> Commit ID</span>
                <span className="font-mono text-zinc-300">{version.id}</span>
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-[10px] uppercase tracking-widest text-zinc-500 flex items-center gap-1"><User className="w-3 h-3"/> Author</span>
                <span className="font-mono text-zinc-300">{version.authorName || version.authorId || "Unknown User"}</span>
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-[10px] uppercase tracking-widest text-zinc-500 flex items-center gap-1"><Calendar className="w-3 h-3"/> Date</span>
                <span className="font-mono text-zinc-300">{date.toLocaleString()}</span>
              </div>
            </div>
          </div>
        ),
      };
    });
  }, [versions]);

  if (!versions || versions.length === 0) {
    return <div className="flex h-full items-center justify-center text-xs text-muted-foreground">No version history available.</div>;
  }

  return (
    <div className="h-full w-full bg-[#09090b] overflow-y-auto overflow-x-hidden p-6" onClick={() => setSelectedNodeId(null)}>
      <GitGraphCanvas nodes={nodes} className="max-w-5xl mx-auto" />
    </div>
  );
}
