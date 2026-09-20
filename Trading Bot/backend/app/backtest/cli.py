import argparse
import json
from pathlib import Path
from dataclasses import replace
from .data import read_contract_csv
from .reconstruction import dhan_research
from .engine import BacktestEngine, BacktestConfig
from .reports import report_from_run
from .walk_forward import validation_windows
from ..store import Store, json_safe
from ..config import settings, current_credentials
from ..risk import PlanRiskPolicy
from ..market_data import DhanGateway, HISTORY_CACHE_ONLY


def main():
    parser=argparse.ArgumentParser(description="Replay sourced, contract-specific option candles")
    parser.add_argument("--source",choices=("csv","rolling-cache"),default="csv")
    parser.add_argument("--csv")
    parser.add_argument("--from",dest="from_date")
    parser.add_argument("--to",dest="to_date")
    parser.add_argument("--symbols",default="NIFTY,SENSEX")
    parser.add_argument("--capital",type=float,default=30000)
    parser.add_argument("--strategy",choices=("orb_retest","trend_pullback","range_rejection","portfolio"))
    parser.add_argument("--walk-forward",action="store_true",help="Report disjoint base-rule validation windows; does not promote policies")
    args=parser.parse_args()
    if args.capital<=0: parser.error("Capital must be positive")
    if args.source=="csv" and not args.csv: parser.error("--csv is required for --source csv")
    if args.source=="rolling-cache" and (not args.from_date or not args.to_date):
        parser.error("--from and --to are required for --source rolling-cache")
    if args.source=="rolling-cache":
        if args.strategy not in (None,"orb_retest"):
            parser.error("rolling-cache supports only orb_retest; use exact-contract CSV for other strategies")
        if args.walk_forward:
            parser.error("--walk-forward requires exact-contract CSV")
        store_path=Path(__file__).resolve().parents[2]/"trading_bot.db"
        gateway=DhanGateway(settings, Store(store_path), credential_provider=current_credentials)
        token=HISTORY_CACHE_ONLY.set(True)
        try:
            try:
                result=dhan_research(
                    gateway,
                    {"from":args.from_date,"to":args.to_date,
                     "symbols":[x.strip().upper() for x in args.symbols.split(",") if x.strip()],
                     "capital":args.capital,"risk_per_trade":settings.max_trade_risk_rupees,
                     "daily_loss_limit":settings.daily_loss_limit_rupees,
                     "correlated_risk_limit":settings.max_correlated_risk_rupees,
                     "strategy_version":"orb-retest-v1","net_costs":True},
                    lambda *_: None, lambda: False, settings)
            except ValueError as exc:
                result={"status":"data_blocked","quality":"incomplete",
                        "source":"rolling-cache","deployment_ready":False,
                        "evidence_status":"LOCAL_CACHE_INCOMPLETE",
                        "trades":[],"metrics":{"total_pnl":None},
                        "issues":[str(exc)]}
        finally:
            HISTORY_CACHE_ONLY.reset(token)
        print(json.dumps(json_safe(result),indent=2,allow_nan=False))
        return
    frame,digest=read_contract_csv(Path(args.csv),{"session_exit":settings.session_exit})
    cfg=BacktestConfig(initial_capital=args.capital,strategy_mode=args.strategy or "portfolio",
                       risk_per_trade=settings.max_trade_risk_rupees,daily_loss_limit=settings.daily_loss_limit_rupees,
                       correlated_risk_limit=settings.max_correlated_risk_rupees,monthly_target=settings.monthly_profit_target,
                       entry_cutoff=settings.entry_cutoff,exit_at=settings.session_exit,
                       plan_policy=PlanRiskPolicy.from_settings(settings),adaptive_exits=True)
    if args.walk_forward:
        windows=validation_windows(frame.timestamp.dt.strftime("%Y-%m-%d"))
        if not windows: parser.error("At least 50 complete sessions are required")
        result={}
        for part in ("train","validation","test"):
            start,end=windows[part+"_from"],windows[part+"_to"]
            subset=frame[frame.timestamp.dt.strftime("%Y-%m-%d")<=end]
            run=BacktestEngine(replace(cfg,trade_from=start)).run(subset)
            result[part]={"from":start,"to":end,"quality":run["quality"],"metrics":run["metrics"],"issues":run["issues"]}
    else:
        result=report_from_run(BacktestEngine(cfg).run(frame),{"capital":args.capital,"dataset_id":digest})
    print(json.dumps(json_safe(result),indent=2,allow_nan=False))


if __name__=="__main__": main()
