"""Isolated evidence fixtures on E:; never imported by the running paper account."""
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
import threading
import pandas as pd
import pytest

from app.autonomous_policy import VERSION, evaluate_market, plan_candidate, management_decision, strategy_order
from app.autonomous_paper import AutonomousPaperEngine
from app.paper_engine import PaperEngine
from app.portfolio_engine import MultiStrategyPaperEngine
from app.paper_learning import PaperResearchLearning, eligibility, COLUMNS, RESEARCH_VERSION
from app.ai import MLTradeQualityModel, SCHEMA
from app.config import Settings
from tests.test_paper import plan_account, contract, quote, enter
from tests.test_simple_paper import downtrend_frame


def setup_engine(tmp_path, monkeypatch):
    broker, store, clock = plan_account(tmp_path)
    clock["now"] += timedelta(minutes=5)
    monkeypatch.setattr("app.strategy_portfolio.add_features", lambda f: f)
    frame = downtrend_frame(clock)
    frame.loc[49, "ema21"] = 24013.
    c = {**contract(), "option_type": "PUT", "strike": 24000., "oi": 1000., "volume": 1000.,
         "security_id": "12345", "exchange": "NSE",
         "delta": -.5, "greeks_observed_at": clock["now"].isoformat(), "metadata_source": "isolated_fixture",
         "strike_universe": [23800., 23850., 23900., 23950., 24000., 24050., 24100.], "is_atm": True}
    q = {**c, **quote(c, clock), "bid": 100., "ask": 100.05, "bid_qty": 1000, "ask_qty": 1000,
         "quote_update_timestamp": clock["now"].isoformat(), "observation_id": "isolated-entry"}
    under = {"ltp": 23990., "quote_update_timestamp": clock["now"].isoformat(), "source": "dhan_market_feed"}
    market = SimpleNamespace(execution_snapshot=lambda s: {"underlying": under if s == "NIFTY" else {},
                                 "options": {c["contract_id"]: q} if s == "NIFTY" else {}},
                             executable_quotes=lambda: {c["contract_id"]: q}, snapshot=lambda: {"symbols": {"NIFTY": under}}, recorder=None)
    gateway = SimpleNamespace(credential_generation=0, credential_provider=None)
    engine = AutonomousPaperEngine(Settings(_env_file=None, paper_strategy_mode="autonomous"), store, gateway, broker, market, clock=lambda: clock["now"])
    engine.frames["NIFTY"] = frame
    engine.status["market_structure"]["NIFTY"] = {"status": "OBSERVED", "as_of": clock["now"].isoformat(), "zones": [], "sweeps": []}
    engine.status["market_context"]["NIFTY"] = {"captured_at": clock["now"].isoformat(), "credential_generation": 0, "session_exit": "15:05",
        "positioning": {"status": "OBSERVED", "scope": "FULL_RETURNED_FIXED_CONTRACT_CHAIN", "observed_at": clock["now"].isoformat(), "pcr": 1., "call_oi": 1000., "put_oi": 1000.},
        "futures": {"status": "DATA_UNAVAILABLE"}, "volatility": {"status": "DATA_UNAVAILABLE"}}
    engine._request_protection = lambda s, k: ({**k, "low": 98., "option_atr": 2.}, None)
    return engine, broker, store, clock, q, under


