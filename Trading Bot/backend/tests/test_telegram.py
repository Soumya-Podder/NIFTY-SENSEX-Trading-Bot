from types import SimpleNamespace
from app.telegram import TelegramNotifier
from app.config import Settings
from app.broker import PaperBroker
from app.paper_engine import PaperEngine
from app.expectancy import CostModel
from tests.test_paper import plan_account,contract,quote,signal


def test_disabled_or_unconfigured_telegram_never_queues():
    assert not TelegramNotifier(enabled=False).notify("hello")
    assert not TelegramNotifier(enabled=True).notify("hello")


def test_paper_entry_and_exit_queue_local_notifications(tmp_path):
    broker,store,clock=plan_account(tmp_path)
    messages=[]
    broker.notifier=SimpleNamespace(notify=lambda message: messages.append(message))
    c=contract(); order=broker.place_order(contract=c,quote=quote(c,clock),quantity=10,
        signal=signal(),now=clock["now"])
    broker.close(order["id"],quote(c,clock,bid=110),"TARGET",clock["now"])
    assert len(messages)==2
    assert messages[0].startswith("PAPER ENTRY CONFIRMED")
    assert "Current session P&L:" in messages[0]
    assert messages[1].startswith("PAPER EXIT CONFIRMED")
    assert "Trade net P&L:" in messages[1] and "Current session P&L:" in messages[1]


def test_non_trade_state_changes_do_not_notify_telegram(tmp_path):
    broker,store,clock=plan_account(tmp_path)
    messages=[]
    broker.notifier=SimpleNamespace(notify=lambda message: messages.append(message))
    broker.control(halted=True,reason="TEST_HALT")
    assert messages==[]


def test_percentage_only_stop_is_rejected(tmp_path):
    broker,store,clock=plan_account(tmp_path)
    candidate=signal()
    candidate.pop("stop_price")
    try:
        broker.place_order(contract=contract(),quote=quote(contract(),clock),quantity=10,
            signal=candidate,now=clock["now"])
    except ValueError as exc:
        assert "market-derived premium stop" in str(exc)
    else:
        raise AssertionError("percentage-only stop must not be executable")


def test_session_reports_are_idempotent_and_position_updates_are_throttled(tmp_path,monkeypatch):
    broker,store,_=plan_account(tmp_path)
    messages=[]
    broker.notifier=SimpleNamespace(enabled=True,configured=True,notify=lambda message: messages.append(message) or True)
    engine=object.__new__(PaperEngine)
    engine.broker=broker; engine.store=store
    engine.settings=Settings(_env_file=None,telegram_position_update_seconds=2,telegram_session_report_time='15:35')
    engine.telegram_position_updates={}; engine.strategies=[{'name':'Trend pullback'}]
    engine.market=SimpleNamespace(recorder=SimpleNamespace(status=lambda:{'persisted_this_run':123,'dropped_this_run':0}))
    account={'initial_capital':30000,'equity':30000,'positions':[],'open_positions':0,
             'session_pnl':0,'liquidation_pnl':0}
    import pandas as pd
    start=pd.Timestamp('2026-09-25 09:15:00',tz='Asia/Kolkata').to_pydatetime()
    engine._telegram_session_reports(start,account)
    engine._telegram_session_reports(start,account)
    assert sum(message.startswith('PAPER SESSION START') for message in messages)==1

    position={'id':'paper-1','symbol':'NIFTY','option_type':'PUT','strike':23000,
              'qty':65,'entry':100,'mark':102,'entry_charges_remaining':20,'exit_cost_estimate':10}
    account.update(positions=[position],open_positions=1,liquidation_pnl=100,session_pnl=130)
    clock={'value':100.0}; monkeypatch.setattr('app.paper_engine.time.monotonic',lambda:clock['value'])
    engine._telegram_session_reports(start.replace(hour=10),account)
    clock['value']=101; engine._telegram_session_reports(start.replace(hour=10),account)
    clock['value']=102.1; engine._telegram_session_reports(start.replace(hour=10),account)
    assert sum(message.startswith('PAPER POSITION UPDATE') for message in messages)==2

    account.update(positions=[],open_positions=0,liquidation_pnl=0,session_pnl=0)
    store.record_event({'id':'reason-1','timestamp':'2026-09-25T10:00:00+05:30','agent':'Scanner',
                        'symbol':'NIFTY','status':'WAITING','summary':'No confirmed trend resumption'})
    end=start.replace(hour=15,minute=35)
    engine._telegram_session_reports(end,account)
    engine._telegram_session_reports(end,account)
    reports=[message for message in messages if message.startswith('PAPER SESSION REPORT')]
    assert len(reports)==1 and 'No trade was taken' in reports[0]
    assert 'No confirmed trend resumption' in reports[0]


def test_session_reports_do_not_send_on_weekends(tmp_path):
    broker,store,_=plan_account(tmp_path); messages=[]
    broker.notifier=SimpleNamespace(enabled=True,configured=True,notify=lambda message: messages.append(message) or True)
    engine=object.__new__(PaperEngine); engine.broker=broker; engine.store=store
    engine.settings=Settings(_env_file=None); engine.telegram_position_updates={}; engine.strategies=[]; engine.market=None
    import pandas as pd
    account={'initial_capital':30000,'equity':30000,'positions':[],'open_positions':0,'session_pnl':0,'liquidation_pnl':0}
    engine._telegram_session_reports(pd.Timestamp('2026-09-26 09:15',tz='Asia/Kolkata').to_pydatetime(),account)
    assert messages==[]
