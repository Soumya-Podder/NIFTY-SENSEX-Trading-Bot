# Paper trading and research architecture contract

This is the operating contract for the NIFTY and SENSEX paper-trading project. It records the requested architecture so future implementation work is judged against the same boundaries.

## Account and authority

- Paper capital is **₹30,000**.
- Maximum planned loss per trade is **₹750**. The correlated open-risk veto remains **₹600** until explicitly changed.
- The hard daily halt is **₹1,200**, with ₹600 planned loss allocation plus a ₹200 execution reserve retained; the remaining ₹400 is additional daily-loss capacity, not a separate entry budget.
- The account has a one-position cap and does not replenish the loss allocation after a loss.
- The monthly gross target is ₹20,000 or more on average before charges and taxes; it is a target only and never a promise of return.
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

The current implementation has a deterministic multi-strategy paper selector and an eight-stage decision pipeline. The additional specialist roles remain an explicit expansion path; until each role has its own recorded inputs, outputs, tests and forward attribution, its learning state must be reported as unverified rather than inferred from generic agent activity.

The running implementation now includes a deterministic **Individual Agent Learning Auditor**. It audits each role separately, reports decision/outcome/session counts, identifies candidate-model and forward evidence, applies the current overfitting guard, and records loss-investigator hypotheses. The auditor is advisory and has no order, risk or parameter-edit authority. A strategy preference order is derived from the completed-bar day regime for ranking only; all configured strategies continue to be evaluated and every entry still passes the shared risk and execution gates.

Candidate offers also carry a specialist evidence matrix for regime, direction, flow, gamma, theta, IV, liquidity, momentum, structure, event risk, adversarial review and orchestration. Missing optional provider fields are labelled `DATA_UNAVAILABLE`; they are never replaced with estimates. Liquidity and adversarial contradictions are hard vetoes before the shared Risk Sentinel. The event role has an explicit confidence penalty when no validated event feed is attached, rather than treating silence as a bullish signal.

## Execution realism

Entries and exits must use observed bid/ask/depth where available, quote-age checks, spread and slippage assumptions, latency/partial-fill handling, charges and pending-exit states. A missing quote must produce `WAITING_DATA` or a pending exit, never an invented fill.

## Learning and promotion gates

Losses create forensic records (contract, spot/option state, Greeks when available, volatility, liquidity, regime, agent evidence, entry/exit reason, MAE/MFE, slippage and charges). A single loss must not rewrite a policy. Any candidate change requires chronological replay, walk-forward and unseen validation, overfitting checks, stress/regime checks, shadow or forward paper comparison, and a frozen baseline before promotion. Risk code is never learned.

Synthetic, estimated or incomplete historical outcomes are excluded from learning. Downloaded-file presence is not evidence of complete option coverage. Paper observations are labelled unvalidated until independent forward evidence supports a claim.

## Session lifecycle

The service starts before the market session, monitors from **09:15 IST** on market days, stops new entries at the configured cutoff, and requests liquidation at **15:05 IST**. It reloads the project `.env` before credential-sensitive work and after credential rotation; stale in-memory credentials must not be retried. The dashboard must expose feed freshness, pipeline evidence, agent status, risk state, recorder health and learning eligibility.
