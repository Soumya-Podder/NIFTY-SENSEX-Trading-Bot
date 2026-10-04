import MarketContext from "./MarketContext";
type Data = Record<string, any>;
const rupees = (n: number | null) => n == null ? "—" : n.toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
const time = (s?: string) => s ? new Date(s).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" }) : "—";

export default function StrategyPortfolio({ data }: { data?: Data }) {
  if (!data) return null;
  return <details className="panel spaced workspace-disclosure">
    <summary>Strategy details <small>{data.offers?.length || 0} eligible · Checked {time(data.checked_at)} IST</small></summary>
    <div className="disclosure-content">
    <p>{data.reason}</p>
    <details><summary>Market data health</summary>
      <div className="table-wrap"><table><thead><tr><th>Index</th><th>Completed candles</th><th>Last bar · IST</th><th>Recovery</th><th>Option chain</th></tr></thead><tbody>
       {Object.entries(data.data_health || {}).map(([symbol, value])=>{const h=value as Data;return <tr key={symbol}>
        <td>{symbol}</td><td>{h.candle_error || h.candle_reason || h.candle_status || "Waiting"}</td><td>{time(h.last_bar)}</td>
        <td>{h.repair_successes || 0} recovered / {h.repair_attempts || 0} attempts{h.repair_error ? ` · ${h.repair_error}` : ""}</td>
        <td>{h.chain_error || (h.chain_updated_at ? `Updated ${time(h.chain_updated_at)}` : "Awaiting update")}</td>
       </tr>;})}
       {!Object.keys(data.data_health || {}).length && <tr><td colSpan={5}>Awaiting the next market data cycle.</td></tr>}
      </tbody></table></div>
    </details>
    {data.option_screen ? <details><summary>Active option-buying screen · {data.option_screen.version}</summary>
      <p>ATM eligible · preferred |Delta| 0.45–0.60 · 0.30–0.45 requires an aligned trend · observed Greeks no older than {data.option_screen.max_greek_age_seconds}s.</p>
      <p>Spread ≤ {(data.option_screen.max_spread_pct * 100).toFixed(1)}% of midpoint · full-lot depth · expiry-day entries excluded · minimum net reward/risk {data.option_screen.min_net_reward_risk}:1.</p>
      <p>{data.option_screen.target_policy}. IV percentile: comparable history required. These filters are unvalidated paper hypotheses.</p>
    </details> : null}
    <MarketContext data={data.market_context} />
    <div className="table-wrap"><table><thead><tr><th>Index</th><th>Strategy</th><th>Market context</th><th>Status</th><th>Current reason</th></tr></thead><tbody>
      {(data.evaluations || []).map((r: Data) => <tr key={`${r.symbol}:${r.id}`}><td>{r.symbol}</td><td>{r.name}</td><td>{r.regime || "—"}</td><td>{r.status}</td><td>{r.reason}</td></tr>)}
      {!data.evaluations?.length && <tr><td colSpan={5}>Waiting for the next market evaluation.</td></tr>}
    </tbody></table></div>
    {!!data.offers?.length && <><h3>Eligible opportunities</h3><div className="table-wrap"><table><thead><tr><th>Rank</th><th>Strategy / index</th><th>All-in stop risk</th><th>Net reward at target</th><th>Reward / risk</th><th>Evidence</th><th>Model / exit policy</th></tr></thead><tbody>
      {data.offers.map((o: Data, i: number) => <tr key={`${o.signal_id}:${o.contract_id}`}><td>{i+1}</td><td>{o.strategy} · {o.symbol}</td><td>{rupees(o.risk)}</td><td>{rupees(o.net_reward_at_target)}</td><td>{o.net_reward_risk.toFixed(2)}</td><td>{o.evidence} · {o.samples} outcomes</td><td>{o.ml_quality?.probability == null ? "No learned filter deployed" : `Positive-net outcome model score ${(o.ml_quality.probability * 100).toFixed(1)}% · ${o.ml_quality.status} · not a calibrated trading probability`} · {o.exit_policy}</td></tr>)}
    </tbody></table></div></>}

    {(data.performance || []).some((s: Data) => s.closed_trades > 0) && <><h3>Performance by strategy · unvalidated paper</h3>
    <div className="table-wrap"><table><thead><tr><th>Strategy</th><th>Closed positions</th><th>Wins / losses</th><th>Net P&amp;L</th><th>Estimated costs</th></tr></thead><tbody>
      {(data.performance || []).filter((s: Data) => s.closed_trades > 0).map((s: Data) => <tr key={s.id}><td>{s.name}</td><td>{s.closed_trades}</td><td>{s.wins} / {s.losses}</td><td>{rupees(s.net_pnl)}</td><td>{rupees(s.estimated_costs)}</td></tr>)}
    </tbody></table></div>
    </>}
    <details><summary>Selection method &amp; evidence</summary><p>{data.selection_rule}</p><p>{data.historical_scope}. Candidate signals are not filled trades. Paper performance remains unvalidated.</p></details>
    <details><summary>Recent candidate decisions and data blockers</summary>{(data.opportunities || []).map((o: Data) => <p key={o.id}><strong>{o.symbol} · {o.strategy_name}</strong> · {o.status}: {o.reason || "Selected for the shared account"} · {time(o.evaluated_at)} IST</p>)}{!data.opportunities?.length && <p>No candidate decisions recorded for this strategy portfolio yet.</p>}</details>
    </div>
  </details>;
}
