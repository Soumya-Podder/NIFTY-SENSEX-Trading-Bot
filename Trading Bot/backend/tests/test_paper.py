"""Isolated accounting fixtures; none are loaded by the runtime or dashboard."""
from datetime import datetime,timedelta
import pytest
from app.broker import PaperBroker,DhanBroker
from app.store import Store
from app.session import IST,quote_is_fresh,session_state
from app.paper_engine import PaperEngine
from app.config import Settings


class TestFees:
    __test__=False
    def quote(self,contract,buy,sell,qty):
        return {"total":20,"brokerage":20,"source":"isolated_unit_test","quantity":qty}


def plan_account(tmp_path):
    from app.risk import PlanRiskPolicy
    clock={"now":datetime(2026,9,4,10,0,tzinfo=IST)}
    store=Store(tmp_path/"plan.db")
    broker=PaperBroker(store,30000,TestFees(),clock=lambda:clock["now"],entry_cutoff="14:30",policy=PlanRiskPolicy())
    return broker,store,clock


def test_paper_toggle_is_explicit_and_never_live(monkeypatch,tmp_path):
    # main constructs its service at import: redirect every constructor before
    # import so this API test cannot persist into the user's paper account.
    import app.store as store_module
    import app.autonomous_agent as autonomous_module
    isolated=lambda *args,**kwargs: Store(tmp_path/"api-test.db")
    monkeypatch.setattr(store_module,"Store",isolated)
    monkeypatch.setattr(autonomous_module,"Store",isolated)
    monkeypatch.setattr(autonomous_module,"_agent_instance",None)
    from app import main

    class ToggleOnlyPaper:
        def __init__(self): self.enabled=False
        def control(self,enabled=None):
            if enabled is not None: self.enabled=enabled
        def snapshot(self): return {"enabled":self.enabled}

    paper=ToggleOnlyPaper()
    monkeypatch.setattr(main,"paper",paper)
    assert main.paper_control(main.PaperControl(enabled=True))["enabled"] is True
    assert main.paper_control(main.PaperControl(enabled=False))["enabled"] is False
    assert main.mode()=={"mode":"paper","live_available":False,"live_trading_enabled":False,
                         "reason":"Paper-only implementation; live orders are disabled server-side"}


def test_plan_loss_spend_does_not_refill_after_winner_or_restart(tmp_path):
    broker,store,clock=plan_account(tmp_path)
    first=enter(broker,clock,qty=10)
    clock["now"]+=timedelta(seconds=1)
    broker.close(first["id"],quote(contract(),clock,bid=90),"STOP",clock["now"])
    assert broker.snapshot()["loss_ledger"]["loss_spend"]==140
    clock["now"]+=timedelta(minutes=5)
    second=enter(broker,clock,qty=10,identifier="second")
    clock["now"]+=timedelta(seconds=1)
    broker.close(second["id"],quote(contract(),clock,bid=120),"TARGET",clock["now"])
    assert broker.snapshot()["loss_ledger"]["loss_spend"]==140
    restored=PaperBroker(store,30000,TestFees(),clock=lambda:clock["now"],policy=broker.policy)
    assert restored.snapshot()["remaining_loss_allocation"]==510
    assert restored.snapshot()["loss_ledger"]["entries"]==2


def test_plan_serializes_indices_and_enforces_one_lot_cooldown_and_expiry(tmp_path):
    broker,_,clock=plan_account(tmp_path)
    with pytest.raises(ValueError,match="one lot"): enter(broker,clock,qty=20)
    first=enter(broker,clock,qty=10)
    with pytest.raises(ValueError,match="one position"): enter(broker,clock,c=contract("SENSEX"),qty=10,identifier="second")
    clock["now"]+=timedelta(seconds=1)
    broker.close(first["id"],quote(contract(),clock,bid=100),"EXIT",clock["now"])
    with pytest.raises(ValueError,match="COOLDOWN"): enter(broker,clock,qty=10,identifier="too-soon")
    clock["now"]+=timedelta(minutes=5)
    with pytest.raises(ValueError,match="expiry-day"):
        enter(broker,clock,c={**contract(),"expiry":"2026-09-04"},qty=10,identifier="expiry")


def test_plan_target_locks_even_if_final_fill_is_below_target(tmp_path):
    broker,_,clock=plan_account(tmp_path)
    first=enter(broker,clock,qty=10)
    clock["now"]+=timedelta(seconds=1)
    q={**quote(contract(),clock,bid=225),"exit_cost_estimate":20}
    broker.mark({contract()["contract_id"]:q},clock["now"])
    assert broker.snapshot()["loss_ledger"]["lock_reason"]=="GROSS_PROFIT_LOCK"
    broker.close(first["id"],quote(contract(),clock,bid=210),"PROFIT_LOCK",clock["now"])
    assert broker.snapshot()["gross_session_pnl"]==1100
    with pytest.raises(ValueError,match="cannot be cleared"): broker.control(halted=False)


