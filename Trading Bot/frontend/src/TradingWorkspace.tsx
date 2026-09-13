import { useEffect, useRef, useState } from "react";
type Data = Record<string, any>;
const cash = (v: any) => typeof v === "number" && Number.isFinite(v) ? v.toLocaleString("en-IN", {style:"currency", currency:"INR", maximumFractionDigits:2}) : "—";
const percent = (v: any) => typeof v === "number" && Number.isFinite(v) ? `${(v*100).toFixed(2)}%` : "—";
const number = (v: any) => typeof v === "number" && Number.isFinite(v) ? v.toLocaleString("en-IN", {maximumFractionDigits:2}) : "—";
const tone = (status: string) => /ERROR|REJECT|BLOCK|INVALID|FAIL/.test(status) ? "bad" : /PASS|FILLED|COMPLETE/.test(status) ? "good" : "waiting";
const eligible = (r: Data) => r.presentation?.performance_available ?? (["complete", "research_complete", "scenario_complete"].includes(r.status) && ["verified", "research_net", "research", "estimated_scenario"].includes(r.quality) && !r.unresolved?.length);

export function AgentCanvas({data, online, onDetail}: Data) {
 const [symbol, setSymbol] = useState("NIFTY");
 const [zoom, setZoom] = useState(1);
 const viewport=useRef<HTMLDivElement>(null);
 useEffect(()=>{const element=viewport.current;if(!element)return;const observer=new ResizeObserver(()=>setZoom(Math.max(.5,Math.min(1,(element.clientWidth-16)/1340))));observer.observe(element);return()=>observer.disconnect();},[]);
 const stages: Data[] = data?.pipelines?.[symbol] || [];
 const nodes = stages.length ? stages : ["Scanner","Regime","Setup","Confirmation","Option Selector","EV","Risk","Execution"].map(agent => ({agent,status:"UNAVAILABLE",label:"Waiting for engine telemetry"}));
 const positions = [[80,160],[390,160],[700,160],[1010,160],[1010,365],[700,365],[390,365],[80,365]];
 return <section className="workflow panel spaced">
  <div className="workspace-toolbar"><div><div className="eyebrow">AGENTIC VIEW / PAPER EXECUTION</div><h2>Decision workflow</h2></div><div className="workspace-actions">
   <div className="segmented">{["NIFTY","SENSEX"].map(s => <button key={s} className={symbol===s ? "selected" : ""} onClick={() => setSymbol(s)}>{s}</button>)}</div>
   <button aria-label="Zoom out workflow" onClick={() => setZoom(z=>Math.max(.5,z-.1))}>−</button><button onClick={() => setZoom(1)} title="Reset zoom">{Math.round(zoom*100)}%</button><button aria-label="Zoom in workflow" onClick={() => setZoom(z=>Math.min(1.5,z+.1))}>+</button>
  </div></div>
  <div className="workflow-legend"><span className="good">● Passed / filled</span><span className="bad">● Rejected / blocked</span><span>● Waiting / other</span><span>{online ? "Latest recorded decision chain" : "Disconnected · last received state"}</span></div>
  <div ref={viewport} className="workflow-viewport" tabIndex={0} aria-label="Scrollable decision workflow">
   <div style={{width:1340*zoom,height:600*zoom}}><div className="workflow-canvas" style={{transform:`scale(${zoom})`}}>
    <svg className="workflow-lines" viewBox="0 0 1340 600" aria-hidden="true"><defs><marker id="workflow-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8" fill="none" stroke="#667080"/></marker></defs>
     <path d="M210 104 V152"/>{positions.slice(0,-1).map(([x,y],i) => {const [nx,ny]=positions[i+1]; return <path key={i} d={y===ny ? (nx>x ? `M${x+250} ${y+65} H${nx-8}` : `M${x} ${y+65} H${nx+258}`) : `M${x+125} ${y+130} V${ny-8}`}/>;})}
    </svg>
    <div className="workflow-start"><strong>Session controller</strong><small>09:15 monitoring → 15:05 exit request</small><span>{data?.market?.session || "Session unavailable"}</span></div>
    {nodes.slice(0,8).map((n,i) => <button key={n.agent} className={`workflow-node ${online ? tone(n.status || "") : "waiting"}`} style={{left:positions[i][0],top:positions[i][1]}} onClick={() => onDetail({...n, symbol, telemetry_current:!!online, event:(data?.events || []).find((e: Data)=>e.id===n.event_id)})}>
     <div className="node-title"><span>◈ {n.agent}</span><small>{String(i+1).padStart(2,"0")}</small></div><p>{n.label}</p><div className="node-state">{online ? n.status : "STALE SNAPSHOT"}<span>Inspect ↗</span></div><i className="node-port"/>
    </button>)}
    <div className="workflow-footnote">Logical gate order · arrows show dependencies, not proof of a completed trade.<br/>Click a node to inspect its recorded evidence. Risk approval precedes simulated execution.</div>
   </div></div>
  </div>
 </section>;
}

