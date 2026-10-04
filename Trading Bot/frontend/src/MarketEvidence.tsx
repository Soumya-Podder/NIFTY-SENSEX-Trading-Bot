type Data = Record<string, any>;
const time = (stamp: string) => new Date(stamp).toLocaleString("en-IN", {timeZone: "Asia/Kolkata"}) + " IST";
const names: Data = {UP: "Index up", DOWN: "Index down", FLAT: "Index flat", TARGET_FIRST: "Target first", STOP_FIRST: "Stop first", NEITHER: "Neither barrier", NET_PROFIT: "Actual net profit"};

// Zone charts live in MarketTerminal. Keep only distinct recorded outcome evidence here.
export function MarketEvidence({estimate}: {estimate?: Data}) {
 const statistics = Object.entries(names).filter(([key]) => estimate?.estimates?.[key]);
 if (!statistics.length) return null;
 return <details className="market-evidence workspace-disclosure">
  <summary>Historical outcome evidence <small>{estimate?.samples ?? 0} distinct-session examples</small></summary>
  <div className="market-evidence-body">
   <p>{estimate?.scope ? `${estimate.scope.strategy_version} · ${estimate.scope.option_type} · ${estimate.scope.regime} · ${estimate.scope.horizon_minutes}-minute horizon` : "Recorded option-candidate outcomes"}</p>
   {estimate?.as_of && <small>{estimate.source === "LAST_HISTORICAL_SCOPE" ? "Historical example" : "Candidate assessed"} {time(estimate.as_of)}</small>}
   <div className="outcome-statistics">{statistics.map(([key, label]) => {
    const row = estimate!.estimates[key];
    return <div key={key}><span>{label}</span><strong>{(row.estimate*100).toFixed(1)}%</strong><small>95% interval {(row.low*100).toFixed(0)}–{(row.high*100).toFixed(0)}%</small></div>;
   })}</div>
   {estimate?.reason && <p>{estimate.reason}</p>}
   <p>{estimate?.samples ?? 0} distinct-session examples / {estimate?.minimum_sessions ?? 30} required. Historical frequencies for executed replay trades, not a calibrated forecast. Target/stop refer to original premium barriers; net profit refers to actual exits after costs.</p>
   {estimate?.barrier_reason && <p>{estimate.barrier_reason}</p>}
  </div>
 </details>;
}
