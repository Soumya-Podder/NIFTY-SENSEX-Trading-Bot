from app.paper_performance import summarize_paper_episodes


def test_closed_net_outcomes_are_attributed_without_counting_partial_fills_or_backtests():
    def episode(identifier,pnl,strategy='orb_retest',**extra):
        return {'id':identifier,'exit_ts':'2026-09-11T10:00:00+05:30','pnl':pnl,'gross_pnl':pnl+40,
                'costs':40,'quality':'verified','source':'paper_live_quotes','strategy_id':strategy,**extra}
    rows=[episode('a',-100),episode('b',200,'trend_pullback'),episode('a',-100),
          episode('partial',-10,partial=True),episode('backtest',9999,source='historical_contract_candles')]
    result=summarize_paper_episodes(rows,'2026-09-11')
    assert result['total']['trades']==2 and result['total']['pnl']==100
    assert result['strategies']['orb_retest']['pnl']==-100
    assert result['strategies']['trend_pullback']['pnl']==200
    assert result['total']['max_dd']==100
    assert result['excluded_episodes']==2
    assert not result['self_improvement_proven']
    assert summarize_paper_episodes(rows,'2026-09-12')['total']['trades']==0
