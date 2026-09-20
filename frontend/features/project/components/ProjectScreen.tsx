"use client";

import Link from "next/link";
import { 
  ArrowRight, 
  Clock, 
  Folder, 
  Radar, 
  ScanSearch, 
  ShieldAlert, 
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { buildRoute } from "@/lib/constants/routes";
import { useProjectInvestigations } from "@/features/investigation/hooks/use-investigations";
import { useProjectMissions } from "@/features/missionCommand/hooks/use-active-missions";
import { useProject } from "../hooks/use-project";

interface ProjectScreenProps {
  projectId: string;
}

export function ProjectScreen({ projectId }: ProjectScreenProps) {
  const { data: project, isLoading: isProjectLoading, error: projectError } = useProject(projectId);
  const { data: investigations = [], isLoading: isInvLoading } = useProjectInvestigations(projectId);
  const { data: missionPage, isLoading: isMissionsLoading } = useProjectMissions(projectId);

  const missions = missionPage?.items ?? [];

  if (projectError) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-destructive">
        Failed to load project details.
      </div>
    );
  }

  if (isProjectLoading || !project) {
    return (
      <div className="flex h-full flex-col p-6">
        <div className="h-8 w-64 animate-pulse rounded bg-muted/50 mb-2" />
        <div className="h-4 w-96 animate-pulse rounded bg-muted/40 mb-6" />
        <div className="h-10 w-80 animate-pulse rounded bg-muted/30" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-background">
      {/* Header */}
      <div className="border-b border-border/40 p-6 backdrop-blur">
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Folder className="h-5 w-5 text-primary" />
              <h1 className="text-2xl font-bold tracking-tight text-foreground">{project.name}</h1>
            </div>
            <p className="text-sm text-muted-foreground">
              {project.areaOfInterestName || "Global / Unbounded Project Workspace"}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Badge variant="outline" className="text-xs">
              ID: {project.id}
            </Badge>
            {project.lastActivityAt && (
              <span className="text-xs text-muted-foreground flex items-center gap-1">
                <Clock className="h-3 w-3" />
                Active {new Date(project.lastActivityAt).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex-1 p-6 overflow-hidden">
        <Tabs defaultValue="investigations" className="h-full flex flex-col">
          <TabsList className="w-fit border border-border/40 bg-muted/30">
            <TabsTrigger value="investigations" className="flex items-center gap-2">
              <ScanSearch className="h-4 w-4" />
              Investigations ({investigations.length})
            </TabsTrigger>
            <TabsTrigger value="missions" className="flex items-center gap-2">
              <Radar className="h-4 w-4" />
              Standing Missions ({missions.length})
            </TabsTrigger>
            <TabsTrigger value="data">Data & Scenes</TabsTrigger>
            <TabsTrigger value="reports">Reports</TabsTrigger>
          </TabsList>

          <div className="mt-6 flex-1 overflow-y-auto">
            {/* Investigations Tab */}
            <TabsContent value="investigations" className="m-0 h-full">
              {isInvLoading ? (
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <div key={i} className="h-36 animate-pulse rounded-lg border bg-muted/40" />
                  ))}
                </div>
              ) : investigations.length === 0 ? (
                <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border/60 p-12 text-center">
                  <div className="rounded-full bg-primary/10 p-3 text-primary mb-3">
                    <ScanSearch className="h-6 w-6" />
                  </div>
                  <h3 className="text-base font-semibold text-foreground">No investigations created yet</h3>
                  <p className="mt-1 text-sm text-muted-foreground max-w-sm">
                    Select target scenes from Mission Command or the Imagery Catalogue to launch a deep-dive investigation.
                  </p>
                  <Button asChild className="mt-4" size="sm">
                    <Link href="/">Open Mission Command</Link>
                  </Button>
                </div>
              ) : (
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                  {investigations.map((inv) => (
                    <div
                      key={inv.id}
                      className="group flex flex-col justify-between rounded-xl border border-border/50 bg-card p-5 transition-all duration-150 hover:border-primary/40 hover:shadow-sm"
                    >
                      <div className="space-y-2">
                        <div className="flex items-start justify-between gap-2">
                          <h3 className="font-semibold text-foreground leading-snug line-clamp-1">
                            {inv.name}
                          </h3>
                          <Badge
                            variant={
                              inv.status === "ready"
                                ? "default"
                                : inv.status === "running"
                                ? "secondary"
                                : "outline"
                            }
                            className="capitalize text-xs shrink-0"
                          >
                            {inv.status}
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground line-clamp-1">
                          AOI: {inv.areaOfInterestName}
                        </p>
                        <div className="flex items-center gap-2 pt-1 text-xs text-muted-foreground">
                          <span className="font-mono bg-muted/50 px-1.5 py-0.5 rounded text-[11px]">
                            {inv.mode}
                          </span>
                          <span>•</span>
                          <span>{new Date(inv.updatedAt).toLocaleDateString()}</span>
                        </div>
                      </div>

                      <div className="mt-4 pt-3 border-t border-border/30 flex items-center justify-between">
                        <span className="font-mono text-[10px] text-muted-foreground truncate max-w-[120px]">
                          {inv.traceId}
                        </span>
                        <Button asChild size="sm" variant="ghost" className="gap-1.5 text-xs text-primary hover:text-primary">
                          <Link href={buildRoute.investigationDetail(inv.id)}>
                            Open Workspace
                            <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
                          </Link>
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </TabsContent>

            {/* Missions Tab */}
            <TabsContent value="missions" className="m-0 h-full">
              {isMissionsLoading ? (
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <div key={i} className="h-36 animate-pulse rounded-lg border bg-muted/40" />
                  ))}
                </div>
              ) : missions.length === 0 ? (
                <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border/60 p-12 text-center">
                  <div className="rounded-full bg-primary/10 p-3 text-primary mb-3">
                    <Radar className="h-6 w-6" />
                  </div>
                  <h3 className="text-base font-semibold text-foreground">No standing missions active</h3>
                  <p className="mt-1 text-sm text-muted-foreground max-w-sm">
                    Standing missions are persistent surveillance orders. Promote a completed investigation to start monitoring on a cadence.
                  </p>
                </div>
              ) : (
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                  {missions.map((mission) => (
                    <div
                      key={mission.id}
                      className="flex flex-col justify-between rounded-xl border border-border/50 bg-card p-5 transition-all duration-150 hover:border-primary/40 hover:shadow-sm"
                    >
                      <div className="space-y-2">
                        <div className="flex items-start justify-between gap-2">
                          <h3 className="font-semibold text-foreground leading-snug line-clamp-1">
                            {mission.name}
                          </h3>
                          <Badge
                            variant={
                              mission.status === "alert"
                                ? "destructive"
                                : mission.status === "monitoring"
                                ? "default"
                                : "secondary"
                            }
                            className="capitalize text-xs shrink-0"
                          >
                            {mission.status}
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground line-clamp-2">
                          {mission.summary}
                        </p>
                        <div className="flex items-center gap-2 pt-1 text-xs text-muted-foreground">
                          <span className="capitalize bg-muted/50 px-1.5 py-0.5 rounded text-[11px]">
                            {mission.cadence}
                          </span>
                          <span>•</span>
                          <span>
                            {mission.centroid.latitude.toFixed(2)}°, {mission.centroid.longitude.toFixed(2)}°
                          </span>
                        </div>
                      </div>

                      <div className="mt-4 pt-3 border-t border-border/30 flex items-center justify-between text-xs text-muted-foreground">
                        <span>
                          {mission.confidence != null
                            ? `${Math.round(mission.confidence * 100)}% Confidence`
                            : "Awaiting run"}
                        </span>
                        {mission.openAlertCount > 0 && (
                          <span className="flex items-center gap-1 text-destructive font-medium">
                            <ShieldAlert className="h-3.5 w-3.5" />
                            {mission.openAlertCount} alert{mission.openAlertCount > 1 ? "s" : ""}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </TabsContent>

            {/* Data Tab */}
            <TabsContent value="data" className="m-0 h-full">
              <div className="rounded-xl border border-border/40 bg-card/50 p-6 text-sm text-muted-foreground">
                <p>Bound sensor platforms and catalogued acquisitions across this area of interest ({project.areaOfInterestName}).</p>
              </div>
            </TabsContent>

            {/* Reports Tab */}
            <TabsContent value="reports" className="m-0 h-full">
              <div className="rounded-xl border border-border/40 bg-card/50 p-6 text-sm text-muted-foreground">
                <p>Audited PDF and Markdown intelligence reports generated from investigations within this project.</p>
              </div>
            </TabsContent>
          </div>
        </Tabs>
      </div>
    </div>
  );
}
