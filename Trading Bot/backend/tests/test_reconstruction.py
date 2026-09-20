"""Isolated fixture prices: never imported by application runtime."""
from collections import defaultdict
import pandas as pd
import pytest
from app.backtest.reconstruction import merge_series, ResearchReplay, dhan_research
from app.backtest.reports import report_from_run
from app.config import Settings
from app.store import Store
from app.telemetry.agent_metrics import learn_from_outcomes


def series(stamp, strike=101, price=10):
    return {"timestamp":[int(stamp.timestamp())], "strike":[strike], "spot":[100],
            "open":[price], "high":[price+1], "low":[price-1], "close":[price], "volume":[100], "oi":[200]}


def test_fixed_strike_can_move_offsets_and_conflicts_stay_quarantined():
    book={}; rejected=set(); atm=defaultdict(set)
    t=pd.Timestamp("2026-08-31 09:30",tz="Asia/Kolkata")
    def add(time,offset,price=10):
        return merge_series(book,rejected,atm,series(time,price=price),"NIFTY","CALL","WEEK",offset,"2026-08-31","2026-08-31")
    add(t,"ATM+1"); add(t+pd.Timedelta(minutes=1),"ATM")
    assert len({q["contract_id"] for q in book.values()})==1
    assert all(q["expiry"] is None and not q["identity_verified"] for q in book.values())
    add(t,"ATM+2",11); add(t,"ATM+3")
    assert len(rejected)==1 and len(book)==1
    assert atm[(t+pd.Timedelta(minutes=1),"NIFTY","CALL")]=={101}


def test_bad_arrays_are_not_padded():
    t=pd.Timestamp("2026-08-31 09:30",tz="Asia/Kolkata")
    data=series(t); data["strike"]=[]
    with pytest.raises(ValueError,match="unequal"):
        merge_series({},set(),defaultdict(set),data,"NIFTY","CALL","WEEK","ATM+1","2026-08-31","2026-08-31")


def test_negative_provider_volume_is_quarantined_not_guessed():
    t=pd.Timestamp("2026-08-31 09:30",tz="Asia/Kolkata")
    data=series(t); data["volume"]=[-4275834196]
    book={}; rejected=set(); invalid=[]
    assert merge_series(book,rejected,defaultdict(set),data,"NIFTY","CALL","WEEK","ATM+1","2026-08-31","2026-08-31",invalid)==0
    assert not book and len(rejected)==1
    assert invalid[0]["values"]["volume"]==-4275834196 and invalid[0]["reason"]=="Negative volume in source candle"


def test_invalid_after_strategy_exit_does_not_block_session():
    t=pd.Timestamp("2026-08-31 15:20",tz="Asia/Kolkata")
    data=series(t,price=0); invalid=[]; rejected=set()
    merge_series({},rejected,defaultdict(set),data,"NIFTY","CALL","WEEK","ATM+1","2026-08-31","2026-08-31",invalid)
    assert not invalid and not rejected


def run_fixture(missing_exit=False, gap_entry=False, recover_exit=False, budget_overrides=None):
    cfg={"capital":30000,"risk_per_trade":600,"symbols":["NIFTY"]}
    cfg.update(budget_overrides or {})
    replay=ResearchReplay(cfg,Settings(_env_file=None),{"NIFTY":{"lot_size":10,"historical_verified":False}})
    dates=pd.date_range("2026-08-31 09:15","2026-08-31 15:05",freq="min",tz="Asia/Kolkata")
    frame=pd.DataFrame([{"timestamp":t,"symbol":"NIFTY","open":100,"high":101,"low":99,"close":100,"volume":100} for t in dates])
    def signal(row,*args):
        if row["timestamp"].strftime("%H:%M")!="09:30": return None
        return {"id":"fixture-only","symbol":"NIFTY","option_type":"CALL","stop_percent":.1,"target_percent":.2,
            "setup":"fixture-only","regime":"fixture-only","agent_contexts":{"Scanner":"fixture-only"}}
    replay.pipeline.signal=signal
    book={}; atm=defaultdict(set)
    for t in dates:
        hhmm=t.strftime("%H:%M")
        atm[(t,"NIFTY","CALL")].add(100)
        if (missing_exit and hhmm=="09:32") or (gap_entry and hhmm=="09:31"): continue
        # No forward information at the 09:30 signal; next-bar entry jumps from 10 to 11.
        price=10 if hhmm<="09:30" else 11
        q={"contract_id":"fixed-fixture","strike":101,"open":price,"high":price+.1,"low":price-.1,"close":price,
            "volume":100,"oi":200,"option_type":"CALL","expiry_bucket":"WEEK:1","offsets":["ATM+1" if hhmm<="09:31" else "ATM"]}
        if hhmm=="09:32": q.update(high=15,low=8)  # both barriers; stop wins
        book[(t,"NIFTY","fixed-fixture")]=q
    def recover(stamp,symbol,side):
        q={**book[(stamp+pd.Timedelta(minutes=1),symbol,"fixed-fixture")],"high":15,"low":8,"offsets":["ATM+4"]}
        book[(stamp,symbol,"fixed-fixture")]=q
    replay.consume(frame,book,atm,lambda:False,recover if recover_exit else None)
    return replay,replay.result([]),cfg


