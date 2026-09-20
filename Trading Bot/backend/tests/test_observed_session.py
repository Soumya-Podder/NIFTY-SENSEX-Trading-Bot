"""Fixtures check ingestion and evidence boundaries, not trading returns."""
import pytest
import json
import pandas as pd
from app.backtest.data import read_contract_csv
from app.backtest.observed_session import broker_cost_receipts, candles, fee_scenario, inject_receipts, isolated_replay_frame, stable_receipt_digest
from app.expectancy import CostModel
from app.backtest.engine import BacktestEngine
from app.backtest.reports import report_from_run
from app.backtest.presentation import report_view
from tests.test_backtest import historical_fixture, once_per_session


def test_candle_arrays_reject_misalignment_and_duplicates():
    raw = {"timestamp": [1800330300], "open": [10], "high": [11], "low": [9], "close": [10], "volume": [20]}
    assert str(candles(raw, "NIFTY").timestamp.dt.tz) == "Asia/Kolkata"
    with pytest.raises(ValueError, match="mismatched"):
        candles({**raw, "close": []}, "NIFTY")
    with pytest.raises(ValueError, match="duplicate"):
        candles({k: v * 2 for k, v in raw.items()}, "NIFTY")
    assert candles({}, "NIFTY").empty


def test_estimated_fee_replay_is_visible_but_never_verified(once_per_session):
    frame = historical_fixture()
    for quotes in frame.option_quotes:
        quotes[0]["charge_schedule"] = fee_scenario("2026-09-04")
    result = BacktestEngine().run(frame)
    assert result["quality"] == "research_net"
    assert result["status"] == "research_complete"
    assert result["learning_eligible"] is False
    view = report_view(report_from_run(result, {"capital": 30000}))
    assert view["presentation"]["performance_available"]
    assert "estimated fees" in view["presentation"]["evidence_label"]
    assert not any("current lot sizes" in s for s in view["assumptions"])


def test_broker_receipts_reconcile_to_exact_historical_overrides():
    class Calculator:
        def quote_buy(self, contract, buy_price, qty):
            return {"brokerage":20,"exchange":2,"stt":0,"sebi":.01,"ipft":.02,
                    "stamp_duty":0,"gst":4,"total":26.03,"request_fingerprint":"buy"}
        def quote(self, contract, buy_price, sell_price, qty):
            return {"brokerage":40,"exchange":5,"stt":3,"sebi":.02,"ipft":.04,
                    "stamp_duty":0,"gst":8,"total":56.06,"request_fingerprint":"round"}
    trade={"exchange":"NSE","security_id":1,"lot_size":65,"quantity":65,
           "entry":100.,"exit":110.,"entry_ts":"2026-09-18T10:00:00+05:30"}
    observed=broker_cost_receipts(trade,Calculator(),"2026-09-18")
    schedule={**fee_scenario("2026-09-18"),"observed_costs":observed}
    contract={"charge_schedule":schedule}
    buy=CostModel.historical(contract,100.,65,"buy",trade["entry_ts"])
    sell=CostModel.historical(contract,110.,65,"sell",trade["entry_ts"])
    assert buy["kind"]==sell["kind"]=="broker_calculator_receipt"
    assert buy["total"]==26.03 and sell["total"]==30.03
    assert buy["total"]+sell["total"]==56.06
    corrupted={**schedule,"observed_costs":{key:{**value,"price":999}
        for key,value in observed.items()}}
    with pytest.raises(ValueError,match="receipt_invalid"):
        CostModel.historical({"charge_schedule":corrupted},100.,65,"buy",trade["entry_ts"])


def test_strategy_replay_receipts_do_not_leak_into_another_strategy():
    source=historical_fixture()
    working=isolated_replay_frame(source)
    inject_receipts(working,{"fixed:NIFTY":{"buy|40.00000000|10":{"kind":"broker_calculator_receipt"}}})
    assert working.iloc[0].option_quotes[0]["charge_schedule"].get("observed_costs")
    assert "observed_costs" not in source.iloc[0].option_quotes[0]["charge_schedule"]


def test_receipt_fingerprint_excludes_only_volatile_observation_time():
    first={"NSE:1":{"buy":{"observed_at":"first","total":12.5,"price":100}}}
    second={"NSE:1":{"buy":{"observed_at":"later","total":12.5,"price":100}}}
    changed={"NSE:1":{"buy":{"observed_at":"later","total":13.5,"price":100}}}
    assert stable_receipt_digest(first)==stable_receipt_digest(second)
    assert stable_receipt_digest(first)!=stable_receipt_digest(changed)


def test_backtest_trade_identity_is_deterministic(once_per_session):
    frame=historical_fixture()
    first=BacktestEngine().run(frame)["trades"][0]["id"]
    second=BacktestEngine().run(frame)["trades"][0]["id"]
    assert first==second


def test_missing_option_minute_preserves_observed_index_without_a_quote(tmp_path):
    frame=historical_fixture()
    columns=["timestamp","symbol","open","high","low","close","volume"]
    underlying=frame[columns].copy()
    rows=[]
    for bar in frame.iloc[1:].to_dict("records"):
        q=bar["option_quotes"][0]
        rows.append({**q, "timestamp":bar["timestamp"],
            "charge_schedule":json.dumps(q["charge_schedule"]), "metadata_source":"unit_fixture",
            "metadata_valid_from":"2026-09-04", "metadata_valid_to":"2026-09-04",
            "price_source":"unit_fixture", **{"underlying_"+k:bar[k] for k in columns[2:]}})
    path=tmp_path/"contracts.csv"
    pd.DataFrame(rows).to_csv(path,index=False)
    with pytest.raises(ValueError,match="incomplete one-minute"):
        read_contract_csv(path)
    restored,_=read_contract_csv(path,underlying_frame=underlying)
    assert len(restored)==len(frame)
    assert restored.iloc[0].option_quotes==[]
    assert restored.iloc[0].close==frame.iloc[0].close
    assert restored.iloc[1].option_quotes[0]["contract_id"]=="fixed:NIFTY"
    underlying.loc[1,"volume"]=999
    with pytest.raises(ValueError,match="disagree"):
        read_contract_csv(path,underlying_frame=underlying)


@pytest.mark.parametrize("extra", [{"strategy": "portfolio"}, {"walk_forward": True}])
def test_rolling_cli_rejects_unsupported_requests(monkeypatch, extra):
    from app.backtest.cli import main
    args = ["replay", "--source", "rolling-cache", "--from", "2026-09-01", "--to", "2026-09-18"]
    args += ["--strategy", extra["strategy"]] if "strategy" in extra else ["--walk-forward"]
    monkeypatch.setattr("sys.argv", args)
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
