"""Controlled market fixtures: no broker requests, production writes or Telegram sends."""
from datetime import datetime, timedelta
from types import SimpleNamespace
import pandas as pd
import pytest
from app.market_context import (build_context, chain_window, decision_context, futures_context,
                                positioning_context, volatility_context)
from app.market_data import DhanGateway
from app.session import IST
from app.store import Store
from app.config import Settings
from tests.test_strategy_portfolio import portfolio_account, candidate, executable


NOW = datetime(2026, 9, 25, 10, 5, tzinfo=IST)


def chain_fixture(now=NOW):
    return [{"symbol": "NIFTY", "contract_id": f"NSE:{1000 + i * 2 + side}",
             "security_id": str(1000 + i * 2 + side), "exchange": "NSE", "expiry": "2026-10-01",
             "strike": strike, "option_type": "CALL" if side == 0 else "PUT", "identity_verified": True,
             "metadata_source": "fixture", "metadata_observed_on": str(now.date()), "spot": 24000.,
             "oi": 100. if side == 0 else 200., "previous_oi": 80., "iv": 20., "volume": 300.,
             "chain_observed_at": now.isoformat()}
            for i, strike in enumerate(range(23700, 24301, 50)) for side in (0, 1)]


def future_fixture(now=NOW):
    frame = pd.DataFrame({"timestamp": pd.date_range(now.replace(hour=9, minute=15), periods=50, freq="min"),
                          "open": 24100., "high": 24110., "low": 24090., "close": 24100., "volume": 10.})
    return {"symbol": "NIFTY", "contract_id": "NSE:999", "instrument": "FUTIDX", "identity_verified": True,
            "expiry": "2026-09-29", "security_id": "999", "metadata_source": "fixture"}, frame


def context_fixture(now=NOW):
    rows, _ = chain_window(chain_fixture(now), "NIFTY")
    contract, frame = future_fixture(now)
    return {**build_context("NIFTY", rows, contract, frame, now), "credential_generation": 0, "snapshot_id": "fixture"}


def test_chain_uses_one_exact_window_without_probability_or_multiple_votes():
    rows, error = chain_window(chain_fixture(), "NIFTY")
    observed = positioning_context(rows, "NIFTY", NOW)
    assert error is None and len(rows) == 22
    assert observed["pcr"] == 2 and observed["call_oi_change"] == 220 and observed["put_oi_change"] == 1320
    assert observed["call_wall"]["strike"] > 24000 and observed["put_wall"]["strike"] < 24000
    assert not {"probability", "score", "decision"} & set(observed)


@pytest.mark.parametrize("defect", ["missing", "stale", "future", "mixed_expiry", "rolling", "negative", "duplicate"])
def test_invalid_positioning_cannot_look_observed(defect):
    rows, _ = chain_window(chain_fixture(), "NIFTY")
    if defect == "missing": rows.pop()
    if defect == "stale":
        for row in rows: row["chain_observed_at"] = (NOW - timedelta(minutes=3)).isoformat()
    if defect == "future":
        for row in rows: row["chain_observed_at"] = (NOW + timedelta(seconds=1)).isoformat()
    if defect == "mixed_expiry": rows[0]["expiry"] = "2026-10-08"
    if defect == "rolling": rows[0]["security_id"] = "rolling:NIFTY:ATM"
    if defect == "negative": rows[0]["oi"] = -1
    if defect == "duplicate": rows[-1] = rows[0]
    assert positioning_context(rows, "NIFTY", NOW)["status"] == "DATA_UNAVAILABLE"


def test_missing_prior_oi_and_zero_denominator_are_not_imputed():
    rows, _ = chain_window(chain_fixture(), "NIFTY")
    for row in rows:
        if row["option_type"] == "CALL": row["oi"] = 0
    rows[0]["previous_oi"] = None
    result = positioning_context(rows, "NIFTY", NOW)
    assert result["pcr"] is None and result["call_oi_change"] is None and result["put_oi_change"] is None
    assert result["prior_oi_status"] == "DATA_UNAVAILABLE"


def test_vwap_uses_same_futures_contract_and_only_completed_session_bars():
    contract, bars = future_fixture()
    result = futures_context(contract, bars, NOW)
    assert result["vwap"] == 24100 and result["relation"] == "AT"  # Spot is 24000; basis is not a bearish vote.
    future = bars.iloc[[-1]].copy(); future["timestamp"] = NOW
    future["close"] = 999999
    assert futures_context(contract, pd.concat([bars, future]), NOW) == result
    yesterday = bars.copy(); yesterday["timestamp"] -= pd.Timedelta(days=1)
    assert futures_context(contract, pd.concat([yesterday, bars]), NOW) == result