def test_plan_daily_reset_preserves_weekly_pause_and_previous_day_result(tmp_path):
    broker,_,clock=plan_account(tmp_path)
    broker.state["daily_results"]={"2026-09-01":-650,"2026-09-02":-650}
    broker.state["cash"]-=450
    broker.mark({},clock["now"])
    assert broker.state["loss_ledger"]["lock_reason"]=="WEEKLY_LOSS_PAUSE"
    clock["now"]+=timedelta(days=3)
    broker.new_session(clock["now"])
    assert broker.state["daily_results"]["2026-09-04"]==-450
    assert broker.state["loss_ledger"]["lock_reason"]=="WEEKLY_LOSS_PAUSE"


def test_plan_missing_depth_or_exit_fees_does_not_claim_executable_pnl(tmp_path):
    broker,_,clock=plan_account(tmp_path)
    enter(broker,clock,qty=10)
    broker.mark({contract()["contract_id"]:quote(contract(),clock,bid=225)},clock["now"])
    assert broker.snapshot()["liquidation_pnl"] is None
    assert broker.state["loss_ledger"]["lock_reason"] is None


@pytest.fixture
def account(tmp_path):
    clock={"now":datetime(2026,9,4,10,0,tzinfo=IST)}
    store=Store(tmp_path/"test.db")
    broker=PaperBroker(store,30000,TestFees(),clock=lambda:clock["now"])
    return broker,store,clock


def contract(symbol="NIFTY"):
    return {"symbol":symbol,"contract_id":"test:"+symbol,"identity_verified":True,"expiry":"2026-09-10",
            "lot_size":10,"tick_size":.05,"strike":25000,"option_type":"CALL"}


def quote(c,clock,bid=99,ask=100,qty=1000):
    return {**c,"bid":bid,"ask":ask,"bid_qty":qty,"ask_qty":qty,"source":"dhan_quote",
            "timestamp":clock["now"].isoformat(),"exchange_timestamp":clock["now"].isoformat()}


def signal(identifier="signal"):
    return {"id":identifier,"stop_percent":.1,"target_percent":.2,"risk_rupees":240,
            "stop_price":90,"target_price":120,
            "setup":"TEST_ONLY","regime":"TREND_UP","agent_contexts":{},"policy_versions":{}}


def enter(broker,clock,c=None,qty=20,identifier="signal"):
    c=c or contract()
    return broker.place_order(contract=c,quote=quote(c,clock),quantity=qty,signal=signal(identifier),now=clock["now"])


def test_account_persists_and_partial_exits_reconcile(account):
    broker,store,clock=account
    order=enter(broker,clock)
    assert broker.snapshot()["cash"]==27980
    clock["now"]+=timedelta(seconds=1)
    first=broker.close(order["id"],quote(contract(),clock,bid=110,qty=10),"TARGET",clock["now"])
    assert first["partial"] and first["pnl"]==70
    assert not store.list_records("episodes")
    clock["now"]+=timedelta(seconds=1)
    last=broker.close(order["id"],quote(contract(),clock,bid=90,qty=10),"STOP",clock["now"])
    assert last["pnl"]==-130
    episode=store.list_records("episodes")[0]
    assert episode["pnl"]==-60 and episode["quantity"]==20 and episode["exit_fills"]==2
    restored=PaperBroker(store,30000,TestFees(),clock=lambda:clock["now"])
    assert restored.snapshot()["cash"]==29940
    assert restored.snapshot()["realized_pnl"]==-60
    assert restored.snapshot()["charges"]==60
    assert restored.snapshot()["positions"]==[]
    assert len(store.pending_paper_feedback())==1
    from app.telemetry.agent_metrics import learn_from_outcomes
    learn_from_outcomes([episode],"paper",store,"paper:"+episode["id"],quality="verified")
    assert not store.pending_paper_feedback()


def test_shared_cash_and_duplicate_signals(account):
    broker,_,clock=account
    order=enter(broker,clock,qty=200)
    assert broker.snapshot()["cash"]==9980
    with pytest.raises(ValueError,match="Duplicate"): enter(broker,clock,c=contract("SENSEX"))
    with pytest.raises(ValueError,match="Insufficient paper cash"): enter(broker,clock,c=contract("SENSEX"),qty=100,identifier="other")
    enter(broker,clock,c=contract("SENSEX"),qty=50,identifier="other")
    assert broker.snapshot()["open_positions"]==2
    assert len(broker.state["consumed_signals"])==2


