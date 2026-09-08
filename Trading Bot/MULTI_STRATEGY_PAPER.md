# Paper strategy portfolio v1

This implementation evaluates three price-based hypotheses on NIFTY and SENSEX.
All three are **unvalidated paper strategies**. There is no daily-profit promise,
calibrated win probability, or evidence that these are the most profitable choices.
Existing ORB historical reports do not validate the combined selector.

## Strategies

All inputs are completed one-minute candles. Current-session candles must be
continuous from 09:15, valid and at most 125 seconds old by start timestamp. Future
rows are removed before feature calculation. At least 20 session bars are needed.
Volume is not required for index signals; real option volume/OI/depth are required
for contract eligibility. Parameter choices are fixed engineering hypotheses,
not fitted to today's performance.

- **Opening-range retest:** first 15-minute high/low, close beyond the range plus
  0.1 ATR at a three-minute boundary, then a retest and later continuation within
  five bars of the breakout. CALL for upward continuation; PUT for downward.
- **Trend pullback:** ADX at least 25; aligned EMA 9/21; EMA 21 movement over five
  bars at least 0.2 ATR in the trend direction. The previous candle touches within
  0.25 ATR of EMA 21 and closes on the trend side; the current candle closes beyond
  that candle's extreme. Entry extension may not exceed 1.5 ATR from EMA 21.
- **Range rejection:** ADX at most 20; absolute five-bar EMA 21 movement at most
  0.15 ATR. Use the prior 30 bars, excluding rejection/confirmation candles, to
  establish a range at least 2 ATR wide. Require boundary rejection within
  0.15 ATR and subsequent confirmation with at least 1.2 ATR room to its midpoint.
  Requires at least 32 completed session bars. Exit at the underlying midpoint
  if reached before the option target/stop/time exit.

ORB and trend hypotheses can overlap. They are not assumed independent and do not
receive separate risk allowances. CALL and PUT are option purchases; no short
option selling is implemented.

## Shared selector and protection

Each index has up to 12 CALL and 12 PUT subscriptions. Fresh non-ATM options are
ranked by the existing liquidity/contract filter. The selected contract's actual
completed protection candle is requested on demand, rather than prefetching a
different delta-ranked subset. A bounded full-session contract request is filtered
to the exact retest/rejection minute because narrow timestamp requests were
observed to omit that minute. Missing, duplicate, invalid or changed-credential
responses never produce a stop or fill; missing data is retried with backoff.

Protection is one tick below the option candle's low, with a nominal 2R premium
target. The trend/ORB horizon is 10 minutes; range rejection is 5 minutes. Stops,
underlying invalidation, midpoint exits and 15:05 session liquidation are retained.
These barriers do not guarantee execution prices.

Before ranking, each offer must satisfy all existing cash/loss/position limits,
estimated buy and round-trip charges, and net reward at target of at least its
all-in stop risk. Rank eligible offers across both indices by:

1. Supported net evidence before unvalidated paper observation.
2. Conservative net-outcome lower bound divided by proposed risk.
3. Net reward **if target is reached** divided by all-in stop risk.
4. Lower spread, then stable strategy/index/contract identifiers.

The third metric is not expected profit or a win probability. At fewer than 30
matching verified paper outcomes or 10 sessions, PAPER_COLLECT_EVIDENCE=true allows
explicit observation. Once the sample is sufficient, an unsupported net edge is
rejected. Outcomes are matched by portfolio version, strategy version, setup and
regime; old ORB research outcomes are not mixed into the new portfolio.

The winning offer is rechecked for session, signal age, quote age, unchanged
prices/contract identity, current ATM classification, underlying invalidation,
credential generation and atomic broker risk admission. A failed offer can be
skipped; if no eligible offer remains, the system stays flat. One position/lot,
the 300-rupee trade-risk budget, 650-rupee planned daily loss allocation, maximum
three entries/two losses, reserves, cooldown and portfolio locks remain in force.

## Operation and audit

PAPER_STRATEGY_MODE defaults to portfolio; orb_only retains the older baseline
engine. Historical replay endpoints retain their existing strategy scope. New
paper session models are versioned separately instead of overwriting old models.

Historical and charge requests run outside the shared exit heartbeat. The
dashboard and GET /api/strategies show all six evaluations, candidate rejection
reasons, ranked offers, and per-strategy executed paper outcomes. Candidate logs
and rankings are persisted; candidates are not counted as trades or shadow P&L.

The existing Windows supervisor starts at 09:10 IST; monitoring begins at 09:15,
new entries stop at 14:30, and liquidation starts at 15:05. Pending exits continue
to require real observed liquidity. Project .env credentials remain authoritative
and are rechecked before REST work and order admission. Real orders remain disabled.

Tests cover both directional new setups, ORB continuity, future-data exclusion,
invalid/stale/gapped input, exact protection contract/minute loading and retries,
credential changes, cross-index ranking, one-position admission, changed quotes,
negative-evidence rejection, strategy-specific exits and performance attribution.

Live forward-paper results are required before making any performance claim.
