import { lazy, Suspense, useEffect, useRef, useState, type ReactNode } from "react";

import { createRoot } from "react-dom/client";
import { api } from "./api";
import StrategyPortfolio from "./StrategyPortfolio";
import AutonomyStatus from "./AutonomyStatus";
import ModelLearning from "./ModelLearning";
import LearningMonitor from "./LearningMonitor";
import LearningRegistry from "./LearningRegistry";
import DecisionTimeline from "./DecisionTimeline";
import ThemeToggle from "./ThemeToggle";
import { registrySummary } from "./activityView";
import { AgentCanvas, BacktestHistory, BacktestOverview } from "./TradingWorkspace";
import "./style.css";
import "./workspace.css";
import "./activity.css";
import "./theme.css";
import "./terminal-shell.css";
import { TerminalValue } from "./TerminalValue";

type Data = Record<string, any>;
const MarketTerminal = lazy(() => import("./MarketTerminal"));

const money = (v: number | null | undefined) =>
 v == null || !Number.isFinite(v) ?
  "—"
 : v.toLocaleString("en-IN", {
   style: "currency",
   currency: "INR",
   maximumFractionDigits: 2,
  });

const pct = (v: number | null | undefined) =>
 v == null || !Number.isFinite(v) ? "—" : `${(v * 100).toFixed(1)}%`;

const stamp = (v?: string) =>
 v ?
  new Date(v).toLocaleString("en-IN", {
   timeZone: "Asia/Kolkata",
   dateStyle: "medium",
   timeStyle: "medium",
  }) + " IST"
 : "Timestamp unavailable";

const active = (j: Data) =>
 ["queued", "running", "cancelling"].includes(j.status);

