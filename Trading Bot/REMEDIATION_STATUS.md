# Paper engine remediation — updated 13 September 2026

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
| Critical | Run the newly integrated individual/combined contract-CSV replay against genuine option history; extend rolling research without claiming equivalent execution fidelity | Contract replay integration is implemented and tested; actual individual/combined historical performance remains unvalidated |
| Critical | Obtain/validate observed exact-contract historical option data, historical expiry/lot/tick metadata and dated costs; preserve data gaps | Source manifests, coverage report and complete held-contract intervals; underlying CSVs alone do not satisfy this |
| High | Rerun all relevant historical results after the provenance/accounting/protection fixes | New versioned reports; old reports must not be treated as results of the corrected engine |
| High | Implement a frozen, contemporaneous forward baseline comparison for each learning candidate, including entry and exit attribution | Paired forward evidence with costs, drawdown, independent sessions and rejection/promotion audit; trade counts alone are insufficient |
| High | Improve supervision of an occupied but unhealthy service, and validate unattended scheduling/restart behavior | Fault/restart tests without duplicate execution authority or lost pending exits; current Windows task still depends on interactive login |
| High | Source market holidays and verify exchange-data freshness semantics; record durable execution quote/depth evidence | Calendar provenance, delayed-packet tests and replayable quote records; local receive time alone does not prove exchange freshness |
| High | Verify an actual market session from credential rotation through signals, admission, observed entry/exit and restart recovery | Dated unvalidated-paper observation logs; no simulated fixture inserted into production |
| Medium | Complete paired forward-learning evidence from actual engine outcomes | Coordinator performance now derives from closed paper episodes; causal improvement still needs a contemporaneous baseline |
| External | Restore a successful optional AI review | A bounded provider call completing the read-only evidence tool and returning a valid review; key presence alone is insufficient |

No test establishes a guarantee of ₹1,000 daily profit, a guaranteed maximum realized loss under gaps/liquidity failures, or the absence of overfitting. The software enforces configured admission and halt rules; observed execution and forward performance still need evidence.

## September 13 implementation update

- Added `strategy_mode` values `orb_retest`, `trend_pullback`, `range_rejection` and `portfolio` to sourced-contract backtests, with corresponding UI choices and CLI `--strategy` selection.
- Replay uses the shared completed-bar strategy rules, bounded seven-day indicator warmup, structural protection and strategy-specific 10/10/5-minute horizons. Combined replay ranks eligible offers across both indices using the shared observation ranking and one cash account.
- Tests compare replay signals against the live prefix evaluator, remove a session bar to test continuity rejection, reverse source row order to test stable selection, and exercise attributed entries/time exits for the three strategies. Controlled indicator/price fixtures are explicitly isolated test data.
- CSV jobs use the shared adaptive-exit implementation. Reports carry parity limitations: minute OHLC cannot establish the live two-second quote path, missing spreads are not invented, and historical observation ranking cannot reconstruct unavailable contemporaneous forward expectancy.
- Dhan rolling research remains an explicitly different input path. Requests for the new exact-contract modes with rolling data reject clearly instead of silently running the ORB baseline.
- Dataset listings distinguish underlying-only CSVs from files with contract columns. Underlying-only files cannot be selected as option execution history; a contract-looking header still requires full importer validation.
- Added a sourced NSE derivatives holiday gate and exposed its provenance/limits in health. September 14, 2026 is closed according to [NSE circular FAOP/71777](https://nsearchives.nseindia.com/content/circulars/FAOP71777.pdf). This is a shared portfolio closure gate; independent BSE calendar verification, later amendments and special sessions remain outstanding.
- Found configuration drift that prevented startup: three positions, ₹1,000 loss cap and ₹1,800 correlated risk. Restored the explicit persistent requirements: one position, ₹800 loss/hard halt, ₹600 correlated risk, ₹1,000 net target. No credential values were printed or intentionally changed.
- Coordinator statistics now derive from deduplicated, completed paper episodes, separated by strategy and session. Partial fills, historical backtests, inconsistent net-cost outcomes and invalid records are excluded. Drawdown is explicitly closed-episode drawdown, not intratrade drawdown or proof of learning.
- Full suite after replay/calendar integration: **172 passed**. The later focused performance/monitor suite passed **23 tests**; these runs overlap. The UI production build passed.
- Restarted and verified the running API at approximately 10:32 IST on September 13: healthy heartbeat, no dead execution workers, correct ₹800/₹600/one-position limits, all four replay modes in the live API schema, underlying-only datasets correctly labelled, and coordinator statistics sourced from closed paper episodes.

Example command, from the backend directory, after providing genuine contract history:

```powershell
.\.venv\Scripts\python.exe -B -m app.backtest.cli --csv "E:\trading_bot_full\Trading Bot\data\YOUR_OBSERVED_CONTRACTS.csv" --strategy portfolio
```

The filename above is a placeholder, not an existing verified dataset. Use each individual strategy name for separate reports; `--walk-forward` adds disjoint chronological validation windows.

## Durable observation recording — September 13

- Added a separate SQLite observation tape at `data/market_observations.db` on E:. Its writer is asynchronous, so the market-feed callback does not wait for disk writes or take the paper-account database lock.
- Records normalized underlying observations, option top-of-book prices/quantities, contract metadata, local receipt timestamps, available last-trade timestamps and credential generation numbers. An allowlist excludes credentials and arbitrary raw packets.
- Uses a 10,000-event bounded queue, a 1 GiB recording budget and a 1 GiB minimum free-space reserve. Overflow or storage limits produce explicit dropped-event counts. It does not delete old records silently; archive/capacity management remains an operational requirement when the budget is reached.
- Each writer run records its lifecycle, persisted/dropped counts and clean shutdown. Failed writers stop accepting observations. Existing runs and observations survive restarts.
- Paper entry and exit records now carry quote observation IDs. `GET /api/market/observations/{identifier}` retrieves a durably stored observation; missing, queued or dropped IDs return a clear 404 instead of an invented quote.
- Market-data status reports writer health, queue depth, persisted count, drops and errors. The learning monitor reports recording gaps and never treats this as verified complete exchange history.
- Validation: 26 recorder/runtime/integrity tests passed, followed by 43 broker/monitor/recorder/integrity tests after trace/restart changes. These test runs overlap.
- Restarted and verified the running writer at approximately 10:43 IST. It had persisted one connection marker and two underlying startup observations, with no drops or writer errors. A read-only API lookup matched the stored observation. There were no recorded option quotes or market-session fills in this check; startup observations are not forward performance evidence.

This completes the durable top-of-book recording foundation, not the paired baseline evaluator. A contemporaneous baseline/challenger account comparison, full quote-path replay, exchange book timestamp/sequence assurance and sufficient forward sessions remain required before claiming learning improves entries or exits.
