"""Synthetic fixtures stay in temporary databases; never loaded into the paper account."""
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
import pandas as pd
import pytest
from app.strategy_portfolio import STRATEGIES,PORTFOLIO_VERSION,evaluate_strategies,rank_opportunities,signal_for
from app.portfolio_engine import MultiStrategyPaperEngine
from app.config import Settings
from app.session import session_state
from app.pipeline import plan_exit
from app.expectancy import ExpectancyEngine
from tests.test_paper import plan_account,contract,quote


def frame_fixture():
    return pd.DataFrame({"timestamp":pd.date_range("2026-09-04 09:15",periods=50,freq="min",tz="Asia/Kolkata"),
        "open":105.,"high":110.,"low":100.,"close":105.,"volume":float("nan"),
        "ema9":105.,"ema21":105.,"adx":15.,"atr":2.})


@pytest.mark.parametrize("side",["CALL","PUT"])
def test_trend_pullback_is_directional_and_requires_confirmation(monkeypatch,side):
    f=frame_fixture()
    f.loc[:,["open","high","low","close"]]=[102,103,101,102]
    f["adx"]=30.;f["atr"]=1.;f["ema21"]=101.5;f["ema9"]=102.5
    f.loc[48,["open","high","low","close","ema21"]]=[102,103,101.75,102.7,101.7]
    f.loc[49,["open","high","low","close","ema21"]]=[103,103.4,102.7,103.2,102]
    if side=="PUT":
        old=f.copy()
        for k in ("open","close","ema9","ema21"): f[k]=210-old[k]
        f["high"]=210-old.low;f["low"]=210-old.high
    monkeypatch.setattr("app.strategy_portfolio.add_features",lambda x:x)
    now=f.timestamp.iloc[-1]+pd.Timedelta(minutes=1)
    signals,rows=evaluate_strategies(f,now,"NIFTY")
    trend=next(s for s in signals if s["strategy_id"]=="trend_pullback")
    assert trend["option_type"]==side and trend["horizon_minutes"]==10
    f.loc[49,"close"]=f.loc[48,"close"]
    assert not any(s["strategy_id"]=="trend_pullback" for s in evaluate_strategies(f,now,"NIFTY")[0])


@pytest.mark.parametrize("side",["CALL","PUT"])
def test_range_rejection_targets_prior_midpoint_and_is_disabled_in_trend(monkeypatch,side):
    f=frame_fixture()
    f.loc[48,["open","high","low","close"]]=[100.5,101.2,100.1,100.8]
    f.loc[49,["open","high","low","close"]]=[100.9,101.6,100.7,101.4]
    if side=="PUT":
        old=f.copy()
        for k in ("open","close"): f[k]=210-old[k]
        f["high"]=210-old.low;f["low"]=210-old.high
    monkeypatch.setattr("app.strategy_portfolio.add_features",lambda x:x)
    now=f.timestamp.iloc[-1]+pd.Timedelta(minutes=1)
    signals,_=evaluate_strategies(f,now,"SENSEX")
    s=next(s for s in signals if s["strategy_id"]=="range_rejection")
    assert s["option_type"]==side and s["underlying_target"]==105 and s["horizon_minutes"]==5
    f["adx"]=30
    assert not any(s["strategy_id"]=="range_rejection" for s in evaluate_strategies(f,now,"SENSEX")[0])


def test_orb_remains_in_portfolio_with_real_feature_pipeline():
    f=frame_fixture().iloc[:20].copy()
    f.loc[:,["open","high","low","close"]]=[100,101,99,100]
    f.loc[17,["open","high","low","close"]]=[100,103,100,102]
    f.loc[18,["open","high","low","close"]]=[102,102.5,101,102]
    f.loc[19,["open","high","low","close"]]=[102,104,102,103]
    signals,_=evaluate_strategies(f,f.timestamp.iloc[-1]+pd.Timedelta(minutes=1),"NIFTY")
    assert any(s["strategy_id"]=="orb_retest" and s["option_type"]=="CALL" for s in signals)


def test_future_rows_cannot_change_features_signals_or_ids():
    f=frame_fixture();now=f.timestamp.iloc[-1]+pd.Timedelta(minutes=1)
    before=evaluate_strategies(f,now,"NIFTY")
    future=f.iloc[[-1]].copy();future["timestamp"]=now+pd.Timedelta(minutes=1)
    future.loc[:,["open","high","low","close"]]=[1,999999,1,999999]
    assert evaluate_strategies(pd.concat([f,future]),now,"NIFTY")==before


@pytest.mark.parametrize("defect",["gap","duplicate","stale","invalid"])
def test_data_defects_block_every_strategy(defect):
    f=frame_fixture();now=f.timestamp.iloc[-1]+pd.Timedelta(minutes=1)
    if defect=="gap": f=f.drop(index=10)
    if defect=="duplicate": f=pd.concat([f,f.iloc[[10]]])
    if defect=="stale": now+=pd.Timedelta(minutes=3)
    if defect=="invalid": f.loc[30,"low"]=999
    signals,rows=evaluate_strategies(f,now,"NIFTY")
    assert not signals and all(r["status"]=="WAITING" for r in rows)


