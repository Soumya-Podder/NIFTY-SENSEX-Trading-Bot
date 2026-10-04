export type Evidence = Record<string, any>;
export type LearningGroup = "all" | "entry_model" | "specialist" | "controls" | "analysis";

export const learningGroups: { id: LearningGroup; label: string }[] = [
  { id: "all", label: "All agents" },
  { id: "entry_model", label: "Strategies" },
  { id: "specialist", label: "Specialists" },
  { id: "controls", label: "Pipeline & risk" },
  { id: "analysis", label: "Research & exits" },
];

export function learningGroup(agent: Evidence): LearningGroup {
  if (agent.kind === "entry_model") return "entry_model";
  if (agent.kind === "pipeline" || agent.learnable === false) return "controls";
  if (agent.kind === "rules_or_analysis") return "analysis";
  return "specialist";
}

export function evidenceTone(agent: Evidence): string {
  if (agent.learnable === false || agent.status === "FIXED_RULES") return "fixed";
  const state = `${agent.status || ""} ${agent.validation || ""} ${agent.overfitting?.status || ""}`;
  if (/REJECT|BLOCK|INSUFFICIENT|REVALIDATION|VALIDATION_MISSING|REPLAY_REQUIRED|UNVALIDATED_PARAMETER/.test(state)) return "blocked";
  if (agent.self_improvement_proven === true) return "proven";
  if (/ACTIVE|VALIDATED_NOT_DEPLOYED/.test(agent.status || "")) return "active";
  if (/ATTEMPTED/.test(agent.status || "")) return "attempted";
  return "waiting";
}

export function monitorCurrent(data: Evidence | undefined, online: boolean, now: number): boolean {
  const age = now - Date.parse(data?.checked_at || "");
  return online && data?.worker_alive === true && data.stale === false && data.status === "MONITORING"
    && Number.isFinite(age) && age >= -5000 && age <= 150000;
}

export function evidenceMetrics(agent: Evidence): { label: string; value: number | undefined }[] {
  if (agent.kind === "entry_model") return [
    { label: "Attempts", value: agent.training_attempts },
    { label: "Fitted", value: agent.fitted_candidates },
    { label: "Forward episodes", value: agent.forward_tagged_episodes },
  ];
  if (agent.decision_count != null) return [
    { label: "Decisions", value: agent.decision_count },
    { label: "Outcomes", value: agent.outcome_count },
    { label: "Sessions", value: agent.observed_sessions },
  ];
  return [
    { label: "Outcomes", value: agent.outcomes },
    { label: "Active policy", value: agent.active_policy_version ? 1 : undefined },
  ];
}

// A training run can contain several strategy attempts. Do not add per-agent
// decisions or policy records to the global model totals.
export function learningSummary(data: Evidence) {
  const agents: Evidence[] = data.agents || [];
  return {
    agents,
    fitted: agents.filter(agent => agent.kind === "entry_model").reduce((sum, agent) => sum + (agent.fitted_candidates || 0), 0),
    proven: agents.filter(agent => agent.self_improvement_proven === true).length,
    withEvidence: agents.filter(agent => !!agent.last_evidence_at).length,
  };
}

export function evidenceStamp(agent: Evidence): string {
  return JSON.stringify([agent.status, agent.validation, agent.last_evidence_at, agent.training_attempts,
    agent.fitted_candidates, agent.decision_count, agent.outcome_count, agent.outcomes,
    agent.active_model_ids, agent.active_policy_version, agent.overfitting?.status, agent.self_improvement_proven]);
}
