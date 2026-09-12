# Paper engine remediation — 12 September 2026

This is an implementation checkpoint, not a declaration of market readiness or a profitable strategy. All execution remains paper-only. The active objective is unfinished.

## Operating constraints verified from the running service

- Starting paper capital: ₹30,000.
- Daily target: ₹1,000 net of estimated charges; not guaranteed.
- Daily hard halt: ₹800, consisting of ₹600 planned allocation and ₹200 execution reserve.
- Per-trade and correlated risk caps: ₹600; one position; existing three-entry/two-loss limits retained.
- Monitoring starts at 09:15 IST; entry cutoff remains 14:30; liquidation requests start at 15:05. Missing depth must remain a pending exit, never an invented fill.
- Project `.env` is authoritative for credentials. The running engine reports current credential checks without exposing secrets.

## Changes implemented and checked

1. Removed the raw-index-to-Black–Scholes option generator. Underlying-only CSV files are rejected by the option replay importer. Known synthetic provenance is rejected by exact-contract replay, learning ingestion, and promotion checks, including legacy reports whose quality field says `verified`.
2. Legacy synthetic reports are invalidated when presented through the latest-report and individual-report APIs. Headline metrics and equity/attribution presentations are withheld. The stored original is retained for audit. The UI explicitly labels invalidated reports and distinguishes estimated-net research from verified simulations.
3. The shared paper engine is the sole execution authority. The former independent agent is now a research coordinator observing the engine's actual decisions. Its obsolete independent entry/exit logic was removed; direct execution methods reject calls. It shares the application's learning service and backtest job manager. Repeated identical research inputs are deduplicated.
4. Account writes roll memory back to the last committed state after a persistence failure. Failed entries cannot leave phantom positions or consumed signals; failed exits retain their durable positions. Broker health reports persistence failures and entries pause until persistence recovers. A committed exit is not reported as failed merely because its subsequent valuation write failed.
5. SQLite connections close deterministically. Paper account writes have a bounded 250 ms lock wait without the former three long retries. The execution loop remains alive after persistence errors and attempts protective exits even when the preceding mark write failed.
6. Runtime health uses the actual execution heartbeat, thread liveness, worker errors and broker health. A responding HTTP server alone no longer means healthy execution. This does not establish fresh market data or a validated strategy.
7. Estimated-net rolling research now reserves costs at entry and settles actual estimated round-trip costs on exit. Cash and closing equity reconcile with net P&L, and sizing includes the cost reserve. Removed the invented fixed 1% spread feature.
8. Removed the hidden stop-distance cap that tightened structural stops to fit a rupee allowance. Oversized structural risk must be rejected by admission. CSV jobs no longer silently use a 60-minute horizon, an 8-rupee minimum stop and a 25-point invalidation buffer; the ORB baseline uses its 10-minute horizon and structural protection.
9. Bumped the learning validation version to `learning_guard_v2`, so models validated under the earlier gates require revalidation. Fixed sample thresholds, consumed holdout reservations and full-account replay requirements remain in place.
10. Isolated the API toggle test before application import, preventing it from constructing a broker against the production account database.

## Verification and current evidence

- Complete backend suite: 163 passed. Final focused integrity/learning/runtime run after subsequent changes: 45 passed. These runs overlap and must not be added together.
- Frontend TypeScript/Vite production build passed.
- Restarted the local API only after confirming zero open positions and no active backtest jobs.
- Live API checks after restart: healthy worker heartbeat, no dead execution workers, no persistence error, correct risk limits, research coordinator without order authority, learning monitor live with validation version v2.
- The latest old synthetic report is now `invalidated` / `synthetic_unvalidated`.
- Latest coordinator learning result: `REJECTED_SYNTHETIC_DATA`; 18 excluded trades and zero eligible trades.
- At approximately 22:11 IST: 28 stored training-attempt records, 34 reports, zero saved models/champions and zero completed paper episodes. Attempt counts include rejected attempts and do not mean models learned.
- The advisory provider still returns HTTP 429. The deterministic monitor works independently; no successful current live AI review is claimed.
- September 12 is a Saturday. These checks do not validate an open-market session or exchange fills.

## Work still required

| Priority | Remaining work | Completion evidence |
|---|---|---|
| Critical | Complete replay integration for trend pullback, range rejection and the combined selector, using the same signal/protection/exit rules as paper execution | Individual and combined deterministic replay tests plus reports with explicit parity limitations |
| Critical | Obtain/validate observed exact-contract historical option data, historical expiry/lot/tick metadata and dated costs; preserve data gaps | Source manifests, coverage report and complete held-contract intervals; underlying CSVs alone do not satisfy this |
| High | Rerun all relevant historical results after the provenance/accounting/protection fixes | New versioned reports; old reports must not be treated as results of the corrected engine |
| High | Implement a frozen, contemporaneous forward baseline comparison for each learning candidate, including entry and exit attribution | Paired forward evidence with costs, drawdown, independent sessions and rejection/promotion audit; trade counts alone are insufficient |
| High | Improve supervision of an occupied but unhealthy service, and validate unattended scheduling/restart behavior | Fault/restart tests without duplicate execution authority or lost pending exits; current Windows task still depends on interactive login |
| High | Source market holidays and verify exchange-data freshness semantics; record durable execution quote/depth evidence | Calendar provenance, delayed-packet tests and replayable quote records; local receive time alone does not prove exchange freshness |
| High | Verify an actual market session from credential rotation through signals, admission, observed entry/exit and restart recovery | Dated unvalidated-paper observation logs; no simulated fixture inserted into production |
| Medium | Complete coordinator performance attribution and forward-learning status from actual engine outcomes | Dashboard values tied to closed episodes and active model IDs rather than coordinator-local counters |
| External | Restore a successful optional AI review | A bounded provider call completing the read-only evidence tool and returning a valid review; key presence alone is insufficient |

No test establishes a guarantee of ₹1,000 daily profit, a guaranteed maximum realized loss under gaps/liquidity failures, or the absence of overfitting. The software enforces configured admission and halt rules; observed execution and forward performance still need evidence.
