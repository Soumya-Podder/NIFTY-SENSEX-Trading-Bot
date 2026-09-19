import { useEffect, useRef, useState } from "react";
type Data = Record<string, any>;
const cash = (v: any) => typeof v === "number" && Number.isFinite(v) ? v.toLocaleString("en-IN", {style:"currency", currency:"INR", maximumFractionDigits:2}) : "—";
const percent = (v: any) => typeof v === "number" && Number.isFinite(v) ? `${(v*100).toFixed(2)}%` : "—";
const number = (v: any) => typeof v === "number" && Number.isFinite(v) ? v.toLocaleString("en-IN", {maximumFractionDigits:2}) : "—";
const tone = (status: string) => /ERROR|REJECT|BLOCK|INVALID|FAIL/.test(status) ? "bad" : /PASS|FILLED|COMPLETE/.test(status) ? "good" : "waiting";
const eventAge = (stamp?: string) => { const age = stamp ? (Date.now() - Date.parse(stamp)) / 1000 : Infinity; return Number.isFinite(age) && age >= 0 ? age : Infinity; };
const eligible = (r: Data) => r.presentation?.performance_available ?? (["complete", "research_complete", "scenario_complete"].includes(r.status) && ["verified", "research_net", "research", "estimated_scenario"].includes(r.quality) && !r.unresolved?.length);

const STAGE_METADATA: Record<string, { role: string; color: string; rgb: string; bg: string; icon: string }> = {
 "Scanner": { role: "Market Scanner", color: "#10b981", rgb: "16, 185, 129", bg: "rgba(16, 185, 129, 0.22)", icon: "scanner" },
 "Regime": { role: "Regime Classifier", color: "#f59e0b", rgb: "245, 158, 11", bg: "rgba(245, 158, 11, 0.22)", icon: "regime" },
 "Setup": { role: "Setup Validator", color: "#8b5cf6", rgb: "139, 92, 246", bg: "rgba(139, 92, 246, 0.22)", icon: "setup" },
 "Confirmation": { role: "Multi-TF Confirmation", color: "#06b6d4", rgb: "6, 182, 212", bg: "rgba(6, 182, 212, 0.22)", icon: "confirmation" },
 "Option Selector": { role: "Strike & Contract Picker", color: "#a855f7", rgb: "168, 85, 247", bg: "rgba(168, 85, 247, 0.22)", icon: "options" },
 "EV": { role: "Expected Value Model", color: "#0ea5e9", rgb: "14, 165, 233", bg: "rgba(14, 165, 233, 0.22)", icon: "ev" },
 "Risk": { role: "Deterministic Sentinel", color: "#f43f5e", rgb: "244, 63, 94", bg: "rgba(244, 63, 94, 0.22)", icon: "risk" },
 "Execution": { role: "Paper Execution Gate", color: "#14b8a6", rgb: "20, 184, 166", bg: "rgba(20, 184, 166, 0.22)", icon: "execution" },
};

function renderStageIcon(iconType: string, color: string) {
 switch (iconType) {
  case "scanner":
   return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
     <circle cx="12" cy="12" r="10" /><line x1="22" y1="12" x2="18" y2="12" /><line x1="6" y1="12" x2="2" y2="12" /><line x1="12" y1="6" x2="12" y2="2" /><line x1="12" y1="22" x2="12" y2="18" /><circle cx="12" cy="12" r="3" />
    </svg>
   );
  case "regime":
   return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
     <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
   );
  case "setup":
   return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
     <polygon points="12 2 2 7 12 12 22 7 12 2" /><polyline points="2 17 12 22 22 17" /><polyline points="2 12 12 17 22 12" />
    </svg>
   );
  case "confirmation":
   return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
     <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /><polyline points="9 12 11 14 15 10" />
    </svg>
   );
  case "options":
   return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
     <line x1="4" y1="21" x2="4" y2="14" /><line x1="4" y1="10" x2="4" y2="3" /><line x1="12" y1="21" x2="12" y2="12" /><line x1="12" y1="8" x2="12" y2="3" /><line x1="20" y1="21" x2="20" y2="16" /><line x1="20" y1="12" x2="20" y2="3" /><line x1="1" y1="14" x2="7" y2="14" /><line x1="9" y1="8" x2="15" y2="8" /><line x1="17" y1="16" x2="23" y2="16" />
    </svg>
   );
  case "ev":
   return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
     <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" /><polyline points="17 6 23 6 23 12" />
    </svg>
   );
  case "risk":
   return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
     <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
   );
  case "execution":
  default:
   return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
     <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
   );
 }
}