def test_autonomous_downtrend_enters_and_exits_without_any_dhan_order(tmp_path, monkeypatch):
    engine, broker, store, clock, q, under = setup_engine(tmp_path, monkeypatch)
    engine.portfolio_cycle()
    state = broker.snapshot()
    assert state["open_positions"] == 1
    position = state["positions"][0]
    assert position["option_type"] == "PUT" and position["strategy_id"] == "trend_continuation"
    assert position["portfolio_version"] == VERSION and position["exit_policy"] == "adaptive_observed_v1"
    assert position["risk_rupees"] <= 650 and position["qty"]*position["entry"] < 24000
    assert position["qty"] % position["lot_size"] == 0
    assert position["entry_features"]["paper_policy_version"] == VERSION
    engine.portfolio_cycle()
    assert broker.snapshot()["open_positions"] == 1
    clock["now"] += timedelta(seconds=2)
    q.update(bid=position["stop"]-.05, observation_id="isolated-exit", timestamp=clock["now"].isoformat(), quote_update_timestamp=clock["now"].isoformat())
    engine._protect_once()
    assert broker.snapshot()["open_positions"] == 0
    episode = store.list_records("episodes")[0]
    assert episode["reason"] == "STOP" and episode["mae"] <= episode["pnl"] < 0
    assert episode["entry_quote_observation_id"] == "isolated-entry" and episode["exit_quote_observation_id"] == "isolated-exit"
    assert not eligibility(episode)
    learned = engine.learning.train(clock["now"])
    assert learned["status"] == "INSUFFICIENT_EVIDENCE" and learned["eligible_outcomes"] == 1
    assert len(store.list_records("paper_investigations")) == 1


def test_autonomous_continuation_uses_declared_greek_freshness_policy(tmp_path,monkeypatch):
    from app.option_screen import describe
    engine,broker,_,clock,q,_=setup_engine(tmp_path,monkeypatch)
    q['greeks_observed_at']=(clock['now']-timedelta(seconds=60)).isoformat()
    signals,_=engine.evaluate_market(engine.frames['NIFTY'],clock['now'],'NIFTY',engine.status['market_structure']['NIFTY'])
    assert next(s for s in signals if s['strategy_id']=='trend_continuation')['max_greeks_age_seconds']==describe()['max_greek_age_seconds']
    engine.portfolio_cycle()
    assert broker.snapshot()['open_positions']==1


def test_autonomous_stale_greeks_still_cannot_enter(tmp_path,monkeypatch):
    engine,broker,_,clock,q,_=setup_engine(tmp_path,monkeypatch)
    q['greeks_observed_at']=(clock['now']-timedelta(seconds=121)).isoformat()
    engine.portfolio_cycle()
    assert broker.snapshot()['open_positions']==0


def test_slow_fee_preparation_does_not_expire_final_paper_entry(tmp_path,monkeypatch):
    from app.expectancy import CostModel
    engine,broker,_,clock,q,under=setup_engine(tmp_path,monkeypatch)
    broker.cost=CostModel(paper=True)
    calls=[]
    def request(*args,**kwargs):
        assert not broker.cost.cache_only.get(), 'Final admission performed HTTP'
        calls.append(kwargs['json'])
        clock['now']+=timedelta(seconds=3)
        # Live feed continues publishing fresh books while fee preparation runs.
        q.update(timestamp=clock['now'].isoformat(),quote_update_timestamp=clock['now'].isoformat())
        under['quote_update_timestamp']=clock['now'].isoformat()
        data=kwargs['json']['data']
        turnover=(data['buy_price']+data['sell_price'])*data['qty']*q['lot_size']
        raw={'EXCHANGE_TURNOVER':turnover,'BROKERAGE':20.,'EXCHANGE_CHARGES':0.,'STT_CHARGES':0.,
             'SEBI_CHARGES':0.,'IPFT_CHARGES':0.,'STAMP_DUTY':0.,'GST_CHARGES':0.,'TOTAL_CHARGES_TAX':20.}
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'data':[raw]})
    monkeypatch.setattr('app.expectancy.requests.post',request)
    engine.portfolio_cycle()
    assert calls and broker.snapshot()['open_positions']==1
    position=broker.snapshot()['positions'][0]
    assert position['risk_rupees']<=650 and position['entry_charges']['estimated']
    before=len(calls)
    engine.portfolio_cycle()
    assert len(calls)==before and broker.snapshot()['open_positions']==1


