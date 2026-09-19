# Options Paper Lab

The active paper engine now evaluates opening-range retest, trend pullback and
range rejection with one shared selector. See [the strategy specification](MULTI_STRATEGY_PAPER.md)
for exact rules, evidence labels and execution limits. The existing historical
backtests remain scoped to their recorded baseline; they do not validate this
new combined paper selector.

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
npm run build
```

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

## Paper execution

- Entries start enabled when `PAPER_AUTOSTART=true`. The dashboard's paper toggle enables or pauses only the simulated broker; it never enables live order authority. The paper engine still applies fresh-data, session, contract, cash and risk gates.
- One persistent ₹30,000 account shared by both indices; the current `.env` policy
  permits one open position/lot across the shared account. NIFTY and SENSEX are
  evaluated in parallel, but they do not bypass the shared position or risk authority.
- Session 09:15–15:05 IST; the opening 15 minutes build the range. Entries stop
  at 14:30. The exit loop continues when entries are paused or the account is halted.
- Current `.env` defaults: ₹750 maximum planned risk per trade, ₹600 same-direction
  correlated open-risk cap, ₹800 daily loss/hard halt, ₹600 planned-loss allocation
  plus a ₹200 execution reserve, and a ₹1,000 net daily target. Charges and existing
  exposure reduce capacity; these are configurable limits, not guarantees against
  gaps or a missing exit quote.
- Closed one-minute index candles, automatic CALL/PUT from aligned setups, nearest
  available expiry and liquid non-ATM options sized from current lot sizes and cash.
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

₹1,000 net daily is a tracking target, not an entry quota or promised outcome.
On ₹30,000 it is 3.33% per day. The implementation does not establish that this is
achievable. Paper results do not establish real execution performance.

## Historical backtests: data, calculation and limitations

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
