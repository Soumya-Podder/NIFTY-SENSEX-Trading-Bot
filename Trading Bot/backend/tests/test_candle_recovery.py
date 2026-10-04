from types import SimpleNamespace
import pandas as pd
from tests.test_strategy_portfolio import portfolio_account, frame_fixture


def gateway(engine,frames,chain=None):
    calls=[]
    def candles(*args,**kwargs):
        calls.append(kwargs.get("cache_seconds"))
        return frames.pop(0).copy() if len(frames)>1 else frames[0].copy()
    engine.gateway=SimpleNamespace(credential_generation=0,refresh_credentials=lambda:False,
        candles=candles,chain=chain or (lambda *_a,**_k:[]))
    return calls


def test_current_session_refetch_repairs_gap_and_publishes_before_chain(tmp_path,monkeypatch):
    engine,_,store,clock=portfolio_account(tmp_path,monkeypatch)
    complete=frame_fixture(); gap=complete.drop(index=10)
    def chain(*_a,**_k):
        assert len(engine.frames["NIFTY"])==len(complete)
        raise ValueError("Chain temporarily unavailable")
    calls=gateway(engine,[gap,complete],chain)
    engine.refresh_symbol_data("NIFTY")
    health=engine.status["data_symbols"]["NIFTY"]
    assert calls==[10,0] and health["candle_status"]=="READY"
    assert health["repair_attempts"]==health["repair_successes"]==1
    assert health["chain_error"]=="Chain temporarily unavailable"
    assert store.get_record("data_health",str(clock["now"].date())+":NIFTY")["repair_successes"]==1


def test_unresolved_gap_stays_blocked_and_repair_is_rate_limited(tmp_path,monkeypatch):
    engine,_,_,_=portfolio_account(tmp_path,monkeypatch)
    calls=gateway(engine,[frame_fixture().drop(index=10)])
    engine.refresh_symbol_data("NIFTY")
    engine.refresh_symbol_data("NIFTY")
    health=engine.status["data_symbols"]["NIFTY"]
    assert calls==[10,0,10] and health["candle_status"]=="WAITING"
    assert health["repair_attempts"]==1 and health["repair_successes"]==0
    assert health["candle_reason"]=="Missing or duplicate session candles"


def test_new_generation_response_is_not_published_under_old_generation(tmp_path,monkeypatch):
    engine,_,_,_=portfolio_account(tmp_path,monkeypatch)
    def candles(*_a,**_k):
        engine.gateway.credential_generation+=1
        return frame_fixture()
    engine.gateway=SimpleNamespace(credential_generation=0,refresh_credentials=lambda:False,candles=candles)
    engine.refresh_symbol_data("NIFTY")
    assert "NIFTY" not in engine.frames


def test_future_candles_are_not_published(tmp_path,monkeypatch):
    engine,_,_,clock=portfolio_account(tmp_path,monkeypatch)
    frame=frame_fixture(); future=frame.iloc[[-1]].copy()
    future["timestamp"]=frame.timestamp.iloc[-1]+pd.Timedelta(minutes=2)
    gateway(engine,[pd.concat([frame,future])])
    engine.refresh_symbol_data("NIFTY")
    assert engine.frames["NIFTY"].timestamp.max()<pd.Timestamp(clock["now"])
