from app.session import session_state
from app.market_calendar import calendar_info


def test_published_holiday_prevents_regular_entries():
    assert session_state("2026-09-14T10:00:00+05:30")=="HOLIDAY"
    assert calendar_info("2026-09-14")["holiday"]=="Ganesh Chaturthi"
    assert session_state("2026-09-15T09:15:00+05:30")=="ENTRY_WINDOW"
    assert session_state("2026-09-15T15:05:00+05:30")=="EXIT_ONLY"


def test_calendar_does_not_claim_unknown_year_or_complete_bse_coverage():
    assert not calendar_info("2027-09-14")["year_supported"]
    assert not calendar_info("2026-09-14")["bse_calendar_independently_verified"]
