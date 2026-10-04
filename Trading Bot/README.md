# Options Paper Lab

The active mode is now `PAPER_STRATEGY_MODE=autonomous` (`autonomous-paper-v1`).
It independently compares trend continuation, opening-range retest, trend
pullback and range rejection on both indices, requires causal support/resistance
and fresh full returned fixed-contract OI context, sizes whole lots within the
shared ₹30,000 account and ₹650 risk cap, and manages HOLD/EXIT decisions alongside
the independent protective worker. The daily hard halt is ₹1,200. The monthly
₹18,000 net objective is reported without forcing entries or promising a return.

Archived-input backtests run this same engine in an isolated virtual account;
missing quotes/OI/Greeks/fees stay visible as partial evidence. Completed paper
episodes feed separate paper research learning with chronological holdouts and
independent full-account replay before a next-session entry filter can activate.
The detailed current specification is [the implementation plan](NIFTY_SENSEX_Implementation_Plan.md).
There is no live order authority or automatic source-code rewriting.

The modes and journaling described below remain available for legacy comparison.

With `PAPER_STRATEGY_MODE=simple`, the active paper engine uses the versioned
completed-bar trend continuation rule. It requires a one-to-four ATR structural
invalidation, limits spread to 10% of the Delta-mapped premium stop distance,
requires Greeks no older than 45 seconds, and ranks eligible NIFTY and SENSEX
contracts by net reward per all-in planned risk. These are conservative paper
filters, not a demonstrated profitable edge. The optional portfolio mode is
documented in [the strategy specification](MULTI_STRATEGY_PAPER.md). Existing
historical backtests do not reproduce the active simple engine's streaming depth
and Delta checks.

Every completed-bar candidate seen by the simple engine is journaled with its
subscribed index and option quote observations in the project database, including
signals blocked by an existing paper position. These records are labelled
`OBSERVED_ONLY` and contain no hypothetical fill, exit or P&L. A journal write
failure is shown as an advisory error and cannot stop exit management.

Local NIFTY/SENSEX options-buying research and paper execution. There is **no live
order authority**: both the API Live toggle and the broker order boundary reject it,
regardless of environment flags. No runtime market fixtures or fabricated prices are used.
The unused analytical interfaces in `app/ai.py` are placeholders, not trained models.

## Run

From this project directory, `run_backend.bat` starts the API on 127.0.0.1:8080;
`run_frontend.bat` starts the UI on http://127.0.0.1:5174. Vite uses a same-origin
API proxy and refuses to silently switch ports.

The backend reads the project's existing `.env`. Set `DHAN_CLIENT_ID` and
`DHAN_ACCESS_TOKEN`; the engine now reloads changed credentials automatically. Never put
credentials in frontend code. `PAPER_AUTOSTART=true` enables entries on startup and each new session.
Existing paper account state and manual halts survive restart.

