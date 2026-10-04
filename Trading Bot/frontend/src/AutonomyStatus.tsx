type Data = Record<string, any>;
const money = (value: number) => value.toLocaleString("en-IN", {style: "currency", currency: "INR", maximumFractionDigits: 0});

export default function AutonomyStatus({data}: {data?: Data}) {
  if (!data) return null;
  const learning = data.learning || {};
  const management = Object.entries(data.management || {});
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
    </div>
    {data.learning_error && <p role="status">Learning worker: {data.learning_error}</p>}
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