export function BacktestHistory({jobs: recent, selected, onSelect}: Data) {
 const [jobs,setJobs]=useState<Data[]>([]), [query,setQuery]=useState(""), [page,setPage]=useState(0), [error,setError]=useState("");
 const [includeInvalid,setIncludeInvalid]=useState(false);
 const signature=(recent || []).map((j:Data)=>`${j.id}:${j.status}`).join("|");
 useEffect(()=>{const c=new AbortController();fetch("/api/backtest/history",{signal:c.signal}).then(r=>{if(!r.ok)throw Error("Reviewed history unavailable");return r.json();}).then(d=>{setJobs(d.jobs || []);setError("");}).catch(e=>{if(e.name!=="AbortError")setError(e.message);});return()=>c.abort();},[signature]);
 const filtered=(jobs.length ? jobs : recent || []).filter((j:Data)=>!j.config?.download_only && (includeInvalid || j.report?.status!=="invalidated") && JSON.stringify([j.config,j.id,j.status]).toLowerCase().includes(query.toLowerCase()));
 const visible=filtered.slice(page*8,page*8+8);
 return <section className="panel spaced history-workspace"><div className="workspace-toolbar"><div><div className="eyebrow">SAVED SIMULATIONS</div><h2>Backtest history</h2></div><input className="search" aria-label="Search backtest history" placeholder="Search strategy, index, run…" value={query} onChange={e=>{setQuery(e.target.value);setPage(0);}}/></div>
 {error && <p className="research-note">{error} · showing available snapshot.</p>}
 <label className="research-note"><input type="checkbox" checked={includeInvalid} onChange={e=>{setIncludeInvalid(e.target.checked);setPage(0);}}/> Include invalidated legacy runs ({jobs.filter(j=>j.report?.status==="invalidated").length})</label>
 <div className="table-wrap"><table><thead><tr>{["Strategy / index","Requested period","Status / evidence","Net P&L","Profit factor","Max drawdown","Trades","Version","Report"].map(s=><th key={s}>{s}</th>)}</tr></thead><tbody>{visible.map((j:Data)=>{const r=j.report, ok=r && eligible(r), m=ok ? r.metrics || {} : {};return <tr key={j.id} className={selected===j.report_id ? "selected-run" : ""}>
  <td><strong>{r?.presentation?.strategy_scope || j.config?.strategy_mode || j.config?.strategy_version || "Saved strategy"}</strong><small>{j.config?.symbols?.join(" + ") || "—"}</small></td><td>{j.config?.from || "—"}<small>→ {j.config?.to || "—"}</small></td>
  <td><span className={`result-status ${tone((r?.status || j.status || "").toUpperCase())}`}>{r?.status || j.status}</span><small>{r?.presentation?.evidence_label || (j.report_id ? "Evidence unavailable" : j.message)}</small>{!j.report_id && <button onClick={()=>onSelect(null,j)}>View issue ↗</button>}</td>
  <td className={m.total_pnl<0 ? "negative" : ""}>{r?.quality==="research" ? "Gross only" : cash(m.total_pnl)}</td><td>{number(m.profit_factor)}</td><td>{cash(m.max_drawdown)}</td><td>{number(m.trades)}</td><td>{r?.strategy_version || "—"}</td><td><button disabled={!j.report_id} onClick={()=>onSelect(j.report_id)}>{selected===j.report_id ? "Selected" : "Open ↗"}</button></td>
 </tr>;})}</tbody></table></div>
 {!visible.length && <div className="workspace-empty">No matching saved backtests.</div>}
 <div className="workspace-pagination"><span>Up to 50 most recent saved jobs · metrics retain each report’s evidence status</span><button disabled={page===0} onClick={()=>setPage(p=>p-1)}>Previous</button><span>{page+1} / {Math.max(1,Math.ceil(filtered.length/8))}</span><button disabled={(page+1)*8>=filtered.length} onClick={()=>setPage(p=>p+1)}>Next</button></div></section>;
}

