from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from app.ai import scope
from app.portfolio_engine import MultiStrategyPaperEngine
from app.specialist_agents import VERSION, assess_specialists
from tests.test_specialist_agents import base_signal, base_contract
from tests.test_strategy_portfolio import portfolio_account, candidate, executable, frame_fixture


@pytest.mark.parametrize("defect,role",[
    ("opposite_regime","Regime Agent"), ("opposite_momentum","Momentum Agent"),
    ("missing_momentum","Momentum Agent"), ("forming_bar","Momentum Agent"),
    ("stale_bar","Momentum Agent"), ("invalidated","Structure Agent"),
    ("target_reached","Structure Agent"), ("overextended","Structure Agent"),
    ("invalid_direction","Directional Agent"),
])
def test_coordinator_requires_substantive_current_evidence(defect,role):
    now=datetime.now(timezone.utc); signal=base_signal(); row=signal["feature_row"]
    if defect=="opposite_regime": signal["regime"]="TREND_DOWN"
    if defect=="opposite_momentum": row.update(ema_slope_atr=-.4,ema9=99,ema21=100)
    if defect=="missing_momentum": row.pop("adx")
    if defect=="forming_bar": row["timestamp"]=(now-timedelta(seconds=10)).isoformat()
    if defect=="stale_bar": row["timestamp"]=(now-timedelta(seconds=126)).isoformat()
    if defect=="invalidated": row["close"]=97
    if defect=="target_reached": signal["underlying_target"]=99
    if defect=="overextended": row["close"]=103
    if defect=="invalid_direction": signal["invalidation"]=101
    result=assess_specialists(signal,base_contract(),datetime.now(timezone.utc),risk=300,reward=800)
    assert result["decision"]=="WAIT" and role in result["vetoes"]
    assert "Adversarial Agent" in result["vetoes"]


def test_put_evidence_is_symmetric_and_advisory_inputs_are_not_votes():
    s=base_signal(); s.update(option_type="PUT",regime="TREND_DOWN",invalidation=102)
    s["feature_row"].update(ema9=100.2,ema21=100.5,ema_slope_atr=-.4)
    c=base_contract(); c.update(oi=999999,previous_oi=999000,gamma=None)
    result=assess_specialists(s,c,datetime.now(timezone.utc),risk=300,reward=800)
    assert result["decision"]=="PUT" and not result["vetoes"]
    assert len(result["agents"])==14
    assert result["agents"]["Options Flow Agent"]["evidence"]["change_oi"]==999
    assert result["agents"]["Gamma Agent"]["status"]=="DATA_UNAVAILABLE"
    assert result["agents"]["News/Event Agent"]["status"]=="DATA_UNAVAILABLE"
    assert result["agents"]["Risk Sentinel"]["status"]=="PENDING"


def prepared(tmp_path,monkeypatch):
    e,b,store,clock=portfolio_account(tmp_path,monkeypatch)
    s=candidate(clock); c,candle=executable(clock)
    e._request_protection=lambda *_:(candle,None)
    return e,b,store,clock,s,c


def test_rejected_specialist_review_is_durable_and_visible_after_gate(tmp_path,monkeypatch):
    e,b,store,clock,s,c=prepared(tmp_path,monkeypatch)
    s["feature_row"]["ema_slope_atr"]=-.5
    offer,reason=e._prepare_offer(s,c,b.snapshot(),[],clock["now"])
    assert offer is None and "Momentum Agent" in reason
    e._gate(s,"REJECTED",reason)
    view=e.describe_strategies()["reviews"]["NIFTY"]
    assert view["decision"]=="WAIT" and view["agents"]["Momentum Agent"]["status"]=="VETO"
    assert store.list_records("decision_reviews")[0]["checks"]["specialist_evidence"]["status"]=="BLOCKED"
    assert b.snapshot()["open_positions"]==0


