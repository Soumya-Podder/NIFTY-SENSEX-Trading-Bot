from collections import Counter,defaultdict
from datetime import datetime,timedelta,timezone
import math
import uuid
import threading
import numpy as np
from .decision_trace import AGENT_ORDER


AGENT_ROLES={
    "Scanner":"Evaluates closed-candle quality, opening range and opportunity context.",
    "Regime":"Classifies trend and volatility; rule scores are not win probabilities.",
    "Setup":"Selects an aligned directional entry setup.",
    "Confirmation":"Checks EMA/VWAP agreement and extension.",
    "Option Selector":"Ranks verified, liquid non-ATM contracts within the cash budget.",
    "EV":"Uses recorded outcomes to estimate conservative expectancy; labels cold-start observations.",
    "Risk":"Enforces fixed cash, daily-loss and correlated-exposure caps.",
    "Execution":"Simulates fills from observed depth and records broker-estimated charges."}


PLAN_AGENT_CAPABILITIES = [
    {"agent":"Data Integrity","status":"PARTIAL","evidence":"Causal bar, candle-array, quote-age and contract-identity checks are enforced.","limitation":"Exchange-tick completeness and all field-specific historical ages are not certified."},
    {"agent":"Calendar and Event","status":"DATA_BLOCKED","evidence":"Session clock and weekday boundary checks are enforced.","limitation":"A sourced holiday/event calendar is not configured; entries remain blocked when required."},
    {"agent":"Market Regime","status":"IMPLEMENTED","evidence":"Deterministic completed-bar regime classification is recorded.","limitation":"Rule strength is not a calibrated win probability."},
    {"agent":"Setup","status":"IMPLEMENTED","evidence":"The causal ORB retest baseline is shared by replay and paper observation.","limitation":"Only the frozen baseline is active; alternatives require separate research."},
    {"agent":"Greeks and Volatility","status":"PARTIAL","evidence":"Live chain Greeks and unit-checked scenario math are supported.","limitation":"Historical Greek age, IV surface and dated contract inputs are unavailable from rolling candles."},
    {"agent":"Flow Context","status":"DATA_BLOCKED","evidence":"Volume and OI are retained when Dhan returns them.","limitation":"Historical depth and a validated institutional-flow interpretation are unavailable."},
    {"agent":"Contract Selection","status":"PARTIAL","evidence":"Live selection is automatic, non-ATM, liquid and budget-aware.","limitation":"Rolling historical offsets do not prove an exact historical contract identity."},
    {"agent":"Portfolio Risk","status":"IMPLEMENTED","evidence":"One shared risk authority enforces cash, loss, correlation and position limits.","limitation":"A stop budget is not a guaranteed execution loss cap."},
    {"agent":"Exit Policy","status":"IMPLEMENTED","evidence":"Structural stop, target, thesis-failure, time and session exits are replayable.","limitation":"Historical executable bid/depth is required for verified outcome claims."},
    {"agent":"Execution and Reconciliation","status":"PARTIAL","evidence":"Paper fills, charges, stale-depth vetoes and durable job/order records are supported.","limitation":"Live order authority is disabled and broker recovery is not live-validated."},
    {"agent":"Replay","status":"PARTIAL","evidence":"Exact-contract CSV replay and rolling-source audit paths exist.","limitation":"Dhan rolling data remains a research audit, not exact-contract historical execution."},
    {"agent":"Learning and Validation","status":"IMPLEMENTED","evidence":"Context-attributed ledger, gross research recording and chronological challenger gates exist.","limitation":"No verified candidate has passed the required validation and human review gates."},
    {"agent":"Audit and Reporting","status":"IMPLEMENTED","evidence":"Persistent jobs, reports, coverage, trade exports and archive manifests are exposed.","limitation":"Unavailable source fields remain explicitly unavailable."},
]


def plan_agent_capabilities():
    return [dict(item) for item in PLAN_AGENT_CAPABILITIES]