function App() {
 const [data, setData] = useState<Data | null>(null);

 const [online, setOnline] = useState(false);
 const [connectionChecked, setConnectionChecked] = useState(false);

 const [tab, setTab] = useState(()=>["agentic","backtest","monitor","charts"].includes(window.location.hash.slice(1)) ? window.location.hash.slice(1) : "monitor");
 useEffect(()=>{window.history.replaceState(null,"",`#${tab}`);},[tab]);

 const [notice, setNotice] = useState("");

 const [detail, setDetail] = useState<Data | null>(null);

 const [report, setReport] = useState<Data | null>(null);

 const [reportId, setReportId] = useState("");

 const [reportLoading, setReportLoading] = useState(false);
 const [reportAttempt, setReportAttempt] = useState(0);

 const [submitted, setSubmitted] = useState("");

 const [busy, setBusy] = useState(false);

 const [datasets, setDatasets] = useState<Data[]>([]);

 const [trades, setTrades] = useState<Data[]>([]);
 const [tradeHistoryError, setTradeHistoryError] = useState("");

 const initialReport = useRef(false);
 const manuallySelectedReport = useRef(false);
 const latestSeenReport = useRef("");

 useEffect(() => {
  let stopped = false;
  let timer: number;
  let controller: AbortController;
  const datasetsController = new AbortController();

  const refresh = async () => {
   controller = new AbortController();

   const timeout = window.setTimeout(() => controller.abort(), 10000);

   try {
    const next = await api("/dashboard", undefined, controller.signal);

    if (stopped) return;

    setData(next);
    setOnline(true);

    if (next.latest_report?.report_id && (!initialReport.current || (!manuallySelectedReport.current && latestSeenReport.current !== next.latest_report.report_id))) {
     initialReport.current = true;
     latestSeenReport.current = next.latest_report.report_id;
     setReportId(next.latest_report.report_id);
    }
   } catch {
    if (!stopped) setOnline(false);
   } finally {
    if (!stopped) setConnectionChecked(true);
    clearTimeout(timeout);
    if (!stopped) timer = window.setTimeout(refresh, 2000);
   }
  };

  refresh();

  api("/backtest/datasets", undefined, datasetsController.signal)
   .then((d) => { if (!stopped) setDatasets(d.datasets); })
   .catch((e) => { if (!stopped) setNotice(e.message); });

  return () => {
   stopped = true;
   clearTimeout(timer);
   controller?.abort();
   datasetsController.abort();
  };
 }, []);

 useEffect(() => {
  if (!reportId) return;

  const controller = new AbortController();

  setReportLoading(true);
  setReport(null);

  api(`/backtest/reports/${reportId}`, undefined, controller.signal)
   .then((next) => { if (!controller.signal.aborted) setReport(next); })
   .catch((e) => {
    if (!controller.signal.aborted) setNotice(e.message);
   })
   .finally(() => {
    if (!controller.signal.aborted) setReportLoading(false);
   });

  return () => controller.abort();
 }, [reportId, reportAttempt]);

 useEffect(() => {
  const job = data?.jobs?.find((j: Data) => j.id === submitted);

  if (job && !active(job)) {
   setSubmitted("");

   if (job.report_id) setReportId(job.report_id);
   else setNotice(`${job.status}: ${job.message}`);
  }
 }, [data?.jobs, submitted]);

 useEffect(() => {
  if (!data) return;
  const controller = new AbortController();

  api("/paper/trades", undefined, controller.signal)
   .then((d) => {
    if (!controller.signal.aborted) {
     setTrades(d.trades);
     setTradeHistoryError("");
    }
   })
   .catch((e) => {
    if (!controller.signal.aborted) setTradeHistoryError(`Paper trade history could not refresh: ${e.message}. Displaying the last loaded history.`);
   });
  return () => controller.abort();
 }, [data?.account?.realized_pnl, data?.account?.loss_ledger?.last_exit, data?.account?.session_date, online, tab]);

 const mutate = async (path: string, body: Data = {}) => {
  setBusy(true);
  setNotice("");

  try {
   await api(path, body);
  } catch (e) {
   setNotice((e as Error).message);
  } finally {
   setBusy(false);
  }
 };

 const run = async (config: Data) => {
  setBusy(true);
  setNotice("");

  try {
   const job = await api("/backtest/run", {
    ...config,
    history_cache_only: historyCacheOnly,
   });
   setSubmitted(job.id);
  } catch (e) {
   setNotice((e as Error).message);
  } finally {
   setBusy(false);
  }
 };

 const running = data?.jobs?.find(active);

 const [historyCacheOnly, setHistoryCacheOnly] = useState(true);

 const account = data?.account || {};

 const events = [...(data?.events || [])].reverse();

 const errors = Object.entries(data?.engine || {}).filter(
  ([key, value]) => key.includes("error") && value && (typeof value !== "object" || Object.keys(value).length > 0),
 );

 return (
  <main className="app-shell">
   <header className="topbar">
    <div className="brand-lockup">
     <div className="brand-mark" aria-hidden="true"><svg viewBox="0 0 32 32"><path d="M7 24V12m0 3H4m3 5h3M16 21V5m0 4h-3m3 8h3M25 27V10m0 5h-3m3 8h3" /></svg></div>
     <div>
      <div className="eyebrow">OPTIONS TERMINAL</div>
      <h1>NIFTY / SENSEX</h1>
     </div>
    </div>

    <div className="topbar-right">
     <ThemeToggle />
     <span className={`terminal-connection ${online ? "connected" : "disconnected"}`}><i aria-hidden="true" />{online ? "Engine connected" : connectionChecked ? "Engine offline" : "Connecting"}</span>
     <div className={`market-pill ${online && data?.market?.live ? "is-live" : ""}`}>
      {online && data?.market?.live ?
       "LIVE DATA"
      : online ?
       data?.market?.session
      : connectionChecked ? "DISCONNECTED" : "CONNECTING"}
     </div>

     <span className="mode-pill">Paper trading</span>
    </div>
   </header>

   {tab === "monitor" && <section className="market-strip">
    <div className="market-values">
     {(data?.market?.requested_symbols || []).map((symbol: string) => {
      const q = data?.market?.symbols?.[symbol];

      return (
       <div className="market-quote" key={symbol}>
        <span className="quote-symbol">{symbol === "NIFTY" ? "NIFTY 50" : symbol}<small>INDEX · SPOT</small></span>
        <strong className="market-price"><TerminalValue value={q?.ltp} animate={online && q?.fresh && data?.market?.live}>{money(q?.ltp)}</TerminalValue></strong>

        <span
         className={
          online && q?.fresh && data?.market?.live ? "positive" : "muted"
         }
        >
         {online && q?.fresh && data?.market?.live ? "LIVE" : "LAST OBSERVED"}
        </span>

        <small>
         {q?.quote_update_timestamp ?
          `Tick received ${stamp(q.quote_update_timestamp)}`
         : q?.exchange_timestamp ?
          stamp(q.exchange_timestamp)
         : q?.timestamp ?
          `Snapshot received ${stamp(q.timestamp)}; exchange time unavailable`
         : "Waiting for Dhan data"}
        </small>
       </div>
      );
     })}
    </div>
   </section>}

   {!online && connectionChecked && (
    <Notice>
     Backend unavailable. Displayed values are stale; no connection is inferred.
    </Notice>
   )}

   {notice && (
    <Notice>
     {notice}
     <button className="ghost-button" onClick={() => setNotice("")}>
      Dismiss
     </button>
    </Notice>
   )}

   {data?.market?.error && <Notice>{data.market.error}</Notice>}

   {account.halted && <Notice>{account.halt_reason}</Notice>}
   {errors.map(([key, value]) => <Notice key={key}>
    {key.replace(/_/g, " ")}: {typeof value === "object" ? Object.entries(value as Data).map(([name, reason]) => `${name}: ${String(reason)}`).join(" · ") : String(value)}
   </Notice>)}

   <nav className="tabs" aria-label="Trading workspace">
    <button className={tab === "charts" ? "active" : ""} aria-current={tab === "charts" ? "page" : undefined} onClick={() => setTab("charts")}>Market charts</button>
    <button
     className={tab === "monitor" ? "active" : ""}
     aria-current={tab === "monitor" ? "page" : undefined}
     onClick={() => setTab("monitor")}
    >
     Dashboard
    </button>
    <button className={tab === "agentic" ? "active" : ""} aria-current={tab === "agentic" ? "page" : undefined} onClick={() => setTab("agentic")}>Agentic view</button>
    <button
     className={tab === "backtest" ? "active" : ""}
     aria-current={tab === "backtest" ? "page" : undefined}
     onClick={() => setTab("backtest")}
    >
     Backtest results
    </button>

   </nav>

   <div className="terminal-view" key={tab}>
    {tab === "charts" ? <Suspense fallback={<p>Loading chart terminal…</p>}><MarketTerminal account={account} /></Suspense> : tab === "agentic" ? (
    <>
     <AutonomyStatus data={data?.autonomy} />
     <AgentCanvas data={data} online={online} onDetail={setDetail} />
     <StrategyPortfolio data={data?.strategies} />
     {!data?.autonomy && <details key="learning" className="panel spaced workspace-disclosure">
      <summary>Learning &amp; validation <small>{data?.learning_monitor ? `${data.learning_monitor.deployed_models ?? 0} deployed models` : "Status unavailable"} · {registrySummary(data?.learning_candidates || []).pending.length} awaiting review</small></summary>
      <div className="disclosure-content">
     <LearningMonitor data={data?.learning_monitor} online={online} />
     <ModelLearning
      data={data?.ml_learning}
      busy={busy}
      onTrain={() => mutate("/learning/train", {})}
     />
     <LearningRegistry
      rows={data?.learning_candidates || []}
      busy={busy}
      online={online}
      onDetail={setDetail}
      onReview={async (key: string, action: string, reviewer: string) =>
       mutate(`/learning/candidates/${encodeURIComponent(key)}/review`, {
        action,
        reviewed_by: reviewer,
       })
      }
     />
      </div>
     </details>}
     <details key="decisions" className="panel spaced workspace-disclosure">
      <summary>Decision history <small>{events.length} recorded events</small></summary>
      <div className="disclosure-content"><DecisionTimeline events={events} online={online} onDetail={setDetail} /></div>
     </details>
    </>
   ) : tab === "monitor" ?
    <>
     <div className="section-heading">
      <div>
       <h2>Paper account</h2>
       <span className="muted">{online ? data?.engine?.state || "Connected" : "Offline"}</span>
      </div>
      <div className="actions">
       <button
        className="ghost-button"
        disabled={!online || busy}
        onClick={() => mutate("/paper/control", { enabled: !account.enabled })}
       >
        {account.enabled ? "Pause entries" : "Enable paper entries"}
       </button>

       <button
        className="ghost-button"
        disabled={!online || busy}
        onClick={() => mutate(account.halted ? "/resume" : "/halt")}
       >
        {account.halted ? "Resume after halt" : "Halt & exit paper"}
       </button>
      </div>
     </div>

     {tradeHistoryError && <Notice>{tradeHistoryError}</Notice>}
     <PaperPnlPanel account={account} trades={trades} />

     <div className="compact-risk-strip" aria-label="Paper risk limits">
      <span>Daily loss cap <strong>{money(data?.risk?.daily_loss_limit_rupees)}</strong></span>
      <span>Risk / lot <strong>{money(data?.risk?.max_trade_risk_rupees)}</strong></span>
      <span>Session <strong>{data?.risk?.session_start || "—"}–{data?.risk?.session_exit || "—"} IST</strong></span>
     </div>

     <section className="panel spaced">
      <Head
       title="Open positions"
      />
      {account.positions?.length ?
       <div className="table-wrap">
        <table>
         <thead>
          <tr>
           <th>Index / contract</th>
           <th>Expiry / strike</th>
           <th>Qty</th>
           <th>Entry</th>
           <th>Bid mark</th>
           <th>Stop / target</th>
           <th>Data / exit request</th>
          </tr>
         </thead>
         <tbody>
          {account.positions.map((p: Data) => (
           <tr className="clickable" key={p.id} onClick={() => setDetail(p)}>
            <td>
             {p.symbol} · {p.option_type}
             <br />
             {p.contract_id}
            </td>
            <td>
             {p.expiry}
             <br />
             {p.strike}
            </td>
            <td>{p.qty}</td>
            <td>{money(p.entry)}</td>
            <td>{money(p.mark)}</td>
            <td>
             {money(p.stop)} / {money(p.target)}
            </td>
            <td>{p.stale ? "STALE" : "OBSERVED"}{p.exit_request && <><br /><strong>Exit {p.exit_request.status}</strong><br />{p.exit_request.reason} · {p.exit_request.remaining_quantity} remaining</>}</td>
           </tr>
          ))}
         </tbody>
        </table>
       </div>
      : <Empty>
        No open paper positions.
       </Empty>
      }
     </section>

     <details className="panel spaced workspace-disclosure">
      <summary>Trade history <small>{trades.length} recorded fills</small></summary>
      <div className="disclosure-content">{trades.length ? <Trades rows={trades} onDetail={setDetail} title="Paper fills and charges" /> : <Empty>No paper fills recorded.</Empty>}</div>
     </details>
    </>
   : <>
     <details className="panel spaced implementation-details">
     <summary>New backtest</summary>
     <BacktestForm
      defaults={data?.defaults}
      datasets={datasets}
      disabled={!online || busy || !!running || !!submitted}
      onRun={run}
     />

     <label className="research-note">
      <input
       type="checkbox"
       checked={historyCacheOnly}
       onChange={(e) => setHistoryCacheOnly(e.target.checked)}
      />{" "}
      Use downloaded candles only. Missing ranges stop the run.
     </label>

     <details className="workspace-disclosure">
      <summary>Historical data downloads</summary>
      <Head
       title="Local historical data"
       kicker="DOWNLOAD ONCE / REUSE ACROSS STRATEGIES"
       right={
        <button
         className="ghost-button"
         disabled={!online || busy || !!running || !!submitted}
         onClick={() => mutate("/backtest/cache/download")}
        >
         Download / resume 5-year history
        </button>
       }
      />
      <p>Download available NIFTY and SENSEX rolling candles for research. Existing data is reused; missing periods remain unavailable. Download completion does not verify full coverage or train agents.</p>
     </details>

     </details>
     {(running || submitted) && (
      <section className="panel job-progress" role="status">
       <strong>{running?.message || "Job submitted"}</strong>
       <progress max="100" value={running?.progress ?? 0} />
       <span>
        {running?.progress ?? 0}% · Job continues if you close this page
       </span>
       <button
        className="ghost-button"
        disabled={busy}
        onClick={() =>
         mutate(`/backtest/jobs/${running?.id || submitted}/cancel`)
        }
       >
        Cancel job
       </button>
      </section>
     )}

     <details key="backtest-history" className="panel spaced workspace-disclosure" open={!reportId}>
      <summary>Saved backtests <small>Select a previous run</small></summary>
      <div className="disclosure-content"><BacktestHistory jobs={data?.jobs || []} selected={reportId} onSelect={(id:string|null,job?:Data)=>{if(job){setDetail(job);return;}if(id){manuallySelectedReport.current=true;setReportId(id);}}} /></div>
     </details>
     {data?.latest_report?.report_id && reportId!==data.latest_report.report_id && <Notice>A newer report is available.<button className="ghost-button" onClick={()=>{manuallySelectedReport.current=false;latestSeenReport.current=data.latest_report.report_id;setReportId(data.latest_report.report_id);}}>Open latest report</button></Notice>}
     {data?.jobs?.some((j: Data) => j.config?.download_only) && <details className="panel spaced implementation-details">
      <summary>Download jobs & archive manifests</summary>
      {data?.jobs?.some((j: Data) => j.config?.download_only) ?
       data.jobs.filter((j: Data) => j.config?.download_only).map((j: Data) => (
        <div className="job-row" key={j.id}>
         <div>
          <strong>
           {j.config?.symbols?.join(" + ")} · {j.config?.from} → {j.config?.to}
          </strong>
          <small>
           {j.status} · {j.message}
          </small>
          {j.config?.download_only && (
           <>
            <small>
             Archive scope:{" "}
             {j.config.scope || "NIFTY/SENSEX CALL/PUT historical archive"}
            </small>
            {j.download && (
             <small>
              Archive responses: {j.download.processed ?? 0} /{" "}
              {j.download.total ?? "—"} · populated{" "}
              {j.download.nonempty_responses ?? 0} · empty{" "}
              {j.download.empty_responses ?? 0} · observations{" "}
              {j.download.observations ?? 0}
             </small>
            )}
           </>
          )}
         </div>
         <div className="actions">
          {j.archive_manifest_id && (
           <>
            <ArchiveManifest id={j.archive_manifest_id} />
            <button
             className="ghost-button"
             onClick={async () => {
              try {
               const manifest = await api(
                `/backtest/archives/${j.archive_manifest_id}`,
               );
               download(
                `archive-${j.archive_manifest_id}.json`,
                JSON.stringify(manifest, null, 2),
                "application/json",
               );
              } catch (e) {
               setNotice((e as Error).message);
              }
             }}
            >
             Download archive manifest
            </button>
           </>
          )}
          {j.report_id && (
           <button
            className="ghost-button"
            disabled={reportLoading}
            onClick={() => setReportId(j.report_id)}
           >
            {reportId === j.report_id ? "Selected" : "Open report"}
           </button>
          )}
         </div>
        </div>
       ))
      : <Empty>No saved runs.</Empty>}
     </details>}

     {reportLoading && <div role="status"><Notice>Loading saved report…</Notice></div>}

     {report ?
      <><BacktestOverview key={reportId} report={report} onDetail={setDetail} /><details className="panel spaced implementation-details"><summary>Full report · trades, agent attribution, coverage & assumptions</summary><Report report={report} onDetail={setDetail} /></details></>
     : !reportLoading && (reportId ?
      <div className="report-retry" role="status">
       <p>The selected report could not be loaded.</p>
       <button className="ghost-button" onClick={() => { setNotice(""); setReportAttempt((attempt) => attempt + 1); }}>Retry report</button>
      </div>
      : <Empty>No report selected. Run a source check or select a contract-specific dataset.</Empty>)
     }
    </>
   }

   </div>
   {tab === "monitor" && <details className="panel spaced workspace-disclosure system-details">
    <summary>System &amp; risk details <small>{online ? data?.readiness?.entry_ready ? "Entry checks available" : `Entries blocked · ${data?.readiness?.entry_blockers?.[0] || "Readiness unavailable"}` : "Offline"} · Paper only</small></summary>
    <div className="disclosure-content">
     <p><strong>Entry readiness: {data?.readiness?.entry_ready ? "Ready for candidate evaluation" : "Blocked"}</strong> · {(data?.readiness?.entry_blockers || []).join(" · ")}</p>
     <p>Exit capability: {data?.readiness?.exit_status || "Unknown"}</p>
     {data?.engine?.recovery && <p role="status">Automatic recovery: <strong>{data.engine.recovery.state}</strong> · Last check {data.engine.recovery.checked_at || "pending"}. Detailed checks and repair history are in Agentic view.</p>}
     {(data?.readiness?.positions || []).filter((p: Data) => p.pending).map((p: Data) => <p key={p.position_id}>Pending exit · {p.contract_id} · {p.pending.reason} · Requested {p.pending.first_requested_at} · {p.pending.remaining_quantity} remaining · {p.pending.attempts} attempts · {p.pending.last_error || p.pending.status}</p>)}
     <div className="compact-risk-strip">
      <span>Correlated risk / lot <strong>{money(data?.risk?.max_correlated_risk_rupees)}</strong></span>
      <span>Remaining loss allocation <strong>{money(account.remaining_loss_allocation)}</strong></span>
      <span>Entry cutoff <strong>{data?.risk?.entry_cutoff || "—"} IST</strong></span>
     </div>
     <p>Exit requests stay pending when executable quotes are unavailable.</p>
     <p>Telegram: {data?.telegram?.enabled ? data.telegram.configured ? data.telegram.worker_alive ? "Running" : "Worker stopped" : "Credentials missing" : "Disabled"}{data?.telegram?.last_error ? ` · ${data.telegram.last_error}` : ""}</p>
    </div>
   </details>}
   {detail && <AuditDrawer detail={detail} onClose={() => setDetail(null)} />}
  </main>
 );
}