def test_next_bar_entry_fixed_strike_stop_first_and_net_unavailable():
    replay,result,cfg=run_fixture()
    assert len(result["trades"])==1
    trade=result["trades"][0]
    assert trade["entry_premium"]==11 and "09:31" in trade["entry_time"]
    assert trade["reason"]=="STOP" and trade["exit_premium"]==pytest.approx(9.9)
    assert trade["costs"] is None and trade["pnl"] is None
    assert trade["quantity"]*trade["entry_premium"]<=cfg["capital"]
    assert abs(trade["gross_pnl"])<=cfg["risk_per_trade"]
    assert replay.offset_switches==1
    assert result["metrics"]["total_pnl"] is None and result["metrics"]["total_charges"] is None
    report=report_from_run(result,cfg)
    assert report["agent_performance"][0]["pnl"]==trade["gross_pnl"]
    assert report["trades"][0]["pnl"] is None


def test_missing_exit_stops_portfolio_and_withholds_headlines():
    _,result,_=run_fixture(missing_exit=True)
    assert result["status"]=="research_partial" and len(result["unresolved"])==1
    assert result["metrics"]["gross_pnl"] is None
    assert result["metrics"]["profit_factor"] is None
    assert not result["trades"]


def test_plan_replay_calculates_observed_premium_pnl(monkeypatch):
    def candidates(*args,**kwargs):
        return [{"setup":"ORB_RETEST_LONG","option_type":"CALL","timestamp":"2026-08-31T09:30:00+05:30",
                 "break_timestamp":"2026-08-31T09:28:00+05:30","retest_timestamp":"2026-08-31T09:29:00+05:30",
                 "invalidation":95}]
    monkeypatch.setattr("app.backtest.reconstruction.opening_range_retest",candidates)
    original=ResearchReplay.__init__
    def init(self,config,settings,lots):
        lots["NIFTY"]["tick_size"]=.05
        original(self,config,settings,lots)
    monkeypatch.setattr(ResearchReplay,"__init__",init)
    _,result,_=run_fixture(budget_overrides={"strategy_version":"orb-retest-v1"})
    trade=result["trades"][0]
    assert trade["setup"]=="ORB_RETEST_LONG"
    assert trade["quantity"]==10
    assert trade["stop"]==pytest.approx(9.85)
    assert trade["gross_pnl"]==pytest.approx((9.85-11)*10)
    assert trade["pnl"] is None and trade["costs"] is None
    assert result["replay_version"]=="orb-retest-rolling-v1"


def test_research_sizing_honors_larger_backtest_risk_not_paper_cap():
    _,result,_=run_fixture(budget_overrides={"capital":100000,"risk_per_trade":2000,"daily_loss_limit":5000,"correlated_risk_limit":2000})
    trade=result["trades"][0]
    assert 600 < trade["risk"] <= 2000
    assert trade["quantity"]*trade["entry_premium"]<=100000


def test_missing_entry_is_not_replaced_with_later_open():
    replay,result,_=run_fixture(gap_entry=True)
    assert not result["trades"] and replay.skipped==1
    assert result["status"]=="research_partial" and len(result["skipped_entries"])==1


def test_selected_entry_can_be_recovered_at_same_minute_in_wider_offset():
    _,result,_=run_fixture(gap_entry=True,recover_exit=True)
    assert result["status"]=="research_complete" and len(result["trades"])==1
    assert "09:31" in result["trades"][0]["entry_time"]
    assert result["trades"][0]["entry_offsets"]==["ATM+4"]


def test_wider_offset_recovery_keeps_original_strike():
    _,result,_=run_fixture(missing_exit=True,recover_exit=True)
    assert result["status"]=="research_complete" and not result["unresolved"]
    assert result["trades"][0]["strike"]==101
    assert result["trades"][0]["exit_offsets"]==["ATM+4"]


