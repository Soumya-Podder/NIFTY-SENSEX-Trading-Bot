import { useEffect, useMemo, useRef, useState } from "react";
import { CandlestickSeries, ColorType, CrosshairMode, HistogramSeries, createChart, createSeriesMarkers } from "lightweight-charts";
import { api } from "./api";
import { TerminalZones } from "./TerminalZones";
import { CHART_PERIODS, chartBias, ist, price, syncSeries, tradeMarkers, volumeChangeMarkers, visibleZones, wheelPriceRange, type Row } from "./terminalView";
import "./terminal.css";
import { TerminalValue } from "./TerminalValue";
import { replayCursor, replayDate, replayFrame, replayLoadCursor, replayTime } from "./chartReplay";

export default function MarketTerminal({account}: {account: Row}) {
 const [symbol, setSymbol] = useState("NIFTY"), [period, setPeriod] = useState("5m");
 const [layers, setLayers] = useState(["5m", "1h", "4h"]);
 const [liveData, setData] = useState<Row | null>(null), [error, setError] = useState("");
 const [replaying, setReplaying] = useState(false), [playing, setPlaying] = useState(false);
 const [day, setDay] = useState(""), [seekTime, setSeekTime] = useState("09:15:00");
 const [replaySession, setReplaySession] = useState<Row | null>(null), [cursor, setCursor] = useState(0);
 const [speed, setSpeed] = useState(1), [replayError, setReplayError] = useState("");
 const [loadingReplay, setLoadingReplay] = useState(false), [reloadReplay, setReloadReplay] = useState(0);
 const [followReplay, setFollowReplay] = useState(true);
 const replayClock = useRef({date: "", cursor: 0}), loadedReload = useRef(0);
 const data = useMemo(() => replaying ? replaySession?.symbol === symbol && replaySession?.period === period && replaySession?.date === day ? replayFrame(replaySession, cursor) : null : liveData,
  [replaying, replaySession, cursor, liveData, symbol, period, day]);
 if (data?.replay) replayClock.current = {date: day, cursor};
 const [connected, setConnected] = useState(false), [crosshair, setCrosshair] = useState<Row | null>(null);
 const [volumeShown, setVolumeShown] = useState(true), [selectedZone, setSelectedZone] = useState<Row | null>(null);
 const [zoneDepth, setZoneDepth] = useState(5);
 const host = useRef<HTMLDivElement>(null), instance = useRef<any>(null);
 const model = useRef({zones: [] as Row[], times: [] as number[]});
 const zones = useMemo(() => visibleZones(data?.structure?.zones || [], layers, zoneDepth), [data?.structure, layers, zoneDepth]);
 const bias = useMemo(() => chartBias(data?.candles || []), [data?.candles]);
 const positions = replaying ? [] : (account?.positions || []).filter((p: Row) => p.symbol === symbol);

 useEffect(() => {
  if (replaying) return;
  let stopped = false, timer: number, controller: AbortController;
  setData(null); setError(""); setConnected(false); setCrosshair(null); setSelectedZone(null);
  const refresh = async () => {
   controller = new AbortController();
   const deadline = window.setTimeout(() => controller.abort(), 30000);
   try {
    const result = await api(`/market/chart/${symbol}?period=${period}`, undefined, controller.signal);
    if (!stopped) { setData(result); setError(""); setConnected(true); }
   } catch (e) {
    if (!stopped) { setConnected(false); setError((e as Error).message.includes("Not Found") ? "The connected backend has not loaded the chart endpoint. Restart the backend to load this update." : (e as Error).message); }
   } finally { clearTimeout(deadline); if (!stopped) timer = window.setTimeout(refresh, 2000); }
  };
  refresh();
  return () => { stopped = true; clearTimeout(timer); controller?.abort(); };
 }, [symbol, period, replaying]);

 useEffect(() => {
  if (!replaying) return;
  if (!day) { setReplaySession(null); setPlaying(false); setLoadingReplay(false); setReplayError("Select a replay date"); return; }
  const controller = new AbortController();
  let stopped = false;
  const refresh = loadedReload.current !== reloadReplay;
  loadedReload.current = reloadReplay;
  setPlaying(false); setReplaySession(null); setLoadingReplay(true); setReplayError("");
  api(`/market/replay/${symbol}?day=${day}&period=${period}&refresh=${refresh}`, undefined, controller.signal, 120000).then(result => {
   if (stopped) return;
   const next = replayLoadCursor(result, replayClock.current);
   if (replayClock.current.date !== result.date) setSpeed(result.mode === "candles" ? 60 : 1);
   setReplaySession(result); setCursor(next); setSeekTime(replayTime(next)); setFollowReplay(true);
  }).catch(e => { if (!stopped) setReplayError((e as Error).name === "TimeoutError" ? "Replay loading timed out. Use Reload archive to retry the saved session." : (e as Error).message); })
   .finally(() => { if (!stopped) setLoadingReplay(false); });
  return () => { stopped = true; controller.abort(); };
 }, [replaying, day, symbol, period, reloadReplay]);

 useEffect(() => {
  if (!playing || !replaySession) return;
  const timer = window.setInterval(() => setCursor(value => Math.min(value + speed, replaySession.end)), 1000);
  return () => clearInterval(timer);
 }, [playing, speed, replaySession]);
 useEffect(() => { if (replaySession && cursor >= replaySession.end) setPlaying(false); }, [cursor, replaySession]);
 useEffect(() => { setCrosshair(null); setSelectedZone(null); }, [replaying, cursor]);

 useEffect(() => {
  if (!host.current) return;
  const chart = createChart(host.current, {autoSize: true, height: 590,
   layout: {background: {type: ColorType.Solid, color: "#0c1422"}, textColor: "#9baec7", attributionLogo: true},
   crosshair: {mode: CrosshairMode.Normal}, rightPriceScale: {borderVisible: false},
   timeScale: {timeVisible: true, secondsVisible: false, rightOffset: 8, minBarSpacing: .001, borderVisible: false,
    tickMarkFormatter: (time: any, type: number) => new Date(Number(time)*1000).toLocaleString("en-IN", type <= 2 ? {timeZone: "Asia/Kolkata", day: "2-digit", month: "short"} : {timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false})},
   localization: {timeFormatter: (time: any) => `${ist(Number(time))} IST`},
  });
  const candle = chart.addSeries(CandlestickSeries, {upColor: "#10b981", downColor: "#f43f5e", borderVisible: false, wickUpColor: "#10b981", wickDownColor: "#f43f5e", priceFormat: {type: "price", precision: 2, minMove: .01}});
  const volume = chart.addSeries(HistogramSeries, {priceFormat: {type: "volume"}, lastValueVisible: false, priceLineVisible: false}, 1);
  chart.panes()[1].setHeight(115);
  const primitive = new TerminalZones(); candle.attachPrimitive(primitive);
  primitive.update(model.current.zones, model.current.times);
  const markers = createSeriesMarkers(candle, []);
  const volumeMarkers = createSeriesMarkers(volume, []);
  const value = {chart, candle, volume, primitive, markers, volumeMarkers, bars: [], volumes: [], fitted: false}; instance.current = value;
  const element = host.current;
  const priceWheel = (event: WheelEvent) => {
   const rect = element.getBoundingClientRect(), x = event.clientX-rect.left, y = event.clientY-rect.top;
   const scale = candle.priceScale(), range = scale.getVisibleRange();
   if (x < rect.width-scale.width() || x > rect.width || y < 0 || y >= chart.panes()[0].getHeight() || !range) return;
   const anchor = candle.coordinateToPrice(y);
   if (anchor === null || event.deltaY === 0) return;
   const next = wheelPriceRange(range, anchor, event.deltaY*(event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? rect.height : 1));
   if (!next) return;
   event.preventDefault(); event.stopImmediatePropagation();
   scale.setAutoScale(false); scale.setVisibleRange(next);
  };
  element.addEventListener("wheel", priceWheel, {passive: false, capture: true});
  const theme = () => {
   const light = document.documentElement.dataset.theme === "light";
   chart.applyOptions({layout: {background: {type: ColorType.Solid, color: light ? "#ffffff" : "#0c1422"}, textColor: light ? "#475569" : "#9baec7"},
    grid: {vertLines: {color: light ? "#edf0f4" : "#1b283b"}, horzLines: {color: light ? "#edf0f4" : "#1b283b"}}});
  };
  theme();
  const observer = new MutationObserver(theme); observer.observe(document.documentElement, {attributes: true, attributeFilter: ["data-theme"]});
  chart.subscribeCrosshairMove(param => {
   const bar = param.seriesData.get(candle);
   const volumeBar = param.seriesData.get(volume);
   setCrosshair(bar && param.time ? {...bar, time: Number(param.time), futuresVolume: volumeBar && "value" in volumeBar ? volumeBar.value : null} : null);
  });
  return () => { element.removeEventListener("wheel", priceWheel, true); observer.disconnect(); chart.remove(); instance.current = null; };
 }, [symbol, period, replaying]);

 useEffect(() => {
  const value = instance.current;
  if (!value) return;
  if (!data) {
   value.candle.setData([]); value.volume.setData([]); value.markers.setMarkers([]); value.volumeMarkers.setMarkers([]);
   value.bars = []; value.volumes = []; value.fitted = false;
   return;
  }
  const candles = data.candles.map((c: Row) => ({time: c.time, open: c.open, high: c.high, low: c.low, close: c.close}));
  const volumes = (data.volume?.bars || []).map((c: Row) => ({time: c.time, value: c.value, color: c.close >= c.open ? "#10b98199" : "#f43f5e99"}));
  value.bars = syncSeries(value.candle, value.bars, candles);
  value.volumes = syncSeries(value.volume, value.volumes, volumes);
  value.volumeMarkers.setMarkers(volumeChangeMarkers(data.volume?.bars || []));
  if (!value.fitted && candles.length) { value.chart.timeScale().setVisibleLogicalRange({from: Math.max(0, candles.length-95), to: candles.length+6}); value.fitted = true; }
  if (replaying && followReplay && candles.length) value.chart.timeScale().scrollToRealTime();
 }, [data, replaying, followReplay]);
 useEffect(() => {
  if (data && instance.current) instance.current.markers.setMarkers(tradeMarkers(data.candles, [...(data.trades || []), ...positions], period));
 }, [data, account, symbol, period, replaying]);
 useEffect(() => {
  model.current = {zones, times: (data?.candles || []).map((c: Row) => c.time)};
  instance.current?.primitive.update(zones, model.current.times, parseInt(period)*(period.endsWith("h") ? 3600 : 60));
 }, [zones, data?.candles, period]);
 useEffect(() => { instance.current?.volume.applyOptions({visible: volumeShown}); }, [volumeShown, symbol, period, replaying]);

 const last = data?.candles?.at(-1), display = crosshair || last;
 const displayVolume = crosshair ? crosshair.futuresVolume : data?.volume?.bars?.find((bar: Row) => bar.time === last?.time)?.value;
 const displayVolumeBar = data?.volume?.bars?.find((bar: Row) => bar.time === display?.time);
 const changePeriod = (next: string) => { if (next === period) return; setData(null); setPeriod(next); setLayers(old => [...new Set(old.filter(p => p !== period).concat(next))]); };
 const toggleLayer = (p: string) => setLayers(old => old.includes(p) ? old.filter(v => v !== p) : [...old, p]);
 const fitZones = () => {
  if (!zones.length || !instance.current || !last) return;
  const low = Math.min(last.low, ...zones.map(z => z.lower)), high = Math.max(last.high, ...zones.map(z => z.upper));
  const pad = Math.max((high-low)*.08, 1), scale = instance.current.candle.priceScale();
  scale.setAutoScale(false); scale.setVisibleRange({from: Math.max(.01, low-pad), to: high+pad});
 };
 const zoom = (factor: number) => {
  const scale = instance.current?.chart.timeScale(), range = scale?.getVisibleLogicalRange();
  if (range) { const middle = (range.from+range.to)/2, half = (range.to-range.from)*factor/2; scale.setVisibleLogicalRange({from: middle-half, to: middle+half}); }
 };
 const showMonths = (months: number) => {
  const bars = data?.candles;
  if (!bars?.length || !instance.current) return;
  const end = bars.at(-1).time, start = new Date(end*1000);
  start.setUTCMonth(start.getUTCMonth()-months);
  instance.current.chart.timeScale().setVisibleRange({from: Math.max(bars[0].time, start.getTime()/1000), to: end});
 };
 const toggleReplay = () => {
  setPlaying(false);
  if (!replaying) { replayClock.current = {date: "", cursor: 0}; setDay(replayDate(last?.time ?? Date.now()/1000)); setReplaySession(null); }
  setReplaying(value => !value);
 };
 const moveReplay = (next: number) => {
  if (!replaySession || !Number.isFinite(next)) return;
  setPlaying(false); setFollowReplay(true); setCursor(Math.max(replaySession.start, Math.min(next, replaySession.end)));
 };
 return <section className="market-terminal" aria-label="NIFTY and SENSEX chart terminal">
  <header className="terminal-heading"><div><h2>{symbol === "NIFTY" ? "NIFTY 50" : "SENSEX"} <strong><TerminalValue value={last?.close} animate={!replaying && connected && data?.live}>{price(last?.close)}</TerminalValue></strong></h2><p>{replaying ? "REPLAY · Read-only archive · live paper engine continues separately" : `${data?.session || "Connecting"} · ${connected && data?.live ? "Live observations" : "Historical / awaiting fresh market data"}`}</p></div>
   <div className="terminal-segment" role="group" aria-label="Chart index">{["NIFTY", "SENSEX"].map(s => <button key={s} aria-pressed={symbol === s} onClick={() => { if (s !== symbol) { setData(null); setSymbol(s); } }}>{s}</button>)}</div></header>
  <div className="terminal-toolbar"><div className="terminal-segment" role="group" aria-label="Chart timeframe">{CHART_PERIODS.map(p => <button key={p} aria-pressed={period === p} onClick={() => changePeriod(p)}>{p.replace("h", "H").replace("d", "D")}</button>)}</div>
   <div className="terminal-tools"><button onClick={() => zoom(.75)} aria-label="Zoom chart in">＋</button><button onClick={() => zoom(1.3)} aria-label="Zoom chart out">−</button><details className="terminal-history-menu"><summary>History</summary><div><button onClick={() => showMonths(6)} aria-label="Show six months">6 months</button><button onClick={() => showMonths(12)} aria-label="Show one year">1 year</button><button onClick={() => instance.current?.chart.timeScale().fitContent()}>Fit history</button></div></details><button onClick={() => instance.current?.candle.priceScale().setAutoScale(true)} title="Reset the vertical price scale; wheel over price numbers to zoom">Auto price</button><button onClick={() => instance.current?.chart.timeScale().scrollToRealTime()}>Latest</button><button aria-pressed={volumeShown} onClick={() => setVolumeShown(v => !v)}>Volume</button></div></div>
  <div className="terminal-replay-toggle"><button onClick={toggleReplay} aria-pressed={replaying}>{replaying ? "Return to live" : "Replay"}</button></div>
  {replaying && <section className="terminal-replay" aria-label="Chart replay controls">
   <div className="terminal-replay-controls">
    <label>Session date · IST<input type="date" aria-label="Replay date" value={day} max={replayDate(Date.now()/1000)} onInput={e => setDay(e.currentTarget.value)} /></label>
    <form onSubmit={e => { e.preventDefault(); const time = String(new FormData(e.currentTarget).get("replayTime")); setSeekTime(time); moveReplay(replayCursor(day, time)); }}>
     <label>Go to time · IST<input type="time" name="replayTime" step="1" aria-label="Replay start time" value={seekTime} onInput={e => setSeekTime(e.currentTarget.value)} required /></label>
     <button disabled={!replaySession}>Go</button>
    </form>
    <button disabled={!replaySession || cursor <= replaySession.start} onClick={() => moveReplay(cursor - 1)} aria-label="Replay back one second">−1s</button>
    <button disabled={!replaySession || cursor >= replaySession.end} onClick={() => setPlaying(value => !value)}>{loadingReplay ? "Loading replay…" : playing ? "Pause replay" : "Play replay"}</button>
    <button disabled={!replaySession || cursor >= replaySession.end} onClick={() => moveReplay(cursor + 1)} aria-label="Replay forward one second">+1s</button>
    <button disabled={!data?.replay?.next_update} onClick={() => moveReplay(data!.replay.next_update)}>Next price update</button>
    <button aria-pressed={followReplay} onClick={() => setFollowReplay(value => !value)}>Follow cursor</button>
    <label>Speed<select aria-label="Replay speed" value={speed} onChange={e => setSpeed(Number(e.target.value))}>{[1, 2, 5, 10, 30, 60].map(value => <option key={value} value={value}>{value}×</option>)}</select></label>
    <button disabled={loadingReplay || !day} onClick={() => setReloadReplay(value => value + 1)}>Reload archive</button>
   </div>
   {loadingReplay && <p role="status">Loading saved session data… The first load can take longer while the archive is read. Play enables when the session is ready.</p>}
   {replayError && <p role="alert">{replayError}</p>}
   {replaySession && <>
    <div className="terminal-replay-clock"><strong>{day} · {replayTime(cursor)} IST</strong><span>{replaySession.mode === "observations" ? "Recorded-observation playback" : "Candle-only playback"} · {playing ? "Playing" : cursor >= replaySession.end ? "Session end" : "Paused"}</span></div>
    <input className="terminal-replay-slider" type="range" aria-label="Replay timeline" min={replaySession.start} max={replaySession.end} step="1" value={cursor} onChange={e => moveReplay(Number(e.target.value))} />
    <p className={data?.replay?.gap ? "replay-gap" : ""} role="status">{data?.replay?.reason}{data?.replay?.next_update ? ` Next recorded price update: ${replayTime(data.replay.next_update)} IST.` : ""}{data?.replay?.last_observation ? ` Last recorded observation: ${replayTime(data.replay.last_observation)} IST.` : ""}</p>
    <details><summary>Replay data &amp; limitations</summary><p>{replaySession.limitations}</p><p>{replaySession.capture.observations.toLocaleString("en-IN")} valid observed ticks · {replaySession.minutes.length} saved session minutes · {replaySession.capture.invalid} invalid observations excluded. This is a frozen archive; reload to include newly saved data.</p>{replaySession.capture.issues.map((issue: string) => <p key={issue}>{issue}</p>)}</details>
   </>}
  </section>}
  <div className="terminal-layers"><span>Zone layers</span>{[...CHART_PERIODS, "1d"].map(p => <label key={p}><input type="checkbox" checked={layers.includes(p)} onChange={() => toggleLayer(p)} />{p.replace("h", "H").replace("d", "D")}</label>)}<label>Levels per side<select value={zoneDepth === Infinity ? "all" : zoneDepth} onChange={e => setZoneDepth(e.target.value === "all" ? Infinity : Number(e.target.value))}><option value="5">5 nearest</option><option value="10">10 nearest</option><option value="all">All retained</option></select></label><button onClick={fitZones} disabled={!zones.length}>Fit zones</button></div>
  {!replaying && error && <div className="terminal-alert" role="status">{error} Retained values are not live.</div>}
  <div className="terminal-grid"><div className="terminal-plot-column">
   <div className="terminal-ohlc"><span>{display ? `${ist(display.time)} IST` : "Waiting for candles"}</span>{["open", "high", "low", "close"].map(k => <span key={k}>{k[0].toUpperCase()} <b>{price(display?.[k])}</b></span>)}<span>Futures volume <b>{price(displayVolume)}</b></span><span>{!crosshair && last && (!last.complete ? replaying ? "Partial recorded candle" : "Developing · partial observation" : last.shortened ? "Shortened session-end candle" : "Completed candle")}</span></div>
   <div className="terminal-chart-wrap"><div className="terminal-chart" ref={host} />{!data?.candles?.length && <div className="terminal-empty"><strong>{replaying ? replayError ? "Replay unavailable for this session" : "Loading saved session…" : error ? "Chart feed unavailable" : data ? "No retained candles in the history window" : "Loading observed candles…"}</strong><span>Real market observations appear here. No sample prices are used.</span></div>}</div>
   <div className="terminal-volume-caption"><b>Futures volume</b><span>{displayVolumeBar?.contract_id ? `${displayVolumeBar.contract_id} · expiry ${displayVolumeBar.expiry}` : "No volume at the selected candle"}</span>{data?.volume?.bars?.length > 0 ? <small>{ist(data.volume.from)} → {ist(data.volume.to)} IST · {data.volume.contracts?.length || 1} recorded contracts · arrows mark contract changes · missing intervals remain blank</small> : <small>{data?.volume?.reason || "Awaiting recorded futures candles"}</small>}</div>
   <div className="terminal-footnote"><details className="terminal-data-details"><summary>Chart &amp; data details</summary><p>{data?.source || "Read-only market feed"} · {replaying ? "Archive playback" : "Refresh every 2s"} · {data?.history_days ?? 365}-day window · {data?.candles?.length ?? 0} candles{data?.candles?.length ? ` · ${ist(data.candles[0].time)} → ${ist(last.time)} IST` : ""}.</p>{!replaying && <p>Last exchange tick: {data?.tick?.exchange_timestamp ? `${ist(data.tick.exchange_timestamp)} IST` : "Timestamp unavailable"}.</p>}<p>Zone reference {price(data?.structure?.price)} at {data?.structure?.as_of ? ist(data.structure.as_of) : "awaiting completed candles"}. Green support · Red resistance · Purple inside zone. Bands span the chart; vertical marks show confirmation time. Crowded labels use +N.</p><p>Scroll over price numbers to zoom vertically; Auto price resets. Paper arrows mark trade times, not index fills.</p><p>{data?.volume?.contract?.expiry && `Futures expiry ${data.volume.contract.expiry} · captured ${ist(data.volume.captured_at || data.volume.contract.captured_at)} IST. `}{data?.volume?.bars?.length > 0 && `${data.volume.bars.length.toLocaleString("en-IN")} volume bars · ${ist(data.volume.from)} → ${ist(data.volume.to)} IST. `}{data?.volume?.reason}</p><p>{bias.reason}</p><p>{data?.probabilities?.reason || "No validated forecasting model is available."}</p></details><a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">TradingView Lightweight Charts™ · Copyright © 2026 TradingView, Inc.</a></div>
  </div><aside className="terminal-analysis">
   <article><span className="eyebrow">DIRECTIONAL CONTEXT · {period.replace("h", "H")}</span><h3>{bias.label}</h3><small>{!connected || !data?.live ? "Historical context · not a forecast" : "Indicator context · not a forecast"}</small></article>
   {!replaying && <article><span className="eyebrow">ENGINE DECISION</span><h3>{data?.decision?.reason || data?.session || "Awaiting engine"}</h3>{data?.decision?.scan?.reason && data.decision.scan.reason !== (data?.decision?.reason || data?.session) && <p>{data.decision.scan.reason}</p>}</article>}
  </aside></div>
  <div className="terminal-zones"><details className="terminal-zone-list"><summary>Confirmed zones · {zones.length} levels</summary>
   <div className="terminal-zone-grid">{zones.map(z => <button key={z.id} className={`terminal-zone ${z.relation.toLowerCase()}`} onClick={() => setSelectedZone(z)}><span>{z.label} · {z.kind.replaceAll("_", " ")}</span><strong>{price(z.lower)} – {price(z.upper)}</strong><small>Known {ist(z.available_at)} IST · {price(z.distance_points)} pts away</small></button>)}</div>
   {!zones.length && <p>No confirmed zones for these layers. Higher timeframes need more completed sessions.</p>}
   {selectedZone && <div className="terminal-zone-detail" role="status"><strong>{selectedZone.label} · {selectedZone.id}</strong><p>Formed {ist(selectedZone.formed_at)} · Confirmed {ist(selectedZone.available_at)} IST. Extended across the chart as a current reference; it was not known before confirmation. Relation is measured against the latest chart price; this is a price zone, not evidence of hidden orders.</p><button onClick={() => setSelectedZone(null)}>Close details</button></div>}
   </details>
   {!replaying && <details><summary>Timeframe coverage &amp; sweep evidence</summary><div className="terminal-coverage">{CHART_PERIODS.map(p => <p key={p}><b>{p.replace("h", "H").replace("d", "D")}</b> {data?.structure?.coverage?.[p]?.complete_bars ?? 0} complete bars · {data?.structure?.coverage?.[p]?.reason || "Awaiting data"}</p>)}</div>{(data?.structure?.sweeps || []).map((s: Row, i: number) => <p key={i}>{s.bias === "CALL" ? "Bullish" : "Bearish"} reclaim · {s.timeframe} · {price(s.level)} · confirmed {ist(s.confirmed_at)} IST</p>)}{!data?.structure?.sweeps?.length && <p>No recorded confirmed sweep in the detector's recent window.</p>}<p>Confirmed structure uses full candles only; shortened closing candles shown on the chart do not confirm swing zones. Missing historical minute groups are omitted.</p></details>}
  </div>
 </section>;
}