function AuditDrawer({ detail, onClose }: { detail: Data; onClose: () => void }) {
 const dialog = useRef<HTMLDialogElement>(null);
 useEffect(() => {
  const element = dialog.current!;
  const trigger = document.activeElement as HTMLElement | null;
  const previousOverflow = document.body.style.overflow;
  element.showModal();
  document.body.style.overflow = "hidden";
  return () => {
   element.close();
   document.body.style.overflow = previousOverflow;
   if (trigger?.isConnected) trigger.focus({ preventScroll: true });
  };
 }, []);
 return (
    <dialog ref={dialog} className="drawer-backdrop" aria-label="Audit details"
     onCancel={(event) => { event.preventDefault(); onClose(); }}
     onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
     <aside className="drawer">
      <button
       className="close-button"
       aria-label="Close details"
       onClick={onClose}
      >
       ×
      </button>
      <div className="eyebrow">AUDIT / SOURCE EVIDENCE</div>
      <h2>{detail.agent || detail.symbol || "Details"}</h2>
      {detail.message && <div className="drawer-block"><strong>{detail.status || "Job details"}</strong><p>{detail.message}</p>{detail.config && <p>{detail.config.from} → {detail.config.to} · {detail.config.symbols?.join(" + ")}</p>}</div>}
      {detail.label && <div className="drawer-block"><strong>{detail.status}</strong><p>{detail.label}</p><small>{detail.event_id ? `Recorded event: ${detail.event_id}` : "No event recorded for this stage"}</small></div>}
      <AuditDetails detail={detail} />
      {detail.decision_review && <div className="drawer-block">
       <h3>Coordinator checks</h3>
       <p>{detail.decision_review.version} · {stamp(detail.decision_review.evaluated_at)}</p>
       <p>{detail.decision_review.reason}</p>
       {Object.entries(detail.decision_review.checks || {}).map(([name, value]) => {
        const check = value as Data;
        return <p key={name}><strong>{name.replace(/_/g, " ")} · {check.status}</strong><br />{check.reason}</p>;
       })}
       <h3>Specialist availability</h3>
       {Object.entries(detail.decision_review.agents || {}).map(([name, value]) => {
        const agent = value as Data;
        return <p key={name}><strong>{name} · {agent.status}</strong><br />{agent.task}</p>;
       })}
      </div>}
      {detail.evaluation?.task && <div className="drawer-block">
       <h3>Assigned task and current evidence</h3>
       <p>{detail.evaluation.task}</p>
       <p>{detail.evaluation.status} · {detail.evaluation.required ? "Required entry check" : "Context or research role"}</p>
       <pre>{JSON.stringify(detail.evaluation.evidence, null, 2)}</pre>
      </div>}
      <details className="drawer-block">
       <summary>All recorded fields / raw evidence</summary>
       <pre>{JSON.stringify(detail, null, 2)}</pre>
      </details>
     </aside>
    </dialog>
 );
}

function ArchiveManifest({ id }: Data) {
 const [manifest, setManifest] = useState<Data | null>(null);

 const [open, setOpen] = useState(false);

 const [error, setError] = useState("");

 const inspect = async () => {
  if (manifest) {
   setOpen((value) => !value);
   return;
  }

  try {
   setError("");
   setManifest(await api(`/backtest/archives/${id}`));
   setOpen(true);
  } catch (e) {
   setError((e as Error).message);
  }
 };

 return (
  <>
   <button className="ghost-button" onClick={inspect}>
    {open ? "Hide archive details" : "View archive details"}
   </button>
   {error && <small className="negative">{error}</small>}
   {open && manifest && (
    <div className="research-note">
     <strong>
      {manifest.actual_from} → {manifest.actual_to}
     </strong>{" "}
     · {manifest.coverage_status}
     <br />
     Processed {manifest.processed_requests} / {manifest.request_count} requests
     · populated {manifest.nonempty_responses} · empty{" "}
     {manifest.empty_responses} · {manifest.observations} observations
     <br />
     {manifest.symbols?.join(" + ")} · {manifest.sides?.join(" / ")} ·{" "}
     {manifest.expiry_flags?.join(" / ")} expiry · codes{" "}
     {manifest.expiry_codes?.join(", ")} · offsets{" "}
     {manifest.strike_offsets?.join(", ")}
    </div>
   )}
  </>
 );
}