export function BacktestOverview({report:r,onDetail}: Data) {
 const [basis,setBasis]=useState("net"), [year,setYear]=useState("all"), [hover,setHover]=useState<number|null>(null);
 const ok=eligible(r), net=ok && r.quality!=="research";
 const netMetrics=ok ? r.metrics || {} : {};
 const m=ok ? (basis==="net" ? (net ? netMetrics : {}) : (r.gross_metrics && Object.keys(r.gross_metrics).length ? r.gross_metrics : r.quality==="research" ? netMetrics : {})) : {};
 const end=String(r.config?.to || r.created_at || new Date().toISOString()).slice(0,10);
 const endYear=Number(end.slice(0,4)) || new Date().getFullYear();
 const startYear=Number(String(r.config?.from || endYear).slice(0,4));
 const years=Array.from({length:Math.max(1,Math.min(6,endYear-startYear+1))},(_,i)=>String(Math.max(startYear,endYear-5)+i));
 const daily:Data[]=ok ? r.daily || [] : [];
 const fullCurve:Data[]=ok ? (basis==="net" ? (net ? r.equity || [] : []) : r.gross_equity?.length ? r.gross_equity : r.quality==="research" ? r.equity || [] : []) : [];
 const curve:Data[]=fullCurve.filter((p:Data)=>Number.isFinite(p.value) && (year==="all" || String(p.timestamp || p.date).startsWith(year)));
 let peak=r.config?.capital ?? r.config?.initial_capital ?? 0;
 const dd:Data[]=fullCurve.filter((p:Data)=>Number.isFinite(p.value)).map((p):Data=>{peak=Math.max(peak,p.value);return {...p,value:p.value-peak};}).filter(p=>year==="all" || String(p.timestamp || p.date).startsWith(year));
 const amount=basis==="net" ? (net ? m.total_pnl : null) : (m.total_pnl ?? netMetrics.gross_pnl);
 const capital=r.config?.capital ?? r.config?.initial_capital;
 const final=ok && typeof capital==="number" && typeof amount==="number" ? capital+amount : null;
 const bounds=(rows:Data[])=>rows.reduce<[number,number]>(([lo,hi],p)=>[Math.min(lo,p.value),Math.max(hi,p.value)],[Infinity,-Infinity]);
 const points=(rows:Data[])=>{const [lo,hi]=bounds(rows);return rows.map((p,i)=>`${60+i/Math.max(1,rows.length-1)*900},${260-(p.value-lo)/Math.max(hi-lo,1)*220}`).join(" ");};
 const summary=[["Initial capital",cash(capital)],[`Final capital · ${basis}`,cash(final)],[`${basis} return`,capital>0 ? percent(amount==null ? null : amount/capital):"—"],["Winning trades",number(m.wins)],["Losing trades",number(m.losses)],["Average winner",cash(m.average_winner)],["Average loser",cash(m.average_loser)],["Largest winner",cash(m.largest_winner)],["Largest loser",cash(m.largest_loser)],["Estimated charges",cash(netMetrics.total_charges)],["Observed sessions",number(netMetrics.sessions)]];
 return <section className="results-workspace panel spaced"><div className="workspace-toolbar"><div><div className="eyebrow">BACKTEST RESULTS / {r.quality || "UNAVAILABLE"}</div><h2>{r.strategy_version || r.strategy_mode || "Strategy report"}</h2><p>{r.config?.from || "Start unavailable"} → {r.config?.to || "End unavailable"} · Capital {cash(capital)}</p></div><div className="segmented">{["net","gross"].map(b=><button key={b} className={basis===b ? "selected" : ""} onClick={()=>setBasis(b)}>{b==="net" ? "Net view" : "Gross view"}</button>)}</div></div>
 <div className="report-evidence">
  <strong>{r.presentation?.evidence_label || r.quality} · {ok ? "Completed observed replay" : "Performance not established"}</strong>
  <p>Requested: {r.config?.requested_from || r.config?.from} → {r.config?.to}. Observed: {r.presentation?.observed_from || r.daily?.[0]?.date || "unavailable"} → {r.presentation?.observed_to || r.daily?.[r.daily.length-1]?.date || "unavailable"} · {r.presentation?.observed_sessions ?? r.daily?.length ?? 0} sessions.</p>
  {r.config?.range_note && <p>{r.config.range_note}</p>}
  {r.estimation && <div><strong>EXPLORATORY ESTIMATES · NOT HISTORICAL PERFORMANCE</strong><p>{r.estimation.estimated_exits} estimated exits · {percent(r.estimation.haircut)} reduction from the preceding observed premium. The entire account path is excluded from learning.</p><button className="ghost-button" onClick={()=>onDetail({estimation:r.estimation,assumptions:r.assumptions})}>Inspect estimated exits ↗</button></div>}
  {(r.presentation?.blockers || []).map((s:string)=><p className="negative" key={s}>{s}</p>)}
  <p>Current scope: {r.presentation?.strategy_scope || r.strategy_version || "Saved strategy"}. This report does not establish performance for every portfolio strategy.</p>
 </div>
 <div className="results-columns"><div className="results-main"><div className="summary-strip">{[[`${basis} P&L`,cash(amount)],["Profit factor",number(m.profit_factor)],["Total trades",number(m.trades)],["Win rate",percent(m.win_rate)],["Max drawdown",cash(m.max_drawdown)]].map(([k,v])=><div key={k}><small>{k}</small><strong>{v}</strong></div>)}</div>
 <div className="workspace-toolbar"><h3>Performance chart</h3><div className="segmented"><button className={year==="all" ? "selected" : ""} onClick={()=>setYear("all")}>Full run</button>{years.map(y=><button className={year===y ? "selected" : ""} key={y} onClick={()=>setYear(y)}>{y}</button>)}</div></div>
 <div className="chart-legend"><span>● Capital · INR</span><span>● Drawdown · INR, independent scale</span></div>
 {curve.length ? <div className="performance-plot"><svg viewBox="0 0 1000 310" role="img" aria-label="Recorded capital and drawdown over time" onMouseLeave={()=>setHover(null)} onMouseMove={e=>{const b=e.currentTarget.getBoundingClientRect();setHover(Math.max(0,Math.min(curve.length-1,Math.round(((e.clientX-b.left)/b.width*1000-60)/900*(curve.length-1)))));}}>
 {[40,95,150,205,260].map(y=><line key={y} x1="60" x2="960" y1={y} y2={y} stroke="#292b34" strokeDasharray="3 5"/>)}
 <polyline fill="none" stroke="#6760ff" strokeWidth="2.5" points={points(curve)}/>{dd.length>0 && <polyline fill="none" stroke="#a373d8" strokeWidth="1.5" points={points(dd)}/>}
 <text x="60" y="295">{String(curve[0]?.timestamp || curve[0]?.date || "").slice(0,10)}</text><text x="960" y="295" textAnchor="end">{String(curve[curve.length-1]?.timestamp || curve[curve.length-1]?.date || "").slice(0,10)}</text>
 </svg><div className="plot-readout">{hover===null ? `Capital range ${cash(bounds(curve)[0])} – ${cash(bounds(curve)[1])}` : `${curve[hover]?.timestamp || curve[hover]?.date || "Recorded point"} · ${cash(curve[hover]?.value)}`}</div></div> : <div className="workspace-empty chart-placeholder"><span>⌁</span><strong>{!ok ? "Performance withheld" : basis==="gross" ? "Gross equity series not recorded" : "No recorded equity for this period"}</strong><p>{!ok ? "Invalidated or incomplete evidence cannot establish returns. Inspect the source and coverage details below." : "The chart requires a saved series for the selected view. Missing observations are not replaced with simulated chart values."}</p></div>}
 <div className="workspace-toolbar"><h3>Backtest calendar</h3><span className="muted">Years in the requested range · observed sessions only</span></div>
 <div className="table-wrap"><table><thead><tr><th>Year</th><th>{basis==="net" ? "Net" : "Gross"} P&L</th><th>Trades</th><th>Observed sessions</th><th>Coverage</th></tr></thead><tbody>{years.map(y=>{const rows=daily.filter(d=>String(d.date).startsWith(y)), field=basis==="net" ? "pnl" : "gross_pnl", known=rows.length>0 && (basis!=="net" || net) && rows.every(d=>typeof d[field]==="number" && Number.isFinite(d[field]));return <tr key={y}><td><button onClick={()=>setYear(y)}>{y}</button></td><td>{known ? cash(rows.reduce((s,d)=>s+d[field],0)) : "—"}</td><td>{rows.length ? number(rows.reduce((s,d)=>s+(d.trades || 0),0)) : "—"}</td><td>{rows.length || "—"}</td><td><button onClick={()=>onDetail({year:y,rows,coverage:r.coverage || [],issues:r.issues || [],note:"Observed rows do not certify a complete year."})}>{rows.length ? "Inspect observed coverage ↗" : "No eligible results ↗"}</button></td></tr>;})}</tbody></table></div>
 <p className="research-note">Only years intersecting the requested range are shown. A five-year rolling range can span six calendar years; partial endpoint years are not full years. Full-run metrics include the report’s entire requested period. Year selection changes the chart only.</p>
 </div><aside className="backtest-summary"><h3>Backtest summary</h3><span className={`result-status ${tone((r.status || "").toUpperCase())}`}>{r.status || "Unknown"}</span><p>{basis==="gross" ? "Before charges · gross scenario" : "Net of recorded / estimated charges"}</p><dl>{summary.map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl><p>Historical simulation · not a proven edge. Unavailable metrics remain blank.</p><button onClick={()=>onDetail({config:r.config,assumptions:r.assumptions,coverage:r.coverage,issues:r.issues})}>Inspect assumptions ↗</button></aside></div>
 </section>;
}