Verification:

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q
cd ../frontend
npm test
npm run build
```

Frontend request tests use Node's built-in test runner and TypeScript stripping
(Node 22.18+ or 24+). No additional test packages are required. Requests have a
30-second deadline even when cancellable; switching reports discards older
responses. A failed report can be retried without starting a new backtest.
Paper trade history refreshes on exits, session changes and reconnection, and
displays a warning if it cannot refresh. The audit drawer supports keyboard
focus containment, Escape to close, and returning focus to its opener.

## Automatic operation and credential refresh

The installed Windows task `Options Paper Lab Supervisor` starts at 09:10 IST on
weekdays and at user logon. Reinstall/update it with `./install_paper_schedule.ps1`.
Windows must remain on India Standard Time. The task uses the current user's
logged-in session, requests wake from sleep, and starts when a missed trigger
becomes available. A powered-off PC or signed-out user cannot be guaranteed a
09:15 start. The supervisor checks every two seconds and restarts a missing API
without killing a running service. Open positions and risk halts remain persisted.

Monitoring begins at 09:15; the opening range forms during the first fifteen
minutes. New entries stop at 14:30. Session liquidation begins at 15:05. Missing
executable quotes remain visible as pending exits, and exit management continues.

The project `.env` is authoritative for Dhan credentials, including over inherited
process environment values. It is checked every engine cycle and before REST
requests and response acceptance. Changed credentials replace the client,
invalidate current data, and reconnect the stream. Responses from an older
credential generation are discarded. Health exposes check times and a generation
counter, never credential values.

`PAPER_COLLECT_EVIDENCE=true` permits paper observation while the matching
net-outcome sample is below 30 trades / 10 sessions. The EV stage reports
OBSERVATION and records the evidence mode on positions and outcomes; it does not
claim positive expected profit. All structural protection, fee, liquidity, cash,
position and loss gates still apply. When the sample becomes sufficient, a
nonpositive net-evidence screen rejects entry. Set this flag false to require
supported net evidence before any entry. Historical research is not promoted by
this setting.

Current per-index scan status includes the last completed bar, evaluation time
and waiting/rejection reason. A new scan clears old downstream agent-card states.
NIFTY and SENSEX have separate data workers and one shared portfolio authority.

The research coordinator and learning worker have a liveness watchdog. If either
worker thread stops unexpectedly, it is recreated and a `WORKER_RESTARTED` event
is recorded. This means the agents keep observing, retrying data/learning work,
and waiting through unavailable evidence without silently becoming inactive.
It does **not** mean they force trades, bypass risk halts, retry indefinitely
against a broken process, or invent prices/fills; the shared paper engine,
freshness gates, persistence checks and Risk Sentinel remain authoritative.

## Paper execution

- Entries start enabled when `PAPER_AUTOSTART=true`. The dashboard's paper toggle enables or pauses only the simulated broker; it never enables live order authority. The paper engine still applies fresh-data, session, contract, cash and risk gates.
- One persistent ₹30,000 account shared by both indices; the current `.env` policy
  permits one open position across the shared account and multiple whole lots only
  when the combined cash, depth and ₹600 risk checks pass. NIFTY and SENSEX do not
  bypass that shared authority.
- Session 09:15–15:05 IST; the opening 15 minutes build the range. Entries stop
  at 14:30. The exit loop continues when entries are paused or the account is halted.
- Current `.env` defaults: ₹600 maximum planned risk per trade, ₹600 same-direction
  correlated open-risk cap, ₹1,200 daily loss/hard halt, ₹1,000 planned-loss allocation
  plus a ₹200 execution reserve, and a ₹15,000 monthly net target after trading charges. Charges and existing
  exposure reduce capacity; these are configurable limits, not guarantees against
  gaps or a missing exit quote.
- Entry selection requires option depth received within two seconds and an index
  reference received within five seconds. The simple trend rule checks completed
  one-minute bars and rejects an index quote more than one ATR beyond the signal
  close. Every attempted fill rechecks the current quote, costs and total risk.
- Closed one-minute index candles, automatic CALL/PUT from aligned setups, nearest
  available non-expiry-day contracts including eligible ATM options, sized from current lot sizes and cash.
  Missing index volume stays missing: volume/VWAP setups are unavailable; price-only
  EMA setups can still be evaluated and are explicitly labelled.
- Entries use observed ask/depth; exits observed bid/depth. Option depth comes
  from Full WebSocket packets; index monitoring uses Ticker packets. Stream update
  receipt times determine observed update age. Provider last-trade timestamps are
  retained separately and do not establish bid/ask age. REST price snapshots never
  qualify as executable depth. Missing or stale depth fails closed.
  A session-exit request without liquidity remains visible as a pending exit, never
  a fabricated fill. Partial exit attempts are separate simulated orders and each
  incurs an estimated order charge. Completed-position learning aggregates partials.
- Charges come from Dhan's current public brokerage calculator. Component values,
  source, calculation date, total and broker rounding residual are retained. They
  are estimates, not broker contract-note settlements. Open P&L excludes prospective
  exit charges; realized P&L includes entry and exit charges.
- NIFTY/SENSEX display refreshes every two seconds. Weekend/closed-market values
  are labelled last observed, not live. An exchange holiday calendar is not yet
  integrated; fresh quote and closed-bar gates prevent stale holiday entries.

₹15,000 net monthly is an average tracking target after trading charges, not
an entry quota or promised outcome. The implementation does not establish that
this is achievable. Paper results do not establish real execution performance.

## Historical backtests: data, calculation and limitations

New dashboard, CLI and observed-session exact-contract runs share the paper settings
snapshot (₹30,000 capital, ₹600 risk, ₹1,000 loss allocation + ₹200 reserve by default).
The current option screen is the default for these entry points. Choose
`--option-screen legacy` only for an explicitly labelled historical comparison.
Historical candle files without timestamped Greeks and executable depth cannot
validate the current buying screen; missing evidence stays blocked, not zero-profit
performance. Full specialist-review and two-second execution parity remain unproven.
Reports retain their own target/basis and policy snapshot; old reports are not rewritten.

Monthly metrics now sum net session P&L. The dashboard shows monthly net progress;
open positions use estimated liquidation value only when executable valuation is
available. Exit analysis groups actual completed exits and holding periods rather
than assuming that every nominal 2R target is realised.

Backtest capital and per-trade risk accept positive finite values without an
application-defined upper cap. Daily and correlated risk budgets can be overridden
independently; blank values scale with per-trade risk using the configured paper
budget ratios. Effective values are saved with the run. They never update paper
account safeguards. Whole-lot cash affordability and the selected portfolio budgets
still constrain simulated quantity.

Paper execution and both historical engines share `available_risk` in `app/risk.py`,
as well as the signal/feature pipeline. Execution parity is not claimed: historical
rolling data lacks observed depth/spread and exact expiry metadata, so its selection
and fill adapters remain research assumptions. Paper EV uses prior paper evidence;
today's policies/outcomes are not injected into earlier backtests as future knowledge.

Every learning ledger entry now includes agent-context outcome lessons: sample
counts, observed P&L, losing exit reasons, and explicit exclusion-test proposals
where the configured sample threshold is met. These associations do not establish
causation or loss reduction. Gross research proposals remain unapplied; verified
datasets require chronological training, validation and untouched-test replays before
policy promotion. Never estimate improvement by simply deleting losing trades.

Dhan's expired-options endpoint returns **rolling moneyness**, not continuous
history for a held fixed strike. It supplies strike per candle, but not the dated
contract identity, historical lot-size validity and fee schedules required by this
verified replay. Today's security master must not be represented as historical metadata.

The bot now calculates a **gross research scenario** from Dhan candles over the
requested range, not merely a recent-week integrity probe. Choose 7/30/90 calendar
days, 1–5 years, or custom dates. Data is downloaded in bounded chunks, subject to
actual API availability; selecting five years does not prove five years of coverage.

Entries use the same frozen base signal pipeline, automatically choose CALL/PUT
and non-ATM budget-fit strikes, and share the selected capital between indices.
The replay joins actual strikes across ATM±3 rolling series. A held strike moving
outside that range triggers on-demand ATM±4 through ATM±10 recovery. Expiry bucket
identity is provisional and scoped to one session, never represented as a verified
exchange contract. Missing or conflicting held candles stop the replay and withhold
headline performance. Opening fills occur before intrabar exit proceeds can fund
other entries. Stops take priority over targets within an ambiguous candle.

Rupee sizing explicitly uses current nearest-expiry lot sizes fetched from Dhan.
This is **not historical lot-size verification**. Gross scenarios have no bid/ask,
slippage or dated fee model; net P&L and charges remain unavailable. They cannot
establish after-charges profitability or promote learning policies. Agent contexts
and gross outcomes are retained in the learning ledger as research evidence only.

Historical responses are compressed inside the existing
`backend/trading_bot.db` (`history_cache`), not scattered across generated files.
Nonempty backtest responses have no automatic expiration; matching requests reuse
them across restarts. Empty responses retry after one day. New date/request ranges
still require downloads, and retained data does not automatically incorporate later
provider corrections. Live quotes and current metadata keep their refresh rules.

The UI includes daily/monthly/yearly breakdowns, every saved trade through paging,
index/date/outcome filters, CSV export of all matching trades, full JSON report
export, entry/exit timestamps, SL/target, gross/charges/net columns, and readable
agent/contract audit details. No export file is created until the user downloads it.

Primary sources:

- [Dhan's explanation of rolling versus fixed-strike history](https://dhan.co/support/platforms/dhanhq-api/can-i-fetch-ohlc-data-for-a-fixed-option-strike-throughout-the-entire-trading-session-using-the-rolling-option-data-api/)
- [Expired-options response fields](https://dhanhq.co/docs/v2/expired-options-data/)
- [Dhan compact-master tick sizes are paise, converted to rupees](https://madefortrade.in/t/clarification-on-tick-size-of-5-0/55951)

## Running an actual historical simulation

Place a **sourced contract-specific CSV** in the existing `data` directory and
select it in Backtest Lab. The application never creates a demo dataset. Each row
represents one actual option contract at one minute's start. Required columns:

```text
timestamp,symbol,contract_id,expiry,strike,lot_size,tick_size,option_type,
open,high,low,close,volume,oi,
underlying_open,underlying_high,underlying_low,underlying_close,underlying_volume,
metadata_source,metadata_valid_from,metadata_valid_to,price_source,charge_schedule
```

### Optional Telegram paper alerts

Set these values in `Trading Bot/.env`, then restart the backend:

```dotenv
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_or_channel_id
```

Telegram sends one market-day start report at 09:15, confirmed simulated entry and
exit messages, position/P&L updates approximately every two seconds only while a
durably entered paper position is open, and one session report at 15:35. A no-trade
report includes persisted rejection reasons. Start/end checkpoints survive restart.
Message delivery is asynchronous and never authorizes or blocks an order.

Use IST timestamps or timezone-qualified timestamps, ISO expiry/validity dates,
CALL/PUT, prices/tick sizes in rupees, and actual historical lot sizes. Contract IDs
must remain unique across exchange, expiry, strike and option type. Source metadata
is checked structurally, not independently authenticated against an external vendor.

`charge_schedule` is a quoted JSON object with a source reference, `valid_from`,
`valid_to`, per-order `brokerage`, `gst_rate`, and `buy`/`sell` objects containing
turnover rates for `exchange`, `stt`, `sebi`, `ipft`, `stamp_duty`. It also requires
`rounding`, with decimal precision for those components and `gst` (0/2/4/6).
Populate these from dated broker/exchange schedules, never guessed defaults.
The calculator currently supports fixed per-order brokerage and these charge
components; a materially different historical tariff needs a matching calculator.

Include the real candidate universe (including the nearest strike so ATM can be
excluded correctly), both directions, and held contracts' subsequent candles.
Every supplied session must have all one-minute underlying bars from 09:15 through
15:05. Missing entire trading days still require an exchange calendar; reports state
actual supplied coverage and must not be interpreted as complete requested-year results.

The recorder database at `data/market_observations.db` is auditable with:

```powershell
python -m app.backtest.observation_audit `
  --db ..\data\market_observations.db `
  --output ..\data\option_observation_audit.json
