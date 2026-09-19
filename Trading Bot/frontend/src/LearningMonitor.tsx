type Data = Record<string, any>;
export default function LearningMonitor({data}: {data?: Data}) {
  if (!data) return <section className="panel spaced"><h2>Learning evidence monitor</h2><p>Monitor status unavailable. No learning claim can be verified.</p></section>;
  const audit = data.individual_agent_audit;
  const loss = audit?.loss_investigation;
  return <section className="panel spaced">
    <div className="eyebrow">INDIVIDUAL AGENT AUDIT / UNVALIDATED PAPER OBSERVATION</div>
    <h2>Are the agents learning?</h2>
    <p><strong>{data.stale ? "Monitor stale or stopped" : data.status}</strong> · Last check: {data.checked_at ? new Date(data.checked_at).toLocaleString() : "Not checked"}</p>
    <p>{data.total_training_attempts ?? 0} training attempts · {data.deployed_models ?? 0} deployed models · Training now: {data.training_now ? "Yes" : "No"}</p>
    <p><strong>{data.overfitting_status === "BLOCKED" ? "Overfitting gate blocked one or more candidates." : "Overfitting has not been ruled out."}</strong> Activity, backtest profit and generated lessons are not proof of improvement.</p>
    {audit && <div className="research-note">
      <strong>Deterministic individual-agent auditor: {audit.overfitting_status?.replace(/_/g, " ") || "NOT ASSESSED"}</strong>
      <p>{audit.agents?.length ?? 0} architecture roles audited · Self-improvement proven: {audit.self_improvement_proven ? "Yes" : "No"} · Authority: audit only, no order or risk control.</p>
      <p>Loss Investigator: {loss?.losses ?? 0} losing episodes · {loss?.classified ?? 0} classified hypotheses. Research continues after losses; no automatic strategy rewrite or loss chasing is permitted.</p>
      {loss?.categories && <p>Failure categories: {Object.entries(loss.categories).map(([name, count]) => `${name.replace(/_/g, " ")} ${count}`).join(" · ") || "none"}</p>}
    </div>}
    <div className="research-note">
      <strong>Forward comparison: {data.forward_comparison?.status?.replaceAll("_", " ") || "Not available"}</strong>
      <p>A separate reference paper account compares the frozen learned entry filter with the fixed strategy rules. Its profit is never added to your primary account.</p>
      <p>Monitor worker: {data.forward_comparison?.worker_alive ? "running" : "unavailable"} · Freshness: {data.forward_comparison?.stale === true ? "stale" : data.forward_comparison?.stale === false ? "current" : "not reported by this backend"}
        {data.forward_comparison?.session ? ` · Session: ${data.forward_comparison.session}` : ""}</p>
      {(data.forward_comparison?.issues || []).map((issue: string) => <p key={issue}>{issue}</p>)}
      <p>Quote recorder: {data.quote_recording?.worker_alive ? "running" : "unavailable"} · Dropped observations: {data.quote_recording?.dropped_this_run ?? "unknown"}. A completed comparison alone does not prove improved trading.</p>
    </div>
    {(data.alerts || []).map((text: string) => <p key={text}>{text}</p>)}
    {(data.downloaded_data || []).map((item: Data) => <p key={item.symbol}>{item.symbol} underlying candles: {item.present ? "file present" : "file not found"}. File presence does not prove training coverage.</p>)}
    <div style={{overflowX: "auto"}}><table style={{width: "100%", textAlign: "left"}}>
      <thead><tr><th>Agent / strategy</th><th>Learning state</th><th>Latest validation</th><th>Evidence</th></tr></thead>
      <tbody>{(data.agents || []).map((agent: Data) => <tr key={agent.id}>
        <td>{agent.id}</td><td>{agent.status?.replaceAll("_", " ")}</td><td>{agent.validation || agent.overfitting?.status || "Not demonstrated"}</td>
        <td>{agent.fitted_candidates != null && <span>{agent.fitted_candidates} fitted / {agent.training_attempts} attempts. </span>}{agent.reason}
          {agent.decision_count != null && <small style={{display: "block"}}>{agent.decision_count} decisions · {agent.outcome_count ?? 0} outcomes · {agent.observed_sessions ?? 0} sessions · overfit gate: {agent.overfitting?.status || "not assessed"}</small>}
          {agent.last_evidence_at && <small style={{display: "block"}}>Evidence: {new Date(agent.last_evidence_at).toLocaleString()}</small>}
          {agent.last_fitted_validation?.test_trades != null && <details><summary>Last fitted candidate evidence</summary>
            <p>{agent.last_fitted_validation.train_trades} training trades / {agent.last_fitted_validation.test_trades} test trades · {agent.last_fitted_validation.test_from}–{agent.last_fitted_validation.test_end}</p>
            <p>Selected holdout net P&amp;L: ₹{agent.last_fitted_validation.filter_metrics?.net_pnl?.toFixed(2) ?? "unavailable"}. Baseline: ₹{agent.last_fitted_validation.baseline?.net_pnl?.toFixed(2) ?? "unavailable"}.</p>
            <p>Train-to-holdout Brier score increase: {agent.last_fitted_validation.holdout_brier_gap?.toFixed(3) ?? "not recorded"}. An increase can indicate poorer generalization or changed market conditions.</p>
            <p>Full replay checks: {agent.last_fitted_validation.overfitting_checks ? (agent.last_fitted_validation.overfitting_checks.passed ? "Passed; forward improvement still unproven" : agent.last_fitted_validation.overfitting_checks.reasons.join("; ")) : "Not recorded"}</p>
          </details>}</td>
      </tr>)}</tbody>
    </table></div>
    <details><summary>Checks and limitations</summary>{(data.limits || []).map((text: string) => <p key={text}>{text}</p>)}</details>
    <p><strong>AI review: {data.advisory?.status || "Not requested"}</strong>{data.advisory?.stale ? " · Review is not current" : ""}</p>
    {data.advisory?.text && <p style={{whiteSpace: "pre-wrap"}}>{data.advisory.text}</p>}
    <small>AI commentary is advisory only. It cannot change the evidence status, risk limits, models or orders.</small>
  </section>;
}