@pytest.mark.parametrize("defect", ["gap", "duplicate", "zero_volume", "stale", "negative_volume", "price", "timestamp"])
def test_futures_vwap_rejects_unusable_candles(defect):
    contract, bars = future_fixture()
    if defect == "gap": bars = bars.drop(index=3)
    if defect == "duplicate": bars = pd.concat([bars, bars.iloc[[2]]])
    if defect == "zero_volume": bars["volume"] = 0
    if defect == "stale": bars = bars.iloc[:-5]
    if defect == "negative_volume": bars.loc[5, "volume"] = -1
    if defect == "price": bars.loc[5, "close"] = 30000
    if defect == "timestamp": bars.loc[5, "timestamp"] = pd.NaT
    assert futures_context(contract, bars, NOW)["status"] == "DATA_UNAVAILABLE"


def test_iv_is_time_limited_scenario_not_a_premium_profitability_gate():
    now = NOW.replace(hour=15, minute=3)
    rows, _ = chain_window(chain_fixture(now), "NIFTY")
    positioning = positioning_context(rows, "NIFTY", now)
    result = volatility_context(rows, positioning, now, horizon_minutes=10)
    assert result["status"] == "SCENARIO" and result["horizon_minutes"] == 2
    assert result["move_points"] == pytest.approx(24000 * .2 * (2 / (365 * 24 * 60)) ** .5)
    assert volatility_context(rows, positioning, now.replace(minute=5))["status"] == "DATA_UNAVAILABLE"
    rows[10]["iv"] = None
    assert volatility_context(rows, positioning, now)["status"] == "DATA_UNAVAILABLE"


def test_context_expires_on_time_day_or_credential_change_and_shortens_for_strategy():
    context = context_fixture()
    shorter = decision_context(context, NOW, 0, 5)
    assert shorter["volatility"]["move_points"] == pytest.approx(context["volatility"]["move_points"] / 2 ** .5)
    for now, generation in ((NOW + timedelta(minutes=3), 0), (NOW + timedelta(days=1), 0), (NOW, 1)):
        result = decision_context(context, now, generation)
        assert result["status"] == "STALE" and result["positioning"]["status"] == "DATA_UNAVAILABLE"
    assert context["positioning"]["status"] == "OBSERVED"  # Caller cannot mutate the archived snapshot.


def test_missing_context_is_advisory_and_context_cannot_change_offer_risk(tmp_path, monkeypatch):
    engine, broker, store, clock = portfolio_account(tmp_path, monkeypatch)
    signal = candidate(clock); contract, candle = executable(clock)
    engine._request_protection = lambda *_: (candle, None)
    before, reason = engine._prepare_offer(signal, contract, broker.snapshot(), [], clock["now"])
    assert before and reason is None
    context = context_fixture(clock["now"])
    context["positioning"]["pcr"] = 100000
    context["decision"] = "BOTH"  # An injected heuristic has no order or ranking authority.
    engine.status["market_context"]["NIFTY"] = context
    after, reason = engine._prepare_offer(signal, contract, broker.snapshot(), [], clock["now"])
    assert after and reason is None
    for key in ("risk", "net_reward", "net_reward_risk", "ev"):
        assert after[key] == before[key]
    assert after["signal"]["orchestrator_decision"] == "CALL"
    assert broker.snapshot()["open_positions"] == 0
    assert after["signal"]["market_context"]["learning_eligible"] is False


def test_context_inputs_persist_for_reproduction_and_survive_position_exit(tmp_path, monkeypatch):
    engine, broker, store, clock = portfolio_account(tmp_path, monkeypatch)
    engine.gateway.refresh_credentials = lambda: False
    engine.gateway.chain = lambda *_, **kw: chain_fixture(clock["now"])
    engine.gateway.futures_candles = lambda *args: future_fixture(clock["now"])
    engine.collect_market_context("NIFTY")
    context = engine.context_at("NIFTY", clock["now"])
    inputs = store.get_record("market_context_inputs", context["snapshot_id"])
    restored = build_context("NIFTY", inputs["chain"], inputs["futures_contract"],
        pd.DataFrame(inputs["futures_candles"]), clock["now"])
    assert restored["futures"] == context["futures"]
    assert restored["positioning"] == context["positioning"]
    signal = candidate(clock); contract, candle = executable(clock)
    engine._request_protection = lambda *_: (candle, None)
    offer, reason = engine._prepare_offer(signal, contract, broker.snapshot(), [], clock["now"])
    assert reason is None
    signal = {**offer["signal"], "risk_rupees": offer["risk"]}
    order = broker.place_order(contract=contract, quote=contract, quantity=contract["lot_size"], signal=signal, now=clock["now"])
    broker.close(order["id"], contract, "TEST", now=clock["now"])
    assert store.list_records("episodes")[0]["market_context"]["snapshot_id"] == context["snapshot_id"]


