"""Published NSE derivatives closures used as a shared portfolio entry gate.

This is a sourced closure list, not proof of complete historical session coverage.
Special sessions and later exchange amendments require an updated manifest.
"""
SOURCE="https://nsearchives.nseindia.com/content/circulars/FAOP71777.pdf"
CHECKED_AT="2026-09-13"
NSE_CLOSURES_2026={
    "2026-01-26":"Republic Day", "2026-03-03":"Holi", "2026-03-26":"Shri Ram Navami",
    "2026-03-31":"Shri Mahavir Jayanti", "2026-04-03":"Good Friday",
    "2026-04-14":"Dr. Baba Saheb Ambedkar Jayanti", "2026-05-01":"Maharashtra Day",
    "2026-05-28":"Bakri Id", "2026-06-26":"Muharram", "2026-09-14":"Ganesh Chaturthi",
    "2026-10-02":"Mahatma Gandhi Jayanti", "2026-10-20":"Dussehra",
    "2026-11-10":"Diwali-Balipratipada", "2026-11-24":"Guru Nanak Dev Jayanti",
    "2026-12-25":"Christmas",
}


def calendar_info(day):
    date=str(day)[:10]
    return {"date":date,"closed":date in NSE_CLOSURES_2026,"holiday":NSE_CLOSURES_2026.get(date),
            "source":SOURCE,"checked_at":CHECKED_AT,"scope":"NSE derivatives closures; shared portfolio gate",
            "complete_historical_calendar_verified":False,
            "bse_calendar_independently_verified":False,
            "year_supported":date.startswith("2026-")}