def portfolio_account(tmp_path,monkeypatch):
    broker,store,clock=plan_account(tmp_path)
    clock["now"]=clock["now"].replace(hour=10,minute=5)
    gateway=SimpleNamespace(credential_generation=0)
    engine=MultiStrategyPaperEngine(Settings(_env_file=None),store,gateway,broker)
    monkeypatch.setattr("app.portfolio_engine.now_ist",lambda:clock["now"])
    monkeypatch.setattr("app.paper_engine.now_ist",lambda:clock["now"])
    monkeypatch.setattr(engine,"_session",lambda:session_state(clock["now"]))
    engine._freeze_policies(clock["now"])
    return engine,broker,store,clock


def candidate(clock,symbol="NIFTY",strategy=1):
    stamp=clock["now"]-timedelta(minutes=1)
    c={"timestamp":stamp.isoformat(),"available_at":clock["now"].isoformat(),"retest_timestamp":(stamp-timedelta(minutes=1)).isoformat(),
       "option_type":"CALL","setup":"TEST_ONLY_"+STRATEGIES[strategy]["id"],"invalidation":24000}
    return signal_for(c,STRATEGIES[strategy],symbol,"TREND_UP")


def executable(clock,symbol="NIFTY",bid=99,low=90):
    c={**quote(contract(symbol),clock,bid=bid),"oi":1000,"volume":1000,"spread_pct":(100-bid)/100,"option_context":"test"}
    return c,{**contract(symbol),"open":95.,"high":99.,"low":low,"close":96.}


def test_exact_selected_contract_is_queued_and_missing_candle_retries(tmp_path,monkeypatch):
    e,b,store,clock=portfolio_account(tmp_path,monkeypatch)
    s=candidate(clock);c,_=executable(clock)
    candle,reason=e._request_protection(s,c)
    key=(s["id"],c["contract_id"])
    assert candle is None and key in e.protection_requests
    calls=[]
    def fetch(contract,start,end):
        calls.append((contract["contract_id"],start,end))
        return pd.DataFrame({"timestamp":pd.to_datetime([])})
    e.gateway.contract_candles=fetch
    e.prepare_protection(key,e.protection_requests[key])
    assert calls[0][0]==c["contract_id"]
    assert pd.Timestamp(calls[0][2])-pd.Timestamp(calls[0][1])==pd.Timedelta(days=1)
    assert not e.protection_results[key]["candle"]
    e.protection_results[key]["retry_after"]=0
    good={"timestamp":pd.Timestamp(s["retest_timestamp"]),"open":95.,"high":99.,"low":90.,"close":96.}
    e.gateway.contract_candles=lambda *args:pd.DataFrame([good])
    e._request_protection(s,c);e.prepare_protection(key,e.protection_requests[key])
    result,reason=e._request_protection(s,c)
    assert result["contract_id"]==c["contract_id"] and result["low"]==90 and reason is None


def test_old_generation_protection_is_discarded(tmp_path,monkeypatch):
    e,b,store,clock=portfolio_account(tmp_path,monkeypatch);s=candidate(clock);c,_=executable(clock)
    e._request_protection(s,c);key=(s["id"],c["contract_id"]);request=e.protection_requests[key]
    def fetch(*args):
        e.gateway.credential_generation=1
        return pd.DataFrame([{"timestamp":pd.Timestamp(s["retest_timestamp"]),"open":95.,"high":99.,"low":90.,"close":96.}])
    e.gateway.contract_candles=fetch;e.prepare_protection(key,request)
    assert key not in e.protection_results


def test_global_selector_chooses_one_offer_and_records_strategy_exit(tmp_path,monkeypatch):
    e,b,store,clock=portfolio_account(tmp_path,monkeypatch)
    offers=[]
    for symbol,bid in (("NIFTY",98),("SENSEX",99)):
        s=candidate(clock,symbol);c,candle=executable(clock,symbol,bid=bid)
        e.protection_results[(s["id"],c["contract_id"])]=dict(candle=candle,generation=0)
        offer,reason=e._prepare_offer(s,c,b.snapshot(),[],clock["now"])
        assert reason is None and offer["ev"]["status"]=="OBSERVATION"
        offers.append(offer);e.quotes[c["contract_id"]]=c
    ranked=rank_opportunities(offers)
    assert ranked[0]["signal"]["symbol"]=="SENSEX"
    assert e._execute_offer(ranked[0])
    assert not e._execute_offer(ranked[1])
    assert b.snapshot()["open_positions"]==1
    p=b.snapshot()["positions"][0]
    assert p["strategy_id"]=="trend_pullback" and p["portfolio_version"]==PORTFOLIO_VERSION
    clock["now"]+=timedelta(minutes=10)
    e.quotes={p["contract_id"]:quote(contract("SENSEX"),clock,bid=110)}
    e.cycle()
    assert b.snapshot()["open_positions"]==0
    stats=e.describe_strategies()["performance"]
    assert next(s for s in stats if s["id"]=="trend_pullback")["closed_trades"]==1
    assert store.list_records("episodes")[0]["reason"]=="TIME_EXIT"