def test_account_risk_veto_cannot_be_outvoted(tmp_path,monkeypatch):
    e,b,store,clock,s,c=prepared(tmp_path,monkeypatch)
    account=b.snapshot(); account["cash"]=0
    offer,reason=e._prepare_offer(s,c,account,[],clock["now"])
    review=e.describe_strategies()["reviews"]["NIFTY"]
    assert offer is None and "cash" in reason
    assert review["agents"]["Momentum Agent"]["status"]=="PASS"
    assert review["agents"]["Risk Sentinel"]["status"]=="VETO"
    assert review["decision"]=="WAIT"


def test_final_admission_rechecks_changed_regime_and_keeps_exit_path_independent(tmp_path,monkeypatch):
    e,b,store,clock,s,c=prepared(tmp_path,monkeypatch)
    offer,_=e._prepare_offer(s,c,b.snapshot(),[],clock["now"])
    e.quotes[c["contract_id"]]=c
    monkeypatch.setattr(e,"_current_signal",lambda signal,now:({**signal,"regime":"TREND_DOWN"},None))
    assert not e._execute_offer(offer)
    assert b.snapshot()["open_positions"]==0
    assert e.describe_strategies()["reviews"]["NIFTY"]["decision"]=="WAIT"


def test_current_signal_uses_completed_frames_and_rejects_gaps(tmp_path,monkeypatch):
    e,b,store,clock,s,c=prepared(tmp_path,monkeypatch)
    frame=frame_fixture(); clock["now"]=frame.timestamp.iloc[-1].to_pydatetime()+timedelta(minutes=1)
    e.frames["NIFTY"]=frame
    current,reason=MultiStrategyPaperEngine._current_signal(e,s,clock["now"])
    assert reason is None and current["feature_row"]["timestamp"]==str(frame.timestamp.iloc[-1])
    future=frame.iloc[[-1]].copy(); future["timestamp"]=pd.Timestamp(clock["now"])+pd.Timedelta(minutes=1)
    future.loc[:,"close"]=999999
    e.frames["NIFTY"]=pd.concat([frame,future])
    assert MultiStrategyPaperEngine._current_signal(e,s,clock["now"])== (current,None)
    e.frames["NIFTY"]=frame.drop(index=10)
    current,reason=MultiStrategyPaperEngine._current_signal(e,s,clock["now"])
    assert current is None and "Missing" in reason


def test_old_scope_and_outcomes_do_not_validate_new_coordinator(tmp_path,monkeypatch):
    e,b,store,clock,s,c=prepared(tmp_path,monkeypatch)
    offer,reason=e._prepare_offer(s,c,b.snapshot(),[],clock["now"])
    assert reason is None
    new=offer["signal"]
    assert new["decision_policy_version"]==VERSION
    old={k:v for k,v in new.items() if k!="decision_policy_version"}
    assert scope(new)!=scope(old)
    assert new["agent_scores"]["Risk Sentinel"]=="PASS"
    e.quotes[c["contract_id"]]=c
    assert e._execute_offer(offer)
    p=b.snapshot()["positions"][0]
    assert p["decision_review"]["agents"]["Risk Sentinel"]["status"]=="PASS"
    assert p["decision_policy_version"]==VERSION


def test_closed_session_has_no_fabricated_specialist_passes(tmp_path,monkeypatch):
    e,b,store,clock,s,c=prepared(tmp_path,monkeypatch)
    monkeypatch.setattr(e,"_session",lambda:"WEEKEND")
    e.portfolio_cycle()
    review=e.describe_strategies()["reviews"]["NIFTY"]
    assert review["decision"]=="WAIT" and review["reason"]=="WEEKEND"
    assert review["coverage"]["available"]==0
    assert review["agents"]["Momentum Agent"]["status"]=="NOT_EVALUATED"
    assert {row["symbol"] for row in store.list_records("decision_reviews")}=={"NIFTY","SENSEX"}


