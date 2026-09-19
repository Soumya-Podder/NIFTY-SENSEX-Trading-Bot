# Learning evidence monitor

The backend runs one local evidence-monitor worker every 60 seconds. Its dashboard section is **Are the agents learning?** on the Paper & agents tab. It reports each pipeline agent separately, plus the three entry strategies for each of NIFTY and SENSEX. Analysts and adaptive exits are identified separately from trained models.

## What the monitor establishes

- Training requests, actual fitted candidates, validation results, loaded model IDs and attributed paper episodes are separate evidence stages.
- A saved or approved policy is not reported as loaded unless it appears in the running engine's policy dictionary.
- Missing, expired or outdated validation for a loaded model is flagged. Generated commentary and changing rule parameters do not constitute proven improvement.
- A new worker must produce a new heartbeat. A stopped worker, an error or an old heartbeat cannot claim healthy monitoring.
- Changed evidence is retained in `learning_monitor_history` in the existing project database. The API returns the latest 100 changes. Stable evidence does not create a new history entry every minute.
- Historical training records lacking input fingerprints are identified as unverifiable lineage. File presence alone does not prove use of all downloaded candles or complete option-contract history.

Status endpoints:

- `GET http://127.0.0.1:8080/api/learning/monitor`
- `GET http://127.0.0.1:8080/api/learning/monitor/history`

## Overfitting controls

New classifier evaluations use fixed minimums of 34 sessions, 60 training trades and 30 holdout trades. Small research datasets no longer lower these requirements. Training and testing remain chronological, with completed training outcomes required before the holdout boundary.

The holdout is reserved in an atomic SQLite transaction before fitting. A second process, renamed strategy or different exit-policy name cannot reuse the same symbol's already consumed period. Failed fits also leave the reservation intact. This is deliberately conservative: competing same-symbol strategies need a predeclared joint evaluation workflow or later untouched periods.

Promotion additionally requires complete verified replay, valid net costs, matching session coverage, positive net outcomes, no worse daily drawdown, and a positive lower confidence bound for paired daily improvement. The bound includes a conservative correction for recorded classifier attempts. Research-quality replay cannot authorize deployment. New model loading and scoring reject models without the current gate version. An entry-filter validation no longer causes an automatic 5% increase in an exit target.

Legacy policy evaluation retains separate chronological validation/test stages and human review. Its sample floors are restored, and its improvement bound must be positive rather than accepting a negative tolerance.

These are risk-reduction checks, **not proof of no overfitting**. Daily observations can be correlated; unrecorded experiments are not counted; historical execution data and feature semantics may be incomplete. There is no automatic claim of verified forward improvement without model attribution and a contemporaneous baseline. All displayed trading evidence remains **unvalidated paper observation**.

## AI reviewer

The OpenAI Agents SDK runs locally. `LEARNING_MONITOR_PROVIDER=openai` now selects the newly supplied OpenAI key with `LEARNING_MONITOR_MODEL=gpt-5.6-luna`. The existing trading analysts retain their OpenRouter configuration. The monitor also supports explicit `openrouter` selection. It has one read-only tool containing the monitor snapshot. It cannot place orders, change risk settings, fit models, edit files or approve deployments. Its explanation is advisory and cannot overwrite deterministic statuses.

`Trading Bot/.env` is read before every provider call. The explicitly selected provider determines whether `OPENAI_API_KEY` or `OPENROUTER_API_KEY` is used; merely adding a key does not change selection. Keys and full provider exceptions are never included in monitor records. SDK tracing is disabled. Only the allowlisted evidence snapshot is sent for the AI review; keys, raw market files and order tools are not included.

The reviewer checks changed evidence no more often than every 30 minutes. Changed provider credentials/configuration are noticed on the next monitoring cycle. `LLM_ENABLED=false` disables the reviewer while local monitoring continues. Provider errors are visible; HTTP 429 displays `RATE_LIMITED`. A provider outage does not fabricate a successful explanation or stop the local evidence scan.

## Current risk requirements

The project `.env` sets a ₹1,000 net daily profit target, ₹800 daily-loss limit and hard halt, ₹600 planned-loss allocation, and ₹200 execution reserve. The current per-trade risk override is ₹750; the correlated open-risk veto remains ₹600 with one open position. The profit target initiates a lock using estimated net liquidation value, so ₹1,000 gross with charges still outstanding does not satisfy it. These are targets and controls; executable fills cannot be guaranteed during gaps or unavailable liquidity.

The legacy API field `plan_policy.gross_target` retains its name for compatibility. Its interpretation is explicitly provided by `plan_policy.target_basis`, now `net` in this project's configuration.

## Run and verify

Use the existing backend service from the backend directory:

```powershell
.\.venv\Scripts\python.exe -B -m uvicorn app.main:app --host 127.0.0.1 --port 8080 --no-access-log
```

Do not start a duplicate service on port 8080. The monitor starts with the FastAPI lifespan and exposes its actual worker heartbeat. Tests use temporary databases on E: and never seed synthetic outcomes into the production database. The SDK test exercises the real Runner/tool cycle using a deterministic provider stub; this is an integration test, not a successful live-provider inference or performance evidence.

At the initial live check on 12 September 2026, both keys authenticated with HTTP 200; inference requests to both selected providers returned HTTP 429. The local monitor was live and showed no deployed models. A successful live AI review remains provider-dependent.