def test_research_feedback_is_recorded_without_promotions(tmp_path):
    _,result,_=run_fixture()
    store=Store(tmp_path/"research-test.db")
    learn_from_outcomes(result["trades"],"dhan",store,"research-fixture",quality="research")
    entries=store.get_record("learning_runs","research-fixture")["entries"]
    assert len(entries)==8 and all(e["validation_status"]=="DATA_BLOCKED" for e in entries)
    assert entries[0]["metadata"]["research_gross_outcomes"][0]["gross_pnl"]<0
    assert not store.active_learning_policies()


def test_downloader_uses_full_requested_range_in_bounded_chunks():
    class EmptyGateway:
        calls=[]
        def underlyings(self): return [{"symbol":"NIFTY"}]
        def contracts(self,symbol): return [{"expiry":"2026-09-08","lot_size":10,"metadata_observed_on":"2026-09-06"}]
        def candles(self,symbol,start,end,**kwargs):
            self.calls.append((start,end))
            return pd.DataFrame(columns=["timestamp","symbol"])
    g=EmptyGateway()
    with pytest.raises(ValueError,match="no index candles"):
        dhan_research(g,{"from":"2026-06-01","to":"2026-08-31","symbols":["NIFTY"]},lambda *a:None,lambda:False,Settings(_env_file=None))
    assert g.calls[0][0]=="2026-06-01" and g.calls[-1][1]=="2026-09-01"
    assert all((pd.Timestamp(b)-pd.Timestamp(a)).days<=29 for a,b in g.calls)


def test_retained_history_reuses_sqlite_without_provider_call(tmp_path):
    from app.market_data import DhanGateway
    settings=Settings(_env_file=None)
    store=Store(tmp_path/"cache-test.db")
    gateway=DhanGateway(settings,store)
    calls=[]
    def fixture_history():
        calls.append(True)
        return {"status":"success","data":{"timestamp":[1],"close":[10]}}
    first=gateway.call(fixture_history,cache_seconds=-1)
    restarted=DhanGateway(settings,Store(tmp_path/"cache-test.db"))
    assert restarted.call(fixture_history,cache_seconds=-1)==first
    assert len(calls)==1 and store.cache_summary()["retained_responses"]==1


def test_empty_history_is_not_retained_forever(tmp_path):
    from app.market_data import DhanGateway
    store=Store(tmp_path/"empty-cache-test.db")
    gateway=DhanGateway(Settings(_env_file=None),store)
    def fixture_empty(): return {"status":"success","data":{"ce":None,"pe":None}}
    gateway.call(fixture_empty,cache_seconds=-1)
    gateway.call(fixture_empty,cache_seconds=-1)
    assert store.cache_summary()["retained_responses"]==0


def test_lessons_propose_from_agent_contexts_without_claiming_improvement():
    from app.telemetry.agent_metrics import outcome_lessons
    trades=[{"id":str(i),"gross_pnl":-10,"pnl":None,"reason":"STOP","agent_contexts":{"Setup":"fixture-context"}} for i in range(20)]
    lessons=outcome_lessons(trades,"Setup","research",20)
    assert lessons[0]["pnl"]==-200 and lessons[0]["loss_exit_reasons"]=={"STOP":20}
    assert lessons[0]["status"]=="PROPOSED_NOT_VALIDATED" and not lessons[0]["applied"]
    assert outcome_lessons(trades,"Risk","research",20)==[]
    assert outcome_lessons(trades[:1],"Setup","research",20)[0]["status"]=="OBSERVATION"
    winners=[{**t,"gross_pnl":10,"reason":"TARGET"} for t in trades]
    lesson=outcome_lessons(winners,"Setup","research",20)[0]
    assert lesson["action"]=="FOCUS_CANDIDATE" and lesson["status"]=="PROPOSED_NOT_VALIDATED"
    assert lesson["win_exit_reasons"]=={"TARGET":20} and not lesson["applied"]


