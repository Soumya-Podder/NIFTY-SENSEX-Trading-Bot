import pandas as pd
import pytest
import json
from copy import deepcopy
from app.backtest.engine import BacktestEngine
from app.backtest.engine import BacktestConfig
from app.backtest.metrics import metrics
from app.backtest.reports import report_from_run
from app.indicators import add_features,rsi
from app.pipeline import DecisionPipeline
from app.store import Store
from app.telemetry.agent_metrics import learn_from_outcomes
from app.telemetry.agent_metrics import plan_agent_capabilities
from app.telemetry.decision_trace import AGENT_ORDER
from app.setups import opening_range_retest


def test_orb_retest_requires_completed_sequential_bars():
    # Synthetic prices are isolated unit fixtures, never runtime market inputs.
    frame = pd.DataFrame({"timestamp": pd.date_range("2026-09-04 09:15", periods=20, freq="min"),
                          "open": 100., "high": 101., "low": 99., "close": 100., "atr": 2.})
    frame.loc[17, ["open", "high", "low", "close"]] = [100, 103, 100, 102]
    frame.loc[18, ["open", "high", "low", "close"]] = [102, 102.5, 101, 102]
    frame.loc[19, ["open", "high", "low", "close"]] = [102, 104, 102, 103]
    assert opening_range_retest(frame, "2026-09-04 09:34:59") is None
    signal = opening_range_retest(frame, "2026-09-04 09:35")
    assert signal["option_type"] == "CALL"
    assert signal["invalidation"] == 101
    assert signal["available_at"] == "2026-09-04T09:35:00+05:30"
    assert opening_range_retest(frame.drop(index=5), "2026-09-04 09:35") is None
    assert opening_range_retest(pd.concat([frame, frame.iloc[[5]]]), "2026-09-04 09:35") is None
    frame.loc[19, "close"] = 102.5
    assert opening_range_retest(frame, "2026-09-04 09:35") is None


def test_orb_retest_put_mirror_and_future_data_is_ignored():
    frame = pd.DataFrame({"timestamp": pd.date_range("2026-09-04 09:15", periods=21, freq="min"),
                          "open": 100., "high": 101., "low": 99., "close": 100., "atr": 2.})
    frame.loc[17, ["open", "high", "low", "close"]] = [100, 100, 97, 98]
    frame.loc[18, ["open", "high", "low", "close"]] = [98, 99, 97.5, 98]
    frame.loc[19, ["open", "high", "low", "close"]] = [98, 98, 96, 97]
    signal = opening_range_retest(frame, "2026-09-04 09:35")
    assert signal["option_type"] == "PUT"
    frame.loc[20, ["open", "high", "low", "close"]] = [1, 99999, 1, 99999]
    assert opening_range_retest(frame, "2026-09-04 09:35") == signal


@pytest.mark.parametrize("agent,context", [
    ("Scanner", "completed_bars"), ("Regime", "price_only_baseline"),
    ("Confirmation", "completed_resumption"), ("Setup", "ORB_RETEST_CALL"),
])
@pytest.mark.parametrize("policy_field,policy_value", [("blocked_value", None), ("allowed_value", "different_context")])
def test_baseline_honors_each_participating_agent_veto(agent, context, policy_field, policy_value):
    candidate={"setup":"ORB_RETEST_CALL", "break_timestamp":"2026-09-04T09:32:00+05:30",
               "retest_timestamp":"2026-09-04T09:33:00+05:30"}
    events=[]
    pipeline=DecisionPipeline({agent:{"version":1,policy_field:policy_value or context}},events.append)
    assert pipeline.plan_candidate(candidate,"NIFTY") is None
    assert events[-1]["agent"]==agent and events[-1]["status"]=="REJECTED"
    assert not any(e["status"]=="PASS" for e in events if e["agent"]==agent)


def test_baseline_preserves_contexts_for_all_contributing_agents():
    candidate={"setup":"ORB_RETEST_CALL", "break_timestamp":"2026-09-04T09:32:00+05:30",
               "retest_timestamp":"2026-09-04T09:33:00+05:30"}
    events=[]
    signal=DecisionPipeline(publish=events.append).plan_candidate(candidate,"NIFTY")
    assert signal["agent_contexts"]=={e["agent"]:e["context"] for e in events}
    assert set(signal["agent_contexts"])=={"Scanner","Regime","Confirmation","Setup"}
    assert not signal["execution_ready"]


