"""Closed-position attribution; counts are not causal proof of learning."""
import math
from .strategy_portfolio import STRATEGIES


def summarize_paper_episodes(episodes, day):
    rows=[]; excluded=0; seen=set()
    for row in sorted(episodes,key=lambda r:str(r.get('exit_ts',''))):
        if str(row.get('exit_ts',''))[:10]!=day: continue
        try:
            pnl,gross,costs=(float(row[k]) for k in ('pnl','gross_pnl','costs'))
            valid=(not row.get('partial') and row.get('source')=='paper_live_quotes' and
                   row.get('quality')=='verified' and all(math.isfinite(v) for v in (pnl,gross,costs)) and
                   costs>=0 and abs(pnl-gross+costs)<.01 and bool(row.get('id')))
        except (KeyError,ValueError,TypeError): valid=False
        if not valid:
            excluded+=1; continue
        if row['id'] in seen: continue
        seen.add(row['id']); rows.append(row)
    def stats(items):
        total=peak=drawdown=0.
        for row in items:
            total+=float(row['pnl']); peak=max(peak,total); drawdown=max(drawdown,peak-total)
        return {'trades':len(items),'wins':sum(float(r['pnl'])>0 for r in items),
                'losses':sum(float(r['pnl'])<0 for r in items),'pnl':total,
                'gross_pnl':sum(float(r['gross_pnl']) for r in items),'max_dd':drawdown}
    return {'session':day,'total':stats(rows),
            'strategies':{s['id']:stats([r for r in rows if r.get('strategy_id')==s['id']]) for s in STRATEGIES},
            'unattributed_trades':sum(r.get('strategy_id') not in {s['id'] for s in STRATEGIES} for r in rows),
            'excluded_episodes':excluded,'source':'closed_paper_episodes','self_improvement_proven':False,
            'drawdown_basis':'closed_episode_net_pnl; excludes intratrade excursions'}
