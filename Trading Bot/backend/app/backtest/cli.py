import argparse
import json
from pathlib import Path
from dataclasses import replace
from .data import read_contract_csv
from .engine import BacktestEngine, BacktestConfig
from .reports import report_from_run
from .walk_forward import validation_windows
from ..store import json_safe
from ..config import settings
from ..risk import PlanRiskPolicy


def main():
    parser=argparse.ArgumentParser(description="Replay sourced, contract-specific option candles")
    parser.add_argument("--csv",required=True)
    parser.add_argument("--capital",type=float,default=30000)
    parser.add_argument("--strategy",choices=("orb_retest","trend_pullback","range_rejection","portfolio"),default="portfolio")
    parser.add_argument("--walk-forward",action="store_true",help="Report disjoint base-rule validation windows; does not promote policies")
    args=parser.parse_args()
    if args.capital<=0: parser.error("Capital must be positive")
    frame,digest=read_contract_csv(Path(args.csv),{"session_exit":settings.session_exit})
    cfg=BacktestConfig(initial_capital=args.capital,strategy_mode=args.strategy,
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