function BacktestForm({ defaults, datasets, disabled, onRun }: Data) {
 const [source, setSource] = useState("observed");
 const [dataset, setDataset] = useState("");
 const [strategyMode, setStrategyMode] = useState("portfolio");
 const [optionScreen, setOptionScreen] = useState("option-buyer-v1");

 const [underlying, setUnderlying] = useState("PARALLEL");
 const [years, setYears] = useState("days:7");

 const [from, setFrom] = useState("");
 const [to, setTo] = useState("");

 const [capital, setCapital] = useState("");
 const [risk, setRisk] = useState("");

 const [dailyLimit, setDailyLimit] = useState("");
 const [estimateExits,setEstimateExits]=useState(false);
 const [estimateHaircut,setEstimateHaircut]=useState("0.05");
 const [correlatedLimit, setCorrelatedLimit] = useState("");

 useEffect(() => {
  if (defaults) {
   setCapital((c) => c || String(defaults.capital));
   setRisk((r) => r || String(defaults.risk_per_trade));
  }
 }, [defaults]);

 return (
  <>
   <div className="section-heading">
    <div>
     <div className="eyebrow">
      CAUSAL REPLAY / ONE SHARED PAPER ACCOUNT
     </div>
     <h2>Backtest lab</h2>
    </div>
   </div>

   <form
    className="backtest-controls panel"
    onSubmit={(e) => {
     e.preventDefault();
     onRun({
      source,
      ...(source === "observed" ? {strategy_mode: "autonomous"} : {}),
      ...(source === "dhan" ? {estimate_missing_exits:estimateExits,estimate_haircut:Number(estimateHaircut)} : {}),
      dataset,
      ...(source === "csv" ? { strategy_mode: strategyMode, option_screen: optionScreen } : {}),
      underlying,
      ...(years === "custom" ? { from, to }
      : years.startsWith("days:") ? { days: Number(years.split(":")[1]) }
      : { years: Number(years) }),
      capital: Number(capital),
      risk_per_trade: Number(risk),
      ...(dailyLimit ? { daily_loss_limit: Number(dailyLimit) } : {}),
      ...(correlatedLimit ?
       { correlated_risk_limit: Number(correlatedLimit) }
      : {}),
     });
    }}
   >
    <label className="control">
     Data source
     <select
      aria-label="Data source"
      value={source}
      onChange={(e) => setSource(e.target.value)}
     >
      <option value="observed">Active autonomous policy · archived quotes and OI</option>
      <option value="dhan">Dhan rolling candles · estimated research</option>
      <option value="csv">Sourced contract CSV</option>
     </select>
    </label>

    {source === "observed" && <p className="research-note">Uses saved responses through the active paper selector and broker. Missing sessions, depth, contract candles or fee receipts remain unavailable; partial runs do not establish a complete result.</p>}

    {source === "dhan" && <label className="control">Missing exit prices<select aria-label="Missing exit price mode" value={estimateExits ? "estimate" : "strict"} onChange={e=>setEstimateExits(e.target.value==="estimate")}><option value="strict">Observed data only</option><option value="estimate">Exploratory estimated exit</option></select></label>}
    {source === "dhan" && estimateExits && <label className="control">Exit price reduction<select aria-label="Estimated exit haircut" value={estimateHaircut} onChange={e=>setEstimateHaircut(e.target.value)}><option value="0">0% · prior price sensitivity</option><option value="0.05">5% · scenario assumption</option><option value="0.10">10% · higher loss sensitivity</option></select><small>Previous minute only. No learning from this run.</small></label>}
    {source === "csv" && <label className="control">Option screen
     <select aria-label="Option screen" value={optionScreen} onChange={e=>setOptionScreen(e.target.value)}>
      <option value="option-buyer-v1">Current screen · observed Greeks and depth required</option>
      <option value="legacy">Legacy comparison · does not validate current trading</option>
     </select>
    </label>}
    {source === "csv" && (
     <label className="control">
      Strategy
      <select aria-label="Replay strategy" value={strategyMode} onChange={(e) => setStrategyMode(e.target.value)}>
       <option value="portfolio">Combined portfolio · one shared account</option>
       <option value="orb_retest">Opening-range retest</option>
       <option value="trend_pullback">Trend pullback</option>
       <option value="range_rejection">Range rejection</option>
      </select>
     </label>
    )}

    {source === "csv" && (
     <label className="control">
      Dataset
      <select
       required
       value={dataset}
       onChange={(e) => setDataset(e.target.value)}
       aria-label="Dataset"
      >
       <option value="">Choose dataset</option>
       {datasets.map((d: Data) => (
        <option key={d.name} value={d.name} disabled={d.option_replay_available === false}>
         {d.name}{d.option_replay_available === false ? ` · ${d.reason}` : ""}
        </option>
       ))}
      </select>
     </label>
    )}

    <label className="control">
     Indices
     <select
      aria-label="Indices"
      value={underlying}
      onChange={(e) => setUnderlying(e.target.value)}
     >
      <option value="PARALLEL">NIFTY + SENSEX · shared capital</option>
      <option>NIFTY</option>
      <option>SENSEX</option>
     </select>
    </label>

    <label className="control">
     History
     <select
      aria-label="History range"
      value={years}
      onChange={(e) => setYears(e.target.value)}
     >
      <option value="0">0 years · last completed session</option>
      {[7, 30, 90].map((n) => (
       <option key={n} value={`days:${n}`}>
        Last {n} calendar days
       </option>
      ))}
      {[1, 2, 3, 4, 5].map((n) => (
       <option key={n} value={n}>
        {n} year{n > 1 ? "s" : ""}
       </option>
      ))}
      <option value="custom">Custom dates</option>
     </select>
    </label>

    {years === "custom" && (
     <>
      <label className="control">
       From
       <input
        aria-label="From date"
        type="date"
        required
        value={from}
        max={to || undefined}
        onChange={(e) => setFrom(e.target.value)}
       />
      </label>
      <label className="control">
       To
       <input
        aria-label="To date"
        type="date"
        required
        value={to}
        min={from || undefined}
        onChange={(e) => setTo(e.target.value)}
       />
      </label>
     </>
    )}

    <label className="control">
     Capital (₹)
     <input
      aria-label="Capital"
      type="number"
      required
      min="0.01"
      step="any"
      value={capital}
      onChange={(e) => setCapital(e.target.value)}
     />
    </label>

    <label className="control">
     Max risk/trade (₹)
     <input
      aria-label="Risk per trade"
      type="number"
      required
      min="0.01"
      step="any"
      value={risk}
      onChange={(e) => setRisk(e.target.value)}
     />
    </label>

    <label className="control">
     Daily loss budget (₹)
     <input
      aria-label="Backtest daily loss budget"
      type="number"
      min="0.01"
      step="any"
      placeholder={
       defaults ?
        String(
         (Number(risk) * defaults.daily_loss_limit) / defaults.risk_per_trade,
        )
       : "Automatic"
      }
      value={dailyLimit}
      onChange={(e) => setDailyLimit(e.target.value)}
     />
    </label>

    <label className="control">
     Same-direction risk budget (₹)
     <input
      aria-label="Backtest correlated risk budget"
      type="number"
      min="0.01"
      step="any"
      placeholder={
       defaults ?
        String(
         (Number(risk) * defaults.correlated_risk_limit) /
          defaults.risk_per_trade,
        )
       : "Automatic"
      }
      value={correlatedLimit}
      onChange={(e) => setCorrelatedLimit(e.target.value)}
     />
    </label>

    <button
     className="run-button"
     disabled={disabled || !capital || !risk || (source === "csv" && !dataset)}
    >
     {disabled ? "WAITING" : "RUN BACKTEST"}
    </button>
   </form>
   <p className="research-note">
    Backtest capital and risk have no application-defined upper cap. Blank daily
    and same-direction budgets scale with Max Risk/Trade using the configured
    paper-budget ratios; the placeholders show their effective values. Set
    either explicitly to override it. Cash and whole-lot affordability still
    apply. Paper-account settings are unchanged.
   </p>
   <p className="research-note">
    Dhan runs calculate an ORB retest research scenario from cached index and
    option candles, with automatic direction, a held strike, structural stops
    and time exits. Current Dhan lot sizes are disclosed sizing assumptions.
    Net P&L uses estimated charges; dated historical fees, expiry identity and
    executable quote depth remain unverified. Inspect each run's assumptions for differences from
    the full paper policy.
   </p>
  </>
 );
}

