# Exact-contract backtest evidence — 20 September 2026

## Decision

The strict evidence pipeline now produces complete, verified reports for the observed 17–18 September 2026 sessions. Every executed portfolio trade passes all seven learning-admission gates. The report is eligible to supply training observations, while model fitting and promotion remain blocked by the minimum-sample guard.

This result is a two-session paper simulation. It does not establish a profitable edge or support a daily-profit guarantee.

## Reproducible report

- Report ID: `observed-2026-09-17-to-2026-09-18-portfolio-ca29e67f22`
- Report file: `data/backtest_inputs/2026-09-17_to_2026-09-18/portfolio_report.json`
- Suite summary: `data/backtest_inputs/2026-09-17_to_2026-09-18/suite.json`
- Input manifest: `data/backtest_inputs/2026-09-17_to_2026-09-18/manifest.json`
- Saved charge evidence: `data/backtest_inputs/2026-09-17_to_2026-09-18/portfolio_charge_receipts.json`
- Broader-range data blockers: `data/backtest_inputs/2026-09-11_to_2026-09-18/coverage_blockers.json`

Running the same replay twice produced the same report IDs and the same trade IDs.

## Data and execution evidence

- 132 exact archived contracts: 68 on 17 September and 64 on 18 September.
- 46,330 exact-security-ID option minute observations.
- Same-day archived Dhan security-master metadata supplies exchange, security ID, expiry, strike, option type, lot size and tick size.
- Dhan intraday candle responses supply the underlying and option prices. Missing option minutes remain empty and are never filled or interpolated.
- The acquisition envelope covers each session's observed ATM strike plus or minus six strikes for the nearest later expiry.
- Candidate sizing uses a conservative fee scenario. Every completed trade is replayed with saved Dhan brokerage-calculator components for its exact exchange, security ID, quantity, entry price and exit price.
- The replay uses one adverse exchange tick and a stop-first rule when a minute candle crosses both barriers.

## Strategy results

| Strategy | Trades | Wins / losses | Net P&L | Charges | Profit factor | Seven-gate result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Opening-range retest | 1 | 0 / 1 | -₹184.40 | ₹57.65 | 0.00 | 1 passing, 0 failing at every gate |
| Trend pullback | 4 | 3 / 1 | +₹486.36 | ₹265.14 | 2.287 | 4 passing, 0 failing at every gate |
| Range rejection | 0 | 0 / 0 | ₹0.00 | ₹0.00 | No trades | No trade records to admit or reject |
| Shared portfolio selector | 4 | 3 / 1 | +₹486.36 | ₹265.14 | 2.287 | 4 passing, 0 failing at every gate |

The shared portfolio selected the trend-pullback opportunities during these sessions. The strategy and portfolio rows describe the same four simulated outcomes and must not be added together.

Portfolio daily net outcomes were +₹261.21 on 17 September and +₹225.15 on 18 September. Neither day reached the ₹1,000 net target. Maximum intraday drawdown was ₹499.41. The largest planned trade risk was ₹567.07, below the ₹600 per-trade and correlated-risk cap. No daily result breached the ₹800 hard daily loss limit.

## Seven learning gates

| Gate | Portfolio passing | Portfolio failing | Evidence |
| --- | ---: | ---: | --- |
| `quality="verified"` | 4 | 0 | The report and every completed trade are verified. |
| `status="complete"` | 4 | 0 | Both supplied sessions finished with complete account results. |
| No report issues | 4 | 0 | `issues=[]`. |
| No unresolved exits | 4 | 0 | `unresolved=[]`. |
| Verified fixed-contract provenance | 4 | 0 | Numeric NSE/BSE security IDs and archived dated metadata are present. |
| Completed observed net-cost outcomes | 4 | 0 | Gross P&L, saved entry/exit charge receipts and net P&L reconcile within one paisa. |
| Causal entry features | 4 | 0 | The required feature schema and at least six values were recorded before entry. |

The earlier 195-trade rolling report remains ineligible. Its rolling identities, estimated fees and incomplete report coverage are properties of its source evidence and cannot be repaired by relabeling it.

## Learning status

Four portfolio observations are admitted by the evidence gates. No model was fitted or promoted. Each current strategy/index scope contains only one independent trade day. The guard requires at least 34 independent sessions before splitting the data, at least 60 training trades, and at least 30 unseen holdout trades. Any future fitted filter must then pass the holdout and full-account replay checks before it can become effective in a later paper session.

This is the correct result for the available evidence. Lowering these thresholds would make the dashboard appear active without establishing out-of-sample improvement.

## Rejected coverage

The attempted 11–18 September range failed closed:

- 11 September: Dhan returned no exact option candles for NIFTY or SENSEX.
- 14 September: Dhan returned no NIFTY or SENSEX index candles, so no session was replayed.
- 15 and 16 September: NIFTY option candles were present, while SENSEX option candles were absent.

The runner writes these failures to `coverage_blockers.json` and refuses to publish a complete two-index report for those dates.

## Fixed controls

- Paper capital: ₹30,000.
- Planned loss allocation: ₹600.
- Execution reserve: ₹200.
- Hard daily loss halt: ₹800.
- Maximum risk per trade: ₹600.
- Maximum correlated open risk: ₹600.
- Maximum open positions: one.
- Monitoring starts at 09:15 IST and session liquidation is requested at 15:05 IST.
- Live-money order authority remains disabled.

## Verification

- Backend full suite: 240 tests passed after the final determinism changes.
- Evidence, learning and backtest focused suite: 59 tests passed.
- Python bytecode compilation: passed.
- Frontend TypeScript and Vite production build: passed.
- Economic invariant audit: every trade reconciles `net = gross - charges`; every admitted gate has zero failures; configured risk and time boundaries match the report.
- Graphify AST graph refreshed after the code changes.

## Remaining evidence limits

- Two sessions and four portfolio trades are far below the validation minimum.
- Minute OHLC candles do not reproduce bid/ask depth, queue position, latency or partial fills.
- Dhan calculator receipts certify the calculator result used by the replay; they are not broker contract notes or actual fills.
- The same-day archived master establishes the contract metadata used for that date; it does not prove the exact intraday publication time of every master row.
- The downloaded universe is the session ATM ±6 envelope for the nearest later expiry, rather than every listed option.
- Consistent daily profit cannot be inferred from these observations.

## External fee references

- [Dhan pricing](https://dhan.co/pricing/)
- [NSE securities transaction tax](https://www.nseindia.com/static/products-services/equity-derivatives-securities-transaction-tax)
- [NSE statutory levies and stamp duty](https://www.nseindia.com/static/invest/first-time-investor-sebi-turnover-fees-stt-other-levies)
