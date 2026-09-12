# Paper learning and adaptive exits

Implemented on 11 September 2026. These are unvalidated paper mechanisms, not a demonstrated profitable edge.

## Entry-quality learning

`backend/app/ai.py` implements regularized logistic regression using scikit-learn. Its label is a positive completed net P&L, not "target hit first". Twelve entry-time features include explicit missing values for unavailable index volume, VWAP, option delta or option ATR. Training-only medians, missingness indicators and scaling are stored with coefficients in JSON in the project SQLite database; no untrusted pickle is loaded. Coefficients describe the standardized model and are not causal feature importance.

Models are separated by symbol, strategy version and exit-policy version. Training rejects gross-only reports, incomplete reports, missing costs, inconsistent accounting, partial outcomes, future outcomes and features observed after entry. Duplicate positions are removed. Splits are chronological by session: 70% earlier sessions for fitting and 30% later sessions for testing. Training exits overlapping the test boundary are purged. A tested holdout cannot be reused for another attempt.

At least 60 training trades, 30 test trades and 34 total sessions are required. The fixed probability threshold is 0.55; it is not optimized against the test set. Filter evidence requires at least 30 selected trades over 10 sessions, at least three losses, profit factor above 1.25 and positive net expectancy. A filter-only result cannot promote a model. A full baseline-versus-model account replay must additionally pass those evidence requirements and produce higher net P&L while reapplying cash, fee, stop and risk rules. Gross-only Dhan rolling-option research cannot promote models.

Successful models are eligible from the following date and expire after 30 days. Model IDs are frozen durably per session, including sessions with no model. Restarting cannot activate a newly trained model mid-session. A scope without a validated model continues baseline paper observation; a selected model that expires or fails inference blocks its candidates. Risk settings never learn to increase themselves.

Training runs automatically after backtest completion. `POST /api/learning/train` trains from the latest saved report; without a full replay callback it can only assess filter evidence. Full account replay is supplied by new verified-contract CSV backtest jobs. `GET /api/learning/model` exposes the training state, validation metrics, coefficients and session model IDs. Dashboard candidates display estimated probabilities only when an eligible model exists.

## Adaptive exits

New multi-strategy paper positions use `adaptive_observed_v1`. The original structural stop is retained. Fresh observed bids update durable peak and trailing state. At +1R, the engine may request a stop above entry plus estimated entry/exit fees and one tick. At +1.2R it trails 0.5 option ATR, tightening to 0.35 after 13:00 IST. Option ATR is frozen from at least 14 completed, same-contract pre-entry candles; no underlying ATR or invented Greeks substitute for it.

Momentum-stall exits require five contiguous completed bid bars: four bars without a new high, each with a range below half the option ATR. Partial entry-minute bars and quote gaps invalidate this evidence. Structural failure, hard stop and session liquidation remain higher-priority exits. Exits require observed fresh bids and available depth; no stop guarantees its execution price or zero loss. Minute-candle replay checks the existing stop first, and adaptive updates use only the completed close before affecting subsequent bars. Intrabar tick and minute-candle fidelity are different and must not be represented as identical.

Adaptive exit parameters are explicit paper hypotheses, not learned or validated improvements. There is no implemented weekend parameter-search optimizer, and there is no evidence that these rules improve profits yet.

## Storage and scope

WebSocket raw ticks no longer write a row per packet to SQLite. The latest executable quotes remain in memory, with a bounded 512-event diagnostic buffer. REST quote snapshots overwrite one latest record. Position, decision, order, trade and model records remain durable. Existing database history was not deleted or vacuumed.

Dependencies, build output and test temporary files remain inside `E:\trading_bot_full`. Active risk configuration remains in `Trading Bot/.env`: ₹600 per trade and correlated risk, ₹1,200 daily/hard cap, ₹1,000 planned loss allocation plus ₹200 execution reserve, one position, three entry attempts, two losses.

The historical job runner still tests the ORB baseline. Individual trend-pullback/range-rejection replay and a combined portfolio replay have not been implemented by this change. All three live paper strategies capture entry features, but this does not establish historical coverage or provide a validated model for them. The local data folder currently contains no verified-contract CSV dataset. Existing gross research cannot establish net performance or train an eligible champion.

## Historical data learning and net cost verification (Updated)

- **Net Fee Reconstruction**: Dhan historical backtests (`ResearchReplay`) now compute realistic Indian options transaction costs (brokerage, STT, turnover charges, SEBI fees, stamp duty, and GST) via `CostModel.estimate_round_trip` in Indian Rupees (₹).
- **Causal Feature Extraction**: Each simulated trade captures 12 causal entry features (`SCHEMA = "entry_features_v1"`) at the entry timestamp without lookahead bias.
- **Self-Learning Pipeline**: `LearningService` in `ai.py` now accepts `research_net` backtest reports with net P&L. It partitions sessions chronologically (70% train / 30% test holdout) and fits regularized logistic regression models (`MLTradeQualityModel`).
- **Zero Data Loss**: All 338,948 historical records and 5-year archives in `trading_bot.db` are completely preserved on drive `E:`. No historical data was deleted.
- **Full Test Suite Validation**: All 143 backend unit tests (`pytest -q`) pass cleanly with 100% success rate.