```

This audit reports recorded option rows, symbols, contracts, exchange-date
coverage, missing quote fields, dropped recorder rows and unclean runs. It
deliberately does not convert quote/depth observations into OHLC candles or
mark them eligible for fixed-contract replay: that requires a documented
one-minute aggregation policy, dated charges, and a complete coverage manifest.

To replay downloaded Dhan rolling history already retained in the local cache
without making a network request, run:

```powershell
python -m app.backtest.cli --source rolling-cache `
  --from 2023-01-01 --to 2026-09-15
```

This is a rolling research replay. Its output remains incomplete/research-only
because Dhan rolling candles do not prove fixed security IDs, historical lot
sizes, bid/ask execution, or dated broker charges. Use the CSV path above for
verified fixed-contract replay.

Replay uses shared cash across indices, the next candle's actual open, one adverse
tick with adverse tick-grid rounding, entry-bar exit checks, stop-first resolution
when both barriers cross, 15:05 exits and marked-to-market drawdown. OHLC cannot
model queue priority, exact intrabar order, real spreads or market impact. MAE/MFE
are bar-extrema estimates, not exact fill-path observations. Missing held-contract
data or changed identity withholds headline P&L and leaves unresolved positions visible.

The fixed one-minute strategy never silently switches to hourly candles for longer
ranges. Background jobs have persisted progress, cancellation, errors and reports;
page refresh does not clear results. Interrupted server jobs are labelled interrupted,
and source caches are retained. Reports and accounting use the existing SQLite DB;
legacy learning rows are preserved, but cannot control new trades.