@pytest.mark.parametrize("change",["stale","price","generation","cutoff"])
def test_ranked_offer_is_revalidated_before_fill(tmp_path,monkeypatch,change):
    e,b,store,clock=portfolio_account(tmp_path,monkeypatch);s=candidate(clock);c,candle=executable(clock)
    e.protection_results[(s["id"],c["contract_id"])]=dict(candle=candle,generation=0)
    offer,_=e._prepare_offer(s,c,b.snapshot(),[],clock["now"]);e.quotes[c["contract_id"]]=dict(c)
    if change=="stale": clock["now"]+=timedelta(seconds=3)
    if change=="price": e.quotes[c["contract_id"]]["ask"]+=1
    if change=="generation": e.gateway.credential_generation=1
    if change=="cutoff": clock["now"]=clock["now"].replace(hour=14,minute=30)
    assert not e._execute_offer(offer) and b.snapshot()["open_positions"]==0


def test_supported_negative_evidence_is_not_overridden(tmp_path,monkeypatch):
    e,b,store,clock=portfolio_account(tmp_path,monkeypatch);s=candidate(clock);c,candle=executable(clock)
    e.protection_results[(s["id"],c["contract_id"])]=dict(candle=candle,generation=0)
    monkeypatch.setattr(ExpectancyEngine,"evaluate_net",lambda *a:{"status":"REJECTED","reason":"Net edge is not supported"})
    offer,reason=e._prepare_offer(s,c,b.snapshot(),[],clock["now"])
    assert offer is None and reason=="Net edge is not supported"


def test_range_target_exit_and_old_session_models_remain_distinct(tmp_path,monkeypatch):
    e,b,store,clock=portfolio_account(tmp_path,monkeypatch)
    p={"stop":90,"target":120,"option_type":"CALL","invalidation":99,"underlying_target":105}
    assert plan_exit(p,clock["now"],bid=100,underlying=105)=="UNDERLYING_TARGET"
    assert store.get_record("session_models",str(clock["now"].date())+":"+PORTFOLIO_VERSION)["strategy_version"]==PORTFOLIO_VERSION


def test_session_close_reports_all_six_evaluations_without_network(tmp_path,monkeypatch):
    e,b,store,clock=portfolio_account(tmp_path,monkeypatch)
    clock["now"]=clock["now"].replace(hour=15,minute=5)
    e.portfolio_cycle()
    assert len(e.status["portfolio"]["evaluations"])==6
    assert e.status["portfolio"]["reason"]=="EXIT_ONLY"


def test_full_selector_waits_for_exact_protection_then_selects_shared_account(tmp_path,monkeypatch):
    e,b,store,clock=portfolio_account(tmp_path,monkeypatch)
    e.frames={s:frame_fixture() for s in ("NIFTY","SENSEX")}
    def signals(frame,now,symbol):
        s=candidate(clock,symbol)
        return [s],[{**STRATEGIES[1],"symbol":symbol,"status":"CANDIDATE","reason":"Fixture confirmation","last_bar":s["timestamp"]}]
    monkeypatch.setattr("app.portfolio_engine.evaluate_strategies",signals)
    for symbol,bid in (("NIFTY",98),("SENSEX",99)):
        c,_=executable(clock,symbol,bid=bid);e.quotes[c["contract_id"]]=c
    e.portfolio_cycle()
    assert b.snapshot()["open_positions"]==0 and len(e.protection_requests)==2
    e.gateway.contract_candles=lambda *args:pd.DataFrame([{"timestamp":pd.Timestamp(candidate(clock)["retest_timestamp"]),
        "open":95.,"high":99.,"low":90.,"close":96.}])
    for key,request in list(e.protection_requests.items()): e.prepare_protection(key,request)
    e.portfolio_cycle()
    assert b.snapshot()["open_positions"]==1
    assert b.snapshot()["positions"][0]["symbol"]=="SENSEX"
    assert len(store.list_records("strategy_selections"))==1
    assert any(o["status"]=="SELECTED" for o in store.list_records("strategy_opportunities"))


def test_selector_cost_requests_do_not_run_on_exit_heartbeat(tmp_path,monkeypatch):
    e,b,store,clock=portfolio_account(tmp_path,monkeypatch)
    e.frames={"NIFTY":frame_fixture()}
    def forbidden(*args): raise AssertionError("Network/fee work on exit heartbeat")
    monkeypatch.setattr(e,"portfolio_cycle",forbidden)
    monkeypatch.setattr(b.cost,"quote",forbidden)
    e.cycle()
    assert e.entry_wakeup.is_set() and e.status["state"]=="RUNNING"
