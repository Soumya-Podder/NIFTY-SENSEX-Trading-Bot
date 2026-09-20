"""Fixtures check ingestion and evidence boundaries, not trading returns."""
import pytest
import json
import pandas as pd
from app.backtest.data import read_contract_csv
from app.backtest.observed_session import candles, fee_scenario
from app.backtest.engine import BacktestEngine
from app.backtest.reports import report_from_run
from app.backtest.presentation import report_view
from tests.test_backtest import historical_fixture


def test_candle_arrays_reject_misalignment_and_duplicates():
    raw = {"timestamp": [1800330300], "open": [10], "high": [11], "low": [9], "close": [10], "volume": [20]}
    assert str(candles(raw, "NIFTY").timestamp.dt.tz) == "Asia/Kolkata"
    with pytest.raises(ValueError, match="mismatched"):
        candles({**raw, "close": []}, "NIFTY")
    with pytest.raises(ValueError, match="duplicate"):
        candles({k: v * 2 for k, v in raw.items()}, "NIFTY")
    assert candles({}, "NIFTY").empty


def test_estimated_fee_replay_is_visible_but_never_verified():
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