function Report({ report, onDetail }: Data) {
 const m = report.metrics || {};
 const valid = report.quality === "verified";
 const research = report.quality === "research";
 const netResearch = report.quality === "research_net";
 const autonomousReplay = report.source === "autonomous_observed_quote_replay";
 const invalidated = report.status === "invalidated";

 const [cache, setCache] = useState<Data | null>(null);

 useEffect(() => {
  api("/backtest/cache")
   .then(setCache)
   .catch(() => setCache(null));
 }, [report.run_id]);

 return (
  <>
   <div className="section-heading">
    <div>
     <div className="eyebrow">{report.source}</div>
     <h2>
      {valid ?
       "Simulation results"
      : invalidated ?
       "Invalidated synthetic option report"
      : netResearch ?
       autonomousReplay ? "Archived autonomous replay · estimated fees" : "Estimated net research · current-lot scenario"
      : research ?
       "Gross research · current-lot scenario"
      : "Data quality blocked"}
     </h2>
    </div>
    <span className="data-badge">{stamp(report.created_at)}</span>
   </div>

   {(report.issues || []).map((issue: string, i: number) => (
    <Notice key={i}>{issue}</Notice>
   ))}
   {(report.parity_limitations || []).map((issue: string, i: number) => (
    <Notice key={`parity-${i}`}>{issue}</Notice>
   ))}

   {report.strategy_version && (
    <Notice>
     Strategy: {report.strategy_version} · Fidelity:{" "}
     {report.fidelity || "See original run assumptions"} · Deployment:{" "}
     {report.deployment_ready ? "See reviewed evidence" : "Not validated"}
    </Notice>
   )}

   {report.opportunities?.length > 0 && (
    <Opportunities rows={report.opportunities} onDetail={onDetail} />
   )}

   {report.decision_blockers?.length > 0 && <section className="panel spaced">
    <Head title="Recorded entry blockers" kicker="DECISION HISTORY / INCLUDING EARLIER DATA WAITS" />
    <p>Counts are recorded decision checks, including repeated checks of the same candidate. They are not trades or independent opportunities.</p>
    {report.data_blocked_candidates != null && <p>{report.data_blocked_candidates} distinct candidates encountered data gaps; {report.unresolved_data_blocked_candidates ?? "—"} remained unfilled. A later expired setup does not erase an earlier data wait.</p>}
    {report.decision_blockers.map((row: Data) => <button className="stream-row" key={row.reason} onClick={() => onDetail(row)}>
     <div className="stream-body"><strong>{row.reason}</strong><p>{row.checks} checks · {stamp(row.first_at)} → {stamp(row.last_at)}</p></div><span>Details ›</span>
    </button>)}
   </section>}

   {research &&
    !["rolling-research-v3", "orb-retest-rolling-v1"].includes(
     report.replay_version,
    ) && (
     <Notice>
      This saved report predates the current shared risk-budget replay. It is
      retained for audit; rerun the same range to apply the current strategy
      rules and selected budgets.
     </Notice>
    )}

   <section className="panel spaced">
    <Head
     title="Research validation & local data"
     kicker="PERFORMANCE / LEARNING / LOCAL DATA"
     right={
      <button
       className="ghost-button"
       onClick={() =>
        download(
         `backtest-${report.run_id}.json`,
         JSON.stringify(report, null, 2),
         "application/json",
        )
       }
      >
       Download full report
      </button>
     }
    />
    <Empty>
     <p>
      Agent improvement:{" "}
      {(
       report.learning_run?.some(
        (l: Data) => l.validation_status === "PROMOTED",
       )
      ) ?
       "A candidate passed recorded validation in this run; inspect the baseline and candidate evidence below. Future loss reduction is not guaranteed."
      : "Not demonstrated in this run. Recording outcomes is not the same as a validated improvement or an active policy change."
      }
     </p>
     {cache && (
      <p>
       Local candle cache: {cache.retained_responses} retained responses ·{" "}
       {(cache.compressed_bytes / 1048576).toFixed(2)} MiB compressed across{" "}
       {cache.responses} cached responses. Stored in {cache.storage}. Matching
       historical requests reuse local data; missing ranges still require Dhan.
      </p>
     )}
    </Empty>
   </section>

   {report.coverage?.length > 0 && (
    <section className="panel spaced">
     <Head
      title={autonomousReplay ? "Archived session input coverage" : "Observed historical API coverage"}
      kicker={
       research ?
        "REQUESTED-RANGE CHUNKS / CLICK FOR GAPS AND LOT PROVENANCE"
       : "SOURCE COVERAGE"
      }
     />
     {report.coverage.map((c: Data, index: number) => (
      <button
       className="stream-row"
       key={`${c.symbol}:${c.contract_id || "rolling"}:${c.day || c.probe_from}:${index}`}
       onClick={() => onDetail(c)}
      >
       <div className="stream-body">
        <strong>
         {autonomousReplay ? `${c.date} · ${c.underlying_observations ?? "—"} underlying observations` : <>{c.symbol} · {c.contract_id ? `${c.contract_id} · ${c.observed_minutes ?? "—"} observed minutes` : `${c.candles ?? "—"} candles returned`}</>}
        </strong>
        <p>
         {autonomousReplay ? `${c.full_sessions ? "Complete" : "Incomplete"} session inputs · Quote observations are not candles or verified fills` : c.contract_id ? `${c.day} · ${c.missing_minutes ?? "—"} missing minutes · Contract-specific candles` :
          `${c.probe_from} → ${c.probe_to} · ${c.api_access} · ${c.expiry_cycle || "No cycle returned"}`}
        </p>
       </div>
       <span>Details ›</span>
      </button>
     ))}
    </section>
   )}

   {(valid || netResearch) && <section className="metric-grid">
    <Kpi label="Average daily P&L" value={money(m.average_daily_pnl)} sub={`${m.sessions} observed sessions`} />
    <Kpi label="Target month rate" value={pct(m.target_month_rate)} sub={`${money(m.monthly_target)} ${m.monthly_target_basis || "unspecified basis"} target · observed sessions only; not guaranteed`} />
    <Kpi label="Worst session" value={money(m.worst_day)} sub={`${m.no_trade_days} no-trade sessions`} />
   </section>}
   {research && <Kpi label="Partial realized gross" value={money(m.partial_realized_gross_pnl)} sub="Excludes unresolved positions; not full performance" />}

   <section className="panel spaced">
    <Head
     title="Agent performance in this run"
     kicker="EVALUATIONS / OUTCOMES / VALIDATION"
    />
    <div className="table-wrap">
     <table>
      <thead>
       <tr>
        <th>Agent</th>
        <th>Evaluations</th>
        <th>Passed</th>
        <th>Rejected</th>
        <th>Outcomes</th>
        <th>Validation</th>
       </tr>
      </thead>
      <tbody>
       {(report.agent_performance || []).map((a: Data) => {
        const learning = report.learning_run?.find(
         (l: Data) => l.agent === a.agent,
        );

        return (
         <tr
          key={a.agent}
          className="clickable"
          onClick={() => onDetail({ ...a, learning })}
         >
          <td>{a.agent}</td>
          <td>{a.candidates ?? "—"}</td>
          <td>{a.passed ?? "—"}</td>
          <td>{a.rejected ?? "—"}</td>
          <td>{a.outcomes}</td>
          <td>{learning?.validation_status || "Not evaluated"}</td>
         </tr>
        );
       })}
      </tbody>
     </table>
    </div>
    <p className="research-note">
     Click an agent for contexts, proposed changes and baseline/candidate
     validation.
    </p>
   </section>

   <PerformanceBreakdown report={report} onDetail={onDetail} />

   <Trades
    rows={report.trades || []}
    onDetail={onDetail}
    title={
     valid ? "Backtest trades"
     : netResearch && report.status === "research_complete" ? "Research trades · estimated net charges"
     : report.status === "research_complete" ?
      "All research trades · gross scenario"
     : "Partial trades · not validated performance"
    }
   />

   {report.unresolved?.length > 0 && (
    <Notice>
     {report.unresolved.length} positions lack a trustworthy exit. Headline P&L
     is withheld.
    </Notice>
   )}

   {report.skipped_entries?.length > 0 && (
    <section className="panel spaced">
     <Head
      title="Selected entries that could not be simulated"
      kicker="MISSING OPEN / NOT SILENTLY DROPPED"
     />
     {report.skipped_entries.map((s: Data, i: number) => (
      <button
       className="stream-row"
       key={`${s.id}:${i}`}
       onClick={() => onDetail(s)}
      >
       <div className="stream-body">
        <strong>
         {s.symbol} · {s.option_type} · {stamp(s.attempted_entry_time)}
        </strong>
        <p>{s.reason}</p>
        <small>{s.contract_id}</small>
       </div>
       <span>Inspect ›</span>
      </button>
     ))}
    </section>
   )}

   <section className="panel spaced">
    <Head title="Assumptions and provenance" kicker="RESEARCH LIMITATIONS" />
    <Empty>
     {(report.assumptions || []).map((s: string) => (
      <p key={s}>{s}</p>
     ))}
     <button
      className="ghost-button"
      onClick={() =>
       onDetail({ config: report.config, windows: report.validation_windows })
      }
     >
      Configuration & validation windows
     </button>
    </Empty>
   </section>
  </>
 );
}

