WHY THIS PROJECT WILL NOT WORK — HONEST FAILURE ANALYSIS
Verified from source code, DB, endpoints, .env, and backtest (no fabrication)

=== 1. DATA FORMAT BLOCK ===
Evidence: CSV columns = timestamp, open, high, low, close, volume, symbol
Engine (backtest/engine.py lines 61-68) requires: option_quotes with contract_id, expiry, strike, lot_size, tick_size, is_atm, charge_schedule
Result: Engine returns INCOMPLETE with error "Contract-specific option candles required" when run on index CSV
The 5yr data is UNDERLYING INDEX — not option contract history
Fix needed: Option-level historical data from Dhan rolling endpoint OR accept verified DB report as proxy
Status: BLOCKED (cannot run engine continuously on current data)

=== 2. SELF-LEARNING BLOCKED AT PHASE 2 ===
Evidence: /api/learning/model returns eligible_trades=0, status=REJECTED_SYNTHETIC_DATA
DB: ml_models has 1 validated model (Setup v2), ml_sessions frozen — but session model array empty
Evidence (skill rule 1): Need 60+ verified trades to train; need 30+ test; need 10+ days; need 70/30 split
Current: 0 eligible from endpoint; 65 from historical DB; 288 ledger entries from prior runs
The 65 are from ONE backtest window (13 days, Sep 2026) — not continuous 5yr
Result: No new model can be trained, no dynamic scoring, no adaptive promotion
Status: BLOCKED (needs live market days to accumulate)

=== 3. SINGLE-POSITION / SHARED ACCOUNT ===
Evidence: .env MAX_OPEN_POSITIONS=1, MAX_CORRELATED_RISK_RUPEES=600, paper_capital=30000
Engine (backtest/engine.py): max_positions=1 enforced; one position per symbol; shared cash across NIFTY+SENSEX
Result: Even with 3 strategies, only 1 can be active. Can't run ORB + trend + range simultaneously even when all find setups.
The "take best of all 3" works via ranking — but only ONE fills. Rest stay flat.
Status: STRUCTURAL LIMIT (architectural choice — not a bug, but caps output)

=== 4. STRATEGY IS SELECTIVE, NOT CONTINUOUS ===
Evidence: ORB retest requires: first 15-min range + close beyond range + 0.1 ATR + retest within 5 bars + continuation
Most trading days do NOT form opening-range breakages
Result: 65 verified trades / 13 active days = ~5 trades/day when setup occurs; 0 on flat/no-break days
The user's expectation of "trade every day" conflicts with ORB design (needs range + break + retest)
Status: BY DESIGN — not fixable without changing strategy rules

=== 5. EVIDENCE GATES BLOCK EARLY LEARNING ===
Evidence (skill rule 4): PAPER_COLLECT_EVIDENCE=true allows observation
But skill rule 1: 60 trades needed; skill rule 2: 30 test + 10 days needed; skill rule 5: 30-day expiry
Result: Even with evidence collected, promotion requires full replay verification
No promotion = no dynamic scoring = engine stays at baseline (orb-retest-v1 only)
Status: DELIBERATE CONSERVATISM — prevents overfitting, but stalls adaptation

=== 6. NO REAL-TIME OPTION DEPTH / QUOTE AGE ===
Evidence (README): REST price snapshots never qualify; only observed depth from WebSocket counts; missing depth = fail closed
Result: Entries require fresh 2-sec depth; exits require observed bid/depth
During gaps, stale data, or weekend (current state): no entries, exits remain pending
Status: DATA QUALITY — not a code error, but a real execution gap

=== 7. LLM IS CONFIGURED BUT NOT DRIVING DECISIONS ===
Evidence: LLM_ENABLED=true, OPENROUTER_KEY present, /api/llm/status = configured
But: No evidence that LLM market analysis output feeds into pipeline selection (market_analyst is advisory; pipeline uses fixed rules)
The LLM generates hypotheses — but hypothesis promotion requires human review (/api/learning/candidates/{key}/review)
Result: LLM provides insight, not automatic policy change
Status: ADVISORY ONLY — not a failure, but not adaptive either

=== 8. HISTORICAL BASELINE IS NEGATIVE ===
Evidence: learning_ledger — all 8 agents: 36 trades each, net PnL = -14023.64
Result: Prior backtest evidence is negative expectancy; promoting a new model requires PROVED improvement over this
The validated Setup v2 (positive expectancy +40.85 / 22 trades) is an exception — it passed validation
But new strategies must beat this baseline — harder when baseline is poor
Status: REALITY CHECK — historical evidence doesn't support optimistic expectations

=== 9. WEEKEND / CLOSED MARKET ===
Evidence: Engine state = WEEKEND; market_data session = WEEKEND; scans WAITING; last bar 2026-09-11 14:28
Result: No new market data = no new scans = no new entries = no new trades = no new training
Status: TEMPORARY — resolves on next market open (Mon 09:15 IST)

=== 10. MACHINE LEARNING MODEL NOT LOADED IN SESSION ===
Evidence: /api/learning/model shows models=[]; frozen session has no model loaded
DB ml_models exists (validated-setup-v1) but engine's freeze() or score() not using it in current session
Result: Even with validated model, system runs unvalidated paper mode (evidence=UNVALIDATED_PAPER)
Status: INTEGRATION GAP — model exists but session doesn't load it

=== SUMMARY: WHY IT WON'T REACH 1000+/DAY AUTOMATICALLY ===
- Data format (index CSV) prevents continuous engine run
- Self-learning blocked at Phase 2 (needs 60 live verified)
- Single position / shared account limits scale
- Strategy selective (ORB) = not continuous
- Evidence gates conservative
- Historical baseline negative
- Weekend / no live trades currently
- Model not loaded in current session

WHAT WOULD ACTUALLY BE NEEDED (honest, not invented):
1. Option-level historical data or Dhan download for continuous backtest
2. Live market execution (Mon-Fri) to accumulate 60+ per strategy
3. Multiple positions (config change + risk scaling with capital)
4. Less selective strategy combination or lower entry gates
5. Human review of promoted policies (current design, not automatic)
6. Positive forward-paper evidence before scaling limits

THIS IS NOT A BROKEN ENGINE — IT IS A CONSERVATIVE, PROTECTED, UNVALIDATED SYSTEM
That is the correct behavior per the implementation (README, MULTI_STRATEGY_PAPER.md, skill rules).
The user's goal (1000+/day, every day, min losses) requires either:
  (a) Much larger capital + more positions + less selective entry + faster validation
  (b) Acceptance that 65 verified / 13 days is proof of concept, not production
  (c) Real option-level data + continuous execution + validated promotion
None of these can be FABRICATED — they all require real execution, real data, real validation.
