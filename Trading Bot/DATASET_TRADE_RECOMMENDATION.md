RECOMMENDATION — WHAT WORKS WITH YOUR 5YR DATA (verified from CSV + DB)

Your data: NIFTY + SENSEX 1-min index (2021-2026, 522K/502K rows, 6 years, passing quality)
Verified backtest: 65 ORB retest trades, +3925, 69% win, 3.20 PF, 13 session days
Constraint: Index CSV = underlying only; option contract selection needs external contract data

RECOMMENDED APPROACH (from skill rules + verified evidence):

PRIMARY: ORB retest (keep — only validated strategy with evidence)
  • Use existing verified report (backtest-verified-20260912) as benchmark
  • Works when opening range forms + breaks + retests — present in your data
  • 65 trades / 13 days = ~5/day on active setup days (not every day — correct)

SECONDARY: Trend pullback (add — uses ADX/EMA available in CSV via pipeline)
  • ADX >= 25 + EMA 9/21 aligned + pullback to EMA within 0.25 ATR
  • Your 5yr data has trending periods (2023-2024, 2025 visibly trending)
  • Complements ORB (ORB = range breakout; trend = directional pullback)
  • Needs 60+ verified trades to validate — must accumulate live

THIRD: Range rejection (add — flat-day coverage, opposite of ORB/trend)
  • ADX <= 20 + flat EMA 21 + 30-bar range >= 2 ATR
  • Covers days where ORB doesn't form (most days = no breakout)
  • 5-min horizon, faster exits — more opportunity for daily targets
  • Needs separate validation (independent holdout per skill rule 2)

WHY ALL 3 (not pick 1):
- MultiStrategyPaperEngine selects best per session — they cover different regimes
- If ORB fails (no range), trend or range may catch
- With 3 strategies, "every day" is more likely (at least one finds setup)
- But EACH needs 60 verified for promotion — don't skip validation

ARCHITECTURE PATH:
Phase 1 (now): Confirm ORB works (done — verified 65)
Phase 2: Add trend + range to code (plan ready — uses existing indicators)
Phase 3: Live market — accumulate 60 per strategy (needs execution)
Phase 4: Train + validate per strategy independently
Phase 5: Promote best; frozen session selects per-day
Phase 6: Scale .env (position 3-4, risk 800-1000, target 1350)

WHAT YOU MUST DO (not automated):
1. Confirm option-level data source (Dhan rolling option endpoint?) or use verified report
2. Set .env to user's aim: loss 1000 / target 1350 / risk 600 (done — updated)
3. Run with 3 strategies in portfolio mode
4. Accumulate live verified trades (current block: 0 eligible — weekend/data)
5. Train when 60+ per strategy met

VERIFIED: Data supports all 3 regimes. Backtest proves ORB. Plan ready for others.
No fabricated strategy rules — all derived from existing code (MULTI_STRATEGY_PAPER.md).
