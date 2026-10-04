export type Row = Record<string, any>;
export const CHART_PERIODS = ["2m", "5m", "15m", "30m", "1h", "2h", "4h"];
export const price = (n: unknown) => typeof n === "number" && Number.isFinite(n) ? n.toLocaleString("en-IN", {maximumFractionDigits: 2}) : "—";
export const ist = (v: string | number) => new Date(typeof v === "number" ? v * 1000 : v).toLocaleString("en-IN", {timeZone: "Asia/Kolkata", day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit"});

/** Wheel up narrows the price span, anchored to the price beneath the cursor. */
export function wheelPriceRange(range: {from: number; to: number}, anchor: number, delta: number) {
 const span = range.to-range.from;
 if (![range.from, range.to, anchor, delta].every(Number.isFinite) || span <= 0) return null;
 anchor = Math.max(range.from, Math.min(range.to, anchor));
 const nextSpan = Math.max(.1, Math.min(Math.max(anchor, 1)*2, span*Math.exp(Math.max(-250, Math.min(250, delta))*.002)));
 const from = Math.max(.01, anchor-(anchor-range.from)/span*nextSpan);
 return {from, to: from+nextSpan};
}

export function visibleZones(zones: Row[], layers: string[], perSide = 5): Row[] {
 return [...new Set(layers)].flatMap(period => ["SUPPORT", "RESISTANCE", "AT_ZONE"].flatMap(relation => {
  const seen = new Set<string>();
  return zones.filter(z => z.timeframe === period && z.relation === relation &&
    [z.lower, z.upper, z.price, z.distance_points].every(Number.isFinite) && z.lower > 0 && z.upper >= z.lower)
   .sort((a, b) => a.distance_points-b.distance_points || Date.parse(b.available_at)-Date.parse(a.available_at))
   .filter(z => { const key = `${z.lower}:${z.upper}:${z.price}`; if (seen.has(key)) return false; seen.add(key); return true; })
   .slice(0, perSide)
   .map((z, i) => ({...z, label: `${period.replace("h", "H").replace("d", "D")} ${relation === "SUPPORT" ? "S" : relation === "RESISTANCE" ? "R" : "Z"}${i+1}`}));
 }));
}

export function chartBias(candles: Row[]) {
 const bars = candles.filter(c => c.complete);
 if (bars.length < 22) return {label: "Insufficient history", reason: "Needs 22 completed chart candles for EMA context."};
 const ema = (span: number) => {
  let value = bars[0].close, previous = value;
  for (const bar of bars.slice(1)) { previous = value; value += (bar.close-value)*2/(span+1); }
  return {value, previous};
 };
 const fast = ema(9), slow = ema(21), last = bars[bars.length-1].close;
 const up = last > fast.value && fast.value > slow.value && slow.value > slow.previous;
 const down = last < fast.value && fast.value < slow.value && slow.value < slow.previous;
 return {label: up ? "Bullish alignment" : down ? "Bearish alignment" : "Mixed / neutral",
  reason: "Completed-candle price, EMA 9/21 alignment and EMA 21 slope. Chart context only; not a forecast or entry instruction."};
}

/** Incremental last-bar updates; history corrections trigger one full reset. */
export function syncSeries(series: any, previous: Row[], next: Row[]) {
 const same = (a: Row, b: Row) => JSON.stringify(a) === JSON.stringify(b);
 const prefix = previous.length > 0 && next.length >= previous.length &&
  previous.slice(0, -1).every((bar, i) => same(bar, next[i]));
 if (!prefix || (next[previous.length-1]?.time !== previous[previous.length-1]?.time)) series.setData(next);
 else for (let i = previous.length-1; i < next.length; i++) if (!same(previous[i] || {}, next[i])) series.update(next[i]);
 return next;
}

export function tradeMarkers(candles: Row[], trades: Row[], period: string) {
 const minutes = period.endsWith("h") ? parseInt(period)*60 : parseInt(period);
 const seen = new Set<string>(), markers: Row[] = [];
 for (const trade of trades) for (const field of ["entry_ts", "exit_ts"]) {
  const stamp = Date.parse(trade[field])/1000;
  const bar = candles.find(c => c.time <= stamp && stamp < (c.end_time ?? c.time+minutes*60));
  const key = `${trade.contract_id}|${field}|${stamp}`;
  if (!bar || seen.has(key)) continue;
  seen.add(key);
  const entry = field === "entry_ts";
  markers.push({time: bar.time, position: entry ? "belowBar" : "aboveBar", shape: entry ? "arrowUp" : "arrowDown",
   color: entry ? "#38bdf8" : "#f59e0b", text: `${entry ? "Paper buy" : "Paper exit"} ${trade.option_type || ""}`});
 }
 return markers.sort((a, b) => a.time-b.time);
}

export function volumeChangeMarkers(bars: Row[]) {
 return bars.filter((bar, i) => bar.contract_id && (i === 0 || bar.contract_id !== bars[i-1].contract_id || bar.expiry !== bars[i-1].expiry))
  .map(bar => ({time: bar.time, position: "aboveBar", shape: "arrowDown", color: "#94a3b8", text: `Futures ${bar.contract_id} · ${bar.expiry}`}));
}