export function AgentCanvas({data, online, onDetail}: Data) {
 const [symbol, setSymbol] = useState("NIFTY");
 const [zoom, setZoom] = useState(1);
 const viewport = useRef<HTMLDivElement>(null);
 useEffect(() => {
  const element = viewport.current;
  if (!element) return;
  const observer = new ResizeObserver(() => setZoom(Math.max(0.5, Math.min(1, (element.clientWidth - 16) / 1340))));
  observer.observe(element);
  return () => observer.disconnect();
 }, []);

 const stages: Data[] = data?.pipelines?.[symbol] || [];
 const fallbackNodes: Data[] = ["Scanner", "Regime", "Setup", "Confirmation", "Option Selector", "EV", "Risk", "Execution"].map(agent => ({
  agent,
  status: "UNAVAILABLE",
  label: "Waiting for engine telemetry"
 }));
 const rawNodes: Data[] = stages.length ? stages : fallbackNodes;
 const eventIndex = new Map((data?.events || []).map((event: Data) => [event.id, event]));
 const nodes: Data[] = rawNodes.map(node => {
  const recorded = eventIndex.get(node.event_id) as Data | undefined;
  return {
   ...node,
   timestamp: node.timestamp || recorded?.timestamp,
   context: node.context || recorded?.context,
   evaluation: node.evaluation || recorded?.evaluation,
   policy_version: node.policy_version ?? recorded?.policy_version
  };
 });

 // Modern balanced coordinate geometry (1340 x 710)
 // Top row: Scanner (80), Regime (390), Setup (700), Confirmation (1010) at Y=135, height 132
 // Orchestrator Center: left 415, top 285, width 510, height 165
 // Bottom row: Execution (80), Risk (390), EV (700), Option Selector (1010) at Y=470, height 132
 // Footnote: left 80, top 640 (cleanly below bottom row!)
 const positions = [
  [80, 135],   // 0: Scanner
  [390, 135],  // 1: Regime
  [700, 135],  // 2: Setup
  [1010, 135], // 3: Confirmation
  [1010, 470], // 4: Option Selector
  [700, 470],  // 5: EV
  [390, 470],  // 6: Risk Sentinel
  [80, 470],   // 7: Execution
 ];

 const lastObserved = nodes.reduce<string | undefined>((latest, node) =>
  !latest || (node.timestamp && Date.parse(node.timestamp) > Date.parse(latest)) ? node.timestamp : latest, undefined);
 const chainFresh = Boolean(online && lastObserved && eventAge(lastObserved) <= 120);

 const edgePath = (i: number) => {
  switch (i) {
   case 0: return "M340 201 L390 201"; // Scanner -> Regime
   case 1: return "M650 201 L700 201"; // Regime -> Setup
   case 2: return "M960 201 L1010 201"; // Setup -> Confirmation
   case 3: return "M1270 201 C1320 201 1320 536 1270 536"; // Confirmation -> Option Selector (Smooth U-turn)
   case 4: return "M1010 536 L960 536"; // Option Selector -> EV
   case 5: return "M700 536 L650 536"; // EV -> Risk Sentinel
   case 6: return "M390 536 L340 536"; // Risk Sentinel -> Execution
   default: return "";
  }
 };

 const flowing = (i: number) => chainFresh && Boolean(nodes[i]?.event_id && nodes[i+1]?.event_id
  && /^(PASS|PASSED|OBSERVATION|FILLED|COMPLETE)$/.test(nodes[i]?.status || "")
  && eventAge(nodes[i]?.timestamp) <= 120 && eventAge(nodes[i+1]?.timestamp) <= 120
  && Date.parse(nodes[i+1]?.timestamp) >= Date.parse(nodes[i]?.timestamp));

 const recordedCount = nodes.filter(n => n.event_id).length;
 const freshCount = nodes.filter(n => n.event_id && eventAge(n.timestamp) <= 120).length;
 const passedCount = nodes.filter(n => /^(PASS|PASSED|FILLED|COMPLETE)$/.test(n.status || "")).length;
 const blockedNode = nodes.find(n => /ERROR|REJECT|BLOCK|INVALID|FAIL/.test(n.status || ""));
 const direction = nodes.find(n => n.agent === "Setup" || n.agent === "Directional Agent")?.evaluation?.direction;

 const consensusStance = blockedNode ? "BLOCKED" : direction ? direction.toUpperCase() : passedCount >= 4 ? "CALL_BIAS" : !online ? "OFFLINE" : "WAIT / MONITOR";
 const consensusColor = consensusStance === "CALL" || consensusStance === "CALL_BIAS" ? "#10b981" : consensusStance === "PUT" ? "#f43f5e" : consensusStance === "BLOCKED" ? "#ef4444" : "#ec4899";

 const chainMessage = !online ? "Disconnected · last received state" :
  recordedCount === 0 ? "No decision events recorded" :
  chainFresh ? `${freshCount}/8 stages have recent evidence · ${positions.slice(0,-1).some((_,i)=>flowing(i)) ? "active handoffs streaming" : nodes.find(n=>n.event_id)?.label || "waiting for next gate"}` :
  `${recordedCount}/8 stages have recorded evidence · awaiting fresh cycle`;

 const handoffs: Data[] = [...(data?.events || [])]
  .filter((event: Data) => event.symbol === symbol)
  .sort((a: Data, b: Data) => Date.parse(b.timestamp || "") - Date.parse(a.timestamp || ""))
  .slice(0, 4);

 const monitorPulse = Boolean(online && data?.generated_at && eventAge(data.generated_at) <= 10);

 const routes = [
  ["Regime Agent", "Directional Agent · Setup", "Classifies market state before a setup is considered", "#f59e0b", "245, 158, 11"],
  ["Directional Agent", "Orchestrator", "Passes directional evidence and invalidation levels", "#8b5cf6", "139, 92, 246"],
  ["Options Flow Agent", "Gamma · Theta · IV", "Shares OI, migration and premium context", "#a855f7", "168, 85, 247"],
  ["Gamma Agent", "Orchestrator", "Reports convexity, concentration and asymmetric risk", "#ec4899", "236, 72, 153"],
  ["Theta Agent", "Orchestrator", "Checks decay-adjusted reward versus premium paid", "#06b6d4", "6, 182, 212"],
  ["IV Agent", "Orchestrator", "Checks volatility regime, skew and premium expansion", "#0ea5e9", "14, 165, 233"],
  ["Liquidity Agent", "Risk Sentinel", "Supplies spread, depth and slippage evidence", "#10b981", "16, 185, 129"],
  ["Momentum Agent", "Orchestrator", "Confirms acceleration across observed timeframes", "#3b82f6", "59, 130, 246"],
  ["Structure Agent", "Setup", "Supplies VWAP, EMA and opening-structure context", "#6366f1", "99, 102, 241"],
  ["News/Event Agent", "Adversarial Agent", "Publishes timestamped event risk and severity", "#f97316", "249, 115, 22"],
  ["Adversarial Agent", "Orchestrator", "Challenges every proposed trade and invalidation", "#ef4444", "239, 68, 68"],
  ["Loss Investigator", "Research journal", "Classifies closed losses for later research", "#eab308", "234, 179, 8"],
  ["Risk Sentinel", "Paper execution", "Applies deterministic risk, session and halt vetoes", "#f43f5e", "244, 63, 94"],
  ["Orchestrator", "Risk Sentinel", "Converts evidence into CALL, PUT, WAIT or EXIT", "#ec4899", "236, 72, 153"],
 ];

 const auditById = new Map((data?.learning_monitor?.individual_agent_audit?.agents || []).map((agent: Data) => [agent.id, agent]));

 const handleOrchestratorClick = () => {
  onDetail({
   agent: "Central Orchestrator Core",
   symbol,
   status: blockedNode ? "BLOCKED_BY_GATE" : online ? (chainFresh ? "CONSENSUS_ACTIVE" : "AWAITING_CYCLE") : "OFFLINE",
   label: "Multi-agent consensus engine synthesizing 14 specialist roles into deterministic action gates.",
   telemetry_current: Boolean(online),
   timestamp: lastObserved,
   consensus: {
    stance: consensusStance,
    passed_gates: `${passedCount} of 8 stages passed`,
    fresh_stages: `${freshCount} of 8 stages active (<120s)`,
    blocked_by: blockedNode ? `${blockedNode.agent}: ${blockedNode.status}` : "None (all active gates cleared)",
    direction_signal: direction || "Awaiting directional bias",
    active_specialist_roles: 14,
   },
   specialist_audit_summary: routes.map(([from, to, role]) => {
    const a = auditById.get(from) as Data | undefined;
    return { role: from, target: to, function: role, status: a?.status || "NO_EVIDENCE", decisions: a?.decision_count ?? 0, outcomes: a?.outcome_count ?? 0 };
   }),
   recent_handoffs: handoffs
  });
 };

 return (
  <section className="workflow panel spaced modern-dark-workflow">
   {/* Header & Controls */}
   <div className="workspace-toolbar modern-toolbar">
    <div>
     <div className="eyebrow modern-eyebrow">
      <span className="eyebrow-dot" /> AGENTIC WORKSPACE · MULTI-AGENT TRADING INTELLIGENCE
     </div>
     <h2 className="modern-title">Autonomous Decision Workflow</h2>
     <p className="modern-subtitle">Deterministic 8-stage pipeline coordinated by Central Orchestrator & 14 specialist roles</p>
    </div>
    <div className="workspace-actions">
     <div className="segmented modern-segmented">
      {["NIFTY", "SENSEX"].map(s => (
       <button key={s} className={symbol === s ? "selected" : ""} onClick={() => setSymbol(s)}>
        {s}
       </button>
      ))}
     </div>
     <div className="zoom-group">
      <button aria-label="Zoom out workflow" onClick={() => setZoom(z => Math.max(0.5, z - 0.1))}>−</button>
      <button onClick={() => setZoom(1)} title="Reset zoom">{Math.round(zoom * 100)}%</button>
      <button aria-label="Zoom in workflow" onClick={() => setZoom(z => Math.min(1.5, z + 0.1))}>+</button>
     </div>
    </div>
   </div>

   {/* Legend & Telemetry Status Bar */}
   <div className="workflow-legend modern-legend">
    <div className="legend-pills">
     <span className="legend-item"><i className="legend-dot good" /> Passed / Filled</span>
     <span className="legend-item"><i className="legend-dot bad" /> Rejected / Blocked</span>
     <span className="legend-item"><i className="legend-dot waiting" /> Waiting / Evaluating</span>
     <span className={`legend-item status-chip ${chainFresh ? "flow-live" : ""}`}>
      <i className="legend-dot live-dot" /> {chainMessage}
     </span>
    </div>
    <div className="legend-right">
     <span className={`monitor-heartbeat ${monitorPulse ? "is-live" : ""}`}>
      <i /> {monitorPulse ? "Engine heartbeat live (2s)" : "Telemetry snapshot"}
     </span>
    </div>
   </div>

   {/* Agent Handoff Bus */}
   <div className="handoff-bus modern-handoff-bus" aria-label={`${handoffs.length} recorded agent handoffs`}>
    <div className="handoff-bus-title">
     <div className="bus-tag">
      <span className="bus-pulse-indicator" />
      <span>AGENT HANDOFF BUS</span>
     </div>
     <small>{chainFresh ? "Streaming recorded evidence" : "Replay tape · awaiting fresh cycle"}</small>
    </div>
    <div className="handoff-track">
     {handoffs.length ? handoffs.map((event: Data, index: number) => {
      const fresh = eventAge(event.timestamp) <= 120;
      return (
       <div key={event.id || `${event.agent}-${index}`} className={`handoff-chip modern-chip ${fresh ? "is-fresh" : "is-stale"}`}>
        <span className="handoff-dot" />
        <strong>{event.agent || "Agent"}</strong>
        <b className="handoff-arrow">→</b>
        <span className={`handoff-status ${tone(event.status || "")}`}>{event.status || "WAITING"}</span>
        <small>{event.summary || "Recorded decision evidence"}</small>
       </div>
      );
     }) : (
      <div className="handoff-empty">No recorded handoffs for {symbol}; the workflow is waiting for the next completed market cycle.</div>
     )}
    </div>
   </div>

   {/* Interactive Decision Workflow Canvas */}
   <div ref={viewport} className="workflow-viewport modern-viewport" tabIndex={0} aria-label="Decision workflow canvas">
    <div style={{ width: 1340 * zoom, height: 710 * zoom }}>
     <div className="workflow-canvas modern-canvas" style={{ transform: `scale(${zoom})` }}>

      {/* SVG Pipeline Cables & Sequential Cascading Flow Packets */}
      <svg className="workflow-lines modern-lines" viewBox="0 0 1340 710" aria-hidden="true">
       <defs>
        <linearGradient id="orchLineGrad" x1="0%" y1="0%" x2="100%" y2="100%">
         <stop offset="0%" stopColor="#ec4899" stopOpacity="0.9" />
         <stop offset="50%" stopColor="#8b5cf6" stopOpacity="0.7" />
         <stop offset="100%" stopColor="#06b6d4" stopOpacity="0.8" />
        </linearGradient>
        <linearGradient id="cableGrad_s0" x1="0%" y1="0%" x2="100%" y2="0%">
         <stop offset="0%" stopColor="#10b981" stopOpacity="0.85" />
         <stop offset="100%" stopColor="#f59e0b" stopOpacity="0.95" />
        </linearGradient>
        <linearGradient id="cableGrad_s1" x1="0%" y1="0%" x2="100%" y2="0%">
         <stop offset="0%" stopColor="#f59e0b" stopOpacity="0.85" />
         <stop offset="100%" stopColor="#8b5cf6" stopOpacity="0.95" />
        </linearGradient>
        <linearGradient id="cableGrad_s2" x1="0%" y1="0%" x2="100%" y2="0%">
         <stop offset="0%" stopColor="#8b5cf6" stopOpacity="0.85" />
         <stop offset="100%" stopColor="#6366f1" stopOpacity="0.95" />
        </linearGradient>
        <linearGradient id="cableGrad_s3" x1="0%" y1="0%" x2="100%" y2="0%">
         <stop offset="0%" stopColor="#6366f1" stopOpacity="0.85" />
         <stop offset="100%" stopColor="#38bdf8" stopOpacity="0.95" />
        </linearGradient>
        <linearGradient id="cableGrad_s4" x1="0%" y1="0%" x2="100%" y2="0%">
         <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.85" />
         <stop offset="100%" stopColor="#0ea5e9" stopOpacity="0.95" />
        </linearGradient>
        <linearGradient id="cableGrad_s5" x1="0%" y1="0%" x2="100%" y2="0%">
         <stop offset="0%" stopColor="#0ea5e9" stopOpacity="0.85" />
         <stop offset="100%" stopColor="#f43f5e" stopOpacity="0.95" />
        </linearGradient>
        <linearGradient id="cableGrad_s6" x1="0%" y1="0%" x2="100%" y2="0%">
         <stop offset="0%" stopColor="#f43f5e" stopOpacity="0.85" />
         <stop offset="100%" stopColor="#10b981" stopOpacity="0.95" />
        </linearGradient>
       </defs>

       {/* Cable: Session Controller -> Stage 1 (Scanner) */}
       <g>
        <path
         className="cable-line"
         d="M210 114 L210 135"
         style={{ stroke: "#10b981", strokeWidth: "3px", strokeLinecap: "round", fill: "none" }}
        />
        <circle r="4.5" style={{ fill: "#ffffff", filter: "drop-shadow(0 0 8px #10b981) drop-shadow(0 0 16px #10b981)", opacity: 0 }}>
         <animateMotion dur="7.2s" begin="0s" repeatCount="indefinite" path="M210 114 L210 135" keyTimes="0; 0.055; 1" keyPoints="0; 1; 1" calcMode="linear" />
         <animate attributeName="opacity" dur="7.2s" begin="0s" repeatCount="indefinite" values="0; 1; 1; 0; 0" keyTimes="0; 0.01; 0.045; 0.055; 1" />
        </circle>
        <circle r="4.5" style={{ fill: "#ffffff", filter: "drop-shadow(0 0 8px #10b981) drop-shadow(0 0 16px #10b981)", opacity: 0 }}>
         <animateMotion dur="7.2s" begin="-3.6s" repeatCount="indefinite" path="M210 114 L210 135" keyTimes="0; 0.055; 1" keyPoints="0; 1; 1" calcMode="linear" />
         <animate attributeName="opacity" dur="7.2s" begin="-3.6s" repeatCount="indefinite" values="0; 1; 1; 0; 0" keyTimes="0; 0.01; 0.045; 0.055; 1" />
        </circle>
       </g>

       {/* Stage 0 -> Stage 1: Scanner -> Regime */}
       <g>
        <path className="cable-line" d="M340 201 L390 201" style={{ stroke: "url(#cableGrad_s0)", strokeWidth: "3.2px", strokeLinecap: "round", fill: "none" }} />
        {["0s", "-3.6s"].map((begin, idx) => (
         <g key={idx}>
          <circle r="5" style={{ fill: "#ffffff", filter: "drop-shadow(0 0 6px #ffffff) drop-shadow(0 0 14px #f59e0b)", opacity: 0 }}>
           <animateMotion dur="7.2s" begin={begin} repeatCount="indefinite" path="M340 201 L390 201" keyTimes="0; 0.111; 1" keyPoints="0; 1; 1" calcMode="linear" />
           <animate attributeName="opacity" dur="7.2s" begin={begin} repeatCount="indefinite" values="0; 1; 1; 0; 0" keyTimes="0; 0.015; 0.095; 0.111; 1" />
          </circle>
          <circle r="3.2" style={{ fill: "#f59e0b", filter: "drop-shadow(0 0 8px #f59e0b)", opacity: 0 }}>
           <animateMotion dur="7.2s" begin={begin} repeatCount="indefinite" path="M340 201 L390 201" keyTimes="0; 0.111; 1" keyPoints="0; 1; 1" calcMode="linear" />
           <animate attributeName="opacity" dur="7.2s" begin={begin} repeatCount="indefinite" values="0; 0.8; 0.8; 0; 0" keyTimes="0; 0.015; 0.095; 0.111; 1" />
          </circle>
         </g>
        ))}
       </g>

       {/* Stage 1 -> Stage 2: Regime -> Setup */}
       <g>
        <path className="cable-line" d="M650 201 L700 201" style={{ stroke: "url(#cableGrad_s1)", strokeWidth: "3.2px", strokeLinecap: "round", fill: "none" }} />
        {["0s", "-3.6s"].map((begin, idx) => (
         <g key={idx}>
          <circle r="5" style={{ fill: "#ffffff", filter: "drop-shadow(0 0 6px #ffffff) drop-shadow(0 0 14px #8b5cf6)", opacity: 0 }}>
           <animateMotion dur="7.2s" begin={begin} repeatCount="indefinite" path="M650 201 L700 201" keyTimes="0; 0.139; 0.250; 1" keyPoints="0; 0; 1; 1" calcMode="linear" />
           <animate attributeName="opacity" dur="7.2s" begin={begin} repeatCount="indefinite" values="0; 0; 1; 1; 0; 0" keyTimes="0; 0.139; 0.155; 0.235; 0.250; 1" />
          </circle>
          <circle r="3.2" style={{ fill: "#8b5cf6", filter: "drop-shadow(0 0 8px #8b5cf6)", opacity: 0 }}>
           <animateMotion dur="7.2s" begin={begin} repeatCount="indefinite" path="M650 201 L700 201" keyTimes="0; 0.139; 0.250; 1" keyPoints="0; 0; 1; 1" calcMode="linear" />
           <animate attributeName="opacity" dur="7.2s" begin={begin} repeatCount="indefinite" values="0; 0; 0.8; 0.8; 0; 0" keyTimes="0; 0.139; 0.155; 0.235; 0.250; 1" />
          </circle>
         </g>
        ))}
       </g>

       {/* Stage 2 -> Stage 3: Setup -> Confirmation */}
       <g>
        <path className="cable-line" d="M960 201 L1010 201" style={{ stroke: "url(#cableGrad_s2)", strokeWidth: "3.2px", strokeLinecap: "round", fill: "none" }} />
        {["0s", "-3.6s"].map((begin, idx) => (
         <g key={idx}>
          <circle r="5" style={{ fill: "#ffffff", filter: "drop-shadow(0 0 6px #ffffff) drop-shadow(0 0 14px #6366f1)", opacity: 0 }}>
           <animateMotion dur="7.2s" begin={begin} repeatCount="indefinite" path="M960 201 L1010 201" keyTimes="0; 0.278; 0.389; 1" keyPoints="0; 0; 1; 1" calcMode="linear" />
           <animate attributeName="opacity" dur="7.2s" begin={begin} repeatCount="indefinite" values="0; 0; 1; 1; 0; 0" keyTimes="0; 0.278; 0.295; 0.372; 0.389; 1" />
          </circle>
          <circle r="3.2" style={{ fill: "#6366f1", filter: "drop-shadow(0 0 8px #6366f1)", opacity: 0 }}>
           <animateMotion dur="7.2s" begin={begin} repeatCount="indefinite" path="M960 201 L1010 201" keyTimes="0; 0.278; 0.389; 1" keyPoints="0; 0; 1; 1" calcMode="linear" />
           <animate attributeName="opacity" dur="7.2s" begin={begin} repeatCount="indefinite" values="0; 0; 0.8; 0.8; 0; 0" keyTimes="0; 0.278; 0.295; 0.372; 0.389; 1" />
          </circle>
         </g>
        ))}
       </g>

       {/* Stage 3 -> Stage 4: Confirmation -> Option Selector (Smooth U-turn) */}
       <g>
        <path className="cable-line" d="M1270 201 C1320 201 1320 536 1270 536" style={{ stroke: "url(#cableGrad_s3)", strokeWidth: "3.2px", strokeLinecap: "round", fill: "none" }} />
        {["0s", "-3.6s"].map((begin, idx) => (
         <g key={idx}>
          <circle r="5" style={{ fill: "#ffffff", filter: "drop-shadow(0 0 6px #ffffff) drop-shadow(0 0 14px #38bdf8)", opacity: 0 }}>
           <animateMotion dur="7.2s" begin={begin} repeatCount="indefinite" path="M1270 201 C1320 201 1320 536 1270 536" keyTimes="0; 0.417; 0.639; 1" keyPoints="0; 0; 1; 1" calcMode="linear" />
           <animate attributeName="opacity" dur="7.2s" begin={begin} repeatCount="indefinite" values="0; 0; 1; 1; 0; 0" keyTimes="0; 0.417; 0.440; 0.615; 0.639; 1" />
          </circle>
          <circle r="3.2" style={{ fill: "#38bdf8", filter: "drop-shadow(0 0 8px #38bdf8)", opacity: 0 }}>
           <animateMotion dur="7.2s" begin={begin} repeatCount="indefinite" path="M1270 201 C1320 201 1320 536 1270 536" keyTimes="0; 0.417; 0.639; 1" keyPoints="0; 0; 1; 1" calcMode="linear" />
           <animate attributeName="opacity" dur="7.2s" begin={begin} repeatCount="indefinite" values="0; 0; 0.8; 0.8; 0; 0" keyTimes="0; 0.417; 0.440; 0.615; 0.639; 1" />
          </circle>
         </g>
        ))}
       </g>

       {/* Stage 4 -> Stage 5: Option Selector -> EV */}
       <g>
        <path className="cable-line" d="M1010 536 L960 536" style={{ stroke: "url(#cableGrad_s4)", strokeWidth: "3.2px", strokeLinecap: "round", fill: "none" }} />
        {["0s", "-3.6s"].map((begin, idx) => (
         <g key={idx}>
          <circle r="5" style={{ fill: "#ffffff", filter: "drop-shadow(0 0 6px #ffffff) drop-shadow(0 0 14px #0ea5e9)", opacity: 0 }}>
           <animateMotion dur="7.2s" begin={begin} repeatCount="indefinite" path="M1010 536 L960 536" keyTimes="0; 0.667; 0.750; 1" keyPoints="0; 0; 1; 1" calcMode="linear" />
           <animate attributeName="opacity" dur="7.2s" begin={begin} repeatCount="indefinite" values="0; 0; 1; 1; 0; 0" keyTimes="0; 0.667; 0.680; 0.735; 0.750; 1" />
          </circle>
          <circle r="3.2" style={{ fill: "#0ea5e9", filter: "drop-shadow(0 0 8px #0ea5e9)", opacity: 0 }}>
           <animateMotion dur="7.2s" begin={begin} repeatCount="indefinite" path="M1010 536 L960 536" keyTimes="0; 0.667; 0.750; 1" keyPoints="0; 0; 1; 1" calcMode="linear" />
           <animate attributeName="opacity" dur="7.2s" begin={begin} repeatCount="indefinite" values="0; 0; 0.8; 0.8; 0; 0" keyTimes="0; 0.667; 0.680; 0.735; 0.750; 1" />
          </circle>
         </g>
        ))}
       </g>

       {/* Stage 5 -> Stage 6: EV -> Risk Sentinel */}
       <g>
        <path className="cable-line" d="M700 536 L650 536" style={{ stroke: "url(#cableGrad_s5)", strokeWidth: "3.2px", strokeLinecap: "round", fill: "none" }} />
        {["0s", "-3.6s"].map((begin, idx) => (
         <g key={idx}>
          <circle r="5" style={{ fill: "#ffffff", filter: "drop-shadow(0 0 6px #ffffff) drop-shadow(0 0 14px #f43f5e)", opacity: 0 }}>
           <animateMotion dur="7.2s" begin={begin} repeatCount="indefinite" path="M700 536 L650 536" keyTimes="0; 0.778; 0.861; 1" keyPoints="0; 0; 1; 1" calcMode="linear" />
           <animate attributeName="opacity" dur="7.2s" begin={begin} repeatCount="indefinite" values="0; 0; 1; 1; 0; 0" keyTimes="0; 0.778; 0.790; 0.848; 0.861; 1" />
          </circle>
          <circle r="3.2" style={{ fill: "#f43f5e", filter: "drop-shadow(0 0 8px #f43f5e)", opacity: 0 }}>
           <animateMotion dur="7.2s" begin={begin} repeatCount="indefinite" path="M700 536 L650 536" keyTimes="0; 0.778; 0.861; 1" keyPoints="0; 0; 1; 1" calcMode="linear" />
           <animate attributeName="opacity" dur="7.2s" begin={begin} repeatCount="indefinite" values="0; 0; 0.8; 0.8; 0; 0" keyTimes="0; 0.778; 0.790; 0.848; 0.861; 1" />
          </circle>
         </g>
        ))}
       </g>

       {/* Stage 6 -> Stage 7: Risk Sentinel -> Execution */}
       <g>
        <path className="cable-line" d="M390 536 L340 536" style={{ stroke: "url(#cableGrad_s6)", strokeWidth: "3.2px", strokeLinecap: "round", fill: "none" }} />
        {["0s", "-3.6s"].map((begin, idx) => (
         <g key={idx}>
          <circle r="5" style={{ fill: "#ffffff", filter: "drop-shadow(0 0 6px #ffffff) drop-shadow(0 0 14px #10b981)", opacity: 0 }}>
           <animateMotion dur="7.2s" begin={begin} repeatCount="indefinite" path="M390 536 L340 536" keyTimes="0; 0.889; 0.972; 1" keyPoints="0; 0; 1; 1" calcMode="linear" />
           <animate attributeName="opacity" dur="7.2s" begin={begin} repeatCount="indefinite" values="0; 0; 1; 1; 0; 0" keyTimes="0; 0.889; 0.900; 0.960; 0.972; 1" />
          </circle>
          <circle r="3.2" style={{ fill: "#10b981", filter: "drop-shadow(0 0 8px #10b981)", opacity: 0 }}>
           <animateMotion dur="7.2s" begin={begin} repeatCount="indefinite" path="M390 536 L340 536" keyTimes="0; 0.889; 0.972; 1" keyPoints="0; 0; 1; 1" calcMode="linear" />
           <animate attributeName="opacity" dur="7.2s" begin={begin} repeatCount="indefinite" values="0; 0; 0.8; 0.8; 0; 0" keyTimes="0; 0.889; 0.900; 0.960; 0.972; 1" />
          </circle>
         </g>
        ))}
       </g>

       {/* Convergence Pipelines to Central Orchestrator (Smooth solid curves with synchronized flow pulses) */}
       <g className="orchestrator-convergence-cables">
        {/* Regime -> Orchestrator */}
        <path d="M520 267 C520 276 560 276 560 285" stroke="url(#orchLineGrad)" strokeWidth="2.5" strokeLinecap="round" fill="none" style={{ filter: "drop-shadow(0 0 6px rgba(236, 72, 153, 0.4))" }} />
        <circle r="4" style={{ fill: "#ffffff", filter: "drop-shadow(0 0 8px #f59e0b) drop-shadow(0 0 14px #ec4899)", opacity: 0 }}>
         <animateMotion dur="7.2s" begin="0s" repeatCount="indefinite" path="M520 267 C520 276 560 276 560 285" keyTimes="0; 0.111; 0.194; 1" keyPoints="0; 0; 1; 1" calcMode="linear" />
         <animate attributeName="opacity" dur="7.2s" begin="0s" repeatCount="indefinite" values="0; 0; 1; 1; 0; 0" keyTimes="0; 0.111; 0.125; 0.180; 0.194; 1" />
        </circle>
        <circle r="4" style={{ fill: "#ffffff", filter: "drop-shadow(0 0 8px #f59e0b) drop-shadow(0 0 14px #ec4899)", opacity: 0 }}>
         <animateMotion dur="7.2s" begin="-3.6s" repeatCount="indefinite" path="M520 267 C520 276 560 276 560 285" keyTimes="0; 0.111; 0.194; 1" keyPoints="0; 0; 1; 1" calcMode="linear" />
         <animate attributeName="opacity" dur="7.2s" begin="-3.6s" repeatCount="indefinite" values="0; 0; 1; 1; 0; 0" keyTimes="0; 0.111; 0.125; 0.180; 0.194; 1" />
        </circle>

        {/* Setup -> Orchestrator */}
        <path d="M830 267 C830 276 780 276 780 285" stroke="url(#orchLineGrad)" strokeWidth="2.5" strokeLinecap="round" fill="none" style={{ filter: "drop-shadow(0 0 6px rgba(236, 72, 153, 0.4))" }} />
        <circle r="4" style={{ fill: "#ffffff", filter: "drop-shadow(0 0 8px #8b5cf6) drop-shadow(0 0 14px #ec4899)", opacity: 0 }}>
         <animateMotion dur="7.2s" begin="0s" repeatCount="indefinite" path="M830 267 C830 276 780 276 780 285" keyTimes="0; 0.250; 0.333; 1" keyPoints="0; 0; 1; 1" calcMode="linear" />
         <animate attributeName="opacity" dur="7.2s" begin="0s" repeatCount="indefinite" values="0; 0; 1; 1; 0; 0" keyTimes="0; 0.250; 0.265; 0.318; 0.333; 1" />
        </circle>
        <circle r="4" style={{ fill: "#ffffff", filter: "drop-shadow(0 0 8px #8b5cf6) drop-shadow(0 0 14px #ec4899)", opacity: 0 }}>
         <animateMotion dur="7.2s" begin="-3.6s" repeatCount="indefinite" path="M830 267 C830 276 780 276 780 285" keyTimes="0; 0.250; 0.333; 1" keyPoints="0; 0; 1; 1" calcMode="linear" />
         <animate attributeName="opacity" dur="7.2s" begin="-3.6s" repeatCount="indefinite" values="0; 0; 1; 1; 0; 0" keyTimes="0; 0.250; 0.265; 0.318; 0.333; 1" />
        </circle>

        {/* Orchestrator -> EV Assessment */}
        <path d="M780 450 C780 460 830 460 830 470" stroke="url(#orchLineGrad)" strokeWidth="2.5" strokeLinecap="round" fill="none" style={{ filter: "drop-shadow(0 0 6px rgba(14, 165, 233, 0.4))" }} />
        <circle r="4" style={{ fill: "#ffffff", filter: "drop-shadow(0 0 8px #ec4899) drop-shadow(0 0 14px #0ea5e9)", opacity: 0 }}>
         <animateMotion dur="7.2s" begin="0s" repeatCount="indefinite" path="M780 450 C780 460 830 460 830 470" keyTimes="0; 0.639; 0.722; 1" keyPoints="0; 0; 1; 1" calcMode="linear" />
         <animate attributeName="opacity" dur="7.2s" begin="0s" repeatCount="indefinite" values="0; 0; 1; 1; 0; 0" keyTimes="0; 0.639; 0.655; 0.705; 0.722; 1" />
        </circle>
        <circle r="4" style={{ fill: "#ffffff", filter: "drop-shadow(0 0 8px #ec4899) drop-shadow(0 0 14px #0ea5e9)", opacity: 0 }}>
         <animateMotion dur="7.2s" begin="-3.6s" repeatCount="indefinite" path="M780 450 C780 460 830 460 830 470" keyTimes="0; 0.639; 0.722; 1" keyPoints="0; 0; 1; 1" calcMode="linear" />
         <animate attributeName="opacity" dur="7.2s" begin="-3.6s" repeatCount="indefinite" values="0; 0; 1; 1; 0; 0" keyTimes="0; 0.639; 0.655; 0.705; 0.722; 1" />
        </circle>

        {/* Orchestrator -> Risk Sentinel */}
        <path d="M560 450 C560 460 520 460 520 470" stroke="url(#orchLineGrad)" strokeWidth="2.5" strokeLinecap="round" fill="none" style={{ filter: "drop-shadow(0 0 6px rgba(244, 63, 94, 0.4))" }} />
        <circle r="4" style={{ fill: "#ffffff", filter: "drop-shadow(0 0 8px #ec4899) drop-shadow(0 0 14px #f43f5e)", opacity: 0 }}>
         <animateMotion dur="7.2s" begin="0s" repeatCount="indefinite" path="M560 450 C560 460 520 460 520 470" keyTimes="0; 0.750; 0.833; 1" keyPoints="0; 0; 1; 1" calcMode="linear" />
         <animate attributeName="opacity" dur="7.2s" begin="0s" repeatCount="indefinite" values="0; 0; 1; 1; 0; 0" keyTimes="0; 0.750; 0.765; 0.818; 0.833; 1" />
        </circle>
        <circle r="4" style={{ fill: "#ffffff", filter: "drop-shadow(0 0 8px #ec4899) drop-shadow(0 0 14px #f43f5e)", opacity: 0 }}>
         <animateMotion dur="7.2s" begin="-3.6s" repeatCount="indefinite" path="M560 450 C560 460 520 460 520 470" keyTimes="0; 0.750; 0.833; 1" keyPoints="0; 0; 1; 1" calcMode="linear" />
         <animate attributeName="opacity" dur="7.2s" begin="-3.6s" repeatCount="indefinite" values="0; 0; 1; 1; 0; 0" keyTimes="0; 0.750; 0.765; 0.818; 0.833; 1" />
        </circle>
       </g>
      </svg>

      {/* Session Controller Node */}
      <div className={`workflow-start modern-session-node ${chainFresh ? "data-backed" : ""}`} style={{ left: 80, top: 20 }}>
       <div className="session-header">
        <span className="session-dot" />
        <strong>Session Controller</strong>
       </div>
       <small className="session-sub">09:15 monitoring → 15:05 exit request</small>
       <div className="session-badge-wrap">
        <span className="session-status-badge">{data?.market?.session || "Session unavailable"}</span>
       </div>
       <em className="session-time">
        {lastObserved ? `Updated ${new Date(lastObserved).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}` : "No event timestamp"}
       </em>
      </div>

      {/* 8 Pipeline Stage Nodes */}
      {nodes.slice(0, 8).map((n, i) => {
       const cfg = STAGE_METADATA[n.agent] || { role: "Specialist", color: "#8b5cf6", rgb: "139, 92, 246", bg: "rgba(139, 92, 246, 0.22)", icon: "default" };
       const fresh = Boolean(n.event_id && eventAge(n.timestamp) <= 120);
       const current = Boolean(n.event_id && eventAge(n.timestamp) <= 30);
       const toneClass = online ? tone(n.status || "") : "waiting";

       return (
        <button
         key={n.agent}
         aria-label={`${n.agent}: ${n.status || "WAITING"}`}
         title={n.timestamp ? `Recorded ${new Date(n.timestamp).toLocaleString("en-IN")}` : "No event recorded"}
         className={`workflow-node modern-stage-card ${toneClass} ${n.event_id ? "data-backed" : "no-data"} ${fresh ? "is-fresh" : "is-stale"} ${current ? "is-current" : ""}`}
         style={{
          left: positions[i][0],
          top: positions[i][1],
          ["--stage-accent" as any]: cfg.color,
          ["--stage-rgb" as any]: cfg.rgb,
         }}
         onClick={() => onDetail({
          ...n,
          symbol,
          telemetry_current: Boolean(online),
          event: (data?.events || []).find((e: Data) => e.id === n.event_id)
         })}
        >
         {/* Top bar with Role Icon, Stage # & Agent Name */}
         <div className="stage-top-bar">
          <div className="stage-icon-box" style={{ background: cfg.bg, color: cfg.color, borderColor: cfg.color }}>
           {renderStageIcon(cfg.icon, cfg.color)}
          </div>
          <div className="stage-title-wrap">
           <div className="stage-agent-name">{n.agent}</div>
           <span className="stage-role-sub">{cfg.role}</span>
          </div>
          <div className="stage-idx" style={{ color: cfg.color, borderColor: `${cfg.color}88`, background: `${cfg.color}25` }}>
           0{i + 1}
          </div>
         </div>

         {/* Middle: Evaluated Description */}
         <p className="stage-label-text">{n.label || "Waiting for engine telemetry"}</p>

         {/* Bottom: Status Pill + Timestamp / Inspect */}
         <div className="stage-footer">
          <div className={`modern-status-pill ${toneClass}`}>
           <span className="status-indicator-dot" />
           <span className="status-text">{online ? (n.status || "WAITING") : "STALE"}</span>
          </div>
          <span className="stage-inspect-action">
           {n.timestamp ? new Date(n.timestamp).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : "—"} · Inspect ↗
          </span>
         </div>
        </button>
       );
      })}

      {/* CENTRAL ORCHESTRATOR CORE (Center Hub) */}
      <div
       className="orchestrator-core-card"
       style={{ left: 415, top: 285 }}
       onClick={handleOrchestratorClick}
       role="button"
       tabIndex={0}
       aria-label="Inspect Central Orchestrator Consensus"
      >
       {/* Animated concentric glowing rings */}
       <div className="orch-ring orch-ring-outer" />
       <div className="orch-ring orch-ring-mid" />
       <div className="orch-ring orch-ring-inner" />

       <div className="orchestrator-inner-content">
        <div className="orch-badge-row">
         <span className="orch-glow-dot" />
         <span className="orch-title-tag">ORCHESTRATOR CONSENSUS CORE</span>
         <span className="orch-inspect-link">Audit Consensus ↗</span>
        </div>

        <div className="orch-main-readout">
         <div className="orch-stance-box">
          <small className="orch-stance-label">CONSENSUS STANCE</small>
          <strong className="orch-stance-val" style={{ color: consensusColor, textShadow: `0 0 20px ${consensusColor}` }}>
           {consensusStance}
          </strong>
         </div>

         <div className="orch-meter-box">
          <div className="orch-meter-label">
           <span>Pipeline Gate Clearance</span>
           <strong style={{ color: "#ec4899" }}>{passedCount}/8 Passed</strong>
          </div>
          <div className="orch-meter-track">
           <div
            className="orch-meter-fill"
            style={{
             width: `${(passedCount / 8) * 100}%`,
             background: `linear-gradient(90deg, #ec4899, #a855f7, ${consensusColor})`,
             boxShadow: `0 0 14px ${consensusColor}`
            }}
           />
          </div>
         </div>
        </div>

        <div className="orch-footer-note">
         <span>14 specialist roles synthesized</span>
         <span className="orch-dot-sep">·</span>
         <span className={chainFresh ? "orch-fresh" : "orch-waiting"}>
          {chainFresh ? `${freshCount}/8 stages with live telemetry` : "Awaiting market cycle"}
         </span>
        </div>
       </div>
      </div>

      {/* Modern Footnote positioned cleanly below all cards */}
      <div className="workflow-footnote modern-footnote">
       Packets stream live handoff events from the past 2 minutes · Click any stage or the Central Orchestrator to inspect recorded audit evidence.
      </div>
     </div>
    </div>
   </div>

   {/* How the agents communicate (14 specialist roles) */}
   <div className="communication-panel modern-comm-panel">
    <div className="communication-heading">
     <div>
      <div className="eyebrow modern-eyebrow">ARCHITECTURE BUS · RECORDED TELEMETRY</div>
      <h3 className="modern-comm-title">Specialist Agent Architecture & Consensus Bus</h3>
     </div>
     <span className="comm-header-sub">14 specialized roles · Central consensus engine · Deterministic risk gate</span>
    </div>

    <div className="communication-grid modern-comm-grid">
     {routes.map(([from, to, role, roleColor, roleRgb]) => {
      const agent = auditById.get(from) as Data | undefined;
      const observed = Boolean(agent?.last_evidence_at);
      const fresh = Boolean(observed && eventAge(agent.last_evidence_at) <= 120);
      const state = agent?.status || "NO_EVIDENCE";

      return (
       <article
        key={from}
        className={`communication-node modern-comm-node ${fresh ? "comm-fresh" : observed ? "comm-observed" : "comm-muted"}`}
        style={{
         ["--comm-accent" as any]: roleColor,
         ["--comm-rgb" as any]: roleRgb,
        }}
       >
        <div className="communication-node-title">
         <i className="comm-status-dot" style={{ background: roleColor, boxShadow: `0 0 10px ${roleColor}` }} />
         <strong>{from}</strong>
         <small>{state.replaceAll("_", " ")}</small>
        </div>
        <p>{role}</p>
        <div className="communication-route">
         <b aria-hidden="true"><i /></b>
         <strong>{to}</strong>
        </div>
        <div className="communication-stats">
         <span>{agent?.decision_count ?? 0} decisions</span>
         <span>{agent?.outcome_count ?? 0} outcomes</span>
         <em>{fresh ? "fresh" : observed ? "recorded" : "quiet"}</em>
        </div>
       </article>
      );
     })}
    </div>

    <p className="communication-note">
     Routes define the immutable multi-agent contract. Status, decision counts, and timestamps derive from the live telemetry audit stream. A route reflects consensus participation, never an unverified fill.
    </p>
   </div>
  </section>
 );
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
  <strong>{r.presentation?.evidence_label || r.quality} · {ok ? (r.quality === "estimated_scenario" ? "Completed exploratory scenario" : "Completed observed replay") : "Performance not established"}</strong>
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
