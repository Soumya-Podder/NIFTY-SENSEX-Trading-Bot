# Option-buying screen implementation — 26 September 2026

This is a paper research change, not evidence of improved profits. Capital remains
₹30,000; per-trade and correlated risk remain ₹600; daily planned loss allocation
is ₹1,000 plus ₹200 execution reserve, with a ₹1,200 hard halt and one-position cap.

## Entry rules

`backend/app/option_screen.py` provides one shared screen used by candidate
selection, offer preparation, final revalidation and the primary paper broker.

| Check | Implemented behavior |
| --- | --- |
| ATM | Included in subscriptions and eligible for selection/fill |
| Delta | Absolute 0.45–0.60 preferred; 0.30–0.45 only in an aligned trend |
| Direction | CALL Delta positive; PUT Delta negative |
| Greek age | Original observation time, 0–120 seconds; missing/future values block |
| Spread | `(ask-bid)/((ask+bid)/2)`; at most 2%, at most 1% preferred |
| Depth | Fresh observed bid/ask, sufficient quantity on each side for one lot |
| Expiry | Nearest eligible expiry, excluding expiry day |
| Target | Existing structural 2R nominal target; never extended to pass a screen |
| Net economics | `(target-entry)*quantity - round-trip target charges` divided by all-in stop risk |

`MAX_SPREAD_PCT=0.02` uses midpoint throughout the new screen. The setting
`MIN_NET_REWARD_RISK` defaults to 1.0. Nominal 2R is less than net 2R after spread
and costs. Raising the minimum to 2 rejects those existing targets; it does not
invent a farther target or establish a better strategy. A candidate can still be
rejected by structure, fees, remaining risk, cash, session, ML/EV or account locks.

All-in risk reserves one adverse spread at exit and includes round-trip stop
charges once. Stop fills remain uncertain. Targets are conditional outcomes, not
expected profit. Zero trades remains a valid result.

## Greek and positioning evidence

- Gamma is recorded as a local sensitivity, not a direction or institutional-money signal.
- `abs(theta)/midpoint*100` is exposed as daily Theta percentage only when units
  explicitly establish premium per day. Dhan's public field definition does not
  specify its time convention; the runtime leaves daily normalization unavailable.
- Vega's response to a one-percentage-point IV drop is a conditional sensitivity,
  using the provider's documented units. It is never subtracted from observed P&L.
- An IV percentile requires a comparable underlying/maturity history. None is
  fabricated from mixed expiries or today's chain. This remains unavailable.
- Raw Greeks, units, original observation timestamps and OI context are retained
  in project-local context inputs and the bounded quote recorder for future replay.
- Missing OI/volume in a depth packet preserves the chain observation; an explicit
  zero stays zero. The source Greek/chain timestamp is never advanced by that merge.

## Versioning and learning

Prepared entry signals, confirmed positions, episodes and selection evidence carry
`option_screen_version=option-buyer-v1`. Expectancy matching requires the same
screen. ML scopes include it, so old screen models cannot silently control entries.
This is deterministic filtering, not newly learned behavior. Existing validation
and promotion requirements are not relaxed.

## Replay and limitations

The candle engine defaults to the labelled `legacy` screen to preserve historical
baseline research. New reports expose `option_screen_validation` and explicitly
deny current runtime-screen validation. Existing saved reports are not rewritten.

The CLI accepts `--option-screen option-buyer-v1` and `--min-net-reward-risk 2`
for research comparisons. When observed depth or timestamped Greeks are absent,
the screen records missing-data reasons and the result is `research_partial`,
not a successful zero-trade validation. Even with those fields, candle fills do
not reproduce a two-second book path; these comparisons cannot train/promote a model.
Fees, intrinsic value or an average premium cannot substitute for missing Greeks.

From `Trading Bot/backend` in CMD:

```bat
.venv\Scripts\python.exe -B -m app.backtest.cli --source csv --csv "..\data\backtest_inputs\2026-09-23\contracts.csv" --strategy portfolio --option-screen option-buyer-v1
```

Use the actual downloaded CSV path. Full forward validation still requires enough
independent sessions, realistic spreads/fees, chronological holdouts and review.

Sources: [Dhan option-chain fields](https://dhanhq.co/docs/v2/option-chain/),
[OIC Theta](https://www.optionseducation.org/advancedconcepts/theta),
[OIC Vega](https://www.optionseducation.org/advancedconcepts/vega).

## Verification completed 27 September 2026, shortly after midnight IST

- Full backend suite: **297 passed**. After the final same-price/changed-Delta
  revalidation change, the affected screen, portfolio and runtime suite: **65 passed**.
- Frontend: **15 passed**; TypeScript and Vite production build passed.
- Tests cover ATM admission, signed Delta bands, stale/future Greeks, midpoint
  spread boundaries, atomic broker bypass rejection, expiry day, one-time cost
  accounting, final feature refresh, old model isolation, missing replay inputs,
  recorder field retention, and sparse depth packets preserving OI.
- Restarted backend and checked the actual dashboard: `option-buyer-v1`, 2% midpoint
  spread, ₹30,000 capital, ₹600 trade risk and ₹1,200 daily loss limit. Paper enabled,
  real orders disabled, no positions, `WEEKEND`. This is not live-session validation.
- Graphify AST update: **2,527 nodes, 4,439 edges, 298 communities**. The existing
  parser warning for `frontend/src/main.tsx:305` remains; TypeScript/Vite compile it
  successfully, but Graphify may extract that file only partially.

Offline comparisons used the downloaded exact-contract CSV for **23 September**
and the current account limits, without changing the saved dashboard report:

| Run | Outcome | Meaning |
| --- | --- | --- |
| [Legacy baseline](data/maintenance/option-screen-2026-09-26/legacy-baseline.json) | 2 trades, −₹580.94, research net | Raw CSV fee scenario; not the previously reviewed receipt-based report |
| [Current buying screen](data/maintenance/option-screen-2026-09-26/current-screen.json) | 254 missing-data checks; 0 admitted trades; headline P&L unavailable | Depth/timestamped Greeks absent; cannot validate the new rules |
| [Strict net-2R comparison](data/maintenance/option-screen-2026-09-26/legacy-net-2r.json) | 0 trades | Existing nominal-2R targets do not clear net-2R after costs |

These results justify neither a profit claim nor model promotion. New screen
validation still needs sufficient observed data and independent forward sessions.
