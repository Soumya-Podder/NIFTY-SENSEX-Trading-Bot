type Data = Record<string, any>;
const money = (value: number) => value.toLocaleString("en-IN", {style: "currency", currency: "INR", maximumFractionDigits: 0});

export default function AutonomyStatus({data}: {data?: Data}) {
  if (!data) return null;
  const learning = data.learning || {};
  const management = Object.entries(data.management || {});
  const recovery = data.recovery;
  const issues = Object.entries(recovery?.components || {}).filter(([, row]) => ["RETRYING", "BLOCKED"].includes((row as Data).state));
  return <section className="panel spaced autonomy-status" aria-label="Autonomous paper status">
    <div className="section-heading">
      <div><h2>Market assessment &amp; learning</h2></div>
    </div>
    <div className="autonomy-grid">
      <div><strong>Setup selection</strong><p>{data.strategies?.length || 0} setups evaluated · NIFTY / SENSEX</p></div>
      {management.length > 0 && <div><strong>Position management</strong>{management.map(([symbol, row]) => {
        const decision = row as Data;
        return <p key={symbol}><b>{symbol} · {decision.action}</b><br/>{decision.reason}</p>;
      })}</div>}
      <div><strong>Learning · {String(learning.status || "INSUFFICIENT_EVIDENCE").replace(/_/g, " ")}</strong><p>{learning.eligible_outcomes ?? 0} eligible outcomes · {learning.independent_days ?? 0} days · {learning.active_models?.length || 0} active filters</p></div>
      {recovery && <div role="status"><strong>Automatic recovery · {recovery.state}</strong><p>{issues.length ? `${issues.length} components awaiting recovery` : recovery.state === "STARTING" ? "Checking current runtime" : "Runtime checks active"}</p></div>}
    </div>
    {data.learning_error && <p role="status">Learning worker: {data.learning_error}</p>}
    {recovery && <details><summary>Automatic recovery checks &amp; history</summary>
      <p>Technical repairs run automatically. Fresh data, executable depth and risk approval are still required for every paper entry.</p>
      {issues.map(([name, value]) => {
        const row = value as Data;
        return <p key={name}><strong>{name.replace(/_/g, " ")} · {row.state}</strong><br/>{row.cause}<br/>{row.action} · {row.attempts} attempts{row.error_type ? ` · ${row.error_type}` : ""}</p>;
      })}
      <p>Last check: {recovery.checked_at || "Awaiting first check"}. Historical repairs are not proof of current entry readiness.</p>
      {(recovery.history || []).slice(-5).reverse().map((row: Data, index: number) => <p key={`${row.component}:${row.checked_at}:${index}`}><strong>{row.component.replace(/_/g, " ")} · {row.state}</strong> · {row.checked_at}<br/>{row.action}</p>)}
      {!recovery.history?.length && <p>No recovery event recorded yet.</p>}
    </details>}
    <details><summary>Research evidence and investigations</summary>
      <p>Policy {data.policy_version}. Monthly objective {money(data.monthly_net_objective)} after estimated charges; it does not change entry gates, sizing or protection.</p>
      <p>Learning activation requires at least 60 training outcomes, 30 holdout outcomes and 34 independent days, plus an independent account replay before the next-session paper filter can activate.</p>
      <p>{data.selection}</p>
      {(learning.candidates || []).map((row: Data) => <p key={row.id}>Challenger {row.id.slice(0, 8)} · {row.status} · {row.train_count} training / {row.holdout_count} holdout outcomes</p>)}
      {(learning.investigations || []).map((row: Data) => <p key={row.trade_id}>{row.category.replace(/_/g, " ")} · {money(row.pnl || 0)} · {row.exit_reason}<br/><small>{row.conclusion}</small></p>)}
      {!learning.investigations?.length && <p>No closed outcome investigation is available yet.</p>}
      {(data.limitations || []).map((text: string) => <p key={text} className="muted">{text}</p>)}
    </details>
  </section>;
}
