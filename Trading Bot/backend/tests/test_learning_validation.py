"""Controlled validation inputs only; never persisted as trading evidence."""
from copy import deepcopy
from datetime import date, timedelta

import pytest

from app.learning_validation import replay_evidence, VERSION


def account(improvement=0):
    rows=[]; daily=[]
    for i in range(20):
        day=str(date(2025,1,1)+timedelta(days=i))
        pnl=10+improvement if i<15 else 0
        daily.append({"date":day,"pnl":pnl*2})
        if i<15:
            for n in range(2):
                rows.append({"id":f"{i}-{n}","entry_ts":f"{day}T10:0{n}:00+05:30",
                             "exit_ts":f"{day}T10:1{n}:00+05:30","pnl":pnl,
                             "gross_pnl":pnl+2,"costs":2,"quality":"verified"})
    return {"quality":"verified","status":"complete","daily":daily,"trades":rows}


def check(candidate,baseline=None):
    return replay_evidence(candidate,baseline or account(),"2025-01-01","2025-01-20")


def test_reconciled_accounts_include_observed_no_trade_sessions():
    result=check(account(20))
    assert result["passed"] and result["version"]==VERSION
    assert result["paired_days"]==20 and result["improvement_lower_bound"]>0


@pytest.mark.parametrize("mutation",[
    lambda r:r.pop("daily"),
    lambda r:r["daily"].pop(0),
    lambda r:r["daily"].append(deepcopy(r["daily"][0])),
    lambda r:r["daily"][0].update(pnl=999),
    lambda r:r["daily"][0].update(pnl=float("nan")),
    lambda r:r["trades"].append(deepcopy(r["trades"][0])),
    lambda r:r["trades"][0].update(exit_ts="invalid"),
    lambda r:r["trades"][0].update(exit_ts="2025-01-01T09:00:00+05:30"),
    lambda r:r["trades"][0].update(exit_ts="2025-01-02T10:00:00+05:30"),
    lambda r:r["trades"][0].update(learning_eligible=False),
    lambda r:r.update(learning_eligible=False),
    lambda r:r.update(estimation={"estimated_exits":1}),
])
def test_malformed_or_estimated_evidence_cannot_promote(mutation):
    candidate=account(20); mutation(candidate)
    assert not check(candidate)["passed"]


def test_omitting_trade_days_from_both_account_calendars_is_rejected():
    candidate=account(20); baseline=account()
    candidate["daily"].pop(0); baseline["daily"].pop(0)
    assert not check(candidate,baseline)["passed"]


def test_different_observed_no_trade_coverage_is_rejected():
    candidate=account(20); candidate["daily"].pop()
    assert not check(candidate)["passed"]
