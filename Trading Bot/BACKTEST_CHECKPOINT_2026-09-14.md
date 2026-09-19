# Backtest and learning checkpoint — September 14, 2026

## Verified running behavior

- NIFTY March 31, 2023 observed-data-only replay completed: `c23c3e56-39ec-489a-9843-f0378d1a52e2`, `research_complete`, `research_net`. Two losing trades; gross -₹78.00, estimated charges ₹100.73, net -₹178.73. Coverage recorded zero missing index/ATM minutes and zero conflicting/invalid candles for this session. Held-strike recovery used cached wider offsets. Current lot size 65 remains an explicitly unverified historical sizing assumption.
- Matching optional scenario `0d8ee787-a09b-40cc-8f0a-9be986833de6` completed. No estimated exits were needed after actual-price recovery. Entire run was nevertheless labelled `estimated_scenario`, `learning_eligible=false`; zero pipeline learning records and `EXCLUDED_ESTIMATED_SCENARIO` model-training status.
- Browser shows both saved reports, observed-data-only default, exploratory mode, and the new ATM±6 button.
- Runtime risk at the time of the earlier checkpoint: capital target configuration ₹30,000, trade/correlated risk ₹600, daily/hard halt ₹800, one position, net daily target ₹1,000. The current user override is per-trade risk ₹750 while the correlated open-risk veto remains ₹600.
- Learning monitor alive and fresh; zero deployed learned models. Existing NIFTY candidates rejected/holdout reuse blocked; SENSEX insufficient sessions. No proven entry or exit improvement. Optional provider explanation reports HTTP 429; deterministic evidence monitoring still works.
- Market WebSocket reports `InvalidStatus`. Last observed market values are stale and visibly labelled. Credential refresh reports project `.env`, generation 2. Key presence does not establish working streaming access.

## ATM±6 archive extension activated and completed

- Added `POST /api/backtest/cache/extend-atm6`, requesting near-expiry code 1, weekly/monthly CALL/PUT, offsets -6/-5/+5/+6 over the current five-year boundary. Existing ATM±4 archive remains retained; entry selection remains unchanged.
- Extension requests OHLC, volume, OI, strike and spot. IV is not mandatory for cache reuse. Manifest records the actual requested fields.
- Backend activation is complete; the running API reports `learning_guard_v3` and exposes the new route.
- Download job `bf042407-b18b-4153-9fdf-a8c94217071f` completed at `2026-09-15 07:31:29 IST` with `2142/2142` requests processed, `1814` non-empty responses, `328` empty responses, and `12,385,646` observations. The manifest records `OHLC, volume, OI, strike, spot` for NIFTY and SENSEX, near-expiry code 1, weekly/monthly CALL/PUT and ATM±5/±6.
- The archive is retained as a downloaded-source cache; empty responses and provider boundaries mean coverage is not certified. No strategy replay or model training was run by this download-only job.

## Validation and outstanding work

- 43 focused archive/jobs/reconstruction/estimated-exit/report tests passed (50 existing/dependency deprecation warnings). Final frontend production build passed.
- All new generated files and test temporary files were kept under the E: project workspace.
- Five-year combined report remains partial. Resolving one missing held-contract interval does not certify all five years, historic lot/expiry identity, fees, or executable liquidity.
- Activate and complete extension, inspect empty periods, then rerun coverage and the full historical range. Individual strategy/portfolio execution replay still requires observed exact-contract inputs; Dhan rolling mode remains ORB research.
- Sufficient independent forward comparison is still required before any learned model can be described as improving trading. No guarantee of daily profit or absence of overfitting is established.

## Subsequent learning-validation hardening

- Introduced `learning_guard_v3`: candidate and baseline need explicit matching daily coverage, including observed no-trade sessions; daily account P&L must reconcile with completed net trades. Missing/duplicate daily rows, missing/duplicate trade identities, invalid or reversed timestamps, overnight outcomes and explicitly excluded/estimated evidence fail promotion.
- Manual/model training now respects report-level and trade-level `learning_eligible=false` and estimated-exit provenance even if a legacy record still says `verified`.
- 46 focused learning, monitor, adaptive-exit and execution-integrity tests passed. The valid-promotion fixture now supplies reconciled daily account evidence; rejection tests include malformed calendars and exclusion flags.
- These source changes are pending the same backend activation. Existing v2 validations must be revalidated under v3 before deployment. This is an evidence gate, not proof that overfitting has been eliminated.
- Complete backend regression suite after this hardening: **201 passed in 118.71 seconds**. It emitted 16,524 repeated NumPy/pandas timedelta deprecation warnings; there were no failed tests. These are isolated software checks, not observed market performance or successful runtime activation.