def _stats(trades, field="pnl"):
    p=[float(t[field]) for t in trades if t.get(field) is not None]
    return {"samples":len(p),"wins":sum(v>0 for v in p),"losses":sum(v<0 for v in p),
            "pnl":sum(p),"expectancy":sum(p)/len(p) if p else None}


def _agent_trades(trades, agent):
    """Restrict learning statistics to outcomes with recorded agent context."""
    return [trade for trade in trades if agent in (trade.get("agent_contexts") or {})]


def outcome_lessons(trades,agent,quality,min_samples):
    """Observed associations and hypotheses; not causal proof or deployed policies."""
    field="pnl" if quality=="verified" else "gross_pnl"
    groups=defaultdict(list)
    for trade in trades:
        context=trade.get("agent_contexts",{}).get(agent)
        value=trade.get(field)
        if context is not None and value is not None and math.isfinite(float(value)): groups[str(context)].append(trade)
    lessons=[]
    for context,items in groups.items():
        values=[float(t[field]) for t in items]; pnl=sum(values)
        losses=[t for t in items if float(t[field])<0]
        sufficient=len(items)>=min_samples
        action="AVOID_CANDIDATE" if pnl<0 else "FOCUS_CANDIDATE" if pnl>0 else "OBSERVE"
        lessons.append({"context":context,"samples":len(items),"wins":sum(v>0 for v in values),"losses":len(losses),
            "action":action if sufficient else "COLLECT_EVIDENCE",
            "pnl":pnl,"expectancy":pnl/len(items),"basis":"net" if field=="pnl" else "gross_research",
            "loss_exit_reasons":dict(Counter(t.get("reason","unavailable") for t in losses)),
            "win_exit_reasons":dict(Counter(t.get("reason","unavailable") for t in items if float(t[field])>0)),
            "proposal":(f"Test excluding context '{context}' in separate chronological portfolio replays." if pnl<0 else f"Test focusing on context '{context}' without bypassing entry, liquidity or risk checks.") if pnl!=0 and sufficient else "Collect more independent evidence.",
            "status":"PROPOSED_NOT_VALIDATED" if pnl!=0 and sufficient else "OBSERVATION",
            "minimum_context_samples":min_samples,"applied":False,
            "caution":"Association, not an agent-specific causal loss. No savings or future profit are inferred by deleting losing trades."})
    return sorted(lessons,key=lambda item:item["pnl"])


def _passes(baseline,candidate,min_trades,min_days):
    if candidate.get("quality")!="verified" or baseline.get("quality")!="verified": return False,"Replay data is incomplete"
    b=baseline["metrics"]; c=candidate["metrics"]
    bd={d["date"]:d["pnl"] for d in baseline.get("daily",[])}
    cd={d["date"]:d["pnl"] for d in candidate.get("daily",[])}
    if set(bd)!=set(cd): return False,"Baseline and candidate session coverage differs"
    days=sorted(set(bd)&set(cd))
    if c["trades"]<min_trades or len(days)<min_days: return False,"Insufficient independent validation trades or sessions"
    if c["trades"]<.7*b["trades"]: return False,"Candidate removes too much trade coverage"
    diff=np.array([cd[d]-bd[d] for d in days],float)
    lower=float(diff.mean()-3*diff.std(ddof=1)/math.sqrt(len(diff)))
    passed=(c["total_pnl"]>0 and c["expectancy"]>0 and c["total_pnl"]>b["total_pnl"] and
            c["max_drawdown"]>=b["max_drawdown"] and lower>0)
    return passed,f"Paired daily improvement lower bound: {lower:.2f}; positive expectancy and drawdown gates {'passed' if passed else 'failed'}"


_learning_lock=threading.RLock()


def learn_from_outcomes(*args,**kwargs):
    with _learning_lock:
        return _learn_from_outcomes(*args,**kwargs)