def test_backtest_runs():
    ts=pd.date_range("2026-01-05 09:15",periods=500,freq="min")
    c=pd.Series([25000+i for i in range(500)],dtype=float)
    df=pd.DataFrame({"timestamp":ts,"open":c,"high":c+2,"low":c-2,"close":c,"volume":100000})
    result=BacktestEngine().run(df)
    assert result["quality"]=="incomplete"
    assert result["metrics"]["total_pnl"] is None


def test_every_backtest_run_records_learning_for_every_agent(tmp_path):
    store = Store(tmp_path / "audit.db")
    trades = [{"entry_ts": "2026-01-01T09:30:00", "exit_ts": "2026-01-01T10:00:00",
               "pnl": -100, "regime": "TREND_DOWN", "setup": "VWAP_SHORT", "option_mode": "Offset -1"}]
    learn_from_outcomes(trades, "test", store, "run-one")
    learn_from_outcomes(trades, "test", store, "run-two")
    history = store.learning_snapshot()["history"]
    for run_id in ("run-one", "run-two"):
        recorded_agents = {item["agent"] for item in history if item["run_id"] == run_id}
        assert recorded_agents == set(AGENT_ORDER)


def test_learning_only_attributes_outcomes_to_agents_with_context(tmp_path):
    store = Store(tmp_path / "agent-attribution.db")
    trade = {"pnl": -100, "agent_contexts": {"Setup": "ORB_SHORT"}}
    learn_from_outcomes([trade], "test", store, "context-only")
    entries = {item["agent"]: item for item in store.get_record("learning_runs", "context-only")["entries"]}
    assert entries["Setup"]["sample_count"] == 1
    assert entries["Setup"]["pnl"] == -100
    assert entries["Risk"]["sample_count"] == 0
    assert entries["Risk"]["pnl"] == 0


def test_research_learning_records_gross_outcomes_without_promoting(tmp_path):
    store = Store(tmp_path / "research-attribution.db")
    trade = {"pnl": None, "gross_pnl": -25, "agent_contexts": {"Setup": "ORB_SHORT"}}
    learn_from_outcomes([trade], "dhan", store, "research-context", quality="research")
    entries = {item["agent"]: item for item in store.get_record("learning_runs", "research-context")["entries"]}
    assert entries["Setup"]["sample_count"] == 1
    assert entries["Setup"]["pnl"] == -25
    assert entries["Setup"]["validation_status"] == "DATA_BLOCKED"
    assert entries["Risk"]["sample_count"] == 0


def test_plan_role_coverage_exposes_unavailable_evidence_without_fake_activity():
    roles = plan_agent_capabilities()
    names = {role["agent"] for role in roles}
    assert {"Data Integrity", "Calendar and Event", "Greeks and Volatility", "Learning and Validation"} <= names
    assert next(role for role in roles if role["agent"] == "Calendar and Event")["status"] == "DATA_BLOCKED"
    assert all(role["evidence"] and role["limitation"] for role in roles)


def historical_fixture(symbols=("NIFTY",)):
    """Contract fixtures only for regression tests, never runtime market data."""
    fees={"source":"unit_test_schedule","valid_from":"2026-01-01","valid_to":"2026-12-31",
          "brokerage":20,"gst_rate":0,"buy":{k:0 for k in ("exchange","stt","sebi","ipft","stamp_duty")},
          "sell":{k:0 for k in ("exchange","stt","sebi","ipft","stamp_duty")},
          "rounding":{k:2 for k in ("exchange","stt","sebi","ipft","stamp_duty","gst")}}
    rows=[]
    for ts in pd.date_range("2026-09-04 09:15","2026-09-04 15:10",freq="min",tz="Asia/Kolkata"):
        for symbol in symbols:
            q={"contract_id":"fixed:"+symbol,"symbol":symbol,"identity_verified":True,"expiry":"2026-09-10",
               "strike":25000,"lot_size":10,"tick_size":.05,"option_type":"CALL","is_atm":False,
               "open":40.,"high":41.,"low":39.,"close":40.,"oi":1000,"volume":1000,"charge_schedule":deepcopy(fees)}
            rows.append({"timestamp":ts,"symbol":symbol,"open":24000.,"high":24002.,"low":23998.,"close":24000.,"volume":0,"option_quotes":[q]})
    return pd.DataFrame(rows)


