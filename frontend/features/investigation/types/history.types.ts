export interface InvestigationEvent {
  id: string;
  investigationId: string;
  at: string;
  actor: "operator" | "agent";
  commandId: string;
  summary: string;
  params: unknown;
}
