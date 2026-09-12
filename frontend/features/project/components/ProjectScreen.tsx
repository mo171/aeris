"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useProject } from "../hooks/use-project";

interface ProjectScreenProps {
  projectId: string;
}

export function ProjectScreen({ projectId }: ProjectScreenProps) {
  const { data: project, isLoading, error } = useProject(projectId);

  if (error) {
    return <div className="p-6 text-destructive">Failed to load project.</div>;
  }

  if (isLoading || !project) {
    return <div className="p-6 animate-pulse">Loading project...</div>;
  }

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="border-b p-6">
        <h1 className="text-2xl font-bold tracking-tight">{project.name}</h1>
        <p className="text-muted-foreground">{project.areaOfInterestName}</p>
      </div>
      
      <div className="flex-1 p-6 overflow-hidden">
        <Tabs defaultValue="investigations" className="h-full flex flex-col">
          <TabsList className="w-fit">
            <TabsTrigger value="data">Data</TabsTrigger>
            <TabsTrigger value="investigations">Investigations</TabsTrigger>
            <TabsTrigger value="reports">Reports</TabsTrigger>
            <TabsTrigger value="versions">Versions</TabsTrigger>
            <TabsTrigger value="missions">Missions</TabsTrigger>
          </TabsList>
          
          <div className="mt-4 flex-1 overflow-y-auto">
            <TabsContent value="data" className="m-0 h-full">
              <div className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
                Data for this area (Mock)
              </div>
            </TabsContent>
            
            <TabsContent value="investigations" className="m-0 h-full">
              <div className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
                Investigations list (Mock)
              </div>
            </TabsContent>
            
            <TabsContent value="reports" className="m-0 h-full">
              <div className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
                Generated reports (Mock)
              </div>
            </TabsContent>
            
            <TabsContent value="versions" className="m-0 h-full">
              <div className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
                Saved versions across investigations (Mock)
              </div>
            </TabsContent>
            
            <TabsContent value="missions" className="m-0 h-full">
              <div className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
                Standing orders (Missions) (Mock)
              </div>
            </TabsContent>
          </div>
        </Tabs>
      </div>
    </div>
  );
}
