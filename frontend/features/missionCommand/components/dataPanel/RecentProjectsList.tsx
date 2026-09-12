"use client";

import { ChevronDown, ChevronRight, Folder } from "lucide-react";

import { buildRoute } from "@/lib/constants/routes";
import { useProjects } from "@/features/project/hooks/use-project";
import Link from "next/link";
import { Button } from "@/components/ui/button";

interface RecentProjectsListProps {
  isExpanded: boolean;
  onToggleExpanded: () => void;
}

export function RecentProjectsList({ isExpanded, onToggleExpanded }: RecentProjectsListProps) {
  const { data: projectPage, isLoading } = useProjects();

  return (
    <div className="flex shrink-0 flex-col border-t border-border-soft">
      <button
        type="button"
        className="flex items-center gap-2 px-3 py-2 text-xs font-semibold text-foreground transition-colors hover:bg-muted/50 focus-visible:bg-muted focus-visible:outline-none"
        onClick={onToggleExpanded}
      >
        <span className="flex-1 text-left">Recent Projects</span>
        <span className="text-muted-foreground transition-transform">
          {isExpanded ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
        </span>
      </button>

      {isExpanded ? (
        <div className="flex max-h-48 flex-col gap-1 overflow-y-auto px-3 pb-3">
          {isLoading ? (
            <div className="text-xs text-muted-foreground">Loading projects...</div>
          ) : projectPage?.pages.flatMap((p) => p.items).length === 0 ? (
            <div className="text-xs text-muted-foreground">No projects yet.</div>
          ) : (
            projectPage?.pages
              .flatMap((p) => p.items)
              .map((project) => (
                <Link
                  key={project.id}
                  href={buildRoute.project(project.id)}
                  className="flex items-center gap-2 rounded-sm px-2 py-1.5 transition-colors hover:bg-muted/80 focus-visible:bg-muted focus-visible:outline-none group"
                >
                  <Folder className="size-4 text-primary shrink-0" />
                  <div className="flex flex-col min-w-0">
                    <span className="truncate text-xs font-medium group-hover:text-foreground">
                      {project.name}
                    </span>
                    <span className="truncate text-[10px] text-muted-foreground">
                      {project.areaOfInterestName}
                    </span>
                  </div>
                </Link>
              ))
          )}
        </div>
      ) : null}
    </div>
  );
}
