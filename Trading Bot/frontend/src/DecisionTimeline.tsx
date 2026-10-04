import { useEffect, useRef, useState } from "react";
import { decisionId, decisionKind, recentDecision } from "./activityView";
type Data = Record<string, any>;
const filters = [{ id: "all", label: "All events" }, { id: "waiting", label: "Waiting" }, { id: "blocked", label: "Blocked" }, { id: "passed", label: "Passed / filled" }, { id: "system", label: "System" }];
const day = (stamp?: string) => stamp && Number.isFinite(Date.parse(stamp)) ? new Date(stamp).toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric" }) : "Date unavailable";
const time = (stamp?: string) => stamp && Number.isFinite(Date.parse(stamp)) ? new Date(stamp).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", second: "2-digit" }) + " IST" : "Time unavailable";

export default function DecisionTimeline({ events, online, onDetail }: Data) {
  const [kind, setKind] = useState("all");
  const [symbol, setSymbol] = useState("ALL");
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(20);
  const [paused, setPaused] = useState(false);
  const [arrivals, setArrivals] = useState<string[]>([]);
  const seen = useRef<Set<string> | null>(null);
  const signature = JSON.stringify(events.map((event: Data) => ({ id: decisionId(event), timestamp: event.timestamp })));
  useEffect(() => {
    const current: Data[] = JSON.parse(signature);
    const added = seen.current && online ? current.filter(event => !seen.current!.has(event.id) && recentDecision(event)).map(event => event.id) : [];
    seen.current = new Set(current.map(event => event.id));
    setArrivals(added);
    if (added.length) { const timer = window.setTimeout(() => setArrivals([]), 4000); return () => window.clearTimeout(timer); }
  }, [signature, online]);
  const counts = Object.fromEntries(filters.map(filter => [filter.id, filter.id === "all" ? events.length : events.filter((event: Data) => decisionKind(event.status) === filter.id).length]));
  const filtered = events.filter((event: Data) => (kind === "all" || decisionKind(event.status) === kind) && (symbol === "ALL" || event.symbol === symbol)
    && [event.symbol, event.agent, event.status, event.summary, event.context].join(" ").toLowerCase().includes(query.trim().toLowerCase()));
  const shown = filtered.slice(0, limit);
  const latest = events[0];
  return <section className={"panel spaced decisions-workspace " + (paused || !online ? "activity-still" : "")} aria-labelledby="decisions-title">
    <header className="activity-header"><div><div className="activity-kicker">Inputs / contexts / rejections</div><h2 id="decisions-title">Latest decisions</h2><p>Trace what the agents evaluated, allowed or stopped.</p></div>
      <div className="activity-header-actions"><span className="activity-badge">{!online ? "Offline · last snapshot" : arrivals.length ? arrivals.length + " new events" : "Recorded event stream"}</span><button type="button" className="activity-button" aria-pressed={paused} onClick={() => setPaused(value => !value)}>{paused ? "Resume decision motion" : "Pause decision motion"}</button></div>
    </header>
    <div className="decision-overview">
      <div><span className="activity-kicker">Events in this snapshot</span><strong>{events.length}</strong><small>Event counts include repeated checks, not just trades.</small></div>
      <div className="decision-distribution"><div className="decision-distribution-bar" aria-hidden="true">{filters.slice(1).map(filter => <span className={"activity-" + filter.id} key={filter.id} style={{ width: (events.length ? counts[filter.id] / events.length * 100 : 0) + "%" }} />)}</div>
        <div className="decision-counts">{filters.slice(1).map(filter => <span key={filter.id}><i className={"activity-" + filter.id} />{filter.label}<b>{counts[filter.id]}</b></span>)}</div>
        <p>{latest ? "Last recorded: " + day(latest.timestamp) + " · " + time(latest.timestamp) : "Awaiting the first recorded event."}{online && latest && !recentDecision(latest) ? " · No event in the last 2 minutes." : ""}</p>
      </div>
    </div>
    <div className="decision-controls"><div className="decision-filters" role="group" aria-label="Filter decision status">{filters.map(filter => <button type="button" key={filter.id} aria-pressed={kind === filter.id} onClick={() => { setKind(filter.id); setLimit(20); }}>{filter.label}</button>)}</div>
      <div className="decision-search"><label>Index / source<select name="decision-symbol" value={symbol} onChange={event => { setSymbol(event.target.value); setLimit(20); }}><option value="ALL">All sources</option>{[...new Set<string>(events.map((event: Data) => event.symbol).filter(Boolean))].map(value => <option key={value}>{value}</option>)}</select></label>
        <label>Search decisions<input type="search" name="decision-query" autoComplete="off" placeholder="Agent, reason or context…" value={query} onChange={event => { setQuery(event.target.value); setLimit(20); }} /></label>
      </div>
    </div>
    <p className="decision-result-count" role="status">{filtered.length} matching events · {shown.length} shown</p>
    <div className="decision-timeline">{shown.map((event: Data, index: number) => <div key={decisionId(event)}>
      {(index === 0 || day(event.timestamp) !== day(shown[index - 1].timestamp)) && <div className="decision-day">{day(event.timestamp)}</div>}
      <button type="button" className={"decision-event activity-" + decisionKind(event.status) + (arrivals.includes(decisionId(event)) ? " decision-arrival" : "")} onClick={() => onDetail(event)}>
        <span className="decision-node" aria-hidden="true">{decisionKind(event.status) === "blocked" ? "×" : decisionKind(event.status) === "passed" ? "✓" : decisionKind(event.status) === "system" ? "◇" : "·"}</span>
        <span className="decision-time">{time(event.timestamp)}</span><span className="decision-body"><span className="decision-event-title"><strong>{event.symbol || "SYSTEM"} <span> / </span>{event.agent || "Agent"}</strong><span className="activity-badge">{event.status || "Unknown"}</span></span>
          <span className="decision-summary">{event.summary || "No summary recorded"}</span><small>{event.context ? "Context: " + event.context : "No context recorded"}</small></span><span className="decision-inspect" aria-hidden="true">↗</span>
      </button>
    </div>)}</div>
    {!filtered.length && <div className="decision-empty"><span aria-hidden="true">◎</span><h3>{events.length ? "No matching decisions" : "No evaluated cycles yet"}</h3><p>{events.length ? "Try another status, source or search term." : "This timeline will fill when the engine records an evaluation."}</p>{events.length > 0 && <button type="button" className="activity-button" onClick={() => { setKind("all"); setSymbol("ALL"); setQuery(""); }}>Clear decision filters</button>}</div>}
    {shown.length < filtered.length && <div className="decision-more"><button type="button" className="activity-button" onClick={() => setLimit(value => value + 20)}>Show 20 more events</button></div>}
  </section>;
}