def test_full_chain_context_is_mandatory_but_missing_advisory_news_is_not(tmp_path, monkeypatch):
    engine, broker, _, _, _, _ = setup_engine(tmp_path, monkeypatch)
    engine.status["market_context"]["NIFTY"]["positioning"]["scope"] = "ATM_PLUS_MINUS_5"
    engine.portfolio_cycle()
    assert broker.snapshot()["open_positions"] == 0
    assert "Whole-chain context" in engine.store.list_records("strategy_opportunities")[0]["reason"]


def test_autonomous_features_cannot_see_future_candles(tmp_path, monkeypatch):
    engine, _, _, clock, _, _ = setup_engine(tmp_path, monkeypatch)
    frame = engine.frames["NIFTY"]
    initial, _ = evaluate_market(frame, clock["now"], "NIFTY", engine.status["market_structure"]["NIFTY"])
    future = frame.tail(1).copy()
    future["timestamp"] = clock["now"]+timedelta(minutes=1)
    future["close"] = future["ema21"] = future["adx"] = 999999.
    later, _ = evaluate_market(pd.concat([frame, future]), clock["now"], "NIFTY", engine.status["market_structure"]["NIFTY"])
    assert [(s["id"], s["feature_row"]) for s in initial] == [(s["id"], s["feature_row"]) for s in later]


def test_strategy_order_changes_with_regime():
    assert strategy_order("TREND_DOWN")["trend_continuation"] < strategy_order("TREND_DOWN")["range_rejection"]
    assert strategy_order("RANGE")["range_rejection"] == 0


def test_current_completed_setup_cannot_be_kept_alive_after_invalidation(tmp_path, monkeypatch):
    engine, _, _, clock, _, _ = setup_engine(tmp_path, monkeypatch)
    signals, _ = engine.evaluate_market(engine.frames["NIFTY"], clock["now"], "NIFTY", engine.status["market_structure"]["NIFTY"])
    signal = signals[-1]
    engine.frames["NIFTY"].loc[49, "close"] = 24005.
    assert engine._current_signal(signal, clock["now"])[0] is None


@pytest.mark.parametrize('side',['CALL','PUT'])
def test_confirmed_setup_survives_next_candle_without_repeating_trigger(tmp_path,monkeypatch,side):
    engine,broker,_,clock,q,under=setup_engine(tmp_path,monkeypatch)
    frame=engine.frames['NIFTY']
    if side=='CALL':
        frame=frame.copy()
        frame[['open','close','ema9','ema21']]=48000-frame[['open','close','ema9','ema21']]
        high,low=48000-frame.low,48000-frame.high
        frame['high'],frame['low']=high,low
        engine.frames['NIFTY']=frame
        q.update(option_type='CALL',delta=.5)
    protection=engine._request_protection
    engine._request_protection=lambda *_:(None,"Waiting for the selected contract's completed protection candle")
    engine.portfolio_cycle()
    assert broker.snapshot()['open_positions']==0
    engine._request_protection=protection
    signal=next(s for s in engine.evaluate_market(frame,clock['now'],'NIFTY',engine.status['market_structure']['NIFTY'])[0]
                if s['strategy_id']=='trend_continuation')
    following=frame.tail(1).copy()
    following['timestamp']+=pd.Timedelta(minutes=1)
    values=[23990.,23996.,23989.,23993.,23999.,24012.]
    if side=='CALL': values=[48000-values[0],48000-values[2],48000-values[1],48000-values[3],48000-values[4],48000-values[5]]
    following[['open','high','low','close','ema9','ema21']]=values
    engine.frames['NIFTY']=pd.concat([frame,following],ignore_index=True)
    clock['now']+=timedelta(minutes=1)
    refreshed,reason=engine._current_signal(signal,clock['now'])
    assert reason is None and refreshed['id']==signal['id'] and refreshed['option_type']==side
    assert refreshed['feature_row']['timestamp']==following.iloc[0].timestamp.isoformat(sep=' ')
    assert engine._current_signal(signal,clock['now']+timedelta(seconds=66))[0] is None
    q.update(timestamp=clock['now'].isoformat(),quote_update_timestamp=clock['now'].isoformat())
    under.update(ltp=float(following.iloc[0].close),quote_update_timestamp=clock['now'].isoformat())
    engine.portfolio_cycle()
    assert broker.snapshot()['open_positions']==1
    assert broker.snapshot()['positions'][0]['option_type']==side
    engine.frames['NIFTY'].loc[50,'low' if side=='CALL' else 'high']=signal['invalidation']
    assert engine._current_signal(signal,clock['now'])[0] is None


