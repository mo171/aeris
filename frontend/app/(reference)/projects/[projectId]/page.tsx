import { ProjectScreen } from "@/features/project/components/ProjectScreen";

export default async function ProjectDetailPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <ProjectScreen projectId={projectId} />;
}