def test_plan_replay_structural_protection_and_one_position():
    from app.risk import PlanRiskPolicy
    from app.pipeline import plan_exit
    frame=historical_fixture(("NIFTY","SENSEX"))
    for symbol in ("NIFTY","SENSEX"):
        indices=frame.index[frame.symbol==symbol]
        frame.loc[indices[17], ["open","high","low","close"]]=[24000,24006,24000,24005]
        frame.loc[indices[18], ["open","high","low","close"]]=[24005,24005,24002,24004]
        frame.loc[indices[19], ["open","high","low","close"]]=[24004,24008,24004,24007]
        frame.loc[indices[20:], ["open","high","low","close"]]=[24007,24008,24006,24007]
    result=BacktestEngine(BacktestConfig(plan_policy=PlanRiskPolicy(),max_positions=1)).run(frame)
    assert result["quality"]=="verified"
    assert len(result["trades"])==1
    trade=result["trades"][0]
    assert trade["entry_ts"].strftime("%H:%M")=="09:35"
    assert trade["stop"]==38.95
    assert trade["qty"]==10
    assert trade["reason"]=="TIME_EXIT"
    assert trade["holding_minutes"]==10
    assert result["loss_ledger"]["entries"]==1
    assert result["loss_ledger"]["loss_spend"]==pytest.approx(-trade["pnl"])
    assert result["deployment_ready"] is False
    assert plan_exit(trade,trade["exit_ts"],bid=40,underlying=24007)==trade["reason"]
    report=report_from_run(result,{"capital":30000})
    assert report["strategy_version"]=="orb-retest-v1"
    assert report["opportunities"]


def test_plan_protection_rejects_wrong_contract_and_does_not_shrink_stop():
    from app.pipeline import plan_protection
    q=historical_fixture().iloc[0].option_quotes[0]
    signal={"retest_timestamp":"2026-09-04T09:33:00+05:30"}
    protected=plan_protection(signal,q,q,40.05)
    assert protected["stop_price"]==38.95
    assert protected["target_price"]==42.25
    with pytest.raises(ValueError,match="unavailable"):
        plan_protection(signal,q,{**q,"contract_id":"wrong"},40.05)
    with pytest.raises(ValueError,match="not below"):
        plan_protection(signal,q,q,30.)


@pytest.fixture
def once_per_session(monkeypatch):
    def signal(self,row,*args):
        if row["timestamp"].strftime("%H:%M")!="09:30": return None
        return {"symbol":row["symbol"],"timestamp":row["timestamp"].isoformat(),"option_type":"CALL",
                "setup":"TEST_ONLY","regime":"TREND_UP","stop_percent":.1,"target_percent":.2,
                "agent_contexts":{a:"test" for a in AGENT_ORDER[:4]},"policy_versions":{}}
    monkeypatch.setattr(DecisionPipeline,"signal",signal)


def test_next_bar_open_and_entry_bar_stop(once_per_session):
    frame=historical_fixture(); q=frame.iloc[16].option_quotes[0]
    q.update(open=44.,high=45.,low=30.,close=40.)
    result=BacktestEngine().run(frame)
    assert result["quality"]=="verified"
    trade=result["trades"][0]
    assert trade["entry"]==44.05
    assert trade["entry_ts"].strftime("%H:%M")=="09:31"
    assert trade["exit_ts"]==trade["entry_ts"] and trade["reason"]=="STOP"
    assert trade["costs"]==40


def test_fixed_contract_drift_blocks_headline_pnl(once_per_session):
    frame=historical_fixture()
    frame.iloc[16].option_quotes[0]["strike"]=25100
    result=BacktestEngine().run(frame)
    assert result["quality"]=="incomplete" and result["metrics"]["total_pnl"] is None
    assert any("identity changed" in e for e in result["issues"])


def test_shared_portfolio_cannot_double_spend(once_per_session):
    result=BacktestEngine(BacktestConfig(initial_capital=1000)).run(historical_fixture(("NIFTY","SENSEX")))
    assert len(result["trades"])==1
    assert result["trades"][0]["reason"]=="SESSION_EXIT"
    assert min(result["equity"])>=0
    assert result["daily"][0]["pnl"]==pytest.approx(result["metrics"]["total_pnl"])


def test_unresolved_exit_is_not_dropped(once_per_session):
    frame=historical_fixture()
    for index in frame.index[frame.timestamp.dt.strftime("%H:%M") >= "15:05"]:
        frame.at[index,"option_quotes"]=[]
    result=BacktestEngine().run(frame)
    assert result["quality"]=="incomplete" and len(result["unresolved"])==1
    assert result["metrics"]["total_pnl"] is None


