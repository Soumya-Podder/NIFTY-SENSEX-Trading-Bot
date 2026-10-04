type Data = Record<string, any>;
const number = (value: unknown, digits = 2) => typeof value === "number" && Number.isFinite(value)
  ? value.toLocaleString("en-IN", { maximumFractionDigits: digits }) : "—";

export default function MarketContext({ data }: { data?: Data }) {
  if (!data) return null;
  return <details className="market-research-context">
    <summary>Market context · research observations</summary>
    <p>Recorded for validation. These observations do not vote on trades, change risk, or represent a probability of profit.</p>
    <div className="table-wrap"><table><thead><tr><th>Index / captured at</th><th>Futures vs own VWAP</th><th>ATM ±5 positioning</th><th>Remaining-time volatility</th></tr></thead><tbody>
      {Object.entries(data).map(([symbol, context]: [string, Data]) => {
        const futures = context.futures || {};
        const oi = context.positioning || {};
        const vol = context.volatility || {};
        const change = oi.since_previous || {};
        const fallback = context.reason || "Awaiting market observations";
        return <tr key={symbol}>
          <td><strong>{symbol}</strong><div>{context.captured_at ? new Date(context.captured_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" }) + " IST" : "Not collected"}</div><small>{context.status}</small></td>
          <td>{futures.status === "OBSERVED" ? <><strong>{futures.relation} · {number(futures.distance_points)} pts</strong><div>Close {number(futures.futures_close)} · VWAP {number(futures.vwap)}</div><small>Minute-bar proxy · {futures.contract_id}</small></> : futures.reason || fallback}</td>
          <td>{oi.status === "OBSERVED" ? <><strong>PCR {number(oi.pcr)}</strong>
            <div>OI vs previous day · Call {number(oi.call_oi_change, 0)} · Put {number(oi.put_oi_change, 0)}</div>
            <small>{oi.contracts} contracts · expiry {oi.expiry}</small>
            {["OBSERVED", "PARTIAL"].includes(change.status) ? <>
              <div><strong>Since previous response · {number(change.interval_seconds, 1)} sec</strong></div>
              <div>OI Δ · Call {number(change.call_oi_change, 0)} · Put {number(change.put_oi_change, 0)}</div>
              <div>Volume Δ · Call {number(change.call_volume_change, 0)} · Put {number(change.put_volume_change, 0)}</div>
              <small>{change.matched_contracts}/{change.window_contracts} fixed contracts matched{change.long_gap ? " · Gap exceeds 2 minutes" : ""}{change.volume_resets ? " · Volume reset/correction detected" : ""}</small>
              <details><summary>Price, IV and Greek changes by contract</summary>
                {(change.contracts || []).map((contract: Data) => <div key={contract.security_id}>
                  <strong>{contract.strike} {contract.option_type}</strong> · ID {contract.security_id}
                  <div>Price Δ {number(contract.changes?.ltp)} · IV Δ {number(contract.changes?.iv)} percentage points</div>
                  <small>Delta Δ {number(contract.changes?.delta, 4)} · Gamma Δ {number(contract.changes?.gamma, 6)} · Theta Δ {number(contract.changes?.theta, 4)} · Vega Δ {number(contract.changes?.vega, 4)}</small>
                </div>)}
              </details>
            </> : <div>{change.reason || "Awaiting a second fresh chain response"}</div>}
          </> : oi.reason || fallback}</td>
          <td>{vol.status === "SCENARIO" ? <><strong>{number(vol.move_points)} index points / {number(vol.horizon_minutes)} min</strong><div>ATM IV {number(vol.iv_percent)}% · {number(vol.remaining_minutes)} min to exit</div><small>Uncalibrated movement scale, not an option-profit forecast</small></> : vol.reason || fallback}</td>
        </tr>;
      })}
    </tbody></table></div>
    <p>OI does not identify buyers, writers or institutions. Previous-day OI and changes since the last response have separate baselines. Volume changes use cumulative day volume; resets and missing fields show as unavailable. Receipt times are not exchange OI update times. VWAP compares futures with futures.</p>
  </details>;
}
