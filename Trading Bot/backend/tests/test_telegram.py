from types import SimpleNamespace
from app.telegram import TelegramNotifier
from app.config import Settings
from app.broker import PaperBroker
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