def test_profit_factor_finite_json_and_setup_attribution():
    m=metrics([{"pnl":5,"costs":1}],pd.Series([100,105]))
    assert m["profit_factor"] is None and m["profit_factor_status"]=="NO_LOSSES"
    result={"quality":"verified","metrics":m,"trades":[{"pnl":5,"setup":"A","regime":"UP","agent_contexts":{}}]}
    report=report_from_run(result,{"capital":100})
    assert report["attribution"]["setups"][0]["name"]=="A"
    json.dumps(report,allow_nan=False)


def test_indicators_do_not_invent_index_volume():
    frame=historical_fixture().drop(columns="option_quotes")
    result=add_features(frame)
    assert result.vwap.isna().all() and result.relative_volume.isna().all()
    assert rsi(pd.Series(range(30),dtype=float)).iloc[-1]==100


def test_vwap_resets_each_session():
    df=pd.DataFrame({"timestamp":pd.to_datetime(["2026-09-03 15:00","2026-09-04 09:15"]),
                     "open":[100,200],"high":[100,200],"low":[100,200],"close":[100,200],"volume":[10,10]})
    assert add_features(df).vwap.tolist()==[100,200]


def test_learning_is_idempotent_and_unverified_data_cannot_promote(tmp_path):
    store=Store(tmp_path/"learning.db")
    trade={"pnl":-100,"agent_contexts":{a:"bad" for a in AGENT_ORDER}}
    learn_from_outcomes([trade]*100,"test",store,"same-run")
    learn_from_outcomes([trade]*100,"test",store,"same-run")
    assert len(store.learning_snapshot()["history"])==8
    assert not store.active_learning_policies()
    assert all(e["validation_status"]=="DATA_BLOCKED" for e in store.learning_snapshot()["history"])


def test_reused_holdout_never_replays_or_promotes(tmp_path):
    store=Store(tmp_path/"learning.db")
    windows={"train_from":"2026-01-01","train_to":"2026-03-01","validation_from":"2026-03-02",
             "validation_to":"2026-04-01","test_from":"2026-04-02","test_to":"2026-05-01"}
    store.put_record("learning_datasets","old",windows)
    def forbidden(*args): raise AssertionError("Holdout was reused")
    learn_from_outcomes([],"test",store,"repeat",quality="verified",replay=forbidden,windows=windows)
    assert all(e["validation_status"]=="REUSED_HOLDOUT" for e in store.learning_snapshot()["history"])


def test_ev_policy_applies_to_cold_start_observations():
    pipeline=DecisionPipeline({"EV":{"version":1,"blocked_value":"uncalibrated"}})
    assert not pipeline.stage("EV","NIFTY","OBSERVATION","Test","uncalibrated")


def test_full_validation_promotes_at_most_one_and_records_both_windows(tmp_path):
    from app.session import now_ist
    from datetime import timedelta
    store=Store(tmp_path/"learning.db"); calls=[]
    windows={"train_from":"2025-01-01","train_to":"2025-03-01","validation_from":"2025-03-02",
             "validation_to":"2025-04-01","test_from":"2025-04-02","test_to":"2025-05-01"}
    training=[{"pnl":-1,"agent_contexts":{a:"bad" for a in AGENT_ORDER}} for _ in range(60)]
    def replay(policies,start,end):
        calls.append((dict(policies),start,end))
        if start==windows["train_from"]: return {"quality":"verified","trades":training}
        improved=bool(policies)
        return {"quality":"verified","metrics":{"trades":35 if improved else 40,"total_pnl":1000 if improved else 0,
            "expectancy":1000/35 if improved else 0,"max_drawdown":-5 if improved else -10},
            "daily":[{"date":f"day-{i}","pnl":100 if improved else 0} for i in range(10)]}
    learn_from_outcomes(training,"test",store,"validated",quality="verified",replay=replay,dataset_id="same-file",windows=windows)
    entries=store.get_record("learning_runs","validated")["entries"]
    assert sum(e["validation_status"]=="AWAITING_REVIEW" for e in entries)==1
    assert all(len(e["metadata"]["evidence"])==2 for e in entries)
    assert sum(start==windows["train_from"] for _,start,_ in calls)==1
    selected=next(e["agent"] for e in entries if e["validation_status"]=="AWAITING_REVIEW")
    policy=store.get_record("learning_candidates","validated:"+selected)
    assert policy["effective_from"] is None and policy["validation_status"]=="AWAITING_REVIEW"
    assert not store.active_learning_policies()
    assert store.get_record("learning_datasets","validated")["dataset_id"]=="same-file"


