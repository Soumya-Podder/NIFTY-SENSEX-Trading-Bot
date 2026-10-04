"""Recorded fixtures only: no broker calls, production DB writes or Telegram."""
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
import json
import sqlite3
import zlib
import pytest
from app.config import Settings
from app.dhan_observations import DhanResponseRecorder, compare_chains
from app.market_context import window_changes
from app.market_data import DhanGateway
from app.store import Store
from tests.test_market_context import NOW


def chain(offset=0):
    return {"_observed_at":(NOW+timedelta(seconds=offset)).isoformat(),"_request_key":"same-expiry",
        "_api_capture_id":f"capture-{offset}","last_price":24000,"oc":{"24000.000000":{
            "ce":{"security_id":100,"oi":1000+offset,"previous_oi":900,"volume":2000+2*offset,
                  "last_price":100+offset,"implied_volatility":20+offset/100,
                  "top_bid_price":99,"top_ask_price":101,"top_bid_quantity":50,"top_ask_quantity":50,
                  "greeks":{"delta":.5+offset/1000,"gamma":.001,"theta":-4,"vega":10}},
            "pe":{"security_id":101,"oi":2000-offset,"volume":1000,"last_price":80,
                  "greeks":{"delta":-.5}}}}}


def test_changes_use_previous_observation_not_previous_day():
    result=compare_chains(chain(60),chain())
    assert result["status"]=="OBSERVED" and result["interval_seconds"]==60
    ce=result["contracts"]["100"]["changes"]; pe=result["contracts"]["101"]["changes"]
    assert ce["oi"]==60 and ce["volume"]==120 and pe["oi"]==-60
    assert ce["iv"]==pytest.approx(.6) and ce["delta"]==pytest.approx(.06)
    assert ce["theta"]==0 and pe["iv"] is None
    assert result["previous_response_id"]=="capture-0"


@pytest.mark.parametrize("defect",["first","same_time","future","overnight","expiry","identity"])
def test_invalid_baselines_never_create_changes(defect):
    previous=chain(); current=chain(60)
    if defect=="first": previous=None
    if defect=="same_time": current=chain()
    if defect=="future": previous=chain(120)
    if defect=="overnight": current=chain(86400)
    if defect=="expiry": current["_request_key"]="next-expiry"
    if defect=="identity": current["oc"]["24000.000000"]["pe"]["security_id"]=100
    result=compare_chains(current,previous)
    assert result["status"]=="DATA_UNAVAILABLE" and "contracts" not in result


def test_contract_roll_and_volume_reset_are_not_money_flow():
    current=chain(180)
    current["oc"]["24000.000000"]["ce"]["volume"]=1
    current["oc"]["24000.000000"]["pe"]["security_id"]=102
    result=compare_chains(current,chain())
    assert result["long_gap"] and result["matched_contracts"]==1
    assert result["added_contracts"]==result["removed_contracts"]==1
    assert result["contracts"]["100"]["volume_status"]=="RESET_OR_CORRECTION"
    assert result["contracts"]["100"]["changes"]["volume"] is None


def test_window_summary_preserves_fixed_contract_coverage():
    comparison=compare_chains(chain(60),chain())
    rows=[{"security_id":sid,"strike":24000.,"option_type":side,"api_response_id":"capture-60",
        "observation_change":{**{k:v for k,v in comparison.items() if k!="contracts"},
            "contract":comparison["contracts"].get(sid)}} for sid,side in (("100","CALL"),("101","PUT"),("999","CALL"))]
    result=window_changes(rows)
    assert result["status"]=="PARTIAL" and result["matched_contracts"]==2 and result["window_contracts"]==3
    assert result["call_oi_change"]==60 and result["put_oi_change"]==-60
    assert result["response_id"]=="capture-60" and len(result["contracts"])==2


def test_full_market_payload_compressed_persistent_and_secret_free(tmp_path):
    path=tmp_path/"api.db"; recorder=DhanResponseRecorder(path,min_free_bytes=0)
    recorder.start()
    payload=chain(); payload["access_token"]="TOP-SECRET"; payload["headers"]={"client-id":"TOP-SECRET"}
    payload["oc"]["24000.000000"]["ce"]["raw"]={"secret":"TOP-SECRET"}
    identifier=recorder.record_response("option_chain",(13,"IDX_I","2026-10-01"),payload,2,NOW.isoformat())
    assert recorder.record_response("place_order",(),payload,2,NOW.isoformat()) is None
    recorder.stop()
    saved=DhanResponseRecorder(path,min_free_bytes=0).read(identifier)
    assert saved["credential_generation"]==2 and saved["received_at"]==NOW.isoformat()
    assert saved["response"]["request"]==[13,"IDX_I","2026-10-01"]
    assert len(saved["response"]["response"]["oc"]["24000.000000"])==2
    with sqlite3.connect(path) as db:
        raw=db.execute("SELECT payload FROM observations").fetchone()[0]
    assert isinstance(raw,bytes) and "TOP-SECRET" not in zlib.decompress(raw).decode()
    assert recorder.status()["persisted_this_run"]==1