def _learn_from_outcomes(trades,source,store,run_id=None,*,quality="unverified",replay=None,dataset_id=None,windows=None,before_commit=None):
    """Every outcome is logged. Promotion requires fresh, full chronological replays."""
    run_id=run_id or str(uuid.uuid4())
    if store.get_record("learning_runs",run_id): return store.learning_snapshot()
    now=datetime.now(timezone.utc); stamp=now.isoformat()
    from ..session import now_ist
    ordered=sorted(trades,key=lambda t:str(t.get("exit_ts","")))
    lesson_trades=ordered
    if source=="paper" and ordered and ordered[-1].get("exit_ts"):
        # Reuse completed position episodes, not individual partial fills or past backtest runs.
        cutoff=datetime.fromisoformat(ordered[-1]["exit_ts"])
        versions=ordered[-1].get("policy_versions",{})
        history=[t for t in store.list_records("episodes",10000)
                 if t.get("exit_ts") and datetime.fromisoformat(t["exit_ts"])<=cutoff
                 and t.get("policy_versions",{})==versions]
        lesson_trades=list({t["id"]:t for t in [*history,*ordered] if t.get("id")}.values())
    existing={} if replay else store.active_learning_policies()
    saved=store.learning_snapshot()["agents"]; entries=[]; promotions=[]
    forward_pending=any(p.get("policy",{}).get("validator_version")==4 and
        p["policy"].get("validation_status")=="PROMOTED" and p["policy"].get("expires_at","")>stamp for p in saved.values())
    overlap=False
    if windows:
        for old in store.list_records("learning_datasets",10000):
            if old.get("validation_from") and not (windows["test_to"]<old["validation_from"] or windows["validation_from"]>old["test_to"]):
                overlap=True; break
    from ..config import settings
    training=replay(existing,windows["train_from"],windows["train_to"]) if replay and windows and quality=="verified" and not overlap and not forward_pending else None
    for agent in AGENT_ORDER:
        agent_outcomes=_agent_trades(ordered,agent)
        outcome_field="gross_pnl" if quality=="research" else "pnl"
        stats=_stats(agent_outcomes,outcome_field); before=saved.get(agent,{}).get("policy_version",0)
        status="INSUFFICIENT_DATA"; proposed="Recording agent-specific decisions and outcomes; no policy change."
        blocked=None; baseline_stats={}; candidate_stats={}; evidence=[]; after=before
        if quality!="verified":
            status="DATA_BLOCKED"; proposed="Historical data quality must be verified before outcomes can change a policy."
            if quality=="research":
                proposed="Gross research outcomes and contexts recorded. Missing historical metadata/fees prevent net validation and policy promotion."
        elif overlap:
            status="REUSED_HOLDOUT"; proposed="This validation period has already been examined. Use a later untouched period."
        elif replay and forward_pending:
            status="FORWARD_VALIDATION_PENDING"; proposed="An existing policy is in forward paper evaluation. Do not combine individually tested changes."
        elif replay and windows:
            training_trades=training.get("trades",[])
            groups=defaultdict(list)
            for trade in training_trades:
                context=trade.get("agent_contexts",{}).get(agent)
                if context is not None: groups[str(context)].append(trade)
            eligible=[(key,_stats(items)) for key,items in groups.items() if len(items)>=settings.learning_min_context_trades and _stats(items)["pnl"]!=0]
            if training.get("quality")=="verified" and len(training_trades)>=settings.learning_min_train_trades and eligible:
                losing=[item for item in eligible if item[1]["pnl"]<0]
                context=(min(losing,key=lambda item:item[1]["expectancy"]) if losing else max(eligible,key=lambda item:item[1]["expectancy"]))[0]
                blocked=context if losing else None
                proposed=f"{'Exclude' if losing else 'Focus on'} {agent} context '{context}' within unchanged entry and risk rules."
                policy={"agent":agent,"version":before+1,("blocked_value" if losing else "allowed_value"):context,"field":"agent_context",
                        "validator_version":4,"validation_status":"PROMOTED","source_run_id":run_id,
                        "effective_from":(now_ist().date()+timedelta(days=1)).isoformat(),
                        "expires_at":(now+timedelta(days=30)).isoformat(),"paper_only":True}
                candidate_policies={**existing,agent:policy}
                baseline=replay(existing,windows["validation_from"],windows["validation_to"])
                candidate=replay(candidate_policies,windows["validation_from"],windows["validation_to"])
                passed,note=_passes(baseline,candidate,settings.learning_min_validation_trades,settings.learning_min_validation_days)
                evidence.append({"window":"validation","reason":note,"baseline":baseline["metrics"],"candidate":candidate["metrics"]})
                baseline_stats=baseline["metrics"]; candidate_stats=candidate["metrics"]
                if passed:
                    baseline_test=replay(existing,windows["test_from"],windows["test_to"])
                    candidate_test=replay(candidate_policies,windows["test_from"],windows["test_to"])
                    passed,note=_passes(baseline_test,candidate_test,settings.learning_min_validation_trades,settings.learning_min_validation_days)
                    evidence.append({"window":"untouched_test","reason":note,"baseline":baseline_test["metrics"],"candidate":candidate_test["metrics"]})
                status="PROMOTED" if passed else "REJECTED"
                if passed:
                    after=before+1
                    promotions.append({"agent":agent,"version":after,"policy":policy,"updated_at":stamp})
            else: proposed="More verified training trades are needed for this agent's contexts."
        elif quality=="verified" and stats["samples"]:
            status="FEEDBACK_RECORDED"
            proposed="Outcome recorded. A full replay on disjoint future validation periods is required before a policy change."
        entries.append({"run_id":run_id,"recorded_at":stamp,"source":source,"agent":agent,
            "policy_before":before,"policy_after":after,"sample_count":stats["samples"],"wins":stats["wins"],
            "losses":stats["losses"],"pnl":stats["pnl"],"loss_pattern":blocked,"proposed_adjustment":proposed,
            "adjustment_status":status,"validation_status":status,
            "baseline_pnl":baseline_stats.get("total_pnl"),"candidate_pnl":candidate_stats.get("total_pnl"),
            "baseline_expectancy":baseline_stats.get("expectancy"),"candidate_expectancy":candidate_stats.get("expectancy"),
            "validation_samples":baseline_stats.get("trades",0),
            "metadata":{"validator_version":4,"dataset_id":dataset_id,"quality":quality,"evidence":evidence,
                        "lessons":outcome_lessons(lesson_trades,agent,quality,settings.learning_min_context_trades),
                        "lesson_scope":"Recent completed paper episodes under matching policy versions, through this exit" if source=="paper" else "This backtest run only",
                        "research_gross_outcomes":[{"trade_id":t.get("id"),"gross_pnl":t.get("gross_pnl"),"context":t.get("agent_contexts",{}).get(agent)} for t in agent_outcomes if quality=="research"],
                        "contexts":dict(Counter(str(t.get("agent_contexts",{}).get(agent)) for t in agent_outcomes))}})
    # Candidates are evaluated individually against a frozen baseline. Promote at most one,
    # avoiding an untested interaction between eight simultaneous changes.
    if len(promotions)>1:
        selected=promotions[0]["agent"]
        promotions=promotions[:1]
        for entry in entries:
            if entry["validation_status"]=="PROMOTED" and entry["agent"]!=selected:
                entry.update(validation_status="AWAITING_COMBINED_VALIDATION",adjustment_status="NOT_APPLIED",policy_after=entry["policy_before"])
    if before_commit: before_commit()
    # Passing a statistical gate creates a review candidate, never a deployment.
    for promotion in promotions:
        candidate={**promotion["policy"],"validation_status":"AWAITING_REVIEW","effective_from":None}
        store.put_record("learning_candidates",run_id+":"+promotion["agent"],candidate)
    for entry in entries:
        if entry["validation_status"]=="PROMOTED":
            entry.update(validation_status="AWAITING_REVIEW",adjustment_status="NOT_APPLIED",policy_after=entry["policy_before"])
    store.record_learning(entries,[])
    store.put_record("learning_runs",run_id,{"entries":entries,"source":source,"recorded_at":stamp,"dataset_id":dataset_id})
    if windows and replay and not overlap and quality=="verified" and any(e["metadata"]["evidence"] for e in entries):
        store.put_record("learning_datasets",run_id,{**windows,"dataset_id":dataset_id})
    return store.learning_snapshot()


