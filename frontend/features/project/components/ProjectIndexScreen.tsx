"use client";

import { useMemo } from "react";
import Link from "next/link";
import { Folder } from "lucide-react";

import { buildRoute } from "@/lib/constants/routes";
import { useProjects } from "../hooks/use-project";

export function ProjectIndexScreen() {
  const { data: projectPage, isLoading, error } = useProjects();

  const projects = useMemo(() => {
    const all = projectPage?.pages.flatMap((p) => p.items) ?? [];
    const seen = new Set<string>();
    return all.filter((proj) => {
      if (!proj?.id || seen.has(proj.id)) {
        return false;
      }
      seen.add(proj.id);
      return true;
    });
  }, [projectPage]);

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-destructive">
        Failed to load projects.
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col p-6 overflow-y-auto">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Projects</h1>
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {isLoading
          ? Array.from({ length: 6 }).map((_, i) => (
              <div
                key={i}
                className="h-28 animate-pulse rounded-lg border bg-muted/50"
              />
            ))
          : projects.map((project) => (
                <Link
                  key={project.id}
                  href={buildRoute.project(project.id)}
                  className="flex items-start gap-4 rounded-lg border bg-card p-4 transition-colors hover:bg-muted/50"
                >
                  <div className="mt-1 flex-shrink-0 rounded bg-primary/10 p-2 text-primary">
                    <Folder className="h-5 w-5" />
                  </div>
                  <div className="flex flex-col gap-1 overflow-hidden">
                    <span className="font-medium leading-none truncate">
                      {project.name}
                    </span>
                    <span className="text-sm text-muted-foreground truncate">
                      {project.areaOfInterestName}
                    </span>
                    <span className="mt-2 text-xs text-muted-foreground">
                      Updated {new Date(project.updatedAt).toLocaleDateString()}
                    </span>
                  </div>
                </Link>
              ))}
      </div>
    </div>
  );
}
