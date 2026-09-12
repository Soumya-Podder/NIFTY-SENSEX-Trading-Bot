SELF-TEACHING CLARIFICATION (2026-09-12) — Addressing user's description

USER DESCRIPTION: Agents check continuously, take best trade, self-teach using better profits/min losses.

VERIFIED ACTUAL STATE:

1. MULTIPLE STRATEGIES (CONFIRMED FROM CODE / HEALTH):
   - orb_retest (opening-range retest): ORB high/low break + retest + continuation
   - trend_pullback (ADX >= 25, EMA 9/21 aligned): pullback to EMA + close beyond
   - range_rejection (ADX <= 20, flat EMA 21): boundary rejection + confirmation
   - All run under MultiStrategyPaperEngine (portfolio mode, not orb_only)
   - Shared portfolio selector ranks eligible offers across both indices by: net evidence > conservative lower bound / risk > target/reward > spread
   - Only 1 open position / shared account (max 1 position, 300-rupee risk per trade)

2. CONTINUOUS CHECK (CONFIRMED):
   - Engine scans every 2 seconds (market data refresh 2 sec, dashboard 2 sec)
   - New entries stop at 14:30; liquidation begins 15:05
   - Monitor checks every 60 sec (learning_monitor.py)
   - Pipeline evaluates all 3 strategies per scan

3. BEST ENTRY / BEST EXIT (PARTIALLY CONFIRMED):
   - Entry: shared selector picks best eligible offer (not just first setup)
   - Exit: plan_exit() + adaptive_exit.py + stop-first resolution
   - Stop = 1 tick below option candle low; target = 2R premium target
   - Exit at midpoint if reached (range rejection); session exit at 15:05
   - Entry uses observed ask/depth; exit uses observed bid/depth

4. SELF-TEACHING (STRUCTURE EXISTS — EXECUTION BLOCKED):
   - Data: 288 learning_ledger entries (historical from prior runs)
   - DB: validated-setup-v1 (Setup v2 policy promoted, effective Sep 13, expires Oct 11)
   - ML model: LogisticRegression (regularized, 70/30 split, holdout reserved)
   - Training: blocked at Phase 2 (needs 60 live verified trades — currently 0 eligible)
   - LLM: generates hypotheses from failure patterns + market analysis
   - Agents: record contexts (Scan, Setup, Confirmation, EV, Risk, Execution) with lesson extraction
   - Adaptation mechanism: if validated model exists, score() predicts probability; if insufficient, LLM provides regime assessment; hypotheses submitted for human review
   - Auto-promotion NOT active — requires human review (review endpoint /api/learning/candidates/{key}/review)
   - Daily-loss rollback implemented; matched shadow comparison not yet

5. WHAT IS ACTUALLY ADAPTIVE NOW:
   - Exit policy: adaptive_exit.py adjusts target/stop based on market conditions
   - Agent contexts: pipeline tracks per-strategy contexts; rejected/accepted based on evidence
   - Risk limits: adaptive to equity, drawdown, daily loss (PlanRiskPolicy)
   - Evidence mode: PAPER_COLLECT_EVIDENCE=true allows observation below threshold
   - Model scoring: if frozen_model loaded (currently not — session has no models loaded), probability guides entry

6. WHAT IS NOT ADAPTIVE (NEEDS LIVE TRADES):
   - Strategy parameter selection: fixed engineering hypotheses (ORB parameters not fitted)
   - Entry criteria: not dynamically adjusted by model probability (no validated model loaded in session)
   - Profit-booking rules: fixed (2R target, stop-first, midpoint exit) — not learned
   - Min-loss management: fixed stop % — not optimized from historical outcomes
   - Hypothesis promotion: requires human review — no automatic policy change

7. TO ACTUALLY SELF-TEACH:
   - Need live market hours (Mon-Fri 09:15-15:05 IST) to accumulate trades
   - Need 60+ verified trades with entry features (current: 0 from endpoint, 65 from historical DB report)
   - Once threshold met: train → validate → replay → promote → effective next session → 30-day expiry → re-validate
   - Only THEN will model probability influence entry and exit decisions dynamically

BOTTOM LINE: Your description matches the ARCHITECTURE correctly (multi-strategy, continuous, best-offer selection, adaptive exit, agent learning). The BLOCKAGE is at Phase 2 — not enough verified trades to train a new model. The existing Setup v2 promotion (validated) is running, but new model-based adaptation requires live execution.
