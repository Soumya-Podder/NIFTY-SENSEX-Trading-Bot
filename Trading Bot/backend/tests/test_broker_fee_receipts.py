"""Fee refreshes retain the receipt available at each replay decision time."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from app.backtest.autonomous_replay import RecordedFeeScenario
from app.expectancy import CostModel
from app.store import Store


def test_paper_fee_reserves_cover_price_moves_without_http_at_admission(monkeypatch):
    calls=[]
    def request(*args,**kwargs):
        body=kwargs['json']['data']; calls.append(body)
        turnover=(body['buy_price']+body['sell_price'])*body['qty']*10
        raw={"EXCHANGE_TURNOVER":turnover,"BROKERAGE":20.,"EXCHANGE_CHARGES":0.,
             "STT_CHARGES":0.,"SEBI_CHARGES":0.,"IPFT_CHARGES":0.,"STAMP_DUTY":0.,
             "GST_CHARGES":0.,"TOTAL_CHARGES_TAX":20.+turnover*.001}
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'data':[raw]})
    monkeypatch.setattr('app.expectancy.requests.post',request)
    costs=CostModel(paper=True)
    c={'contract_id':'NSE:12345','security_id':'12345','exchange':'NSE','lot_size':10}
    prepared=costs.quote(c,100.,110.,10)
    assert prepared['estimated'] and prepared['buy_price']>=102 and prepared['sell_price']>=112.2
    monkeypatch.setattr('app.expectancy.requests.post',lambda *a,**k:pytest.fail('HTTP during final admission'))
    with costs.cached_only():
        assert costs.quote(c,101.,111.,10)['total']==prepared['total']
        from app.risk import PlanRiskPolicy,size_plan_order
        account={'initial_capital':30000,'cash':30000,'positions':[],'open_risk_rupees':0,'loss_ledger':{'loss_spend':0}}
        sized=size_plan_order(PlanRiskPolicy(),account,{**c,'ask':101.,'bid':100.,'bid_qty':100,'ask_qty':100},95.,costs)
        assert sized['quantity']==10  # Skip larger quantities without prepared fees.
        for contract,buy,qty in [(c,103.,10),({**c,'contract_id':'NSE:other'},100.,10),(c,100.,20)]:
            with pytest.raises(ValueError,match='fee reserve'):
                costs.quote(contract,buy,110.,qty)
        for row in costs.memory.values(): row['captured_at']='2020-01-01T00:00:00+00:00'
        with pytest.raises(ValueError,match='fee reserve'): costs.quote(c,100.,110.,10)


def test_refreshed_fee_cache_keeps_earlier_receipt_for_causal_replay(tmp_path, monkeypatch):
    store = Store(tmp_path/"fees.db", keep_open=True)
    clock = {"now": datetime(2026, 9, 4, 3, 30, tzinfo=timezone.utc)}
    monkeypatch.setattr("app.expectancy.datetime", SimpleNamespace(now=lambda tz: clock["now"]))
    calls = []
    def request(*args, **kwargs):
        calls.append(kwargs["json"])
        raw = {"EXCHANGE_TURNOVER": 2000., "BROKERAGE": 20., "EXCHANGE_CHARGES": 0.,
               "STT_CHARGES": 0., "SEBI_CHARGES": 0., "IPFT_CHARGES": 0., "STAMP_DUTY": 0.,
               "GST_CHARGES": 0., "TOTAL_CHARGES_TAX": 20. if len(calls) == 1 else 42.}
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"data": [raw]})
    monkeypatch.setattr("app.expectancy.requests.post", request)
    contract = {"contract_id": "NSE:12345", "security_id": "12345", "exchange": "NSE", "lot_size": 10}
    costs = CostModel(store)
    first = costs.quote(contract, 100., 100., 10)
    assert costs.quote(contract, 100., 100., 10) == first
    assert len(calls) == 1 and len(store.list_records("broker_fee_receipts")) == 1

    costs.memory.clear()
    with store._conn() as connection:
        connection.execute("UPDATE history_cache SET expires_at=1")
    clock["now"] = datetime(2026, 9, 4, 5, 30, tzinfo=timezone.utc)
    costs.quote(contract, 100., 100., 10)
    assert len(store.list_records("broker_fee_receipts")) == 2
    monkeypatch.setattr(store, "cache_get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Replay did a per-receipt cache read")))
    replay_clock = {"now": pd.Timestamp("2026-09-04 10:00", tz="Asia/Kolkata")}
    replay = RecordedFeeScenario(store, [contract], lambda: replay_clock["now"])
    assert replay.quote(contract, 100., 100., 10)["total"] == 20.
    replay_clock["now"] = pd.Timestamp("2026-09-04 11:00", tz="Asia/Kolkata")
    assert replay.quote(contract, 100., 100., 10)["total"] == 42.
    assert not replay.unknown_receipt_time
    store.close()


def test_fee_receipt_failure_cannot_be_bypassed_by_an_in_memory_quote(tmp_path, monkeypatch):
    store = Store(tmp_path/"fees.db", keep_open=True)
    raw = {"EXCHANGE_TURNOVER": 2000., "BROKERAGE": 20., "EXCHANGE_CHARGES": 0., "STT_CHARGES": 0.,
           "SEBI_CHARGES": 0., "IPFT_CHARGES": 0., "STAMP_DUTY": 0., "GST_CHARGES": 0., "TOTAL_CHARGES_TAX": 20.}
    monkeypatch.setattr("app.expectancy.requests.post", lambda *a, **k: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {"data": [raw]}))
    monkeypatch.setattr(store, "put_record", lambda *a: (_ for _ in ()).throw(OSError("Receipt archive unavailable")))
    costs = CostModel(store)
    contract = {"contract_id": "NSE:12345", "security_id": "12345", "exchange": "NSE", "lot_size": 10}
    for _ in range(2):
        with pytest.raises(OSError, match="Receipt archive unavailable"):
            costs.quote(contract, 100., 100., 10)
        assert costs.memory == {}
    store.close()
