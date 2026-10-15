from datetime import datetime
from zoneinfo import ZoneInfo
import pytest
from paper_service import maintain_session_power


@pytest.mark.parametrize('stamp,flag',[
    ('2026-10-14T09:10',0x80000001),
    ('2026-10-14T13:20',0x80000001),
    ('2026-10-14T15:34',0x80000001),
    ('2026-10-14T15:35',0x80000000),
    ('2026-10-14T07:00',0x80000000),
    ('2026-10-11T12:00',0x80000000)])
def test_only_market_monitoring_prevents_idle_sleep(stamp,flag):
    calls=[]
    assert maintain_session_power(datetime.fromisoformat(stamp).replace(tzinfo=ZoneInfo('Asia/Kolkata')),
        lambda value:calls.append(value) or 1)
    assert calls==[flag]


def test_failed_windows_power_request_is_not_reported_as_success():
    assert not maintain_session_power(datetime(2026,10,14,12),lambda _:0)
