# Paper engine remediation — updated 7 October 2026

## October 7 execution audit and repair

The October 7 paper session ended with zero entries and ₹0 session P&L. Read-only inspection found 44 unique opportunities, 795 decision-review records, four selection records and six eligible contract reviews. Reviews are repeated evaluations, not six distinct executable trades.

- A NIFTY CALL review passed at 12:45:27 IST, then final admission rejected its nominal 2:1 protection at 12:45:39. The minimum-stop branch rounded the stop down without recalculating the target from the widened distance. Protection now uses the actual rounded stop distance. An isolated regression reproduces the old failure: entry 100, stop 98.95 and target 102.05; the corrected target is 102.10.
- SENSEX offers passed review around 13:33 but two reached final admission around 13:35:10, after setup expiry. Fee HTTP ran serially in the selector before ranking. Missing fees now queue on the existing preparation worker; selector and final admission use prepared broker fees. Fees, expiry and fresh-book requirements remain mandatory.
- Candidate review retained an earlier option book while the feed had newer observations. It now reads the current book after completed-signal validation, checks contract identity and reassesses option evidence. A truly stale live book still blocks admission.
- Trend rejection now distinguishes a completed close crossing EMA 21 from extension beyond two ATR; thresholds are unchanged.
- Replay accepts the protection repair's existing `cache_seconds` argument. Large quote archives retain compressed book payloads until consumed, preserving observation IDs, receipt ordering and quote content instead of expanding millions of books before replay begins.
- Dhan currently rejects the installed token with DH-906 in renewal; a direct profile check also fails. Its embedded expiry is 7 October, 22:02:38 IST. The application now exposes a redacted, actionable credential-renewal advisory, and clears obsolete renewal status when project credentials rotate. A valid replacement token remains an external prerequisite; no fabricated authentication or quotes are permitted.

Verification: 80 paper/portfolio/fee/recovery/replay tests passed, followed by 64 replay/runtime/integrity checks. Three additional checks passed for expired fee requests, rotated credentials and genuinely stale books. The final credential-advisory/runtime/integrity run passed 57 checks. These runs overlap and are not a count of unique tests. The local backend was reloaded while flat; all 13 existing workers were alive, persistence was healthy, live order authority remained disabled and cash/equity remained ₹30,335.47. Health now exposes DH-906 as a credential advisory and entry readiness shows the disconnected feed. Today's captured-input replay is separate from the production ledger; a completed replay result has not yet been claimed.

The user clarified on October 7 that ₹650 is a per-lot allowance. Sizing and atomic admission now use the smaller of ₹650 × whole lots and the remaining ₹1,000 planned daily loss allocation, including estimated charges and spread. The sizing version is `risk-sized-whole-lots-v3-per-lot`; earlier-policy outcomes retain their original version. Shared capital remains ₹30,000, with one position, ₹200 execution reserve, ₹1,200 hard daily halt, three entries/two losses and five-minute cooldown. Monthly reporting target is ₹18,000 net; daily ₹1,000 net is an objective, not guaranteed. Entry cutoff remains 14:30 and liquidation requests start at 15:05. The incomplete captured-input replay started before this sizing amendment was stopped; it is not a completed result of the new policy.

Per-lot verification: the broader run passed 197 checks; its remaining replay assertion still expected the superseded ₹650 whole-position cap. After correcting that assertion and adding sizing-version checks to learning/replay, all 25 final focused checks passed. These runs overlap. The tests cover a ₹840 two-lot entry and restart recovery, daily-budget and single-lot rejections, preserved loss spend, rejection of old sizing outcomes/models, and an isolated captured-book entry/exit above ₹650 without HTTP or production-ledger writes. Frontend TypeScript/Vite build and changed-Python parsing passed. At 16:50 IST the reloaded API reported `per_lot`, all 13 workers and persistence healthy, ₹30,335.47 cash, zero positions, unchanged ₹1,000 allocation/₹200 reserve/₹1,200 daily halt and live authority disabled. Credential renewal remained failed. Dashboard and Telegram session-summary labels now say risk per lot.

