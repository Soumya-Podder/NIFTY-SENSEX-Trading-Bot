import threading
import pytest
from app.backtest.jobs import BacktestJobs
from app.store import Store
from app.config import Settings
from app.backtest.data import dataset_path
from app.backtest.jobs import resolve_backtest_budgets
from app.backtest.jobs import ARCHIVE_STRIKE_OFFSETS,resolve_backtest_start


def manager(tmp_path):
    return BacktestJobs(Store(tmp_path/"jobs.db"),None,
        Settings(_env_file=None,dhan_client_id="test-only",dhan_access_token="test-only"),tmp_path)


def test_completed_report_survives_manager_restart(tmp_path,monkeypatch):
    jobs=manager(tmp_path)
    monkeypatch.setattr("app.backtest.jobs.dhan_research",lambda *a:{"status":"data_blocked","quality":"incomplete","trades":[],"issues":["Unit-test source intentionally incomplete"]})
    job=jobs.start({"source":"dhan","capital":30000})
    jobs.worker.join(timeout=5)
    assert not jobs.worker.is_alive()
    report=jobs.store.get_record("reports",job["id"])
    assert report["status"]=="data_blocked" and len(report["learning_run"])==8
    restored=manager(tmp_path); restored.recover()
    assert restored.store.get_record("backtest","latest")["report_id"]==job["id"]
    assert restored.store.get_record("reports",job["id"])==report


def test_single_worker_cancel_preserves_previous_report(tmp_path,monkeypatch):
    jobs=manager(tmp_path); entered=threading.Event(); release=threading.Event()
    jobs.store.put_record("backtest","latest",{"report_id":"previous"})
    def fetch(g,c,progress,cancel,settings):
        entered.set(); release.wait(timeout=3)
        if cancel(): raise InterruptedError("Cancelled")
        raise AssertionError("Cancellation was not observed")
    monkeypatch.setattr("app.backtest.jobs.dhan_research",fetch)
    job=jobs.start({"source":"dhan"})
    assert entered.wait(timeout=3)
    with pytest.raises(ValueError,match="already running"): jobs.start({"source":"dhan"})
    jobs.cancel(job["id"]); release.set(); jobs.worker.join(timeout=5)
    assert jobs.store.get_record("jobs",job["id"])["status"]=="cancelled"
    assert jobs.store.get_record("backtest","latest")["report_id"]=="previous"
    assert not jobs.store.list_records("learning_runs")


def test_interrupted_and_failed_jobs_are_not_spinners(tmp_path,monkeypatch):
    jobs=manager(tmp_path)
    jobs.store.put_record("jobs","old",{"id":"old","status":"running"})
    jobs.recover()
    assert jobs.store.get_record("jobs","old")["status"]=="interrupted"
    def fail(*args): raise RuntimeError("Data API unavailable")
    monkeypatch.setattr("app.backtest.jobs.dhan_research",fail)
    job=jobs.start({"source":"dhan"}); jobs.worker.join(timeout=5)
    saved=jobs.store.get_record("jobs",job["id"])
    assert saved["status"]=="failed" and saved["message"]=="Data API unavailable"


def test_dataset_path_cannot_escape_data_folder(tmp_path):
    with pytest.raises(ValueError): dataset_path(tmp_path,"../secrets.csv")


def test_backtest_budgets_are_not_capped_by_paper_settings():
    settings=Settings(_env_file=None)
    config=resolve_backtest_budgets({"capital":20000000,"risk_per_trade":5000},settings)
    assert config["capital"]==20000000 and config["risk_per_trade"]==5000
    assert config["daily_loss_limit"]==pytest.approx(5000*850/300) and config["correlated_risk_limit"]==5000
    assert settings.max_trade_risk_rupees==300 and settings.daily_loss_limit_rupees==850
    explicit=resolve_backtest_budgets({"risk_per_trade":700,"daily_loss_limit":9000,"correlated_risk_limit":8000},settings)
    assert explicit["daily_loss_limit"]==9000 and explicit["correlated_risk_limit"]==8000


def test_historical_archive_scope_is_exactly_requested_offsets():
    assert ARCHIVE_STRIKE_OFFSETS == ("ATM","ATM-4","ATM-3","ATM-2","ATM-1","ATM+1","ATM+2","ATM+3","ATM+4")
    assert len(ARCHIVE_STRIKE_OFFSETS)==9 and "ATM+10" not in ARCHIVE_STRIKE_OFFSETS and "ATM-10" not in ARCHIVE_STRIKE_OFFSETS


def test_zero_year_backtest_is_one_completed_session_not_one_year():
    from datetime import date
    end=date(2026,9,6)
    assert resolve_backtest_start(end,years=0)==end
    assert resolve_backtest_start(end,days=7,years=0)==date(2026,8,31)


