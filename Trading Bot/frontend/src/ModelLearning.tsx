type Data = Record<string, any>;
export default function ModelLearning({data, onTrain, busy}: {data?: Data; onTrain: () => void; busy: boolean}) {
  if (!data) return null;
  const run = data.latest_training || {};
  const active = Object.keys(data.session?.models || {}).length;
  return <section className="panel spaced">
    <div className="section-heading"><div><div className="eyebrow">BACKTEST LEARNING / PAPER ONLY</div><h2>Entry-quality model</h2></div>
      <button className="ghost-button" disabled={busy || data.training} onClick={onTrain}>{data.training ? "Training…" : "Train from latest report"}</button></div>
    <p><strong>{run.status?.replaceAll("_", " ") || "Not trained"}</strong> · {active} model(s) frozen for this session.</p>
    <p>{run.reason || "No validated model is active. The baseline strategies continue collecting unvalidated paper observations."}</p>
    {run.eligible_trades != null && <p>{run.eligible_trades} eligible net-cost trades · {run.excluded_trades} excluded because required evidence is missing.</p>}
    {(run.models || []).map((m: Data) => <p key={m.scope}><strong>{m.scope}</strong>: {m.status} · {m.reason || `${m.days ?? 0} sessions available`}
      {m.replay_metrics && <> · Holdout net P&amp;L ₹{m.replay_metrics.net_pnl.toFixed(2)} · profit factor {m.replay_metrics.profit_factor?.toFixed(2) ?? "undefined"}</>}</p>)}
    <p>Chronological 70/30 session split; at least 60 training trades and 30 holdout trades. Automatic activation requires unseen full-account replay, positive net expectancy, profit factor above 1.25 and improvement over the baseline. Validated models activate at a later session boundary.</p>
    <p>Adaptive exits request cost-covering stops, option-ATR trailing and observed momentum-stall exits. Stops do not guarantee an execution price. Risk limits do not learn to increase themselves.</p>
  </section>;
}
