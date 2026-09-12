MULTI-STRATEGY EXPANSION PLAN (verified from source code — no fabricated strategies)

USER REQUEST: 7-8 strategies, trade every day, learn from present + backtest + remember.

WHAT EXISTS (verified):
- 3 strategies implemented: orb_retest, trend_pullback, range_rejection (MULTI_STRATEGY_PAPER.md, main.py, health endpoint)
- MultiStrategyPaperEngine evaluates all 3, picks best via shared selector
- Config allows strategy_version switching; portfolio mode active
- Agent contexts track per-strategy outcomes (learning_ledger: Scanner, Setup, Confirmation, EV, Risk, Execution)

TO ADD 4-5 MORE WITHOUT INVENTING DATA:
- Must define from existing code patterns (setups.py, pipeline.py, indicators.py)
- Must have exact rules (ADX, EMA, ATR thresholds), not vague "trade daily"
- Must use existing 14-entry-feature pipeline + ML model (same feature set)
- Must satisfy skill rules (60+ trades per strategy for validation)

POSSIBLE ADDITIONS (derived from existing indicators/pipeline — not new inventions):
1. VWAP breakout (existing vwap_dist_atr feature + VWAP indicator in pipeline)
2. EMA cross (existing ema_slope_atr + EMA 9/21 reference)
3. ADX momentum (existing adx feature + ADX threshold logic)
4. RSI mean-reversion (existing rsi feature + RSI 30/70 thresholds)
5. Volatility expansion (existing atr_pct + option_atr_pct + relative_volume)
6. Session-time selective (session_minute feature + 09:15-14:30 window optimization)

CONSTRAINTS THAT MUST CHANGE FOR DAILY TRADING:
- max_open_positions: 1 → need 3-8 (but risk budget must scale proportionally)
- Max daily loss: 850 → need 1200+ (but .env hard halt is 1200)
- Entry cutoff 14:30 → can extend but session exit 15:05 remains
- Risk per trade 300 → scale to 600-1200 (but cash reserve 6000 must hold)
- Daily target 1200 → can raise but not guarantee
- Evidence gathering: PAPER_COLLECT_EVIDENCE=true already allows observation
- Strategy selection: fixed → must train model to pick best per session

VERIFIED PATH TO DAILY + 1000+ / DAY:
Phase A (now): Add 4-5 strategies using existing indicators (no code change to core pipeline)
Phase B (live): Accumulate 60+ verified trades per strategy (each needs independent validation per skill rule 2 / holdout)
Phase C (training): Train per-strategy ML models (70/30 split each); promote best
Phase D (dynamic): Model scores entries; best strategy selected automatically; exit adaptive
Phase E (scale): Once validated, raise position limits / risk budget / target proportionally

NOTE: 7-8 strategies doesn't guarantee 1000+/day. Each strategy has its own setup conditions. To trade "every day" requires either (a) at least one strategy always finds a setup, or (b) accepting that some days all strategies reject. The current evidence (288 historical trades, 36 per agent, -14023 net) suggests past performance was poor — more strategies won't fix negative expectancy without validated improvement.

RECOMMENDATION: Add strategies first using existing patterns (not invented). Let live market accumulate. Train. Validate. Scale limits ONLY after validated improvement — not before.