def test_archive_request_matrix_uses_persisted_scope(tmp_path):
    import pandas as pd
    from app.backtest.jobs import download_history

    class Client:
        expired_options_data=object()

    class Gateway:
        client=Client()
        def underlyings(self):
            return [{"symbol":"NIFTY","security_id":"1","exchange_segment":"NSE_FNO"}]
        def candles(self,*_args,**_kwargs):
            return pd.DataFrame()
        def call(self,method,*args,**kwargs):
            calls.append((method,args))
            return {"ce":{"timestamp":[]},"pe":{"timestamp":[]}}

    calls=[]
    config={"from":"2026-01-01","to":"2026-01-01","symbols":["NIFTY"],
            "expiry_codes":[7],"strike_offsets":["ATM+9"]}
    counts=download_history(Gateway(),config,lambda *_:None,lambda:False,lambda *_:None)
    assert counts["total"]==5 and len(calls)==4
    assert {args[3] for _,args in calls}=={"WEEK","MONTH"}
    assert {args[4] for _,args in calls}=={7}
    assert {args[5] for _,args in calls}=={"ATM+9"}


@pytest.mark.parametrize("value",[0,-1,float("inf"),float("nan")])
def test_invalid_backtest_budgets_remain_rejected(value):
    with pytest.raises(ValueError): resolve_backtest_budgets({"capital":value},Settings(_env_file=None))


def test_download_job_does_not_replace_reports_or_teach_agents(tmp_path,monkeypatch):
    jobs=manager(tmp_path)
    jobs.store.put_record("backtest","latest",{"report_id":"previous"})
    monkeypatch.setattr("app.backtest.jobs.download_history",lambda *a:{"nonempty_responses":1,"empty_responses":2})
    job=jobs.start({"download_only":True,"source":"dhan","symbols":["NIFTY","SENSEX"]}); jobs.worker.join(timeout=5)
    assert jobs.store.get_record("jobs",job["id"])["status"]=="download_complete"
    manifest=jobs.store.get_record("history_archives",job["id"])
    assert manifest["coverage_status"]=="downloaded_source_responses_not_completeness_certified"
    assert manifest["symbols"]==["NIFTY","SENSEX"]
    assert jobs.store.get_record("backtest","latest")["report_id"]=="previous"
    assert not jobs.store.list_records("learning_runs")


def historical_gateway(tmp_path):
    from app.market_data import DhanGateway
    gateway=DhanGateway.__new__(DhanGateway)
    gateway.store=Store(tmp_path/"history.db")
    gateway.locks={"data":threading.Lock()}; gateway.last={"data":0}
    return gateway


def test_history_reuses_overlaps_field_subsets_and_restart(tmp_path):
    import pandas as pd
    gateway=historical_gateway(tmp_path); requests=[]
    def expired_options_data(*args):
        requests.append((args[8],args[9]))
        # Test-only observations; never inserted into the application database.
        timestamps=[int(t.timestamp()) for t in pd.date_range(args[8],args[9],inclusive="left",tz="Asia/Kolkata")]
        return {"status":"success","data":{"ce":{"timestamp":timestamps,**{f:[1]*len(timestamps) for f in args[7]}}}}
    def fetch(start,end,fields):
        return gateway.call(expired_options_data,"test","NSE_FNO","OPTIDX","WEEK",1,"ATM","CALL",fields,start,end,1,cache_seconds=-1)
    fetch("2026-01-01","2026-01-04",["close","iv"])
    fetch("2026-01-03","2026-01-06",["close","iv"])
    assert requests==[("2026-01-01","2026-01-04"),("2026-01-04","2026-01-06")]
    gateway=historical_gateway(tmp_path)
    result=fetch("2026-01-02","2026-01-05",["close"])
    assert len(result["ce"]["timestamp"])==3 and len(requests)==2
    assert "iv" not in result["ce"]


def test_local_history_only_stops_without_network_and_retains_empty_observations(tmp_path):
    from app.market_data import HISTORY_CACHE_ONLY
    import sqlite3
    gateway=historical_gateway(tmp_path); calls=[]
    def intraday_minute_data(*args):
        calls.append(args)
        return {"status":"success","data":{"timestamp":[]}}
    args=("test","IDX_I","INDEX","2026-01-01","2026-01-02",1,False)
    gateway.call(intraday_minute_data,*args,cache_seconds=-1)
    with sqlite3.connect(gateway.store.path) as c: c.execute("UPDATE history_cache SET expires_at=1")
    token=HISTORY_CACHE_ONLY.set(True)
    try:
        assert gateway.call(intraday_minute_data,*args,cache_seconds=-1)["timestamp"]==[]
        with pytest.raises(ValueError,match="Local historical candles missing"):
            gateway.call(intraday_minute_data,*args[:3],"2026-01-02","2026-01-03",1,False,cache_seconds=-1)
    finally: HISTORY_CACHE_ONLY.reset(token)
    assert len(calls)==1


def test_history_cache_does_not_hide_misaligned_fields(tmp_path):
    gateway=historical_gateway(tmp_path)
    def intraday_minute_data(*args):
        return {"status":"success","data":{"timestamp":[1767240000],"close":[]}}
    with pytest.raises(ValueError,match="misaligned"):
        gateway.call(intraday_minute_data,"test","IDX_I","INDEX","2026-01-01","2026-01-02",1,False,cache_seconds=-1)
