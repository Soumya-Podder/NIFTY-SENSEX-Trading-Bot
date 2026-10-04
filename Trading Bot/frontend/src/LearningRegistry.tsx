import { useState } from "react";
import { registrySummary } from "./activityView";
type Data = Record<string, any>;

export default function LearningRegistry({ rows, busy, online, onReview, onDetail }: Data) {
  const [reviewer, setReviewer] = useState("");
  const [paused, setPaused] = useState(false);
  const { pending, approved, rejected } = registrySummary(rows);
  return <section className={"panel spaced review-workspace " + (paused || !online ? "activity-still" : "")} aria-labelledby="registry-title">
    <header className="activity-header"><div><div className="activity-kicker">Challenger / validation / human review</div><h2 id="registry-title">Learning registry</h2><p>A clear path from candidate evidence to a reviewed policy.</p></div>
      <div className="activity-header-actions"><span className="activity-badge">{pending.length} awaiting review</span><button type="button" className="activity-button" aria-pressed={paused} onClick={() => setPaused(value => !value)}>{paused ? "Resume registry motion" : "Pause registry motion"}</button></div>
    </header>
    <div className="review-path" aria-label="Candidate review process">
      {[
        { icon: "01", title: "Challenger", value: rows.length, text: "Candidate records received" },
        { icon: "02", title: "Validated queue", value: pending.length, text: "Passed validation; awaiting a person" },
        { icon: "03", title: "Human review", value: approved.length, text: "Approval records · not active-model count" },
        { icon: "04", title: "Session boundary", value: "After approval", text: "Approved policy eligible from its effective date" },
      ].map((step, index) => <div className={"review-step " + (index === 1 && pending.length ? "review-awaiting" : "")} key={step.title}>
        <span className="review-step-node" aria-hidden="true">{step.icon}</span><span className="activity-kicker">{step.title}</span><strong>{step.value}</strong><small>{step.text}</small>
      </div>)}
    </div>
    <div className="review-guard"><span aria-hidden="true">◇</span><p>A validated challenger stays inactive until a named reviewer approves it. Approval applies from the next available session and cannot change risk, sizing or protection rules.</p></div>
    {!online && <p className="activity-offline">Disconnected · showing the last registry snapshot. Review actions are unavailable.</p>}
    {pending.length ? <div className="review-queue">
      <label className="reviewer-field">Reviewer name<input name="learning-reviewer" autoComplete="name" maxLength={120} value={reviewer} onChange={event => setReviewer(event.target.value)} placeholder="Enter reviewer name…" /></label>
      <p className="activity-caption">Each action applies only to its selected candidate.</p>
      {pending.map((candidate: Data) => <article className="review-candidate" key={candidate.source_run_id + ":" + candidate.agent}>
        <div><span className="activity-badge activity-waiting">Awaiting human review</span><h3>{candidate.agent} · candidate v{candidate.version}</h3><p>{candidate.blocked_value ? "Exclude " + candidate.blocked_value : "Allow " + (candidate.allowed_value || "candidate context")}</p><small>Source run: {candidate.source_run_id}</small></div>
        <div className="review-candidate-actions"><button type="button" className="activity-button" onClick={() => onDetail(candidate)}>Inspect evidence</button>
          <button type="button" className="activity-button review-approve" disabled={busy || !online || !reviewer.trim()} onClick={() => onReview(candidate.source_run_id + ":" + candidate.agent, "approve", reviewer.trim())}>Approve next session</button>
          <button type="button" className="activity-button" disabled={busy || !online || !reviewer.trim()} onClick={() => onReview(candidate.source_run_id + ":" + candidate.agent, "reject", reviewer.trim())}>Reject</button>
        </div>
      </article>)}
    </div> : <div className="review-empty"><div className="review-empty-icon" aria-hidden="true"><svg viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="11" y="8" width="26" height="33" rx="5" /><path d="M18 7v5h12V7M18 21h12m-12 6h8m-8 6h4" /></svg></div><div><h3>{online ? "No validated candidates awaiting review" : "Review queue is not current"}</h3><p>{online ? "The queue will update when a challenger passes validation. There is no policy approval to make right now." : "Connect to the engine to confirm the current review queue."}</p></div></div>}
    <details className="review-history"><summary>Review history <span>{approved.length} approved · {rejected.length} rejected · {rows.length} total records</span></summary>
      <p className="activity-caption">Recorded approvals do not establish current deployment or improved performance.</p>
      {rows.length ? rows.map((candidate: Data) => <button type="button" className="review-history-row" key={candidate.source_run_id + ":" + candidate.agent + ":" + candidate.version} onClick={() => onDetail(candidate)}>
        <span><strong>{candidate.agent} · v{candidate.version}</strong><small>{candidate.reviewed_by ? "Reviewer: " + candidate.reviewed_by : "No reviewer recorded"}</small></span>
        <span><b>{candidate.validation_status === "PROMOTED" ? "Approved record" : candidate.validation_status?.replaceAll("_", " ") || "Status unavailable"}</b><small>Effective from: {candidate.effective_from || "Not scheduled"}</small></span><span aria-hidden="true">↗</span>
      </button>) : <p className="activity-caption">No candidate records available.</p>}
    </details>
  </section>;
}