## Agent learning: what exists and what is not proved

All eight agents record their own contexts and an outcome ledger. Each completed
position's P&L is attributed to participating agents; this is **not** an additive
causal decomposition. Paper fills record feedback, not automatic proof of learning.

For a structurally verified historical dataset with at least 50 sessions, candidate
context-exclusion policies use disjoint 60% training / 20% validation / 20% final
test windows. Defaults require 60 training trades, 20 trades in a proposed loss
context, and 30 retained trades plus 10 sessions in each later window. Baseline and
candidate replay the complete chronological portfolio; trades are not merely removed
from an old report. Gates require positive expectancy, improved P&L, no worse drawdown,
70% trade coverage and a positive conservative paired-session improvement bound.
These gates reduce overfitting risk; they do not establish statistical certainty.

Examined holdouts cannot be reused to promote another candidate. At most one policy
is promoted; it starts no earlier than the next day, expires after 30 days, and is
rolled back on a forward paper daily-loss halt. Further combinations await forward
evaluation. Risk caps cannot be increased by learning. The UI shows proposal,
version, contexts, evidence and rejection/promotion status. Daily-loss rollback is
implemented; a matched live shadow-account comparison and drift-triggered rollback
are not yet implemented.

Until valid replay evidence and forward paper results exist, treat these components
as P&L-attributing filters with a validation framework—not proven self-learning agents.