function Opportunities({ rows, onDetail }: Data) {
 const [page, setPage] = useState(0);

 const [query, setQuery] = useState("");

 useEffect(() => setPage(0), [rows, query]);

 const filtered = rows.filter((r: Data) =>
  `${r.symbol || ""} ${r.setup || ""} ${r.status} ${r.reason || ""}`
   .toLowerCase()
   .includes(query.toLowerCase()),
 );

 return (
  <section className="panel spaced">
   <Head
    title="Strategy opportunities and exclusions"
    kicker={`${filtered.length} RECORDED DECISIONS / NOT ALL ARE TRADES`}
    right={
     <input
      aria-label="Filter opportunities"
      value={query}
      onChange={(e) => setQuery(e.target.value)}
      placeholder="Index, setup or reason"
     />
    }
   />
   <div className="table-wrap">
    <table>
     <thead>
      <tr>
       <th>Available at</th>
       <th>Index / side</th>
       <th>Setup</th>
       <th>Status</th>
       <th>Reason</th>
      </tr>
     </thead>
     <tbody>
      {filtered.slice(page * 25, (page + 1) * 25).map((r: Data, i: number) => (
       <tr
        className="clickable"
        key={`${r.id || r.signal_id}:${page}:${i}`}
        onClick={() => onDetail(r)}
       >
        <td>{stamp(r.available_at || r.timestamp)}</td>
        <td>
         {r.symbol || "See signal"} {r.option_type}
        </td>
        <td>{r.setup || r.contract_id || "—"}</td>
        <td>{r.status}</td>
        <td>{r.reason || "Inspect decision and protection inputs"}</td>
       </tr>
      ))}
     </tbody>
    </table>
   </div>
   <div className="section-heading">
    <button
     className="ghost-button"
     disabled={page === 0}
     onClick={() => setPage(page - 1)}
    >
     Previous
    </button>
    <span>
     Page {page + 1} / {Math.max(1, Math.ceil(filtered.length / 25))}
    </span>
    <button
     className="ghost-button"
     disabled={(page + 1) * 25 >= filtered.length}
     onClick={() => setPage(page + 1)}
    >
     Next
    </button>
   </div>
  </section>
 );
}