def test_intrabar_exit_proceeds_cannot_fund_another_opening_fill():
    cfg={"capital":100,"risk_per_trade":600,"symbols":["NIFTY","SENSEX"]}
    replay=ResearchReplay(cfg,Settings(_env_file=None),{s:{"lot_size":1} for s in cfg["symbols"]})
    dates=pd.date_range("2026-08-31 09:15","2026-08-31 15:05",freq="min",tz="Asia/Kolkata")
    frame=pd.DataFrame([{"timestamp":t,"symbol":s,"open":100,"high":101,"low":99,"close":100,"volume":100} for t in dates for s in cfg["symbols"]])
    def signal(row,*args):
        if row["timestamp"].strftime("%H:%M")!="09:30": return None
        return {"id":row["symbol"],"symbol":row["symbol"],"option_type":"CALL","stop_percent":.1,"target_percent":.2,
                "setup":"fixture-only","regime":"fixture-only","agent_contexts":{}}
    replay.pipeline.signal=signal
    book={}; atm=defaultdict(set)
    for t in dates:
        for symbol in cfg["symbols"]:
            price=100 if symbol=="NIFTY" else 50
            atm[(t,symbol,"CALL")].add(100)
            book[(t,symbol,symbol)]={"contract_id":symbol,"strike":101,"option_type":"CALL","expiry_bucket":"WEEK:1",
                "open":price,"close":price,"high":price+1,"low":price-10,"oi":100,"volume":100,"offsets":["ATM+1"]}
    replay.consume(frame,book,atm,lambda:False)
    assert [t["symbol"] for t in replay.trades]==["NIFTY"]
    assert replay.trades[0]["reason"]=="STOP"
    assert replay.cash==90


def test_research_replay_net_costs_are_excluded_from_learning(tmp_path):
    from app.ai import LearningService
    dates = pd.date_range("2026-08-31 09:15", "2026-08-31 15:05", freq="min", tz="Asia/Kolkata")
    frame = pd.DataFrame([{"timestamp": t, "symbol": "NIFTY", "open": 100, "high": 101, "low": 99, "close": 100,
                          "volume": 100, "atr": 2.0, "rsi": 55.0, "adx": 28.0, "vwap": 100.0, "relative_volume": 1.2} for t in dates])
    cfg = {"capital": 30000, "risk_per_trade": 600, "symbols": ["NIFTY"], "net_costs": True}
    replay = ResearchReplay(cfg, Settings(_env_file=None), {"NIFTY": {"lot_size": 10, "historical_verified": False}})
    def signal(row, *args):
        if row["timestamp"].strftime("%H:%M") != "09:30": return None
        return {"id": "fixture-only", "symbol": "NIFTY", "option_type": "CALL", "stop_percent": .1, "target_percent": .2,
                "setup": "fixture-only", "regime": "fixture-only", "agent_contexts": {"Scanner": "fixture-only"}}
    replay.pipeline.signal = signal
    book = {}; atm = defaultdict(set)
    for t in dates:
        hhmm = t.strftime("%H:%M")
        atm[(t, "NIFTY", "CALL")].add(100)
        price = 10 if hhmm <= "09:30" else 11
        q = {"contract_id": "fixed-fixture", "strike": 101, "open": price, "high": price + .1, "low": price - .1, "close": price,
             "volume": 100, "oi": 200, "option_type": "CALL", "expiry_bucket": "WEEK:1", "offsets": ["ATM+1" if hhmm <= "09:31" else "ATM"]}
        if hhmm == "09:32": q.update(high=15, low=8)
        book[(t, "NIFTY", "fixed-fixture")] = q
    replay.consume(frame, book, atm, lambda: False)
    result = replay.result([])
    assert len(result["trades"]) == 1
    trade = result["trades"][0]
    assert trade["quality"] == "research_net"
    assert trade["pnl_basis"] == "net"
    assert trade["costs"] is not None and trade["costs"] > 0
    assert trade["pnl"] == pytest.approx(trade["gross_pnl"] - trade["costs"])
    assert result["metrics"]["total_pnl"] == pytest.approx(trade["pnl"])
    assert result["metrics"]["total_charges"] == pytest.approx(trade["costs"])
    assert replay.cash == pytest.approx(cfg["capital"]+trade["pnl"])
    assert replay.curve[-1]["value"] == pytest.approx(replay.cash)
    assert replay.gross_curve[-1]["value"] == pytest.approx(cfg["capital"]+trade["gross_pnl"])
    assert replay.gross_curve[-1]["value"]-replay.curve[-1]["value"] == pytest.approx(trade["costs"])
    assert result["gross_metrics"]["total_pnl"] == pytest.approx(trade["gross_pnl"])
    assert trade["risk"] <= cfg["risk_per_trade"]
    assert trade["sizing_audit"]["estimated_cost_reserve"] > 0
    assert "entry_features" in trade
    assert trade["entry_features"]["schema"] == "entry_features_v1"

    store = Store(tmp_path / "learning-net.db")
    service = LearningService(store)
    report = report_from_run(result, cfg)
    train_res = service.train(report, "test-net-run")
    assert train_res["eligible_trades"] == 0
    assert train_res["excluded_trades"] == 1
    assert train_res["models"] == []