At 21:07 IST on October 7, the replacement project `.env` token had resolved the earlier DH-906 authentication blocker: a read-only Dhan profile request returned HTTP 200, the data plan was Active through November 5 and index quote requests succeeded. The replacement token expires October 8 at 20:54:51 IST. Both running credential consumers reloaded it before the controlled backend restart; the new process loaded it directly at startup.

A separate WebSocket handshake initially returned HTTP 429. The feed now reports throttling distinctly from authentication rejection, applies exponential connection backoff (60 seconds initially for 429, up to 300 seconds, with numeric `Retry-After` respected), and prevents the SDK's internal one-second retry loop from bypassing that delay. Each failed attempt is counted once; sockets close before another attempt, and an actual credential replacement clears the prior failure/backoff. Health exposes the HTTP status and remaining retry wait without exception URLs or token values.

Verification: all 76 automatic-recovery/runtime/operational-recovery/execution-integrity tests passed, including isolated handshake and established-connection failures, duplicate SDK callbacks, token replacement and unchanged stale-data admission gates. The API was reloaded only after confirming zero positions and no active replay jobs. At 21:07:39 IST, the reloaded service reported a connected WebSocket, no feed error, all 13 workers healthy, persistence healthy, paper enabled and unhalted, ₹30,335.47 cash, zero positions and ₹0 session P&L. After-hours observations remained stale for entry and the session correctly reported `EXIT_ONLY`; this check does not establish fresh executable option books during tomorrow's market session. Live order authority remains disabled.

### October 7 automatic runtime recovery and three-session audit

Read-only inspection of the latest 5,000 records in each relevant primary-ledger namespace found the following retained evidence. Review counts are repeated checks, not trades; the sparse October 5 records cannot establish full-session coverage.

| Session | Decision-review records | CALL/PUT candidate reviews | Recorded entries / completed trades | Prominent blockers |
| --- | ---: | ---: | ---: | --- |
| October 5 | 10 | 0 | 0 / 0 | Worker/persistence readiness, disconnected feed and missing entry data |
| October 6 | 334 | 4 | 0 / 0 | Fresh option depth, exact-contract protection candles, expired/unconfirmed setup and insufficient structural target room |
| October 7 | 795 | 6 | 0 / 0 | Fresh option depth, exact-contract protection candles, stale completed bars, setup expiry and insufficient structural target room |

This evidence does not support treating every no-trade day as an absence of opportunities. It also cannot prove that every blocked candidate would have filled profitably. The protection rounding, stale cached-book and serial fee-request defects described above have concrete regressions. Technical readiness failures must remain distinct from legitimate market/risk rejection.

A deeper inspection found that October 6's 37 `ERROR` reviews were target-room rejections; October 7's `ERROR` reviews were also predominantly target-room rejections. Expected protection/structure/ATR data gaps now produce `WAITING_DATA`, and target-room/structural-stop rejection produces `BLOCKED`. They no longer throw through the selector as unexpected code exceptions. Actual unexpected exceptions retain `ERROR` records. Historical records are preserved without relabelling or altering outcomes; the trading conditions and target distances are unchanged.

The existing paper engine now independently verifies component recovery in its feed-watch worker. Repairs cover credential reload, stopped workers/recorders/notifier, feed reconnect through backoff and committed account persistence retries. Each component catches its own failure, and admission still checks actual data freshness and liquidity. Candle/chain availability is shown as awaiting recovery during the session and as waiting for the session after hours. Current checks and a bounded fifty-event history appear in the existing monitor UI and persist in the existing database; historical recovery is not current readiness proof.