function Trades({ rows, onDetail, title }: Data) {
 const [query, setQuery] = useState("");

 const [index, setIndex] = useState("ALL");
 const [outcome, setOutcome] = useState("ALL");

 const [from, setFrom] = useState("");
 const [to, setTo] = useState("");
 const [page, setPage] = useState(0);

 useEffect(() => setPage(0), [query, index, outcome, from, to, rows]);

 const filtered = rows.filter((t: Data) => {
  const day = String(t.entry_time || t.entry_ts || "").slice(0, 10);
  const pnl = t.pnl ?? t.gross_pnl;

  return (
   `${t.symbol} ${t.setup} ${t.contract_id} ${t.option_type}`
    .toLowerCase()
    .includes(query.toLowerCase()) &&
   (index === "ALL" || t.symbol === index) &&
   (!from || day >= from) &&
   (!to || day <= to) &&
   (outcome === "ALL" ||
    (outcome === "WIN" ? pnl > 0
    : outcome === "LOSS" ? pnl < 0
    : pnl === 0))
  );
 });

 const pageSize = 50;
 const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
 const current = Math.min(page, pages - 1);

 const exportTrades = () => {
  const fields = [
   "id",
   "symbol",
   "option_type",
   "contract_id",
   "expiry",
   "expiry_bucket",
   "strike",
   "entry_time",
   "exit_time",
   "entry_ts",
   "exit_ts",
   "entry_premium",
   "exit_premium",
   "stop",
   "target",
   "quantity",
   "gross_pnl",
   "costs",
   "pnl",
   "reason",
   "setup",
   "regime",
   "pnl_basis",
   "delta",
   "gamma",
   "theta",
   "vega",
   "greeks_source",
   "greeks_observed_at",
   "agent_contexts",
   "policy_versions",
   "lot_scenario",
  ];

  const cell = (v: any) => {
   const s =
    v == null ? ""
    : typeof v === "object" ? JSON.stringify(v)
    : String(v);
   return '"' + (/^[=+@]/.test(s) ? "'" + s : s).replace(/"/g, '""') + '"';
  };

  download(
   "backtest-trades.csv",
   [
    fields.join(","),
    ...filtered.map((t: Data) => fields.map((f) => cell(t[f])).join(",")),
   ].join("\r\n"),
   "text/csv;charset=utf-8",
  );
 };

 return (
  <section className="panel spaced">
   <Head
    title={title}
    kicker="EVERY RECORDED TRADE / SEARCH, FILTER, EXPORT"
    right={
     <button
      className="ghost-button"
      disabled={!filtered.length}
      onClick={exportTrades}
     >
      Export all {filtered.length} matching trades
     </button>
    }
   />

   <div className="backtest-controls">
    <label className="control">
     Search
     <input
      aria-label="Search trades"
      placeholder="Setup, strike, contract"
      value={query}
      onChange={(e) => setQuery(e.target.value)}
     />
    </label>
    <label className="control">
     Index
     <select
      aria-label="Trade index"
      value={index}
      onChange={(e) => setIndex(e.target.value)}
     >
      <option value="ALL">Both indices</option>
      <option>NIFTY</option>
      <option>SENSEX</option>
     </select>
    </label>
    <label className="control">
     Outcome
     <select
      aria-label="Trade outcome"
      value={outcome}
      onChange={(e) => setOutcome(e.target.value)}
     >
      <option value="ALL">All outcomes</option>
      <option value="WIN">Profit</option>
      <option value="LOSS">Loss</option>
      <option value="FLAT">Breakeven</option>
     </select>
    </label>
    <label className="control">
     Entry from
     <input
      type="date"
      aria-label="Trade start date"
      value={from}
      onChange={(e) => setFrom(e.target.value)}
     />
    </label>
    <label className="control">
     Entry through
     <input
      type="date"
      aria-label="Trade end date"
      value={to}
      onChange={(e) => setTo(e.target.value)}
     />
    </label>
   </div>

   {filtered.length ?
    <div className="table-wrap">
     <table>
      <thead>
       <tr>
        <th>Index / setup</th>
        <th>Strike / expiry</th>
        <th>Entry time (IST)</th>
        <th>Exit time (IST)</th>
        <th>Entry → exit</th>
        <th>SL / target</th>
        <th>Qty</th>
        <th>Gross</th>
        <th>Charges</th>
        <th>Net</th>
        <th>Exit reason</th>
       </tr>
      </thead>
      <tbody>
       {filtered
        .slice(current * pageSize, (current + 1) * pageSize)
        .map((t: Data) => (
         <tr key={t.id} className="clickable" onClick={() => onDetail(t)}>
          <td>
           {t.symbol} · {t.option_type}
           <br />
           {t.setup}
          </td>
          <td>
           {t.strike}
           <br />
           {t.expiry || `${t.expiry_bucket || "Unknown"} · expiry unverified`}
          </td>
          <td>{stamp(t.entry_time || t.entry_ts)}</td>
          <td>{stamp(t.exit_time || t.exit_ts)}</td>
          <td>
           {money(t.entry_premium)} → {money(t.exit_premium)}
          </td>
          <td>
           {money(t.stop)} / {money(t.target)}
          </td>
          <td>{t.quantity}</td>
          <td>{money(t.gross_pnl)}</td>
          <td>{money(t.costs)}</td>
          <td>{money(t.pnl)}</td>
          <td>
           {t.reason}
           {t.partial ? " · partial" : ""}
          </td>
         </tr>
        ))}
      </tbody>
     </table>
    </div>
   : <Empty>
     No completed fills match this view. Missing prices and trades are never
     generated.
    </Empty>
   }

   <div className="job-row">
    <span>
     {filtered.length} of {rows.length} trades · page {current + 1} / {pages} ·{" "}
     {pageSize} per page
    </span>
    <div className="actions">
     <button
      className="ghost-button"
      disabled={current === 0}
      onClick={() => setPage(current - 1)}
     >
      Previous trades
     </button>
     <button
      className="ghost-button"
      disabled={current + 1 >= pages}
      onClick={() => setPage(current + 1)}
     >
      Next trades
     </button>
    </div>
   </div>
   <p className="research-note">
    No 500-trade truncation: every saved backtest trade is accessible through
    pages or export. Filters use net P&L where available; otherwise gross
    scenario P&L. Click any trade for its full decision and sizing audit.
   </p>
  </section>
 );
}

function download(name: string, body: string, type: string) {
 const url = URL.createObjectURL(new Blob([body], { type }));
 const link = document.createElement("a");
 link.href = url;
 link.download = name;
 link.click();
 window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function PerformanceBreakdown({ report, onDetail }: Data) {
 const [group, setGroup] = useState("month");
 const research = report.quality === "research";
 const grouped: Data = {};

 for (const d of report.daily || []) {
  const key =
   group === "day" ? d.date
   : group === "year" ? d.date.slice(0, 4)
   : d.date.slice(0, 7);
  grouped[key] ??= {
   period: key,
   sessions: 0,
   trades: 0,
   gross: 0,
   net: 0,
   netKnown: true,
   rows: [],
  };
  const g = grouped[key];
  g.sessions++;
  g.trades += d.trades || 0;
  g.gross += d.gross_pnl ?? d.pnl ?? 0;
  if (d.pnl == null) g.netKnown = false;
  else g.net += d.pnl;
  g.rows.push(d);
 }

 return (
  <section className="panel spaced">
   <Head
    title="Daily, monthly and yearly performance"
    kicker={
     research ?
      "COMPLETED SESSIONS / GROSS SCENARIO ONLY"
     : "OBSERVED SESSION RESULTS"
    }
    right={
     <select
      aria-label="Performance grouping"
      value={group}
      onChange={(e) => setGroup(e.target.value)}
     >
      <option value="day">Daily</option>
      <option value="month">Monthly</option>
      <option value="year">Yearly</option>
     </select>
    }
   />
   <div className="table-wrap">
    <table>
     <thead>
      <tr>
       <th>Period</th>
       <th>Sessions</th>
       <th>Trades</th>
       <th>{research ? "Gross scenario" : "Net P&L"}</th>
       {research && <th>After-charges result</th>}
      </tr>
     </thead>
     <tbody>
      {Object.values(grouped).map((g: any) => (
       <tr key={g.period} className="clickable" onClick={() => onDetail(g)}>
        <td>{g.period}</td>
        <td>{g.sessions}</td>
        <td>{g.trades}</td>
        <td>{research ? money(g.gross) : g.netKnown ? money(g.net) : "Unavailable"}</td>
        {research && <td>{g.netKnown ? money(g.net) : "Unavailable"}</td>}
       </tr>
      ))}
     </tbody>
    </table>
   </div>
   <p className="research-note">
    Missing or unresolved sessions are not assigned invented P&L. Partial runs
    are not representative full-period totals. Use the trade date filters for a
    specific period.
   </p>
  </section>
 );
}

function AuditDetails({ detail: d }: Data) {
 const learning = d.learning;
 const trade = d.entry_premium != null;

 return (
  <>
   <AgentLessons rows={learning?.metadata?.lessons || d.lessons || []} />
   {d.summary && <div className="drawer-block">
    <h3>Recorded decision · {d.status || "Status unavailable"}</h3>
    <p><strong>{d.summary}</strong></p>
    <p>{d.symbol || "SYSTEM"} · {stamp(d.timestamp)}</p>
    <p>Context: {d.context || "No context recorded"}</p>
    {d.evaluation && <><h3>Evaluation inputs</h3><dl className="decision-evaluation">{Object.entries(d.evaluation).map(([key, value]) => <div key={key}><dt>{key.replace(/_/g, " ")}</dt><dd>{typeof value === "object" ? JSON.stringify(value) : String(value ?? "Unavailable")}</dd></div>)}</dl></>}
   </div>}
   {d.source_run_id && d.version != null && d.validation_status && <div className="drawer-block">
    <h3>Candidate review record</h3>
    <p>Candidate v{d.version} · {d.validation_status}</p>
    <p>{d.blocked_value ? `Exclude ${d.blocked_value}` : `Allow ${d.allowed_value || "candidate context"}`}</p>
    <p>Reviewer: {d.reviewed_by || "Not reviewed"}<br />Reviewed: {d.reviewed_at ? stamp(d.reviewed_at) : "Not recorded"}<br />Effective from: {d.effective_from || "Not scheduled"}</p>
    {d.review_reason && <p>Recorded review note: {d.review_reason}</p>}
    <p>An approval record does not confirm that this policy is active in the current session or that it improves performance.</p>
   </div>}
   {(d.delta != null ||
    d.gamma != null ||
    d.theta != null ||
    d.vega != null) && (
    <div className="drawer-block">
     <h3>Observed option Greeks</h3>
     <p>
      Delta {d.delta ?? "Unavailable"} · Gamma {d.gamma ?? "Unavailable"} ·
      Theta {d.theta ?? "Unavailable"} · Vega {d.vega ?? "Unavailable"}
     </p>
     <p>
      {d.greeks_source || "Source unavailable"} · received{" "}
      {stamp(d.greeks_observed_at)} · age{" "}
      {d.greeks_age_seconds == null ?
       "Unavailable"
      : `${d.greeks_age_seconds.toFixed(1)} seconds`}
      . Greek scenario math is withheld unless units and input ages are
      verified.
     </p>
    </div>
   )}
   {d.probe_from && (
    <div className="drawer-block">
     <h3>Historical coverage and data exclusions</h3>
     <p>
      {d.probe_from} → {d.probe_to}
      <br />
      {d.observed_sessions ?? "Unknown"} index sessions ·{" "}
      {d.option_sessions ?? "Unknown"} option sessions
      <br />
      {d.invalid_candles ?? 0} invalid records · {d.conflicting_candles ?? 0}{" "}
      quarantined candle identities
      <br />
      {d.missing_index_minutes ?? "Unknown"} missing index minutes ·{" "}
      {d.missing_or_ambiguous_atm_minutes_by_side ?? "Unknown"}{" "}
      missing/ambiguous ATM-side minutes
     </p>
     <p>
      {d.note ||
       "Invalid data is excluded, never replaced by guessed prices or volume."}
     </p>
     {d.invalid_candle_examples?.map((v: Data, i: number) => (
      <p key={i}>
       {stamp(v.timestamp)} · {v.side} {v.offset} · strike {v.values?.strike}
       <br />
       {v.reason} · returned volume: {String(v.values?.volume)}
      </p>
     ))}
    </div>
   )}
   {trade && (
    <div className="drawer-block">
     <h3>Trade decision and outcome</h3>
     <p>
      {d.symbol} {d.option_type} · strike {d.strike} · {d.setup} / {d.regime}
     </p>
     <p>
      Signal: {stamp(d.timestamp || d.signal_ts)}
      <br />
      Entry: {stamp(d.entry_time || d.entry_ts)} at {money(d.entry_premium)}
      <br />
      Exit: {stamp(d.exit_time || d.exit_ts)} at {money(d.exit_premium)}
     </p>
     <p>
      Stop-loss {money(d.stop)} · target {money(d.target)} · quantity{" "}
      {d.quantity}
      <br />
      Exit reason: {d.reason || "Unresolved / open"}
     </p>
     <p>
      Gross {money(d.gross_pnl)} · charges {money(d.costs)} · net {money(d.pnl)}
     </p>
     {d.lot_scenario && (
      <p>
       Current-lot scenario: {d.lot_scenario.lot_size} units/lot from{" "}
       {d.lot_scenario.source}, observed {d.lot_scenario.observed_on}.
       Historical lot size and actual expiry are unverified.
      </p>
     )}
     {d.sizing_audit && (
      <p>
       Cash before entry {money(d.sizing_audit.cash_before)} · premium committed{" "}
       {money(d.sizing_audit.premium_committed)}
       <br />
       Stop-risk budget {money(d.sizing_audit.risk_budget)} · planned stop risk{" "}
       {money(d.sizing_audit.stop_risk)}
      </p>
     )}
     {d.signal_features && (
      <>
       <h3>Observed signal inputs</h3>
       {Object.entries(d.signal_features).map(([key, value]) => (
        <p key={key}>
         {key}: {value == null ? "Unavailable" : String(value)}
        </p>
       ))}
      </>
     )}
     <h3>Participating agents</h3>
     {Object.entries(d.agent_contexts || {}).map(([agent, context]) => (
      <p key={agent}>
       <strong>{agent}</strong>: {String(context)} · policy v
       {d.policy_versions?.[agent] ?? 0}
      </p>
     ))}
    </div>
   )}

   {d.agent && !d.summary && !d.decision_review && !d.evaluation?.task && !(d.source_run_id && d.version != null && d.validation_status) && (
    <div className="drawer-block">
     <h3>Evidence of improvement</h3>
     <p>
      {learning?.proposed_adjustment ||
       d.learning_summary ||
       "No validated change recorded."}
     </p>
     <p>
      Validation:{" "}
      {learning?.validation_status || d.validation_status || "Not evaluated"}
      <br />
      Policy version:{" "}
      {learning ?
       `${learning.policy_before} → ${learning.policy_after}`
      : (d.policy_version ?? "Unavailable")}
      <br />
      Baseline net P&L: {money(learning?.baseline_pnl)} · candidate net P&L:{" "}
      {money(learning?.candidate_pnl)}
     </p>
     <p>
      A lower loss in one backtest is not proof of learning. A policy must pass
      the recorded separate validation and untouched-test replays before
      promotion.
     </p>
     {Array.isArray(d.contexts) && (
      <>
       <h3>Agent contexts in this run</h3>
       {d.contexts.map((c: Data) => (
        <p key={c.name}>
         {c.name}: {c.trades} trades · {money(c.pnl)} attributed P&L ·{" "}
         {pct(c.win_rate)} win rate
        </p>
       ))}
      </>
     )}
    </div>
   )}
  </>
 );
}

function AgentLessons({ rows }: Data) {
 if (!rows?.length) return null;

 return (
  <div className="drawer-block">
   <h3>Conditions to avoid or focus on</h3>
   <p>
    Each closed trade contributes evidence. These are associations, not certain
    winning entries. A focus candidate must pass separate validation and all
    normal entry, liquidity and risk checks; it never forces an immediate trade.
   </p>
   {rows.map((l: Data) => (
    <article key={l.context}>
     <h4>{l.context}</h4>
     <strong>{(l.action || "OBSERVATION").replaceAll("_", " ")}</strong>
     <p>
      {l.samples} outcomes · {l.wins} wins / {l.losses} losses · {money(l.pnl)}{" "}
      {l.basis}
      <br />
      Expectancy {money(l.expectancy)} per observed trade
     </p>
     <p>
      Loss exits:{" "}
      {Object.entries(l.loss_exit_reasons || {})
       .map(([reason, count]) => `${reason}: ${count}`)
       .join(", ") || "None recorded"}
      <br />
      Win exits:{" "}
      {Object.entries(l.win_exit_reasons || {})
       .map(([reason, count]) => `${reason}: ${count}`)
       .join(", ") || "None recorded"}
     </p>
     <p>
      {l.proposal}
      <br />
      {l.status} · {l.applied ? "Applied" : "Not applied"}
     </p>
    </article>
   ))}
  </div>
 );
}

function PaperPnlPanel({ account, trades }: Data) {
 const daily = new Map<string, number>();
 for (const [day, value] of Object.entries(account.daily_results || {})) {
  if (Number.isFinite(value)) daily.set(day, Number(value));
 }
 if (account.session_date && Number.isFinite(account.session_pnl)) {
  daily.set(account.session_date, Number(account.session_pnl));
 }

 const days = [...daily.entries()].sort(([a], [b]) => a.localeCompare(b));
 let cumulative = 0;
 const points = [{ label: "Start", value: 0 }];
 for (const [label, value] of days) {
  cumulative += value;
  points.push({ label, value: cumulative });
 }

 const values = points.map((point) => point.value);
 const lo = Math.min(0, ...values);
 const hi = Math.max(0, ...values);
 const span = Math.max(hi - lo, 1);
 const x = (index: number) => 8 + (index / Math.max(points.length - 1, 1)) * 84;
 const y = (value: number) => 88 - ((value - lo) / span) * 72;
 const path = points.map((point, index) => `${x(index)},${y(point.value)}`).join(" ");
 const zeroY = y(0);
 const closed = (trades || []).filter((trade: Data) => Number.isFinite(trade.pnl));
 const wins = closed.filter((trade: Data) => trade.pnl > 0).length;
 const losses = closed.filter((trade: Data) => trade.pnl < 0).length;
 const tone = (value: number | null | undefined) =>
  value == null || !Number.isFinite(value) ? "" : value > 0 ? "positive" : value < 0 ? "negative" : "";
 const sessionValue = account.liquidation_complete && Number.isFinite(account.liquidation_pnl) ?
  account.liquidation_pnl : account.session_pnl;

 return (
  <section className="panel spaced paper-pnl-panel">
   <Head
    title="Paper Trading P&L"
    kicker="NET OF ESTIMATED CHARGES"
    right={<span className="paper-pnl-date">Through {account.session_date || "current session"}</span>}
   />
   <div className="paper-pnl-layout">
    <div className="paper-pnl-chart">
     <div className="paper-pnl-chart-head">
      <div>
       <span>Cumulative net P&amp;L</span>
       <strong className={tone(cumulative)}><TerminalValue value={cumulative}>{money(cumulative)}</TerminalValue></strong>
      </div>
      <div>
       <span>Account equity</span>
       <strong><TerminalValue value={account.equity}>{money(account.equity)}</TerminalValue></strong>
      </div>
     </div>
     <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Paper trading cumulative net profit and loss">
      <defs>
       <linearGradient id="paperPnlFill" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={cumulative >= 0 ? "#32d583" : "#ff7d8b"} stopOpacity="0.32" />
        <stop offset="100%" stopColor={cumulative >= 0 ? "#32d583" : "#ff7d8b"} stopOpacity="0" />
       </linearGradient>
      </defs>
      {[16, 40, 64, 88].map((line) => <line key={line} x1="8" x2="92" y1={line} y2={line} className="paper-pnl-gridline" />)}
      <line x1="8" x2="92" y1={zeroY} y2={zeroY} className="paper-pnl-zero" />
      <polygon points={`${path} 92,${zeroY} 8,${zeroY}`} fill="url(#paperPnlFill)" />
      <polyline points={path} fill="none" stroke={cumulative >= 0 ? "#32d583" : "#ff7d8b"} strokeWidth="2" vectorEffect="non-scaling-stroke" />
      {points.map((point, index) => <circle key={`${point.label}-${index}`} cx={x(index)} cy={y(point.value)} r="1.25" className={point.value >= 0 ? "paper-pnl-point gain" : "paper-pnl-point loss"} />)}
     </svg>
     <div className="paper-pnl-axis">
      <span>{points[0].label}</span>
      <span>{points[points.length - 1]?.label || "Current"}</span>
     </div>
     <p>
      {days.length ? `${days.length} recorded paper session${days.length === 1 ? "" : "s"}.` : "No completed paper sessions recorded yet."}
      {" "}The final point includes the current marked session and is not a guaranteed exit value.
     </p>
    </div>
    <div className="paper-pnl-numbers">
     {account.monthly_progress && <div className="paper-monthly-target">
      <span>Monthly net target · {account.monthly_progress.month}</span>
      <strong>{money(account.monthly_progress.estimated_liquidation_net)} / {money(account.monthly_progress.target)}</strong>
      <small>{account.monthly_progress.estimated_liquidation_net == null ? "Awaiting executable position valuation" : `${money(account.monthly_progress.remaining)} remaining after charges`} · reporting goal, not a trade quota</small>
     </div>}
     {[
      ["Available cash", money(account.cash), ""],
      ["Current session net", money(sessionValue), tone(sessionValue)],
      ["Realized net P&L", money(account.realized_pnl), tone(account.realized_pnl)],
      ["Unrealized P&L", money(account.unrealized_pnl), tone(account.unrealized_pnl)],
      ["Recorded charges", money(account.charges), ""],
      ["Open risk", money(account.open_risk_rupees), account.open_risk_rupees > 0 ? "negative" : ""],
     ].map(([label, value, className]) => (
      <div className="paper-pnl-stat" key={label}>
       <span>{label}</span>
       <strong className={className}>{value}</strong>
      </div>
     ))}
     <div className="paper-pnl-trades">
      <div><strong>{closed.length}</strong><span>Closed fills</span></div>
      <div><strong className="positive">{wins}</strong><span>Profitable</span></div>
      <div><strong className="negative">{losses}</strong><span>Losing</span></div>
     </div>
    </div>
   </div>
  </section>
 );
}

function Notice({ children }: { children: ReactNode }) {
 return (
  <div className="notice" role="status">
   {children}
  </div>
 );
}

function Empty({ children }: { children: ReactNode }) {
 return <div className="empty-state">{children}</div>;
}

function Head({ title, kicker, right }: Data) {
 return (
  <div className="panel-head">
   <div>
    <div className="eyebrow">{kicker}</div>
    <h3>{title}</h3>
   </div>
   {right}
  </div>
 );
}

function Kpi({ label, value, sub }: Data) {
 return (
  <div className="kpi">
   <span className="kpi-label">{label}</span>
   <strong>{value ?? "—"}</strong>
   <small>{sub}</small>
  </div>
 );
}

const root = import.meta.hot?.data.root ?? createRoot(document.getElementById("root")!);
if (import.meta.hot) import.meta.hot.data.root = root;
root.render(<App />);