@pytest.mark.parametrize("method,args,payload",[
    ("quote_data",({"NSE_FNO":[100]},),{"NSE_FNO":{"100":{"last_trade_time":"25/09/2026 10:05:00",
        "depth":{"buy":[{"quantity":50,"orders":2,"price":99.5}]},"oi_day_low":1000}}}),
    ("expired_options_data",("13","NSE_FNO","OPTIDX","WEEK",1,"ATM+6","CALL",["open","iv","oi"],"2026-09-01","2026-09-25",1),
        {"ce":{"open":[100],"iv":[20],"oi":[1000],"timestamp":[1790000000]},"pe":None}),
    ("expiry_list",(13,"IDX_I"),["2026-10-01","2026-10-08"]),
])
def test_documented_market_and_history_fields_survive_capture(tmp_path,method,args,payload):
    recorder=DhanResponseRecorder(tmp_path/"api.db",min_free_bytes=0); recorder.start()
    identifier=recorder.record_response(method,args,payload,0,NOW.isoformat()); recorder.stop()
    saved=recorder.read(identifier)["response"]
    assert saved["response"]==payload and saved["request"]==list(args)


def test_response_archive_reports_storage_limit_without_deleting_history(tmp_path):
    recorder=DhanResponseRecorder(tmp_path/"api.db",min_free_bytes=0,max_bytes=1)
    recorder.start()
    recorder.record_response("option_chain",(13,"IDX_I","2026-10-01"),chain(),0,NOW.isoformat())
    recorder.stop()
    assert recorder.status()["error"]=="STORAGE_LIMIT" and recorder.status()["dropped_this_run"]==1


@pytest.fixture
def gateway_fixture(tmp_path,monkeypatch):
    import dhanhq
    state={"calls":0,"now":NOW,"fail":False}
    class Client:
        def __init__(self,_): self.dhan_http=SimpleNamespace(timeout=None)
        def option_chain(self,*args):
            state["calls"]+=1
            if state["fail"]: return {"status":"failure","remarks":"secret-token-echo"}
            result=chain(state["calls"])
            return {"status":"success","data":{k:v for k,v in result.items() if not k.startswith("_")}}
    monkeypatch.setattr(dhanhq,"dhanhq",Client)
    monkeypatch.setattr("app.market_data.time.sleep",lambda _:None)
    monkeypatch.setattr("app.market_data.now_ist",lambda:state["now"])
    recorder=DhanResponseRecorder(tmp_path/"api.db",min_free_bytes=0); recorder.start()
    gateway=DhanGateway(Settings(_env_file=None),Store(tmp_path/"store.db")); gateway.response_recorder=recorder
    yield gateway,recorder,state
    recorder.stop()


def fetch(gateway,cache_seconds=0,expiry="2026-10-01"):
    return gateway.call(gateway.client.option_chain,13,"IDX_I",expiry,kind="chain",cache_seconds=cache_seconds)


def test_only_real_requests_recorded_and_previous_baseline_survives_restart(gateway_fixture):
    gateway,recorder,state=gateway_fixture
    first=fetch(gateway,30)
    state["now"]+=timedelta(seconds=10)
    assert fetch(gateway,30)==first and state["calls"]==1
    state["now"]+=timedelta(seconds=50)
    restarted=DhanGateway(gateway.settings,gateway.store); restarted.response_recorder=recorder
    second=fetch(restarted)
    assert second["_comparison"]["contracts"]["100"]["changes"]["oi"]==1
    assert second["_comparison"]["previous_response_id"]==first["_api_capture_id"]
    state["now"]+=timedelta(seconds=60)
    rolled=fetch(restarted,expiry="2026-10-08")
    assert rolled["_comparison"]["status"]=="DATA_UNAVAILABLE"
    recorder.stop()
    assert recorder.persisted==3 and recorder.read(second["_api_capture_id"])


def test_request_failure_is_recorded_without_response_or_error_secrets(gateway_fixture):
    gateway,recorder,state=gateway_fixture; state["fail"]=True
    with pytest.raises(RuntimeError): fetch(gateway)
    recorder.stop()
    with sqlite3.connect(recorder.path) as db:
        rows=db.execute("SELECT payload FROM observations").fetchall()
    assert len(rows)==3
    for row in rows:
        decoded=zlib.decompress(row[0]).decode(); payload=json.loads(decoded)
        assert payload["outcome"]=="REQUEST_FAILED" and payload["response"] is None
        assert "secret-token-echo" not in decoded


def test_rotation_discards_old_response_and_storage_failure_does_not_stop_quotes(gateway_fixture):
    gateway,recorder,state=gateway_fixture
    def rotate():
        if state["calls"]==1: gateway.credential_generation=1
    gateway.refresh_credentials=rotate
    result=fetch(gateway)
    recorder.stop()
    with sqlite3.connect(recorder.path) as db:
        rows=[json.loads(zlib.decompress(r[0])) for r in db.execute("SELECT payload FROM observations ORDER BY rowid")]
    assert [r["outcome"] for r in rows]==["CREDENTIAL_CHANGED_DISCARDED","SUCCESS"]
    assert rows[0]["response"] is None and result["_comparison"]["status"]=="DATA_UNAVAILABLE"
    state["now"]+=timedelta(seconds=60)
    def fail(*a,**kw): raise OSError("test disk error")
    recorder.record_response=fail
    assert fetch(gateway)["last_price"]==24000
    assert recorder.status()["error"]=="CAPTURE_FAILED" and recorder.status()["dropped_this_run"]==1