Two newly reproduced defects are repaired: stale exit/protection errors after another worker durably closes the position, and an unbounded Python write-lock wait ahead of the account's existing SQLite timeout. The latter now has bounded waits for account writes and recovery journaling. Manual/risk halts, unresolved positions and durable ledger state are retained. Unchanged recovery failures do not repeatedly write the journal during backoff. The supervisor additionally permits a bounded restart of its own stalled API only after repeated flat-account/healthy-storage checks; it never treats missing data as a reason to repeatedly restart.

Fault injection uses isolated E-drive accounts and controlled provider observations. No fixture enters the production account and no live broker order is authorised. Persistent provider denial, an absent credential replacement, disk failure or an unknown code defect cannot safely be claimed repaired merely because a retry ran. The ₹18,000 monthly net reporting objective remains an unvalidated target, not a reason to force an entry. The user reconfirmed ₹650 per lot capped by the remaining ₹1,000 planned daily allocation; other limits are unchanged.

Verification of the recovery work: the broader recovery/runtime/autonomous run passed 107 checks. After the final heartbeat addition, all 52 automatic-recovery checks passed. The protection classification/entry/replay/paper suite passed 99 checks, including real expected-gate regressions and preservation of unexpected exceptions. Frontend passed 40 tests and the TypeScript/Vite production build. These backend runs overlap and must not be summed into a unique count. Graphify's final AST update produced 3,142 nodes and 6,340 edges; its pre-existing partial `main.tsx` extraction warning remains separate from the successful TypeScript build.

The existing supervised API and supervisor were reloaded while flat with no active replay job. At 21:50:25 IST on October 7, app/execution/persistence were healthy, all thirteen engine workers were alive, the WebSocket was connected without an error, recovery was `MONITORING`, paper was enabled/unhalted and live order authority remained disabled. Cash was unchanged at ₹30,335.47, with zero positions, zero session entries and ₹0 session P&L. The recovery journal was confirmed durably stored. Dashboard System & risk details and Agentic view's recovery history were verified in the browser; the UI distinguishes historical recovery from current readiness.

The enabled Windows supervisor task is running, with WakeToRun and StartWhenAvailable enabled, no execution time limit and a next weekday trigger of October 8 at 09:10 IST. This verifies the configured launch path, not open-market broker continuity. After-hours candle/chain checks correctly show `WAITING_SESSION`, and admission remains `EXIT_ONLY`. Tomorrow's complete session, fresh selected-contract books, eligible fills and profitable forward performance are not yet observed.

The September checkpoint below is retained as historical evidence. Its older ₹600 risk and ₹20,000 gross target descriptions are superseded by the current limits above.

## Historical September 13 checkpoint

This is an implementation checkpoint, not a declaration of market readiness or a profitable strategy. All execution remains paper-only. The active objective is unfinished.

## Operating constraints verified from the running service

- Starting paper capital: ₹30,000.
- Monthly target: ₹20,000 gross before charges and taxes, averaged across the month; not guaranteed.
- Daily hard halt: ₹1,200, with ₹600 planned allocation and ₹200 execution reserve retained.
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
- Found configuration drift that prevented startup: three positions, ₹1,000 loss cap and ₹1,800 correlated risk. Restored the explicit persistent requirements: one position, ₹1,200 loss/hard halt, ₹600 correlated risk, and ₹20,000 monthly gross target. No credential values were printed or intentionally changed.
- Coordinator statistics now derive from deduplicated, completed paper episodes, separated by strategy and session. Partial fills, historical backtests, inconsistent net-cost outcomes and invalid records are excluded. Drawdown is explicitly closed-episode drawdown, not intratrade drawdown or proof of learning.
- Full suite after replay/calendar integration: **172 passed**. The later focused performance/monitor suite passed **23 tests**; these runs overlap. The UI production build passed.
- Restarted and verified the running API at approximately 10:32 IST on September 13: healthy heartbeat, no dead execution workers, correct ₹1,200/₹600/one-position limits, all four replay modes in the live API schema, underlying-only datasets correctly labelled, and coordinator statistics sourced from closed paper episodes.

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