## Principal endpoints

- `GET /api/dashboard`, `/api/health`, `/api/learning`, `/api/paper/trades`
- `POST /api/paper/control` (`enabled`), `/api/halt`, `/api/resume`
- `POST /api/backtest/run` → HTTP 202 job ID
- `GET /api/backtest/jobs/{id}`, `POST /api/backtest/jobs/{id}/cancel`
- `GET /api/backtest/report`, `/api/backtest/reports/{id}`
- `GET /api/backtest/datasets`, `WS /api/ws`

Bind locally. This is not a hardened multi-user deployment.

## Chart replay and retained futures volume

Open **Market charts → Replay**, select a saved market session in IST, and use
Play/Pause, one-second steps, Next price update, the timeline, or Go to time. Playback supports
1×–60× speed; candle-only sessions default to 60× (one saved minute per second).
Follow cursor keeps the latest replay candle visible and can be disabled to pan.
Switching timeframe or index retains the selected session clock. Return to live restores the normal chart polling. Replay reads local
archives and never runs a strategy, places an order, or changes the paper account;
the live paper engine continues separately.

Valid recorded observations appear at their receive second. Completed historical
minute candles and futures volume appear only at candle close, confirmed zones only
after confirmation, and saved trade exits only after their recorded time. Where no
valid observations exist, the UI explicitly uses candle-only playback. Missing or
inconsistent timestamps are excluded; intraminute prices and volume are not invented.
Original historical candle receipt times and complete exchange tick coverage are
not established, so this is a visual reconstruction, not a strategy backtest.
Reload archive refreshes the frozen session dataset and preserves the selected clock.
Two session datasets are cached in memory for reuse across timeframes. Replay sends
up to 200 prior chart candles as context; zone detection still uses the retained
365-day history. The normal live chart retains its longer candle history.
First loading a large archive can take longer than a normal chart refresh.

Futures volume uses verified saved contracts across expiries. Each session uses the
earliest unexpired retained contract with data for that day. Overlapping expiries
are never summed, and missing minutes are not filled from a different contract.
The chart labels the selected candle's contract and expiry, marks contract changes,
and displays the actual retained coverage. This is a recorded contract series;
it does not establish complete front-month history or one-year volume coverage.

- `GET /api/market/chart/{symbol}?period=5m`
- `GET /api/market/replay/{symbol}?day=YYYY-MM-DD&period=5m`
