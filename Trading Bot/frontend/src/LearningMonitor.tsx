import { useEffect, useRef, useState } from "react";
import { evidenceMetrics, evidenceStamp, evidenceTone, learningGroup, learningGroups, learningSummary, monitorCurrent } from "./learningView";
import type { Evidence, LearningGroup } from "./learningView";
import "./learning.css";

const human = (value?: string) => value ? value.replace(/_/g, " ").toLowerCase() : "Not reported";
const number = (value?: number) => typeof value === "number" && Number.isFinite(value) ? value.toLocaleString("en-IN") : "—";
const money = (value?: number) => typeof value === "number" && Number.isFinite(value)
  ? value.toLocaleString("en-IN", { style: "currency", currency: "INR" }) : "Not recorded";
const date = (value?: string) => value && Number.isFinite(Date.parse(value))
  ? new Date(value).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" }) + " IST" : "No evidence timestamp";

function AgentDetails({ agent }: { agent: Evidence }) {
  const fit = agent.last_fitted_validation;
  return <aside className="learning-inspector" id="learning-agent-details" tabIndex={-1} aria-label="Selected agent evidence">
    <div className="learning-kicker">Evidence inspector</div>
    <h3>{agent.id}</h3>
    <span className={"learning-badge tone-" + evidenceTone(agent)}>{human(agent.status)}</span>
    <p className="learning-reason">{agent.reason || "No explanation has been recorded for this agent."}</p>
    <dl className="learning-facts">
      <div><dt>Latest validation</dt><dd>{human(agent.validation || agent.overfitting?.status)}</dd></div>
      <div><dt>Improvement proven</dt><dd>{agent.self_improvement_proven === true ? "Yes · recorded by auditor" : "Not established"}</dd></div>
      <div><dt>Evidence recorded</dt><dd>{date(agent.last_evidence_at)}</dd></div>
      {agent.learning_eligible != null && <div><dt>Learning eligible</dt><dd>{agent.learning_eligible ? "Yes" : "No"}</dd></div>}
      {agent.learning_attempts != null && <div><dt>Recorded learning attempts</dt><dd>{number(agent.learning_attempts)}</dd></div>}
      {agent.candidate_models != null && <div><dt>Candidate models</dt><dd>{number(agent.candidate_models)}</dd></div>}
      {agent.active_model_ids && <div><dt>Active model IDs</dt><dd>{agent.active_model_ids.join(", ") || "None"}</dd></div>}
      {agent.forward_tagged_episodes != null && <div><dt>Model-attributed forward episodes</dt><dd>{number(agent.forward_tagged_episodes)}</dd></div>}
      {agent.saved_policy_version && <div><dt>Saved / active policy</dt><dd>{agent.saved_policy_version} / {agent.active_policy_version || "None"}</dd></div>}
      {agent.source_run && <div><dt>Source run</dt><dd>{agent.source_run}</dd></div>}
    </dl>
    {agent.required_evidence && <div className="learning-callout"><strong>Evidence required</strong><p>{agent.required_evidence}</p></div>}
    {!!agent.overfitting?.reasons?.length && <div className="learning-callout"><strong>Validation findings</strong><ul>{agent.overfitting.reasons.map((reason: string) => <li key={reason}>{reason}</li>)}</ul></div>}
    {fit?.test_trades != null && <details className="learning-disclosure" open>
      <summary>Last fitted candidate</summary>
      <div className="learning-disclosure-body">
        <p>{number(fit.train_trades)} training trades / {number(fit.test_trades)} holdout trades</p>
        <p>{fit.test_from || "Unknown start"} – {fit.test_end || "Unknown end"}</p>
        <dl className="learning-facts">
          <div><dt>Selected holdout net P&amp;L</dt><dd>{money(fit.filter_metrics?.net_pnl)}</dd></div>
          <div><dt>Baseline net P&amp;L</dt><dd>{money(fit.baseline?.net_pnl)}</dd></div>
          <div><dt>Brier score increase</dt><dd>{fit.holdout_brier_gap?.toFixed(3) ?? "Not recorded"}</dd></div>
        </dl>
        <p>An increase can indicate poorer generalization or changed market conditions.</p>
        <p>Full replay: {fit.overfitting_checks ? fit.overfitting_checks.passed ? "Passed; forward improvement still unproven" : fit.overfitting_checks.reasons?.join("; ") || "Not passed" : "Not recorded"}.</p>
      </div>
    </details>}
    {agent.data_lineage && <p className="learning-footnote">Input lineage: {human(agent.data_lineage)}.</p>}
  </aside>;
}

