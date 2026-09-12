type Data = Record<string, any>;
const rupees = (n: number | null) => n == null ? "—" : n.toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
const time = (s?: string) => s ? new Date(s).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" }) : "—";

export default function StrategyPortfolio({ data }: { data?: Data }) {
  if (!data) return null;
  return <section className="panel spaced">
    <div className="section-heading"><div><div className="eyebrow">THREE STRATEGIES / ONE SHARED PAPER ACCOUNT</div><h2>Strategy selection</h2></div><span>Checked {time(data.checked_at)} IST</span></div>
    <p>{data.reason}. Paper evidence collection is unvalidated; a profitable day is not guaranteed.</p>
    <p>{data.selection_rule}</p>
    <div className="table-wrap"><table><thead><tr><th>Index</th><th>Strategy</th><th>Market context</th><th>Status</th><th>Current reason</th></tr></thead><tbody>
      {(data.evaluations || []).map((r: Data) => <tr key={`${r.symbol}:${r.id}`}><td>{r.symbol}</td><td>{r.name}</td><td>{r.regime || "—"}</td><td>{r.status}</td><td>{r.reason}</td></tr>)}
      {!data.evaluations?.length && <tr><td colSpan={5}>Waiting for the next market evaluation.</td></tr>}
    </tbody></table></div>
    {!!data.offers?.length && <><h3>Eligible opportunities</h3><div className="table-wrap"><table><thead><tr><th>Rank</th><th>Strategy / index</th><th>All-in stop risk</th><th>Net reward at target</th><th>Reward / risk</th><th>Evidence</th></tr></thead><tbody>
      {data.offers.map((o: Data, i: number) => <tr key={`${o.signal_id}:${o.contract_id}`}><td>{i+1}</td><td>{o.strategy} · {o.symbol}</td><td>{rupees(o.risk)}</td><td>{rupees(o.net_reward_at_target)}</td><td>{o.net_reward_risk.toFixed(2)}</td><td>{o.evidence} · {o.samples} outcomes</td></tr>)}
    </tbody></table></div></>}
    {!!data.offers?.length && <div>{data.offers.map((o: Data) => <p key={`ml:${o.signal_id}:${o.contract_id}`}>{o.strategy} · {o.symbol}: {o.ml_quality?.probability == null ? "No validated ML probability available" : `Estimated positive-net-exit probability ${(o.ml_quality.probability * 100).toFixed(1)}% · ${o.ml_quality.status}`} · {o.exit_policy}</p>)}</div>}
    <h3>Executed paper performance</h3>
    <div className="table-wrap"><table><thead><tr><th>Strategy</th><th>Closed positions</th><th>Wins / losses</th><th>Net P&amp;L</th><th>Estimated costs</th><th>Evidence</th></tr></thead><tbody>
      {(data.performance || []).map((s: Data) => <tr key={s.id}><td>{s.name}</td><td>{s.closed_trades}</td><td>{s.wins} / {s.losses}</td><td>{rupees(s.net_pnl)}</td><td>{rupees(s.estimated_costs)}</td><td>Unvalidated paper</td></tr>)}
    </tbody></table></div>
    <p>{data.historical_scope}. Candidate signals and unselected opportunities are not counted as filled trades.</p>
    <details><summary>Recent candidate decisions and data blockers</summary>{(data.opportunities || []).map((o: Data) => <p key={o.id}><strong>{o.symbol} · {o.strategy_name}</strong> · {o.status}: {o.reason || "Selected for the shared account"} · {time(o.evaluated_at)} IST</p>)}{!data.opportunities?.length && <p>No candidate decisions recorded for this strategy portfolio yet.</p>}</details>
  </section>;
}