def test_target_room_uses_confirmed_zone_and_does_not_shrink_stop_to_fit(tmp_path, monkeypatch):
    engine, _, _, clock, q, _ = setup_engine(tmp_path, monkeypatch)
    signal = engine.evaluate_market(engine.frames["NIFTY"], clock["now"], "NIFTY", engine.status["market_structure"]["NIFTY"])[0][-1]
    signal["market_structure"]["target_obstacle"] = {"timeframe": "1h", "lower": 23987., "upper": 23989., "distance_points": 1.}
    with pytest.raises(ValueError, match="target room"):
        plan_candidate(signal, q, {**q, "low": 98., "option_atr": 2.})


def test_day_low_cannot_override_completed_contract_protection_low(tmp_path, monkeypatch):
    engine, _, _, clock, q, _ = setup_engine(tmp_path, monkeypatch)
    signal = engine.evaluate_market(engine.frames["NIFTY"], clock["now"], "NIFTY", engine.status["market_structure"]["NIFTY"])[0][-1]
    q["low"] = 1.
    stamp = pd.Timestamp(signal["retest_timestamp"])
    bars = pd.DataFrame({"timestamp": pd.date_range(stamp-timedelta(minutes=20), periods=21, freq="min"), "open": 100., "high": 101., "low": 98., "close": 100.})
    engine.gateway.contract_candles = lambda *a: bars
    key = (signal["id"], q["contract_id"])
    engine.prepare_protection(key, {"signal": signal, "contract": q, "generation": 0})
    assert engine.protection_results[key]["candle"]["low"] == 98.


def test_entry_and_exit_fee_requests_do_not_block_ledger_lock(tmp_path):
    broker, _, clock = plan_account(tmp_path)
    class IndependentFees:
        def quote(self, contract, buy, sell, qty):
            available = threading.Event()
            worker = threading.Thread(target=lambda: (broker.snapshot(), available.set()))
            worker.start()
            worker.join(1)
            assert available.is_set(), "Fee request held the account lock"
            return {"total": 20., "brokerage": 20., "estimated": True}
    broker.cost = IndependentFees()
    c = contract()
    p = enter(broker, clock, c=c)
    q = quote(c, clock)
    clock["now"] += timedelta(seconds=1)
    q.update(timestamp=clock["now"].isoformat(), exchange_timestamp=clock["now"].isoformat())
    trade = broker.close(p["id"], q, "STOP", clock["now"])
    assert trade["costs_estimated"] and not trade["estimated_exit"]


def test_nominal_two_to_one_decimal_boundary_is_accepted(tmp_path):
    broker, _, clock = plan_account(tmp_path)
    c = contract()
    q = {**quote(c, clock), "ask": 474.55, "bid": 474.50}
    signal = {"id": "decimal-boundary", "setup": "fixture", "regime": "fixture", "risk_rupees": 650.,
              "agent_contexts": {}, "stop_price": 457.90, "target_price": 507.85}
    broker.place_order(contract=c, quote=q, quantity=c["lot_size"], signal=signal, now=clock["now"])
    assert broker.snapshot()["open_positions"] == 1


def test_preparation_worker_cannot_replace_independent_protective_loop():
    assert MultiStrategyPaperEngine._protection_loop is PaperEngine._protection_loop
    assert AutonomousPaperEngine._protection_loop is PaperEngine._protection_loop
    assert AutonomousPaperEngine._protect_once is PaperEngine._protect_once


