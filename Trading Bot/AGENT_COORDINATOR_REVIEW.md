# Coordinator and specialist review — 27 September 2026

Policy: `specialist-review-v2`. This is a deterministic paper research policy,
not a learned brain or proof of improved returns. Capital is ₹30,000; trade and
correlated risk are ₹600; daily planned loss is ₹1,000 plus ₹200 execution reserve,
with a ₹1,200 hard halt. One position across both indices remains binding.

## Decision path

1. Check worker liveness, the exit heartbeat, broker persistence, entry session,
   enabled/valued account, position cap and persistent risk-ledger locks.
2. Refresh the candidate against current, contiguous, completed session candles.
   A pending signal has its original maximum age of 185 seconds. Updating its
   features does not renew that lifetime or move its original invalidation.
3. Apply the shared option-buying screen, exact-contract protection candle,
   model-scope filter and cost estimates.
4. Review the required specialists below. A missing required input or contradiction
   returns WAIT. Optional observations are not counted as independent bullish or
   bearish votes. No calibrated probability is claimed.
5. Check one-lot all-in risk, cash reserve, minimum net reward/risk and matching
   prior net outcomes. Insufficient outcomes can only use the existing explicitly
   authorized unvalidated paper-observation mode.
6. Rank eligible candidates across both indices using the existing shared selector.
   Rebuild the current-candle, quote, Greek, fee and specialist review before entry.
   Recheck credential generation and the latest index quote/invalidation.
7. The broker checks the current ledger, cash, session, quote, option screen and
   required specialist evidence again under its lock immediately before the fill.
   Candidate approval is never a fill. Existing bid/depth exit management continues
   independently when entries are blocked or research is unavailable.

## Assigned roles

| Role | Implemented task and authority |
| --- | --- |
| Regime | Trend pullback must match current directional trend; range rejection requires RANGE. ORB can lead RANGE/TRANSITION but cannot oppose an established classified trend. Veto. |
| Directional | CALL invalidation must be below the original setup price; PUT invalidation above it. Missing/invalid prices or direction veto. |
| Momentum | Completed bar age 60–125 seconds, finite ADX/EMA9/EMA21/slope. Trend requires ADX ≥25, aligned EMA and signed slope ≥0.2 ATR. Range requires ADX ≤20 and absolute slope ≤0.15. ORB rejects a strong opposing trend. Veto. |
| Structure | Positive ATR, current close still on the valid side of invalidation and target not reached. Trend cannot extend beyond 1.5 ATR from EMA21; range must retain ≥1.2 ATR to its midpoint. No index-volume VWAP requirement. Veto. |
| Liquidity | Fresh bid/ask, valid midpoint spread and one-lot depth on both sides. Veto. |
| Adversarial | Challenges every failed required specialist plus invalid net risk/reward. Veto. |
| Options Flow | Observes unsigned OI, prior-day OI change and volume; retains chain context. Does not infer buyers, writers, institutions or a direction. |
| Gamma | Fresh contract gamma observation only; dealer inventory and concentration inference are not implemented. |
| Theta | Daily percentage only when units are documented; otherwise DATA_UNAVAILABLE. |
| IV | Fresh IV and separate research context; comparable-maturity historical percentile unavailable. |
| News/Event | DATA_UNAVAILABLE: no validated event feed. Event risk is not assessed. |
| Loss Investigator | Closed-loss classifications are research hypotheses in the learning audit. POST_TRADE in candidate reviews. |
| Risk Sentinel | Shared account preflight, followed by atomic broker admission. Cannot be outvoted or learned. |
| Orchestrator | Produces WAIT or a CALL/PUT candidate from actual checks; never infers direction from a count of passed stages. |

## Persistence, UI and model separation

`decision_reviews` in the existing project SQLite database keeps changed decisions,
failures, reasons, per-role status, checks, symbol, contract, strategy and completed
bar time. Unchanged polls update the same record. Rejected proposals retain their
matrix. Latest reviews are exposed per index at `strategies.reviews`.

Confirmed positions and completed episodes retain the decision review and
`decision_policy_version`. Session-policy hashes, ML scopes and expectancy matching
include this version. Older strategy/screen results cannot silently validate this
new filter. No historical report is upgraded or relabelled.

The Agentic view reads backend reviews. It distinguishes current candidate,
blocked/no-trade state, unavailable context and post-trade work. No current review,
stale/future timestamps, disconnects, engine errors or closed sessions cannot show
a new directional proposal. Historical learning counts are separate from current
role availability; generic Option Selector/Confirmation events no longer count as
proof that another specialist performed its task.

Worker health exposes individual thread liveness and data/quote/entry/exit errors.
A stopped engine can restart after every previous worker has exited; it will not
launch duplicate workers while an old worker is still alive.

## Verification and limits

Regression scenarios cover valid CALL/PUT symmetry; contrary regime/momentum;
forming/stale/missing bars; invalidation, target-room and extension failures; risk
vetoes despite passing specialists; final changed-regime rejection; durable rejected
evidence; causal frame refresh excluding future rows; version separation; closed
sessions; dead workers; restart deduplication; and UI direction/freshness behavior.

Verification on 27 September: full backend suite 319 passed. After the final
atomic-admission, review-persistence and health adjustments, the affected backend
suite passed 95 tests. Frontend suite passed 17 tests; TypeScript/Vite production
build passed. Fixtures use isolated project-local databases, not the trading
account, and do not send Telegram messages.

Deployment note: the automatic approval review blocked the combined command to
stop and restart the existing backend process. The running process was not replaced
by that command. Restart the backend to activate this decision policy.

This does not establish an edge, new agent learning, or live-session performance.
It must collect fresh forward paper evidence. Existing historical candle reports
do not replay this complete coordinator, depth and Greek policy. News coverage,
institutional/dealer inventory inference, IV percentiles and verified daily Theta
units remain absent. These limits stay visible rather than being labelled PASS.
