# Paper trading and research architecture contract

This is the operating contract for the NIFTY and SENSEX paper-trading project. It records the requested architecture so future implementation work is judged against the same boundaries.

## Account and authority

- Paper capital is **₹30,000**.
- Maximum planned loss per trade is **₹650**. The correlated open-risk veto is also **₹650**.
- The hard daily halt is **₹1,200**, consisting of a ₹1,000 planned loss allocation plus a ₹200 execution reserve.
- The account has a one-position cap and does not replenish the loss allocation after a loss.
- The latest monthly target is ₹18,000 net of recorded/estimated trading charges. It is a reporting objective only, never a promised return, entry quota or reason to increase risk.
- Paper execution is the only available order authority. Real-money order placement remains disabled server-side.
- The deterministic Risk Sentinel owns the veto. No model, LLM, learner, orchestrator or agent may override it.

## Data-to-decision path

```text
Market Data Bus
  -> regime, direction, options-flow, gamma, theta, IV, liquidity,
     momentum, structure and news/event evidence
  -> adversarial review (why is this trade wrong?)
  -> orchestrator: CALL / PUT / WAIT / EXIT
  -> deterministic Risk Sentinel
  -> realistic paper execution
  -> trade journal and forensic loss record
  -> offline research, walk-forward validation and shadow/forward paper comparison
```

`WAIT` is a first-class result and is expected to be common. A majority vote cannot approve a trade when a hard veto, stale input, poor liquidity, unstable confidence or event-risk block is present.

## Agent responsibilities

The intended analysis roles are Regime, Directional, Options Flow, Gamma, Theta, IV, Liquidity, Momentum, Structure, News/Event, Adversarial, Loss Investigator, Risk Sentinel and Orchestrator. Agents produce timestamped evidence and reasons; they do not place orders independently. The shared paper engine is the sole execution owner.

The current autonomous paper implementation compares four setups with an eight-stage decision pipeline, fresh full returned fixed-contract chain context and a separate completed-bar HOLD/EXIT manager. Specialist roles record their own checks and unavailable inputs. They remain fixed analytical checks, not fourteen independently trained models. A separate paper entry learner requires causal recorded episodes, untouched chronological holdouts and identical-input full-account replay before next-session paper activation. Strict verified historical learning is not weakened. Risk/sizing/protection authority remains outside all models.

The running implementation now includes a deterministic **Individual Agent Learning Auditor**. It audits each role separately, reports decision/outcome/session counts, identifies candidate-model and forward evidence, applies the current overfitting guard, and records loss-investigator hypotheses. The auditor is advisory and has no order, risk or parameter-edit authority. A strategy preference order is derived from the completed-bar day regime for ranking only; all configured strategies continue to be evaluated and every entry still passes the shared risk and execution gates.

Candidate offers also carry a specialist evidence matrix for regime, direction, flow, gamma, theta, IV, liquidity, momentum, structure, event risk, adversarial review and orchestration. Missing optional provider fields are labelled `DATA_UNAVAILABLE`; they are never replaced with estimates. Liquidity and adversarial contradictions are hard vetoes before the shared Risk Sentinel. The event role has an explicit confidence penalty when no validated event feed is attached, rather than treating silence as a bullish signal.

## Execution realism

The current `option-buyer-v1` screen allows ATM contracts. It requires signed,
observed Delta no older than 120 seconds: absolute 0.45–0.60 is preferred; 0.30–0.45
is allowed only with an aligned trend. Missing Delta cannot pass. The maximum
spread is 2% of midpoint, with 1% or less preferred. Expiry-day entries stay disabled.
The structural nominal 2R target is unchanged; net target reward must cover at
least all-in risk (configurable upward for research). No target is extended to
make a filter pass. Old models and expectancy samples cannot gate a new screen.

Gamma, unit-checked Theta/Vega sensitivities and IV remain contextual estimates.
No dealer positioning or institutional flow is inferred from unsigned OI. Missing
comparable-maturity IV history is reported as unavailable, never a fabricated percentile.

Entries and exits must use observed bid/ask/depth where available, quote-age checks, spread and slippage assumptions, latency/partial-fill handling, charges and pending-exit states. A missing quote must produce `WAITING_DATA` or a pending exit, never an invented fill.

## Learning and promotion gates

Losses create forensic records (contract, spot/option state, Greeks when available, volatility, liquidity, regime, agent evidence, entry/exit reason, MAE/MFE, slippage and charges). A single loss must not rewrite a policy. Any candidate change requires chronological replay, walk-forward and unseen validation, overfitting checks, stress/regime checks, shadow or forward paper comparison, and a frozen baseline before promotion. Risk code is never learned.

Synthetic, estimated or incomplete historical outcomes are excluded from learning. Downloaded-file presence is not evidence of complete option coverage. Paper observations are labelled unvalidated until independent forward evidence supports a claim.

## Session lifecycle

The service starts before the market session, monitors from **09:15 IST** on market days, stops new entries at the configured cutoff, and requests liquidation at **15:05 IST**. It reloads the project `.env` before credential-sensitive work and after credential rotation; stale in-memory credentials must not be retried. The dashboard must expose feed freshness, pipeline evidence, agent status, risk state, recorder health and learning eligibility.