## Forward-comparison integrity and UI

- Comparison sessions now record integrity failures for a stopped recorder, changed recorder identity, dropped quotes, dead/missing execution workers, reference persistence errors, or changed risk policy. Risk-policy divergence disables further reference entries; pending exits remain managed. A session with these issues cannot finalize as COMPLETE.
- Added monitor-cycle freshness: an alive thread with no successful cycle for over 30 seconds is stale. The evidence monitor exposes stale/error and integrity alerts.
- Quote write counts/times and forward-monitor heartbeat times no longer change the learning evidence fingerprint by themselves. Health, dropped observations, stale state and actual learning changes still change it.
- Added lifecycle tests for clean paired accounting, integrity faults, pending exits at 15:05, stale monitors and reference storage isolation. **33 focused tests passed** after these changes; final frontend build passed. The prior 201-test run predates this addition.
- Verified the new forward-comparison panel in the running Agentic view. It reports WAITING FOR VALIDATED MODEL, zero deployed models, and current monitor freshness. The running backend now reports `learning_guard_v3`.
- Corrected the completed estimated-scenario header to say exploratory scenario rather than observed replay.
- Updated `.env` credentials were reloaded by both REST and WebSocket as generation 3. The prior InvalidStatus error cleared and the socket connected; fresh market packets were not established in the after-hours check.

## Live decision workflow canvas

- The Agentic workflow is now data-driven. Each node resolves its event ID against the latest dashboard event stream, displays the recorded event time, evaluation context and policy provenance, and distinguishes a node with no event from a recorded waiting decision.
- Workflow edges carry `marker-end` arrows and animated data packets only when adjacent stages both have fresh recorded evidence. Stale snapshots and holiday waiting states remain visibly static and explain why no packet is moving; no synthetic animation is used to imply a trade.
- The session controller shows the latest recorded event time. The legend reports the number of stages with evidence and whether the chain is fresh. Node inspection continues to open the underlying event.
- Backend pipeline responses now include timestamp, context, evaluation and policy version fields for future refreshed services; the UI also falls back to event-stream data while an older backend is running.
- Verified in the running Agentic view: the pre-open scanner shows `PREOPEN`, `WAITING`, and the actual recorded event time; downstream nodes show `No data`; the legend reports `1/8 stages have recorded evidence · awaiting a fresh cycle`. SVG arrows are present, and only genuinely fresh adjacent handoffs receive the highlighted/animated treatment. This is the correct static-looking state before a decision chain exists, with no fabricated packet flow.
- Workflow tests: **26 passed** for event provenance, agent-monitor integrity and forward-comparison lifecycle. Frontend TypeScript/Vite build passed.

## Individual-agent audit and regime selection

- Added `backend/app/individual_agent_audit.py`, a deterministic audit-only agent that separates activity, learning attempts, candidate validation, deployment and independent forward improvement for the architecture roles. It includes explicit overfitting-gate status and loss-investigator hypotheses; it cannot change parameters, risk or orders.
- Learning monitor now exposes the audit under `individual_agent_audit` and the Agentic UI shows the audit status, role counts and loss-forensics summary.
- Multi-strategy selection now records `day_regime` and `regime_strategy_order`. Completed-bar regimes rank compatible hypotheses without disabling the parallel evaluation or bypassing the shared Risk Sentinel.
- Focused auditor/monitor tests: **18 passed**. Full backend regression after these changes: **218 passed**. Frontend production build passed.
- Live API after activation: `learning_guard_v3`, 14 architecture roles audited, per-trade risk ₹750, correlated cap ₹600, paper capital ₹30,000, zero open positions, and no learned model proven or deployed.
- Candidate offers now retain specialist evidence for regime, direction, options flow, gamma, theta, IV, liquidity, momentum, structure, event risk, adversarial review and orchestration. Missing optional fields remain `DATA_UNAVAILABLE`; liquidity/adversarial contradictions veto before Risk Sentinel. Full backend regression after this addition: **221 passed**; frontend build remains green.

