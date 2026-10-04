type Data = Record<string, any>;

export function registrySummary(rows: Data[]) {
  return {
    pending: rows.filter(row => row.validation_status === "AWAITING_REVIEW"),
    approved: rows.filter(row => row.validation_status === "PROMOTED"),
    rejected: rows.filter(row => row.validation_status === "REJECTED_BY_REVIEW"),
  };
}

export function decisionKind(status?: string): "waiting" | "blocked" | "passed" | "system" {
  if (["REJECTED", "BLOCKED", "VETOED", "ERROR", "FAILED"].includes(status || "")) return "blocked";
  if (["PASS", "PASSED", "FILLED", "APPROVED", "ACCEPTED"].includes(status || "")) return "passed";
  if (["STARTED", "STOPPED"].includes(status || "")) return "system";
  return "waiting";
}

export const decisionId = (event: Data) => event.id || [event.timestamp, event.symbol, event.agent, event.status, event.summary].join("|");
export const recentDecision = (event: Data, now = Date.now()) => {
  const age = now - Date.parse(event.timestamp || "");
  return Number.isFinite(age) && age >= 0 && age <= 120000;
};