export default function LearningMonitor({ data, online = false }: { data?: Evidence; online?: boolean }) {
  const [group, setGroup] = useState<LearningGroup>("entry_model");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [paused, setPaused] = useState(false);
  const [visible, setVisible] = useState(!document.hidden);
  const [now, setNow] = useState(Date.now);
  const [changedIds, setChangedIds] = useState<string[]>([]);
  const previous = useRef<Record<string, string>>({});
  const current = monitorCurrent(data, online, now);
  const agentSignature = JSON.stringify(Object.fromEntries((data?.agents || []).map((agent: Evidence) => [agent.id, evidenceStamp(agent)])));

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 5000);
    const visibility = () => { setVisible(!document.hidden); setNow(Date.now()); };
    document.addEventListener("visibilitychange", visibility);
    return () => { window.clearInterval(timer); document.removeEventListener("visibilitychange", visibility); };
  }, []);

  useEffect(() => {
    const next: Record<string, string> = JSON.parse(agentSignature);
    const changes = Object.keys(next).filter(id => previous.current[id] && previous.current[id] !== next[id]);
    previous.current = next;
    setChangedIds(current ? changes : []);
    if (current && changes.length) {
      const timer = window.setTimeout(() => setChangedIds([]), 2400);
      return () => window.clearTimeout(timer);
    }
  }, [agentSignature, current]);

  if (!data) return <section className="panel spaced learning-workspace"><div className="learning-empty">
    <h2>Learning observatory</h2><p>Learning evidence is unavailable. The view will populate when the monitor reports its first snapshot.</p>
  </div></section>;

  const { agents, fitted, proven, withEvidence } = learningSummary(data);
  const matching = agents.filter(agent => (group === "all" || learningGroup(agent) === group)
    && (agent.id + " " + human(agent.status) + " " + human(agent.validation)).toLowerCase().includes(query.trim().toLowerCase()));
  const selected = matching.find(agent => agent.id === selectedId) || matching[0];
  const comparison = data.forward_comparison || {};
  const audit = data.individual_agent_audit;
  const loss = audit?.loss_investigation;
  const training = current && data.training_now === true;
  const moving = !paused && visible && current;
  const scale = Math.max(1, ...agents.filter(agent => agent.kind === "entry_model").map(agent => agent.training_attempts || 0));
  const inspect = (id: string) => {
    setSelectedId(id);
    if (window.matchMedia("(max-width: 950px)").matches) {
      window.requestAnimationFrame(() => document.getElementById("learning-agent-details")?.focus());
    }
  };

  return <section className={"panel spaced learning-workspace " + (moving ? "learning-motion" : "learning-still")} aria-labelledby="learning-title">
    <header className="learning-header">
      <div><div className="learning-kicker">Individual agent audit · unvalidated paper observation</div>
        <h2 id="learning-title">Learning observatory<span className="learning-version">{agents.length} roles</span></h2>
        <p>Follow the evidence from training attempts to validated improvement.</p>
      </div>
      <div className="learning-header-actions">
        <span className={"learning-connection " + (current ? "is-current" : "")}><i aria-hidden="true" />{current ? "Monitor connected" : online ? "Monitor stale or unavailable" : "Offline · last snapshot"}</span>
        <button type="button" className="learning-motion-button" aria-pressed={paused} onClick={() => setPaused(value => !value)}>{paused ? "Resume motion" : "Pause motion"}</button>
      </div>
    </header>

    <div className="learning-overview">
      <div className="learning-heartbeat">
        <div className="learning-orbit" aria-hidden="true"><div className="learning-orbit-track" /><div className="learning-orbit-track inner" />
          <div className="learning-orbit-core"><svg viewBox="0 0 48 48" fill="none"><path d="M5 25h9l5-13 9 25 5-12h10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg></div>
        </div>
        <div className="learning-kicker">Monitor heartbeat</div>
        <h3>{current ? "Observing evidence" : "Snapshot only"}</h3>
        <p>{!current ? "Training status not current" : training ? "Training in progress" : "Training idle"}</p>
        <small>Checked {date(data.checked_at)}</small>
      </div>
      <div className="learning-evidence-overview">
        <div className="learning-overview-title"><span>Recorded learning evidence</span><span className="learning-badge tone-waiting">{data.self_improvement_proven === true ? "Improvement recorded" : "Improvement unproven"}</span></div>
        <div className="learning-stages">
          {[
            { label: "Training runs", value: data.total_training_attempts, note: "Recorded runs, including retries", active: training },
            { label: "Fitted candidates", value: fitted, note: "Across entry strategies; not approvals", active: false },
            { label: "Deployed models", value: data.deployed_models, note: current ? "Current engine session" : "At last monitor snapshot", active: false },
            { label: "Proven improvement", value: proven, note: "Roles with auditor-confirmed evidence", active: false },
          ].map((stage, index) => <div className={"learning-stage " + (stage.active ? "is-training" : "")} key={stage.label}>
            <div className="learning-stage-top"><span>0{index + 1}</span><i aria-hidden="true" /></div>
            <strong>{number(stage.value)}</strong><span>{stage.label}</span><small>{stage.note}</small>
          </div>)}
        </div>
        <div className="learning-evidence-coverage"><span>{withEvidence} of {agents.length} roles have timestamped evidence</span>
          <div className="learning-coverage-track" aria-hidden="true"><i style={{ transform: "scaleX(" + (agents.length ? withEvidence / agents.length : 0) + ")" }} /></div>
          <small>Evidence coverage · not learning progress or a success probability</small>
        </div>
        <p className="learning-motion-caption">Orbit = current monitor heartbeat. Cards glow only when their recorded evidence changes. Training pulses only while the backend reports training.</p>
      </div>
    </div>

    <div className="learning-service-strip">
      <div><span className={"learning-service-dot " + (current && data.quote_recording?.worker_alive ? "is-current" : "")} /><strong>Quote recorder</strong><span>{current ? data.quote_recording?.worker_alive ? "Worker running" : "Unavailable" : "Status not current"}</span><small>{number(data.quote_recording?.dropped_this_run)} dropped observations</small></div>
      <div><span className={"learning-service-dot " + (current && comparison.worker_alive && comparison.stale === false ? "is-current" : "")} /><strong>Forward comparison</strong><span>{human(comparison.status)}</span><small>{current && comparison.worker_alive && comparison.stale === false ? "Worker current" : "Worker freshness unconfirmed"}</small></div>
      <div><span className="learning-service-dot" /><strong>Overfitting gate</strong><span>{human(data.overfitting_status)}</span><small>Activity and profit alone do not prove improvement</small></div>
    </div>

    <div className="learning-explorer">
      <div className="learning-explorer-heading"><div><div className="learning-kicker">Agent directory</div><h3>Inspect each role</h3></div>
        <label className="learning-search"><span>Search agents</span><input type="search" name="learning-agent-search" autoComplete="off" placeholder="Search name or status…" value={query} onChange={event => setQuery(event.target.value)} /></label>
      </div>
      <div className="learning-filters" role="group" aria-label="Filter agent roles">{learningGroups.map(item => <button type="button" key={item.id} aria-pressed={group === item.id} onClick={() => setGroup(item.id)}>{item.label}<span>{item.id === "all" ? agents.length : agents.filter(agent => learningGroup(agent) === item.id).length}</span></button>)}</div>
      <div className="learning-directory-status" role="status">{matching.length} {matching.length === 1 ? "role" : "roles"} shown · Select a card to inspect its evidence</div>
      <div className="learning-directory">
        <div className="learning-card-grid">
          {matching.map(agent => <button type="button" className={"learning-agent-card tone-" + evidenceTone(agent) + (changedIds.includes(agent.id) ? " evidence-changed" : "")} key={agent.id}
            aria-pressed={selected?.id === agent.id} aria-controls="learning-agent-details" aria-label={"Inspect " + agent.id} onClick={() => inspect(agent.id)}>
            <span className="learning-card-heading"><span className="learning-agent-glyph" aria-hidden="true">{learningGroup(agent) === "controls" ? "◇" : agent.kind === "entry_model" ? "⌁" : "◎"}</span><strong>{agent.id}</strong><span className="learning-card-open" aria-hidden="true">↗</span></span>
            <span className="learning-badge">{human(agent.status)}</span>
            <span className="learning-card-metrics">{evidenceMetrics(agent).map(metric => <span key={metric.label}><b>{number(metric.value)}</b><small>{metric.label}</small></span>)}</span>
            {agent.kind === "entry_model" && <span className="learning-attempt-chart" aria-label={number(agent.training_attempts) + " attempts, " + number(agent.fitted_candidates) + " fitted candidates. Bars use a shared " + scale + "-attempt scale."}>
              <span><i style={{ transform: "scaleX(" + Math.min(1, (agent.training_attempts || 0) / scale) + ")" }} /></span>
              <span className="fitted"><i style={{ transform: "scaleX(" + Math.min(1, (agent.fitted_candidates || 0) / scale) + ")" }} /></span>
              <small>Attempts / fitted · shared scale {scale}</small>
            </span>}
            <span className="learning-card-validation"><span>Validation</span><strong>{human(agent.validation || agent.overfitting?.status)}</strong></span>
            <span className="learning-card-time">{date(agent.last_evidence_at)}</span>
          </button>)}
          {!matching.length && <div className="learning-empty"><h3>No matching agents</h3><p>Try another name or role group.</p><button type="button" onClick={() => { setQuery(""); setGroup("all"); }}>Show all agents</button></div>}
        </div>
        {selected && <AgentDetails key={selected.id} agent={selected} />}
      </div>
    </div>

    <div className="learning-audit-notes">
      <details className="learning-disclosure"><summary>Audit findings &amp; data coverage <span>{data.alerts?.length || 0} notices</span></summary><div className="learning-disclosure-body">
        <ul>{(data.alerts || []).map((text: string) => <li key={text}>{text}</li>)}</ul>
        {data.history_truncated && <p>Historical records reached the monitor limit; these counts are incomplete.</p>}
        {(data.downloaded_data || []).map((item: Evidence) => <p key={item.symbol}>{item.symbol} underlying candles: {item.present ? "file present" : "file not found"}. File presence does not prove training coverage.</p>)}
        {audit && <p>{audit.agents?.length || 0} architecture roles audited · {human(audit.overfitting_status)} · Authority: audit only, no order or risk control.</p>}
        {loss && <p>Loss Investigator: {loss.losses ?? 0} losing episodes · {loss.classified ?? 0} classified hypotheses. Categories: {Object.entries(loss.categories || {}).map(([name, count]) => human(name) + " " + count).join(" · ") || "none"}. No automatic strategy rewrite or loss chasing is permitted.</p>}
        <p>A separate reference paper account compares frozen learned entries with fixed rules. Its profit is never added to the primary account. A completed comparison alone does not prove improvement.</p>
        {comparison.session && <p>Forward session: {comparison.session}</p>}
        {(comparison.issues || []).map((issue: string) => <p key={issue}>{issue}</p>)}
        {(data.limits || []).map((text: string) => <p key={text}>{text}</p>)}
      </div></details>
      <details className="learning-disclosure"><summary>AI evidence review <span>{human(data.advisory?.status)}{data.advisory?.stale ? " · not current" : ""}</span></summary><div className="learning-disclosure-body">
        <p className="learning-advisory">{data.advisory?.text || "No AI commentary is available for this snapshot."}</p>
        <p>Advisory only. AI commentary cannot change evidence status, risk limits, models or orders.</p>
      </div></details>
    </div>
  </section>;
}
