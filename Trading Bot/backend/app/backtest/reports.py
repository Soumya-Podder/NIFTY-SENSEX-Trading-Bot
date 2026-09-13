from collections import defaultdict
from ..store import json_safe
from ..telemetry.decision_trace import AGENT_ORDER


def attribution(trades, field):
    groups=defaultdict(list)
    for trade in trades: groups[str(trade.get(field,"UNKNOWN"))].append(trade)
    return [{"name":name,"trades":len(items),"win_rate":sum(t["pnl"]>0 for t in items)/len(items),
             "pnl":sum(t["pnl"] for t in items),"expectancy":sum(t["pnl"] for t in items)/len(items)}
            for name,items in groups.items()]


def report_from_run(result, config):
    trades=result.get("trades",[]); curve=result.get("curve",[])
    research=result.get("pnl_basis")=="current_lot_gross_scenario"
    attributed=[{**t,"pnl":t.get("gross_pnl")} for t in trades] if research else trades
    attributed=[t for t in attributed if t.get("pnl") is not None]
    peak=config.get("capital",30000); drawdown=[]
    for point in curve:
        peak=max(peak,point["value"])
        drawdown.append({"timestamp":point["timestamp"],"value":point["value"]-peak})
    step=max(1,len(curve)//1200)
    def compact(values):
        result=values[::step]
        if values and result[-1]!=values[-1]: result.append(values[-1])
        return result
    agents=[]
    for agent in AGENT_ORDER:
        items=[t for t in attributed if agent in t.get("agent_contexts",{})]
        contexts=attribution([{**t,"context":t["agent_contexts"][agent]} for t in items],"context")
        agents.append({"agent":agent,**result.get("agent_counts",{}).get(agent,{}),"outcomes":len(items),
            "pnl":sum(t["pnl"] for t in items),"contexts":contexts})
    return json_safe({"status":result.get("status", "complete" if result.get("quality")=="verified" else "data_blocked"),
        "quality":result.get("quality","incomplete"),"source":result.get("source","contract_specific_candles"),
        "replay_version":result.get("replay_version"),
        "strategy_mode":result.get("strategy_mode"),"selection_mode":result.get("selection_mode"),
        "parity_limitations":result.get("parity_limitations",[]),
        "strategy_version":result.get("strategy_version",config.get("strategy_version")),
        "fidelity":result.get("fidelity"),"deployment_ready":result.get("deployment_ready",False),
        "evidence_status":result.get("evidence_status"),"risk_policy":result.get("risk_policy"),
        "opportunities":result.get("opportunities",[]),"loss_ledger":result.get("loss_ledger"),
        "config":config,"pnl_basis":result.get("pnl_basis","net"),"metrics":result.get("metrics",{}),"equity":compact(curve),"drawdown":compact(drawdown),
        "estimation":result.get("estimation"),"learning_eligible":result.get("learning_eligible"),
        "gross_equity":compact(result.get("gross_curve",[])),"gross_metrics":result.get("gross_metrics",{}),
        "daily":result.get("daily",[]),"trades":trades,"unresolved":result.get("unresolved",[]),
        "skipped_entries":result.get("skipped_entries",[]),
        "issues":result.get("issues",[]),"coverage":result.get("coverage",[]),
        "reconstruction":result.get("reconstruction"),
        "agent_counts":result.get("agent_counts",{}),"agent_performance":agents,
        "attribution":{"regimes":attribution(attributed,"regime"),"setups":attribution(attributed,"setup")},
        "assumptions":result.get("assumptions",["Simulation, not broker fills; one adverse tick; stop first if both barriers cross.",
            "Performance attribution is shared trade P&L, not an additive causal contribution per agent.",
            "Source-declared contract metadata and dated fees are validated structurally; no fabricated missing values.",
            "Session statistics cover supplied sessions only; missing whole sessions need a sourced exchange calendar."])})
