from types import SimpleNamespace
from datetime import timedelta

import pandas as pd

from app.config import Settings
from app.simple_paper import SimplePaperEngine, protection, trend_signal
from app.option_screen import assess
from app.pipeline import plan_exit
from tests.test_paper import plan_account, contract, quote


def downtrend_frame(clock):
    times = pd.date_range(clock["now"].replace(hour=9, minute=15), periods=50, freq="min")
    frame = pd.DataFrame({"timestamp": times, "open": 24020., "high": 24035., "low": 24005.,
                          "close": 24020., "volume": 1000., "adx": 28., "atr": 12.,
                          "ema9": 24019., "ema21": 24025.})
    frame.loc[46:48, ["open", "high", "low", "close"]] = [24020., 24035., 24005., 24020.]
    frame.loc[49, ["open", "high", "low", "close", "ema9", "ema21"]] = [24005., 24010., 23989., 23990., 24000., 24015.]
    return frame


def test_simple_signal_uses_only_completed_trend_bars(tmp_path, monkeypatch):
    _, _, clock = plan_account(tmp_path)
    clock["now"] += timedelta(minutes=5)
    monkeypatch.setattr("app.strategy_portfolio.add_features", lambda frame: frame)
    frame = downtrend_frame(clock)
    signal, reason = trend_signal(frame, clock["now"], "NIFTY")
    assert reason is None and signal["option_type"] == "PUT"
    assert signal["invalidation"] == 24035
    frame.loc[49, "close"] = 24020
    assert trend_signal(frame, clock["now"], "NIFTY")[0] is None


def test_simple_trend_opens_only_durable_virtual_paper_position(tmp_path, monkeypatch):
    broker, store, clock = plan_account(tmp_path)
    clock["now"] += timedelta(minutes=5)
    broker.option_screen_limits = (.02, 1.)
    monkeypatch.setattr("app.strategy_portfolio.add_features", lambda frame: frame)
    monkeypatch.setattr("app.simple_paper.now_ist", lambda: clock["now"])
    frame = downtrend_frame(clock)
    c = {**contract(), "option_type": "PUT", "strike": 24000, "oi": 1000, "volume": 1000,
         "delta": -.5, "greeks_observed_at": clock["now"].isoformat()}
    q = {**quote(c, clock), "quote_update_timestamp": clock["now"].isoformat()}
    market = SimpleNamespace(execution_snapshot=lambda symbol: {
        "underlying": {"ltp": 23990, "quote_update_timestamp": clock["now"].isoformat(), "source": "dhan_market_feed"},
        "options": {c["contract_id"]: q}})
    engine = SimplePaperEngine(Settings(_env_file=None), store, SimpleNamespace(), broker, market)
    engine.evaluate_entries({"NIFTY": frame}, {}, clock["now"])
    assert broker.snapshot()["open_positions"] == 1
    assert broker.snapshot()["positions"][0]["strategy_id"] == "simple_trend"
    assert store.list_records("orders")[0]["mode"] == "paper"
    engine.evaluate_entries({"NIFTY": frame}, {}, clock["now"])
    assert broker.snapshot()["open_positions"] == 1
    position = broker.snapshot()["positions"][0]
    assert plan_exit(position, clock["now"], bid=position["stop"] - .05, underlying=23990) == "STOP"


def test_simple_trend_rejects_stale_depth(tmp_path, monkeypatch):
    broker, store, clock = plan_account(tmp_path)
    clock["now"] += timedelta(minutes=5)
    monkeypatch.setattr("app.strategy_portfolio.add_features", lambda frame: frame)
    monkeypatch.setattr("app.simple_paper.now_ist", lambda: clock["now"])
    frame = downtrend_frame(clock)
    c = {**contract(), "option_type": "PUT", "strike": 24000, "oi": 1000, "volume": 1000,
         "delta": -.5, "greeks_observed_at": clock["now"].isoformat()}
    q = {**quote(c, clock), "quote_update_timestamp": (clock["now"] - timedelta(seconds=3)).isoformat()}
    market = SimpleNamespace(execution_snapshot=lambda symbol: {
        "underlying": {"ltp": 23990, "quote_update_timestamp": clock["now"].isoformat(), "source": "dhan_market_feed"},
        "options": {c["contract_id"]: q}})
    engine = SimplePaperEngine(Settings(_env_file=None), store, SimpleNamespace(), broker, market)
    engine.evaluate_entries({"NIFTY": frame}, {}, clock["now"])
    assert broker.snapshot()["open_positions"] == 0


def test_noise_level_stop_and_spread_to_stop_are_rejected():
    signal = {"invalidation": 100., "underlying_atr": 10., "option_type": "CALL"}
    option = {"ask": 100., "bid": 99., "delta": .5, "tick_size": .05}
    assert protection(signal, option, 108.) is None  # Only 0.8 ATR to invalidation.
    assert protection(signal, {**option, "bid": 99.}, 120.) is not None
    assert protection(signal, {**option, "bid": 98.9}, 120.) is None  # Spread > 10% of mapped stop.


