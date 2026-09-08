import numpy as np
import pandas as pd


def metrics(trades,equity,daily=None,target=1200):
    p=np.array([t["pnl"] for t in trades if t.get("pnl") is not None],float)
    wins=p[p>0]; losses=p[p<0]
    eq=pd.Series(equity,dtype=float)
    dd=eq-eq.cummax() if len(eq) else pd.Series([0.0])
    days=daily or []
    day_pnls=[float(d["pnl"]) for d in days]
    return {"trades":len(p),"wins":len(wins),"losses":len(losses),
            "win_rate":float((p>0).mean()) if len(p) else None,
            "gross_profit":float(wins.sum()),"gross_loss":float(-losses.sum()),
            "profit_factor":float(wins.sum()/(-losses.sum())) if len(losses) else None,
            "profit_factor_status":"NO_LOSSES" if len(p) and not len(losses) else "NO_TRADES" if not len(p) else "FINITE",
            "expectancy":float(p.mean()) if len(p) else None,"total_pnl":float(p.sum()),
            "max_drawdown":float(dd.min()),"max_drawdown_pct":float((dd/eq.cummax().replace(0,np.nan)).min()) if len(eq) else 0,
            "average_winner":float(wins.mean()) if len(wins) else None,"average_loser":float(losses.mean()) if len(losses) else None,
            "largest_winner":float(wins.max()) if len(wins) else None,"largest_loser":float(losses.min()) if len(losses) else None,
            "total_charges":sum(t.get("costs",0) for t in trades),"sessions":len(days),
            "average_daily_pnl":sum(day_pnls)/len(days) if days else None,
            "worst_day":min(day_pnls) if days else None,"best_day":max(day_pnls) if days else None,
            "target_day_rate":sum(v>=target for v in day_pnls)/len(days) if days else None,
            "no_trade_days":sum(d.get("trades",0)==0 for d in days),"daily_target":target}