def test_dead_worker_blocks_entry_even_with_passing_signal(tmp_path,monkeypatch):
    e,b,store,clock,s,c=prepared(tmp_path,monkeypatch)
    e.threads=[SimpleNamespace(name="paper-engine",is_alive=lambda:False)]
    e.status["last_cycle"]=clock["now"].isoformat()
    offer,reason=e._prepare_offer(s,c,b.snapshot(),[],clock["now"])
    assert offer is None and "workers" in reason
    assert e.status["portfolio"]["reviews"]["NIFTY"]["checks"]["workers"]["status"]=="BLOCKED"


def test_stopped_engine_can_restart_without_duplicate_live_workers(tmp_path,monkeypatch):
    e,b,store,clock,s,c=prepared(tmp_path,monkeypatch)
    created=[]
    class Worker:
        def __init__(self,*,name,target,daemon): self.name=name; self.alive=False; created.append(self)
        def start(self): self.alive=True
        def is_alive(self): return self.alive
        def join(self,timeout): self.alive=False
    monkeypatch.setattr("app.paper_engine.threading.Thread",Worker)
    e.start()
    assert len(e.threads)==11 and not e.stop_event.is_set()
    assert any(thread.name=="paper-protection" for thread in e.threads)
    e.start()
    assert len(created)==11
    e.stop(); assert e.stop_event.is_set()
    e.start()
    assert len(created)==22 and len(e.threads)==11 and not e.stop_event.is_set()


def test_generic_pipeline_event_does_not_claim_specialist_work(tmp_path):
    from app.store import Store
    from app.individual_agent_audit import audit_individual_agents
    store=Store(tmp_path / "attribution.db")
    store.record_event({"id":"generic","agent":"Option Selector","status":"PASS","timestamp":"2026-09-25T10:00:00+05:30"})
    audit=audit_individual_agents(store)
    assert next(row for row in audit["agents"] if row["id"]=="Options Flow Agent")["decision_count"]==0
    store.record_event({"id":"explicit","agent":"Options Flow Agent","status":"OBSERVATION","timestamp":"2026-09-25T10:00:00+05:30"})
    audit=audit_individual_agents(store)
    assert next(row for row in audit["agents"] if row["id"]=="Options Flow Agent")["decision_count"]==1


def test_atomic_broker_rejects_specialist_data_that_expired_during_costing(tmp_path,monkeypatch):
    e,b,store,clock,s,c=prepared(tmp_path,monkeypatch)
    # Candidate is within its own 185-second lifetime; its latest feature bar
    # expires independently while the still-fresh option quote is being costed.
    s["timestamp"]=(clock["now"]-timedelta(seconds=124)).isoformat()
    s["feature_row"]["timestamp"]=s["timestamp"]
    offer,reason=e._prepare_offer(s,c,b.snapshot(),[],clock["now"])
    assert reason is None
    original=b.cost.quote
    def charge(*args,**kwargs):
        clock["now"]+=timedelta(seconds=.7)
        return original(*args,**kwargs)
    monkeypatch.setattr(b.cost,"quote",charge)
    with pytest.raises(ValueError,match="Specialist evidence"):
        b.place_order(contract=c,quote=c,quantity=c["lot_size"],signal={**offer["signal"],"risk_rupees":offer["risk"]},now=clock["now"])
    assert not b.snapshot()["positions"]


def test_health_distinguishes_execution_and_advisory_failures(tmp_path,monkeypatch):
    from app.runtime_health import execution_health
    e,b,store,clock,s,c=prepared(tmp_path,monkeypatch)
    e.threads=[SimpleNamespace(name="paper-engine",is_alive=lambda:True)]
    e.status.update(last_cycle=clock["now"].isoformat(),quote_error="No depth",feedback_error="Research pending")
    health=execution_health(e,b,clock["now"])
    assert not health["healthy"] and health["errors"]["quote_error"]=="No depth"
    assert health["advisory_errors"]["feedback_error"]=="Research pending"