def test_candles_are_published_before_chain_request(tmp_path,monkeypatch):
    broker,store,clock=plan_account(tmp_path)
    clock['now'] += timedelta(minutes=5)
    frame=downtrend_frame(clock)
    monkeypatch.setattr('app.simple_paper.now_ist',lambda:clock['now'])
    def candles(*args,**kwargs):
        assert kwargs['cache_seconds']==5
        return frame
    def chain(*args,**kwargs):
        assert engine.frames['NIFTY'].timestamp.max()==frame.timestamp.max()
        engine.stop_event.set()
        raise RuntimeError('Delayed chain does not hide completed candles')
    engine=SimplePaperEngine(Settings(_env_file=None),store,SimpleNamespace(candles=candles,chain=chain),broker)
    monkeypatch.setattr(engine,'_session',lambda:'ENTRY_WINDOW')
    engine._data_loop('NIFTY')
    assert engine.frames['NIFTY'].timestamp.max()==frame.timestamp.max()


def test_simple_signal_requires_fresh_delta_for_stop_mapping(tmp_path):
    _, _, clock = plan_account(tmp_path)
    c = {**quote(contract(), clock), "option_type": "PUT", "oi": 1000, "volume": 1000,
         "delta": -.5, "greeks_observed_at": (clock["now"] - timedelta(seconds=46)).isoformat()}
    signal = {"option_type": "PUT", "regime": "TREND_DOWN", "max_greeks_age_seconds": 45}
    assert assess(c, signal, clock["now"])["status"] == "WAITING_DATA"
    c["greeks_observed_at"] = (clock["now"] - timedelta(seconds=45)).isoformat()
    assert assess(c, signal, clock["now"])["status"] == "PASS"


def test_simple_trend_selects_best_net_contract_across_indices(tmp_path, monkeypatch):
    broker, store, clock = plan_account(tmp_path)
    clock["now"] += timedelta(minutes=5)
    broker.option_screen_limits = (.02, 1.)
    monkeypatch.setattr("app.strategy_portfolio.add_features", lambda frame: frame)
    monkeypatch.setattr("app.simple_paper.now_ist", lambda: clock["now"])
    frames = {symbol: downtrend_frame(clock) for symbol in ("NIFTY", "SENSEX")}
    options = {}
    for symbol, bid in (("NIFTY", 99.5), ("SENSEX", 99.9)):
        c = {**contract(symbol), "option_type": "PUT", "strike": 24000, "oi": 1000,
             "volume": 1000, "delta": -.5, "greeks_observed_at": clock["now"].isoformat()}
        options[symbol] = {**quote(c, clock, bid=bid), "quote_update_timestamp": clock["now"].isoformat()}
    market = SimpleNamespace(execution_snapshot=lambda symbol: {
        "underlying": {"ltp": 23990, "quote_update_timestamp": clock["now"].isoformat(), "source": "dhan_market_feed"},
        "options": {options[symbol]["contract_id"]: options[symbol]}})
    engine = SimplePaperEngine(Settings(_env_file=None), store, SimpleNamespace(), broker, market)
    engine.evaluate_entries(frames, {}, clock["now"])
    position = broker.snapshot()["positions"][0]
    assert position["symbol"] == "SENSEX"
    assert position["selection_evidence"]["eligible_contracts"] == 2


def test_simple_data_error_survives_other_symbol_success(tmp_path, monkeypatch):
    broker, store, clock = plan_account(tmp_path)
    frame = downtrend_frame(clock)

    class Gateway:
        def candles(self, symbol, *_, **kwargs):
            if symbol == "NIFTY":
                raise RuntimeError("index unavailable")
            return frame

        def chain(self, *_args, **_kwargs):
            return []

    engine = SimplePaperEngine(Settings(_env_file=None), store, Gateway(), broker, None)
    monkeypatch.setattr(engine, "_session", lambda: "ENTRY_WINDOW")
    monkeypatch.setattr(engine.stop_event, "wait", lambda _: engine.stop_event.set())
    monkeypatch.setattr("app.simple_paper.now_ist", lambda: clock["now"])
    engine._data_loop()
    assert engine.status["data_symbols"]["NIFTY"]["error"] == "RuntimeError"
    assert engine.status["data_symbols"]["SENSEX"]["subscribed_candidates"] == 0
    assert engine.status["data_error"] == "RuntimeError"


def test_candidate_journal_records_observation_without_virtual_fill(tmp_path, monkeypatch):
    broker, store, clock = plan_account(tmp_path)
    clock["now"] += timedelta(minutes=5)
    monkeypatch.setattr("app.strategy_portfolio.add_features", lambda frame: frame)
    monkeypatch.setattr("app.simple_paper.now_ist", lambda: clock["now"])
    market = SimpleNamespace(execution_snapshot=lambda symbol: {
        "underlying": {"symbol": symbol, "ltp": 23990},
        "options": {"one": {"contract_id": "one", "bid": 99, "ask": 100}}})
    engine = SimplePaperEngine(Settings(_env_file=None), store, SimpleNamespace(), broker, market)
    frame = downtrend_frame(clock)
    engine._journal_candidate("NIFTY", frame)
    engine._journal_candidate("NIFTY", frame)
    records = store.list_records("signal_observations")
    assert len(records) == 1
    assert records[0]["status"] == "OBSERVED_ONLY"
    assert records[0]["outcome"] == "NOT_SIMULATED"
    assert records[0]["subscribed_option_quotes"][0]["contract_id"] == "one"
    assert broker.snapshot()["open_positions"] == 0