def test_session_exit_intent_survives_missing_quotes_and_restart(tmp_path, monkeypatch):
    from app.broker import PaperBroker
    engine, broker, store, clock, q, _ = setup_engine(tmp_path, monkeypatch)
    engine.portfolio_cycle()
    position = broker.snapshot()["positions"][0]
    clock["now"] = clock["now"].replace(hour=15, minute=5)
    engine._protect_once()
    assert broker.snapshot()["positions"][0]["exit_request"]["reason"] == "SESSION_EXIT"
    assert not store.list_records("trades")
    recovered = PaperBroker(store, cost=broker.cost, clock=lambda: clock["now"], policy=broker.policy)
    assert recovered.snapshot()["positions"][0]["exit_request"]["status"] == "PENDING"
    q.update(timestamp=clock["now"].isoformat(), quote_update_timestamp=clock["now"].isoformat())
    engine.broker = recovered
    engine._protect_once()
    assert not recovered.snapshot()["positions"]
    assert store.list_records("episodes")[0]["reason"] == "SESSION_EXIT"


def test_learning_freezes_next_session_and_rejects_noncausal_features(tmp_path, monkeypatch):
    engine, broker, store, clock, q, _ = setup_engine(tmp_path, monkeypatch)
    engine.portfolio_cycle()
    position = broker.snapshot()["positions"][0]
    clock["now"] += timedelta(seconds=2)
    q.update(bid=position["target"], timestamp=clock["now"].isoformat(), quote_update_timestamp=clock["now"].isoformat(), observation_id="isolated-exit")
    broker.close(position["id"], q, "TARGET", clock["now"])
    episode = store.list_records("episodes")[0]
    assert not eligibility(episode)
    episode["entry_features"]["observed_at"] = (clock["now"]+timedelta(seconds=1)).isoformat()
    assert "Feature timestamps must precede entry and outcome" in eligibility(episode)
    learning = PaperResearchLearning(store)
    first = learning.freeze(clock["now"])
    artifact = MLTradeQualityModel.fit([{"values": {}}]*4, [0, 1, 0, 1], COLUMNS).artifact
    candidate = {"id": "fixture-model", "version": RESEARCH_VERSION, "policy_version": VERSION, "artifact": artifact,
                 "status": "PAPER_APPROVED_NEXT_SESSION", "paper_approved": True, "approved_at": clock["now"].isoformat(),
                 "effective_on": str(clock["now"].date()+timedelta(days=1))}
    store.put_record("paper_learning_candidates", candidate["id"], candidate)
    assert learning.freeze(clock["now"]) == first and not first["models"]
    assert learning.freeze(clock["now"]+timedelta(days=1))["models"][VERSION]["id"] == "fixture-model"


def test_incompatible_model_is_never_frozen_and_training_is_serialized(tmp_path):
    _, store, clock = plan_account(tmp_path)
    learning = PaperResearchLearning(store)
    store.put_record("paper_learning_candidates", "invalid", {"id": "invalid", "paper_approved": True,
        "status": "PAPER_APPROVED_NEXT_SESSION", "effective_on": "2026-01-01", "artifact": {"schema": "obsolete"}})
    assert not learning.freeze(clock["now"])["models"]
    with learning.training_lock:
        assert learning.train(clock["now"])["status"] == "TRAINING"


@pytest.mark.parametrize("features", [None, {}, {"schema": SCHEMA, "paper_policy_version": VERSION, "values": None}])
def test_legacy_null_features_are_rejected_without_stopping_paper_research(tmp_path, features):
    _, store, clock = plan_account(tmp_path)
    episode = {"id": "legacy-outcome", "portfolio_version": "legacy-policy", "source": "paper_live_quotes",
               "entry_features": features, "pnl": -20., "entry_ts": clock["now"].isoformat(),
               "exit_ts": (clock["now"]+timedelta(minutes=1)).isoformat()}
    store.put_record("episodes", episode["id"], episode)
    learner = PaperResearchLearning(store)
    result = learner.train(clock["now"])
    assert result["status"] == "INSUFFICIENT_EVIDENCE" and result["eligible_outcomes"] == 0
    assert result["rejections"]["Causal active-policy entry features required"] == 1
    assert store.get_record("episodes", episode["id"]) == episode
    assert store.list_records("paper_investigations")[0]["category"] == "PLANNED_TRADE_LOSS"
    assert not store.list_records("paper_learning_candidates")