def test_negative_expectancy_and_different_session_coverage_rejected():
    from app.telemetry.agent_metrics import _passes
    b={"quality":"verified","metrics":{"trades":40,"total_pnl":-100,"expectancy":-2.5,"max_drawdown":-200},
       "daily":[{"date":str(i),"pnl":-10} for i in range(10)]}
    c={"quality":"verified","metrics":{"trades":35,"total_pnl":-10,"expectancy":-10/35,"max_drawdown":-100},
       "daily":[{"date":str(i),"pnl":-1} for i in range(10)]}
    assert not _passes(b,c,30,10)[0]
    c["daily"]=c["daily"][:-1]
    assert "coverage" in _passes(b,c,30,10)[1]


def test_cancel_before_learning_commit_leaves_no_policy_or_ledger(tmp_path):
    store=Store(tmp_path/"learning.db")
    def cancel(): raise InterruptedError("Cancelled")
    with pytest.raises(InterruptedError):
        learn_from_outcomes([],"test",store,"cancelled",before_commit=cancel)
    assert not store.learning_snapshot()["history"]
    assert not store.list_records("learning_runs")


def test_focus_policy_filters_context_without_overriding_rejections():
    from app.pipeline import DecisionPipeline
    pipeline=DecisionPipeline({"Setup":{"version":1,"allowed_value":"supported"}})
    assert pipeline.stage("Setup","NIFTY","PASS","valid","supported")
    assert not pipeline.stage("Setup","NIFTY","PASS","valid","other")
    assert not pipeline.stage("Setup","NIFTY","REJECTED","entry invalid","supported")


def test_profitable_context_requires_independent_improvement_not_just_winners(tmp_path):
    store=Store(tmp_path/"learning.db"); calls=[]
    windows={"train_from":"2025-01-01","train_to":"2025-03-01","validation_from":"2025-03-02",
             "validation_to":"2025-04-01","test_from":"2025-04-02","test_to":"2025-05-01"}
    training=[{"pnl":1,"agent_contexts":{"Setup":"profitable"}} for _ in range(60)]
    def replay(policies,start,end):
        calls.append(policies)
        if start==windows["train_from"]: return {"quality":"verified","trades":training}
        return {"quality":"verified","metrics":{"trades":40,"total_pnl":100,"expectancy":2.5,"max_drawdown":-10},
                "daily":[{"date":str(i),"pnl":10} for i in range(10)]}
    learn_from_outcomes(training,"test",store,"focus",quality="verified",replay=replay,windows=windows)
    assert any(p.get("Setup",{}).get("allowed_value")=="profitable" for p in calls)
    entry=next(e for e in store.get_record("learning_runs","focus")["entries"] if e["agent"]=="Setup")
    assert entry["validation_status"]=="REJECTED"
    assert not store.active_learning_policies()


def test_paper_lessons_accumulate_closed_episodes_without_future_or_duplicate_trades(tmp_path):
    store=Store(tmp_path/"learning.db")
    old={"id":"old","exit_ts":"2026-01-01T10:00:00+05:30","pnl":-10,"agent_contexts":{"Setup":"pullback"}}
    current={**old,"id":"current","exit_ts":"2026-01-02T10:00:00+05:30","pnl":20}
    future={**old,"id":"future","exit_ts":"2026-01-03T10:00:00+05:30","pnl":1000}
    changed={**old,"id":"changed","policy_versions":{"Setup":1},"pnl":1000}
    for trade in (old,current,future,changed): store.put_record("episodes",trade["id"],trade)
    learn_from_outcomes([current],"paper",store,"paper:current",quality="verified")
    learn_from_outcomes([current],"paper",store,"paper:current",quality="verified")
    entry=next(e for e in store.get_record("learning_runs","paper:current")["entries"] if e["agent"]=="Setup")
    lesson=entry["metadata"]["lessons"][0]
    assert lesson["samples"]==2 and lesson["pnl"]==10
    assert lesson["action"]=="COLLECT_EVIDENCE"
    assert entry["sample_count"]==1 and len(store.list_records("learning_runs"))==1