def rollback_policies(store,reason):
    stamp=datetime.now(timezone.utc).isoformat()
    for agent,policy in store.active_learning_policies().items():
        changed={**policy,"validation_status":"ROLLED_BACK","rollback_reason":reason}
        store.record_learning([],[{"agent":agent,"version":policy["version"],"policy":changed,"updated_at":stamp}])
        store.put_record("policy_audit",str(uuid.uuid4()),{"agent":agent,"status":"ROLLED_BACK","reason":reason,"timestamp":stamp})


def agent_metrics_from_events(events,backtest=None,learning=None):
    counts=defaultdict(lambda:{"candidates":0,"passed":0,"rejected":0}); latest={}
    for item in events:
        agent=item.get("agent")
        if agent not in AGENT_ORDER: continue
        counts[agent]["candidates"]+=1
        if item.get("status") in {"PASS","FILLED"}: counts[agent]["passed"]+=1
        if item.get("status")=="REJECTED": counts[agent]["rejected"]+=1
        latest[agent]=item
    state=(learning or {}).get("agents",{})
    rows=[]
    for agent in AGENT_ORDER:
        learned=state.get(agent,{})
        research=learned.get("metadata",{}).get("research_gross_outcomes",[]) if learned.get("metadata",{}).get("quality")=="research" else None
        policy=learned.get("policy",{})
        legacy=bool(policy) and policy.get("validator_version")!=4 and learned.get("metadata",{}).get("validator_version")!=4
        item=latest.get(agent,{})
        values=(backtest or {}).get("agent_counts",{}).get(agent,counts[agent])
        rows.append({"agent":agent,"role":AGENT_ROLES[agent],**values,
            "conversion":values["passed"]/values["candidates"] if values["candidates"] else None,
            "status":item.get("status","WAITING"),"last_action":item.get("summary","Awaiting an evaluated cycle"),
            "outcomes":learned.get("sample_count",0),"wins":learned.get("wins",0),"losses":learned.get("losses",0),
            "research_outcomes":len(research) if research is not None else None,
            "research_losses":sum(t.get("gross_pnl",0)<0 for t in research) if research is not None else None,
            "research_gross_pnl":sum(t.get("gross_pnl",0) for t in research) if research is not None else None,
            "pnl":learned.get("pnl"),"policy_version":learned.get("policy_version",0) if policy.get("validator_version")==4 else 0,
            "validation_status":"LEGACY_NOT_APPLIED" if legacy else learned.get("validation_status","WAITING_FOR_OUTCOMES"),
            "learning_status":"LEGACY_NOT_APPLIED" if legacy else learned.get("validation_status","WAITING_FOR_OUTCOMES"),
            "learning_summary":"Previous filters retained only for audit" if legacy else learned.get("proposed_adjustment","No verified outcomes yet"),
            "proposed_adjustment":learned.get("proposed_adjustment",""),"policy_updated_at":learned.get("updated_at"),
            "policy":policy,
            "lessons":learned.get("metadata",{}).get("lessons",[]),
            "evidence":learned.get("metadata",{}).get("evidence",[]),"contexts":learned.get("metadata",{}).get("contexts",{})})
    return rows