def test_context_download_failure_and_rotation_do_not_touch_account(tmp_path, monkeypatch):
    engine, broker, store, clock = portfolio_account(tmp_path, monkeypatch)
    engine.gateway.refresh_credentials = lambda: False
    def fail(*args, **kwargs): raise RuntimeError("fixture unavailable")
    engine.gateway.chain = fail; engine.gateway.futures_candles = fail
    before = broker.snapshot()
    engine.collect_market_context("NIFTY")
    assert engine.context_at("NIFTY", clock["now"])["futures"]["status"] == "DATA_UNAVAILABLE"
    assert broker.snapshot() == before
    def rotate(*args):
        engine.gateway.credential_generation += 1
        return future_fixture(clock["now"])
    engine.gateway.chain = lambda *args, **kwargs: chain_fixture(clock["now"])
    engine.gateway.futures_candles = rotate
    count = len(store.list_records("market_context"))
    engine.collect_market_context("NIFTY")
    assert len(store.list_records("market_context")) == count
    assert engine.context_at("NIFTY", clock["now"])["status"] == "STALE"


def test_option_chain_cache_retains_original_observation_time(tmp_path, monkeypatch):
    import dhanhq
    calls = []
    class Client:
        def __init__(self, _): self.dhan_http = SimpleNamespace(timeout=None)
        def option_chain(self, *args):
            calls.append(args)
            return {"status": "success", "data": {"oc": {}, "last_price": 24000}}
    monkeypatch.setattr(dhanhq, "dhanhq", Client)
    monkeypatch.setattr("app.market_data.time.sleep", lambda _: None)
    monkeypatch.setattr("app.market_data.now_ist", lambda: NOW)
    gateway = DhanGateway(Settings(_env_file=None), Store(tmp_path / "context.db"))
    first = gateway.call(gateway.client.option_chain, 13, "IDX_I", "2026-10-01", kind="chain", cache_seconds=30)
    monkeypatch.setattr("app.market_data.now_ist", lambda: NOW + timedelta(seconds=10))
    second = gateway.call(gateway.client.option_chain, 13, "IDX_I", "2026-10-01", kind="chain", cache_seconds=30)
    assert first["_observed_at"] == second["_observed_at"] == NOW.isoformat() and len(calls) == 1


def test_gateway_keeps_atm_excluded_from_execution_but_available_for_research(tmp_path, monkeypatch):
    rows = chain_fixture()
    gateway = object.__new__(DhanGateway)
    gateway.client = SimpleNamespace(expiry_list=object(), option_chain=object())
    gateway.store = Store(tmp_path / "chain.db")
    gateway.underlyings = lambda: [{"symbol": "NIFTY", "security_id": "13"}]
    gateway.contracts = lambda _: rows
    raw = {"_observed_at": NOW.isoformat(), "last_price": 24000, "oc": {}}
    for row in rows:
        raw["oc"].setdefault(str(row["strike"]), {})["ce" if row["option_type"] == "CALL" else "pe"] = {
            "security_id": row["security_id"], "oi": row["oi"], "previous_oi": row["previous_oi"],
            "implied_volatility": row["iv"], "last_price": 100}
    gateway.call = lambda method, *args, **kw: ["2026-10-01"] if method is gateway.client.expiry_list else raw
    monkeypatch.setattr("app.market_data.now_ist", lambda: NOW)
    execution = gateway.chain("NIFTY", exclude_expiry_day=True)
    research = gateway.chain("NIFTY", exclude_expiry_day=True, include_atm=True)
    assert len(execution) == 24 and not any(c["is_atm"] for c in execution)
    assert len(research) == 26 and sum(c["is_atm"] for c in research) == 2
    assert research[0]["previous_oi"] == 80 and research[0]["chain_observed_at"] == NOW.isoformat()


def test_nearest_futures_resolved_by_dated_master_not_hardcoded_id(monkeypatch):
    gateway = object.__new__(DhanGateway)
    gateway.client = SimpleNamespace(intraday_minute_data=object())
    gateway.master = lambda: pd.DataFrame([
        {"SEM_INSTRUMENT_NAME": "FUTIDX", "SEM_TRADING_SYMBOL": name, "SEM_EXPIRY_DATE": expiry,
         "SEM_SMST_SECURITY_ID": sid, "SEM_EXM_EXCH_ID": "NSE"}
        for name, expiry, sid in (("NIFTY-SEP-FUT", "2026-09-24", 1), ("NIFTY-OCT-FUT", "2026-10-29", 2),
                                  ("NIFTY-SEP-FUT", "2026-09-29", 3), ("BANKNIFTY-SEP-FUT", "2026-09-29", 4))])
    def fetch(method, *args, **kwargs):
        assert args[:3] == ("3", "NSE_FNO", "FUTIDX")
        return {}
    gateway.call = fetch
    contract, bars = gateway.futures_candles("NIFTY", NOW)
    assert contract["contract_id"] == "NSE:3" and bars.empty