def test_no_receipt_timestamp_fallback(account):
    broker,_,clock=account; c=contract(); q=quote(c,clock)
    q["exchange_timestamp"]=None
    assert not quote_is_fresh(q,clock["now"])
    with pytest.raises(ValueError,match="Stale"): broker.place_order(contract=c,quote=q,quantity=10,signal=signal(),now=clock["now"])
    assert broker.snapshot()["cash"]==30000


def test_stale_depth_and_wrong_contract_never_fill(account):
    broker,_,clock=account; c=contract()
    order=enter(broker,clock)
    old=quote(c,clock); clock["now"]+=timedelta(seconds=11)
    with pytest.raises(ValueError,match="fresh"): broker.close(order["id"],old,"STOP",clock["now"])
    with pytest.raises(ValueError,match="another contract"): broker.close(order["id"],quote(contract("SENSEX"),clock),"STOP",clock["now"])
    broker.mark({c["contract_id"]:quote(c,clock,bid=0)},clock["now"])
    assert not broker.snapshot()["valuation_complete"]
    assert broker.snapshot()["positions"]


def test_entries_recheck_session_after_charge_call(account):
    broker,_,clock=account
    clock["now"]=clock["now"].replace(hour=14,minute=29,second=59)
    class SlowFees(TestFees):
        def quote(self,*args):
            clock["now"]+=timedelta(seconds=2)
            return super().quote(*args)
    broker.cost=SlowFees()
    with pytest.raises(ValueError,match="cutoff"): enter(broker,clock)
    assert broker.snapshot()["cash"]==30000


def test_engine_forces_observed_exit_at_1510(account,monkeypatch):
    broker,store,clock=account; order=enter(broker,clock)
    clock["now"]=clock["now"].replace(hour=15,minute=10)
    engine=PaperEngine(Settings(_env_file=None),store,None,broker)
    monkeypatch.setattr("app.paper_engine.now_ist",lambda:clock["now"])
    monkeypatch.setattr(engine,"_session",lambda:session_state(clock["now"]))
    engine.quotes={contract()["contract_id"]:quote(contract(),clock,bid=101)}
    engine.cycle()
    assert not broker.snapshot()["positions"]
    assert store.list_records("trades")[0]["reason"]=="SESSION_EXIT"


def test_engine_cannot_invent_session_exit(account,monkeypatch):
    broker,store,clock=account; enter(broker,clock)
    clock["now"]=clock["now"].replace(hour=15,minute=10)
    engine=PaperEngine(Settings(_env_file=None),store,None,broker)
    monkeypatch.setattr("app.paper_engine.now_ist",lambda:clock["now"])
    monkeypatch.setattr(engine,"_session",lambda:session_state(clock["now"]))
    engine.cycle()
    assert broker.snapshot()["positions"] and broker.snapshot()["halted"]
    assert not store.list_records("trades")


@pytest.mark.parametrize("hour,minute,expected",[(9,14,"PREOPEN"),(9,15,"ENTRY_WINDOW"),(14,30,"MANAGE_ONLY"),(15,10,"EXIT_ONLY")])
def test_session_boundaries(hour,minute,expected):
    assert session_state(datetime(2026,9,4,hour,minute,tzinfo=IST))==expected


def test_live_broker_is_disabled_even_with_flag():
    with pytest.raises(RuntimeError,match="paper-only"): DhanBroker(live_enabled=True).place_order()


def test_dhan_quote_timestamp_uses_day_first_and_requires_actual_timestamp():
    from app.market_data import exchange_timestamp
    assert exchange_timestamp("04/09/2026 15:39:59")=="2026-09-04T15:39:59+05:30"
    assert exchange_timestamp("2026-09-04T10:00:00Z")=="2026-09-04T15:30:00+05:30"
    assert exchange_timestamp(None) is None
    assert exchange_timestamp("invalid") is None


def test_rest_snapshot_last_trade_does_not_prove_fresh_book():
    from app.session import quote_is_fresh
    now=datetime(2026,9,4,10,0,tzinfo=IST).isoformat()
    assert not quote_is_fresh({"source":"dhan_quote","exchange_timestamp":now,
                               "quote_update_timestamp":None},now)
    assert quote_is_fresh({"source":"dhan_market_feed","exchange_timestamp":now,
                          "quote_update_timestamp":now},now)
