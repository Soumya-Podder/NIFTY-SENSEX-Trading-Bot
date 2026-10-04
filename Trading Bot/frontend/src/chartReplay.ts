import type { Row } from "./terminalView";

export const replayTime = (time: number) => new Date(time * 1000).toLocaleTimeString("en-IN", {
 timeZone: "Asia/Kolkata", hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit",
});
export const replayDate = (time: number) => new Date((time + 19800) * 1000).toISOString().slice(0, 10);
export const replayCursor = (day: string, time: string) => Date.parse(`${day}T${time.length === 5 ? time + ":00" : time}+05:30`) / 1000;

/** Retain the same session clock while comparing indices or chart timeframes. */
export const replayLoadCursor = (session: Row, previous: {date: string; cursor: number}) =>
 Math.max(session.start, Math.min(session.end, previous.date === session.date ? previous.cursor : session.start));

/** Project only observations and completed minutes available at the visible clock. */
export function replayFrame(session: Row, requested: number): Row {
 const cursor = Math.max(session.start, Math.min(session.end, requested));
 const size = parseInt(session.period) * (session.period.endsWith("h") ? 3600 : 60);
 const minutes = new Map<number, Row>();
 for (const bar of session.minutes) if (bar.end_time <= cursor) minutes.set(bar.time, {...bar});
 let lastObservation: Row | undefined;
 for (const observation of session.observations) {
  if (observation.time > cursor) break;
  lastObservation = observation;
  const row = minutes.get(observation.minute);
  if (row?.complete) continue;
  if (!row) minutes.set(observation.minute, {...observation, time: observation.minute, complete: false});
  else { row.high = Math.max(row.high, observation.high); row.low = Math.min(row.low, observation.low); row.close = observation.close; }
 }
 const grouped = new Map<number, Row>();
 for (const [time, minute] of [...minutes].sort((a, b) => a[0] - b[0])) {
  const bucket = session.start + Math.floor((time - session.start) / size) * size;
  const row = grouped.get(bucket);
  if (!row) grouped.set(bucket, {time: bucket, open: minute.open, high: minute.high, low: minute.low,
   close: minute.close, count: 1, allComplete: !!minute.complete, first: time, last: time,
   end_time: Math.min(bucket + size, replayCursor(session.date, "15:30:00"))});
  else { row.high = Math.max(row.high, minute.high); row.low = Math.min(row.low, minute.low);
   row.close = minute.close; row.count++; row.allComplete &&= !!minute.complete; row.last = time; }
 }
 const bars = [...grouped.values()].map(row => {
  const expected = (row.end_time - row.time) / 60;
  const continuous = row.first === row.time && row.last === row.time + (row.count - 1) * 60;
  const complete = row.end_time <= cursor && row.allComplete && continuous && row.count === expected;
  return {time: row.time, end_time: row.end_time, open: row.open, high: row.high, low: row.low,
   close: row.close, complete, partial_observation: !continuous || !row.allComplete || (row.end_time <= cursor && !complete),
   shortened: expected * 60 < size};
 });
 const candles = [...session.history_candles, ...bars];
 const lastCompleted = [...minutes.values()].filter(bar => bar.complete).sort((a, b) => a.time - b.time).pop();
 const reference = lastCompleted?.close ?? session.history_candles.at(-1)?.close;
 const zones = session.zones.filter((z: Row) => Date.parse(z.available_at) / 1000 <= cursor).map((z: Row) => ({...z,
  relation: z.upper < reference ? "SUPPORT" : z.lower > reference ? "RESISTANCE" : "AT_ZONE",
  distance_points: Math.max(z.lower - reference, reference - z.upper, 0),
 })).filter((z: Row) => Number.isFinite(z.distance_points));
 const lastMinute = lastCompleted?.end_time;
 const lastAt = lastObservation?.time;
 const nextUpdate = Math.min(session.observations.find((row: Row) => row.time > cursor)?.time ?? Infinity,
  session.minutes.find((row: Row) => row.end_time > cursor)?.end_time ?? Infinity);
 const disconnected = session.capture.disconnects.some((time: number) => time <= cursor && (!lastAt || time >= lastAt));
 const observationGap = session.mode === "observations" && (lastAt == null || cursor - lastAt > 5 || disconnected);
 const minuteGap = session.mode === "candles" && cursor >= session.start + 60 && (lastMinute == null || cursor - lastMinute >= 60);
 const trades = session.trades.filter((trade: Row) => Date.parse(trade.entry_ts) / 1000 <= cursor).map((trade: Row) => ({...trade,
  exit_ts: Date.parse(trade.exit_ts) / 1000 <= cursor ? trade.exit_ts : null,
 }));
 const volumes = session.volume.bars.filter((bar: Row) => bar.end_time <= cursor);
 const contracts = [...new Map(volumes.filter((bar: Row) => bar.contract_id).map((bar: Row) =>
  [bar.contract_id + ":" + bar.expiry, {contract_id: bar.contract_id, expiry: bar.expiry}])).values()];
 return {symbol: session.symbol, period: session.period, session: "REPLAY", live: false, generated_at: new Date(cursor * 1000).toISOString(),
  candles, trades, structure: {zones, price: reference, as_of: lastMinute ? new Date(lastMinute * 1000).toISOString() : null},
  source: session.mode === "observations" ? "Recorded observations + saved completed minutes" : "Saved completed minutes · candle-only replay",
  history_days: session.history_days, history_context_bars: session.history_context_bars, volume: {...session.volume, bars: volumes, contracts, contract: contracts[contracts.length - 1] ?? {},
   from: volumes[0]?.time, to: volumes.at(-1)?.end_time},
  replay: {cursor, last_observation: lastAt, next_update: Number.isFinite(nextUpdate) && nextUpdate <= session.end ? nextUpdate : null, gap: observationGap || minuteGap,
   reason: observationGap ? "No fresh recorded observation at this second. Last observed prices remain on screen; no prices are interpolated."
    : minuteGap ? "Missing completed minute at this clock time; no candle is generated to fill the gap."
    : session.mode === "candles" ? "Candle-only: prices update when a saved minute closes, not every second." : "Recorded observations · not verified complete exchange ticks."},
 };
}