## Runtime-contract defaults aligned — September 15, 2026

- Settings and standalone risk-policy fallbacks now match the active project contract even when a worker is started without the project `.env`: ₹750 maximum planned risk per trade, ₹800 daily loss/hard halt, ₹600 correlated open-risk cap, ₹600 planned allocation plus ₹200 reserve, and ₹1,000 net target.
- The fallback policy target basis is now `net`, matching the authoritative `.env`; saved legacy reports retain their original configuration and are not rewritten.
- Focused risk, paper, and backtest-job checks passed (**42 passed**). The complete backend regression suite passed (**221 passed**; existing NumPy/pandas deprecation warnings remain).
- Paper position/episode persistence now retains the specialist matrix, agent scores, orchestrator decision and adversarial warnings, so future loss forensics can attribute the exact decision evidence rather than only the generic pipeline context. The persistence regression and specialist/auditor checks pass (**27 passed**).

## UI interaction and five-year cache run — September 15, 2026

- Refined the Agentic view styling with a layered dark workspace, responsive spacing, rounded workflow cards, focus/hover states, clearer status contrast, heartbeat indicator and reduced-motion support.
- Added an evidence-backed **Agent Handoff Bus** above the workflow. It renders the latest recorded events for the selected index and labels them as fresh or stale replay evidence. It does not invent packets or animate a decision when no current event exists.
- Workflow nodes now expose stale/fresh/current evidence states, signal markers and an engine-heartbeat state. Hard arrowheads were replaced with soft dashed monitoring rails and a moving telemetry sweep; brighter SVG handoff packets still animate only when adjacent stages have recent, ordered recorded evidence and a passing status.
- Added a live **Architecture Bus / Recorded Telemetry** matrix for all 14 roles. Each role now shows its fixed recipient route, audit status, decision/outcome counts and fresh/recorded/quiet evidence state. The matrix is explicitly labelled as an architecture contract; it never implies that a route approved a trade. The panel is responsive, hoverable and respects reduced-motion settings.
- Frontend TypeScript/Vite production build passed after the UI changes. Browser verification confirmed the updated Agentic view and handoff bus at `/#agentic`.
- The resumed download-only five-year refresh job `49610172-467d-45c6-9d19-bc906b2f3605` is currently running against the Dhan source: **1,492 / 13,734 requests (10.9%)**, 7,615,531 observations, 1,287 non-empty responses and 205 empty responses as of 22:53 IST. It has no report ID because it only fills the local cache; replay must wait for completion and coverage validation.
- Five-year cache-only backtest job `1495c660-3089-4d50-bb69-95973273d032` processed through the requested 2021-09-15 to 2026-09-14 range and reached 99%, then failed closed during final reconciliation because local `expired_options_data` candles are missing for **2026-09-13 through 2026-09-15**. No historical API request was made and no synthetic data was used. The range remains data-blocked until those local candles are downloaded/resumed.
- The supervised backend was restarted after the terminal backtest state. `/api/health` is healthy, paper-only, and has no dead workers; `/api/dashboard` reports ₹30,000 capital, ₹750 max planned risk per trade, ₹800 daily loss/hard halt, ₹600 correlated cap, ₹600 planned allocation plus ₹200 reserve, ₹1,000 net target, zero open positions and `EXIT_ONLY` after hours. Learning monitor remains `self_improvement_proven=false` with zero deployed models.

### UI surface pass — September 15, 2026

- Reworked the frontend surface layer to remove the hard bordered-box appearance: panels now use soft gradient surfaces, restrained separators, rounded corners, inset highlights and depth shadows.
- Fixed desktop market-quote wrapping by using a responsive two-column quote grid; quotes stack only below the narrow-screen breakpoint. Added overflow guards for long status labels and flex rows.
- Restyled dashboard tables as separated floating rows with hover elevation, preserving horizontal scrolling only for genuinely wide data tables. Tabs now use a blurred sticky surface and a gradient active indicator.
- Browser verification passed for the dashboard and Agentic view after `npm run build`. Agent communication routes continue to use evidence-tied signal animation.
- Normalized panel heading alignment: Strategy selection, its checked timestamp, Executed paper performance and the Individual Agent Audit now share the same inset content rail; timestamps align to the heading baseline and responsive mobile stacking is explicit.