def test_used_holdout_cannot_be_repeated_as_new_learning(tmp_path):
    _, store, clock = plan_account(tmp_path)
    learning = PaperResearchLearning(store)
    days = pd.date_range("2026-07-01", periods=34, freq="D")
    rows = [{"id": f"{day.date()}-{n}", "entry_ts": day.isoformat(), "exit_ts": day.isoformat(), "pnl": -20 if n == 0 else 10}
            for day in days for n in range(3)]
    learning.eligible = lambda: (rows, {})
    store.put_record("paper_learning_candidates", "previous", {"id": "previous", "version": RESEARCH_VERSION,
        "validation_end": str(days[-1].date()), "status": "REPLAY_REJECTED"})
    result = learning.train(clock["now"])
    assert result["status"] == "WAITING_FOR_NEW_HOLDOUT" and result["fresh_holdout_days"] == 0
    assert len(store.list_records("paper_learning_candidates")) == 1


@pytest.mark.parametrize("defect", [None, "inputs", "risk", "incomplete", "training_overlap"])
def test_paper_approval_requires_comparable_independent_account_replays(tmp_path, defect):
    _, store, clock = plan_account(tmp_path)
    learner = PaperResearchLearning(store)
    artifact = MLTradeQualityModel.fit([{"values": {}}]*4, [0, 1, 0, 1], COLUMNS).artifact
    candidate = {"id": "replay-fixture", "version": RESEARCH_VERSION, "policy_version": VERSION, "artifact": artifact,
                 "training_end": "2026-07-24T15:05:00+05:30", "validation_start": "2026-07-25", "validation_end": "2026-08-03"}
    baseline = {"status": "research_complete", "source": "autonomous_observed_quote_replay", "policy_version": VERSION,
                "requested_start": candidate["validation_start"], "requested_end": candidate["validation_end"],
                "coverage_summary": {"full_sessions": True}, "input_digest": "same-archive", "policy_settings_digest": "same-risk",
                "daily_pnl": {str(d.date()): 0 for d in pd.date_range("2026-07-25", "2026-08-03")},
                "trades": [{}]*30, "net_pnl": 0, "estimated_charges": 20, "max_drawdown": -100}
    challenger = {**deepcopy(baseline), "daily_pnl": {d: 25 for d in baseline["daily_pnl"]}, "net_pnl": 250, "max_drawdown": -50}
    if defect == "inputs": challenger["input_digest"] = "different-archive"
    if defect == "risk": challenger["policy_settings_digest"] = "increased-risk"
    if defect == "incomplete": challenger["issues"] = ["Missing quotes"]
    if defect == "training_overlap": candidate["training_end"] = "2026-07-26T10:05:00+05:30"
    validated = learner.validate_replay(candidate, baseline, challenger, clock["now"])
    assert validated["paper_approved"] == (defect is None)
    assert validated["effective_on"] > str(clock["now"].date())


def test_empty_holiday_replay_does_not_touch_live_account_or_event_bus(tmp_path):
    from app.backtest.autonomous_replay import run_replay
    from app.telemetry.event_bus import event_bus
    broker, store, _ = plan_account(tmp_path)
    before, events = deepcopy(broker.state), list(event_bus.recent(100))
    report = run_replay(store=store, gateway=SimpleNamespace(), settings=Settings(_env_file=None), data_dir=tmp_path/"archive",
                        start="2026-10-02", end="2026-10-02")
    assert report["status"] == "research_partial" and not report["trades"]
    assert not report["coverage_summary"]["full_sessions"]
    assert broker.state == before and event_bus.recent(100) == events
