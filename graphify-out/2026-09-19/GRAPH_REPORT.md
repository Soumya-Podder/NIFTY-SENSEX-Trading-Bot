# Graph Report - trading_bot_full  (2026-09-19)

## Corpus Check
- 121 files · ~142,530 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 10 file(s) not represented in the graph (top: .bat 4, (none) 3, .css 2)

## Summary
- 2032 nodes · 3598 edges · 211 communities (183 shown, 18 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 122 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `85799f39`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Getting Started
- test_paper.py
- test_jobs.py
- test_reconstruction.py
- pipeline.py
- datetime
- Allowed and Restricted Operations
- test_strategy_portfolio.py
- AutonomousTradingAgent
- ForwardComparison
- PlanRiskPolicy
- Dhan MCP Architecture Flow
- main.py
- What You Must Do When Invoked
- DhanMarketData
- now_ist
- post
- .run
- engine.py
- main.tsx
- test_learning_monitor.py
- DecisionPipeline
- Store
- LearningService
- frontend/package.json
- audit_individual_agents
- QuoteRecorder
- test_runtime.py
- LLMClient
- cli.py
- learn_from_outcomes
- Self-Learning System Status
- ai.py
- DhanGateway
- test_backtest.py
- Options Paper Lab
- Caveman
- TradingWorkspace.tsx
- Ponytail
- assess_specialists
- Backtest and learning checkpoint — September 14, 2026
- Trading Bot — Full Project Logic (Verified from Source)
- json_safe
- compilerOptions
- DhanHQ API Documentation — Full Export
- graphify reference: extra exports and benchmark
- test_adaptive_learning.py
- PaperEngine
- test_learning_validation.py
- Binary Response
- Behavioral Guidelines
- Paper trading and research architecture contract
- autonomous_agent.py
- EventBus
- Order Management
- Installation
- Connect your client
- Paper engine remediation — updated 13 September 2026
- Deploy Your First Strategy
- Learning evidence monitor
- Behavioral Guidelines
- graphify reference: query, path, explain
- Paper learning and adaptive exits
- calendar_info
- quote_is_fresh
- Market Data
- Modify Order
- Modify Conditional Order
- Modify Order
- Modify Super Order
- dependencies
- CircuitBreaker
- greek_scenario
- Backtest and dashboard audit — 13 September 2026
- Response Structure
- Authentication APIs
- Version 2.0
- Calculate Margin
- Calculate Multi-Order Margin
- Cancel Order
- Cancel Order
- Cancel Super Order Leg
- Conditional and Multi Order
- Consume Consent
- Consume Consent
- Portfolio
- Delete Conditional Order
- EDIS Status Inquiry
- Get Intraday Historical Data
- Ledger Report
- Get Order by Correlation ID
- Get Order by ID
- Trade History
- Get Trades for Order
- Get Order by ID
- Get Past Trades by Security Id
- Margin Calculator
- Order Estimator
- Place Order
- Manage Kill Switch
- Place Order
- Place Super Order
- Slice Order
- Generate Consent
- Generate eDIS Form
- Get Daily Historical Data
- Historical Rolling Options Data
- Get Expiry List
- StrategyPortfolio.tsx
- graphify reference: add a URL and watch a folder
- graphify reference: commit hook and native CLAUDE.md integration
- graphify reference: incremental update and cluster-only
- package.json
- RiskEngine
- add_features
- agent_metrics.py
- csv_adapter.py
- DhanBroker
- Access for Individual Traders
- Access Token Setup
- Supported Agents
- Version 2.2
- Super Order
- Common Error Scenarios
- Configure P&L Based Exit
- Connect Your Dhan Account
- Convert Position
- EDIS Status & Inquiry
- Lot Size Validation
- Kill Switch Status
- Get LTP
- Get OHLC
- Get Option Chain
- Get Order Book
- Get Positions
- Get Full Quote
- Get Super Orders
- Get Trade Book
- Get Fund Limit
- Get Holdings
- Get Market Status
- Get Order Book
- Get Past Trades
- Place Conditional Order
- Place Multi Order
- Generate Token
- Modify IP
- Generate Consent
- Renew Token
- Set IP
- Generate T-PIN
- Get Conditional Order by ID
- Get Fund Limits
- Get Holdings
- Example Workflows
- Supported Values
- Funds
- Market Data
- Order Update
- graphify reference: GitHub clone and cross-repo merge
- graphify reference: transcribe video and audio
- local_mutations
- Trading bot source snapshot
- audit_observation_db
- test_sdk_agent_reads_evidence_and_reloads_key
- Establishing Connection
- Adding Instruments
- API Structure
- Handling Rate Limits
- Version 2.4
- Install
- Indian Stocks
- Historical Data
- Request Messages
- Establishing Connection
- Order Confirmation
- Get P&L Based Exit
- Stop P&L Based Exit
- Get IP
- Exit All Positions
- Get All Conditional Orders
- Feed Disconnect
- Option Chain
- Get P&L Based Exit
- Historical Rolling Data
- LIMIT Order Defaults
- Setup TOTP
- Version 2.5
- Version 2.1
- Structure
- Trade History
- LearningMonitor.tsx
- extraction-spec.md
- README.md
- Global Stocks
- Feed Disconnect
- For Partners
- Version 2.3
- Setting Up Postback
- test_paper_toggle_is_explicit_and_never_live
- once_per_session

## God Nodes (most connected - your core abstractions)
1. `Getting Started` - 352 edges
2. `Store` - 77 edges
3. `now_ist()` - 71 edges
4. `Allowed and Restricted Operations` - 39 edges
5. `LearningService` - 36 edges
6. `local_time()` - 35 edges
7. `session_state()` - 33 edges
8. `Settings` - 32 edges
9. `PaperEngine` - 32 edges
10. `AutonomousTradingAgent` - 31 edges

## Surprising Connections (you probably didn't know these)
- `test_coordinator_has_no_independent_order_authority()` --uses--> `AutonomousTradingAgent`  [INFERRED]
  Trading Bot/backend/tests/test_execution_integrity.py → Trading Bot/backend/app/autonomous_agent.py
- `lifespan()` --uses--> `MultiStrategyPaperEngine`  [INFERRED]
  Trading Bot/backend/app/main.py → Trading Bot/backend/app/portfolio_engine.py
- `BacktestEngine` --uses--> `MLTradeQualityModel`  [INFERRED]
  Trading Bot/backend/app/backtest/engine.py → Trading Bot/backend/app/ai.py
- `test_failed_fit_still_consumes_holdout()` --uses--> `MLTradeQualityModel`  [INFERRED]
  Trading Bot/backend/tests/test_learning_monitor.py → Trading Bot/backend/app/ai.py
- `AutonomousTradingAgent` --uses--> `LearningService`  [INFERRED]
  Trading Bot/backend/app/autonomous_agent.py → Trading Bot/backend/app/ai.py

## Import Cycles
- None detected.

## Communities (211 total, 18 thin omitted)

### Community 0 - "Getting Started"
Cohesion: 0.01
Nodes (245): 1. Create an Account, 2. Generate API Credentials, 3. Install the SDK, 4. Initialize the Client, 5. Place Your First Order, A Few Things to Know, Adding Credits, Adding Instruments (+237 more)

### Community 1 - "test_paper.py"
Cohesion: 0.19
Nodes (27): parametrize, test_failed_persistence_restores_account_and_prevents_ghost_fill(), account(), contract(), enter(), plan_account(), fixture, quote() (+19 more)

### Community 2 - "test_jobs.py"
Cohesion: 0.06
Nodes (36): dataset_path(), archive_manifest(), BacktestJobs, before_commit(), cancelled(), ml_replay(), progress(), replay() (+28 more)

### Community 3 - "test_reconstruction.py"
Cohesion: 0.07
Nodes (42): _valid_bar(), estimate_gap_exit(), Exploratory missing-price liquidation; never an observed candle or live fill., Use only the preceding minute, then liquidate instead of inventing a path., history_row(), Read models for reports: retain audit data without presenting partial profit as…, report_view(), merge_series() (+34 more)

### Community 4 - "pipeline.py"
Cohesion: 0.18
Nodes (14): Enum, str, Decision, Direction, ExpectancyResult, FeatureSnapshot, OptionContract, BaseModel (+6 more)

### Community 5 - "datetime"
Cohesion: 0.25
Nodes (6): datetime, Broker-sourced charges and empirical expectancy; no invented fee percentages., execution_context(), Three paper hypotheses, one selector, one atomic portfolio authority., Local paper API supervisor, started before the session by Windows Task…, Autonomous Trading Agent - Standalone runner. Run this to start the autonomous…

### Community 6 - "Allowed and Restricted Operations"
Cohesion: 0.05
Nodes (37): Allowed, Allowed and Restricted Operations, Architecture, Blocked, Checking Fund Limits, Code Scanner, Common Flags and How to Fix Them, Compatible clients (+29 more)

### Community 7 - "test_strategy_portfolio.py"
Cohesion: 0.08
Nodes (33): ExpectancyEngine, Observed NET outcomes; fees are already included and never deducted twice.…, MultiStrategyPaperEngine, evaluate_strategies(), rank_opportunities(), Frozen, causal paper hypotheses. Scores are not probabilities of profit., Rank only eligible offers; statistical support precedes observation economics.…, Return the current day's deterministic strategy preference order. (+25 more)

### Community 8 - "AutonomousTradingAgent"
Cohesion: 0.06
Nodes (24): AgentState, AutonomousTradingAgent, Start the autonomous agent loop., Stop the autonomous agent., Keep coordinator workers alive without creating another execution authority., Main agent loop - runs every 2 seconds during market hours., Background learning loop - retrains models periodically., Pre-market preparation: load models, validate data, check risk limits. (+16 more)

### Community 9 - "ForwardComparison"
Cohesion: 0.06
Nodes (14): ExperimentStore, FixedLearning, ForwardComparison, All reference-account writes remain in an isolated namespace., ReferenceEngine, Broker, parametrize, Isolated lifecycle evidence; fake accounts never reach the live broker. (+6 more)

### Community 10 - "PlanRiskPolicy"
Cohesion: 0.22
Nodes (10): BacktestConfig, PlanRiskPolicy, Plan v1 risk envelope. Values are frozen configuration, not learned parameters., orb_frame(), parametrize, Synthetic mechanics fixtures, never performance evidence or runtime inputs., test_each_strategy_reaches_an_attributed_entry_and_its_own_time_exit(), test_historical_signals_match_live_prefixes_and_ignore_future() (+2 more)

### Community 11 - "Dhan MCP Architecture Flow"
Cohesion: 0.06
Nodes (31): 1. You, 2. MCP Client, 3. Tool Call to mcp.dhan.co, 4. Dhan MCP Server, 5. DEXT, 6. Exchange, Alerts, Dhan MCP Architecture Flow (+23 more)

### Community 12 - "main.py"
Cohesion: 0.13
Nodes (27): get, dataset_metadata(), Header inspection is an eligibility hint, not verified historical coverage., agent_state(), agent_status(), agents(), backtest_cache(), backtest_history() (+19 more)

### Community 13 - "What You Must Do When Invoked"
Cohesion: 0.08
Nodes (24): For /graphify add and --watch, For /graphify query, For the commit hook and native CLAUDE.md integration, For --update and --cluster-only, /graphify, Honesty Rules, Interpreter guard for subcommands, Part A - Structural extraction for code files (+16 more)

### Community 14 - "DhanMarketData"
Cohesion: 0.10
Nodes (8): Exception, DhanMarketData, Any, Seed latest values from one broker quote call; live ticks replace them., Dhan MarketFeed adapter. No tick is manufactured when the feed is down., test_websocket_packets_are_bounded_and_do_not_write_database(), test_option_stream_requires_depth_and_explicit_freshness(), test_stream_rotation_drops_old_prices_and_old_callbacks()

### Community 15 - "now_ist"
Cohesion: 0.24
Nodes (8): health(), mode(), ModeRequest, set_mode(), execution_health(), Worker liveness is independent of market-data availability and strategy edge., now_ist(), test_health_detects_stuck_execution_worker()

### Community 16 - "post"
Cohesion: 0.10
Nodes (26): post, agent_control(), agent_retrain(), BacktestRequest, cancel_job(), download_backtest_history(), extend_backtest_history(), halt() (+18 more)

### Community 17 - ".run"
Cohesion: 0.15
Nodes (8): close_position(), close(), CostModel, Only a dated source schedule can price a historical order., Standard Dhan index option round-trip charges (₹40 brokerage + STT + turnover +…, plan_protection(), Freeze an observed option-structure stop, never adjust it to fit risk., test_structural_stop_is_not_tightened_to_force_risk_budget()

### Community 18 - "engine.py"
Cohesion: 0.21
Nodes (12): Chronological, shared-cash replay. Every position retains a fixed contract ID., Durable, single-worker backtests; browser lifetime never owns a running job., metrics(), dhan_plan_research(), Dhan rolling candles -> fixed-strike intraday research, never verified net…, Audit the real baseline without laundering rolling offsets into contracts., historical_signals(), Causal portfolio-rule replay with the same seven-day warmup as the live scanner. (+4 more)

### Community 19 - "main.tsx"
Cohesion: 0.16
Nodes (16): active(), AgentLessons(), api(), App(), ArchiveManifest(), AuditDetails(), Chart(), Data (+8 more)

### Community 20 - "test_learning_monitor.py"
Cohesion: 0.13
Nodes (15): build_evidence(), evidence_fingerprint(), explain_evidence(), LearningMonitor, Evidence monitor. No order, training, parameter-edit or promotion tools., Read the authoritative file for EVERY call; never retain an expired key., Heartbeat counters are activity, not new learning or changed evidence quality., Isolated synthetic evidence tests, never performance evidence. (+7 more)

### Community 21 - "DecisionPipeline"
Cohesion: 0.22
Nodes (7): DecisionPipeline, finite(), Shared baseline decision; executable premium protection is a later gate., Apply frozen policy to a causally produced candidate, without future labels., test_baseline_preserves_contexts_for_all_contributing_agents(), test_ev_policy_applies_to_cold_start_observations(), test_focus_policy_filters_context_without_overriding_rejections()

### Community 23 - "LearningService"
Cohesion: 0.14
Nodes (16): LearningService, One fixed model/threshold, purged 70/30 day split, optional FULL replay. A…, test_net_cost_and_future_feature_exclusions(), test_promotion_waits_for_next_session_and_freezes_across_restart(), replay(), test_purged_holdout_not_reused_and_no_promotion_without_full_replay(), test_replay_failure_cannot_promote(), replay() (+8 more)

### Community 24 - "frontend/package.json"
Cohesion: 0.11
Nodes (17): react, react-dom, @types/react, @types/react-dom, typescript, vite, @vitejs/plugin-react, devDependencies (+9 more)

### Community 25 - "audit_individual_agents"
Cohesion: 0.23
Nodes (17): audit_individual_agents(), _day(), _finite(), _loss_investigation(), _matches_agent(), _model_rows(), _overfitting_gate(), Any (+9 more)

### Community 26 - "QuoteRecorder"
Cohesion: 0.17
Nodes (5): QuoteRecorder, Bounded, asynchronous recording of normalized observations, never credentials., test_failed_writer_stops_accepting_observations(), test_queue_overflow_and_storage_limit_are_not_silent(), test_quote_round_trip_is_durable_and_does_not_record_credentials()

### Community 27 - "test_runtime.py"
Cohesion: 0.11
Nodes (21): BaseSettings, model_validator, download_index_candles(), main(), Download raw 5-year historical market data from Dhan directly into local…, Download continuous minute candles from Dhan in chunks with permanent SQLite…, current_credentials(), The project's .env is authoritative over inherited, possibly stale credentials. (+13 more)

### Community 28 - "LLMClient"
Cohesion: 0.06
Nodes (20): AsyncClient, create_llm_client(), FailureAnalyst, get_analysts(), HypothesisGenerator, LLMClient, MarketAnalyst, Async OpenRouter client with retries, timeout, and structured output parsing. (+12 more)

### Community 29 - "cli.py"
Cohesion: 0.20
Nodes (11): Path, get_autonomous_agent(), Get or create the singleton autonomous agent., main(), Read one row per exact option contract/minute, with repeated underlying OHLCV., read_contract_csv(), Disjoint session windows, not a row slice that splits concurrent indices., validation_windows() (+3 more)

### Community 30 - "learn_from_outcomes"
Cohesion: 0.14
Nodes (12): learn_from_outcomes(), Every outcome is logged. Promotion requires fresh, full chronological replays., test_cancel_before_learning_commit_leaves_no_policy_or_ledger(), test_every_backtest_run_records_learning_for_every_agent(), test_full_validation_promotes_at_most_one_and_records_both_windows(), replay(), test_learning_is_idempotent_and_unverified_data_cannot_promote(), test_learning_only_attributes_outcomes_to_agents_with_context() (+4 more)

### Community 31 - "Self-Learning System Status"
Cohesion: 0.12
Nodes (15): API Endpoints, Backend Services, Configuration (.env), CORRECTED (2026-09-12), CORRECTED MULTI-STRATEGY UNDERSTANDING (2026-09-12), Current Model Status, Data Status, Dynamic Market Evaluation (+7 more)

### Community 32 - "ai.py"
Cohesion: 0.14
Nodes (16): Causal paper exit state. A stop is a request, never a guaranteed fill., metrics(), Entry-quality learning from causal, net-cost outcomes. No order authority., scope(), Source validation. Rolling moneyness must never masquerade as a fixed contract., Prospective reference account. No real-order authority or additive profit…, Fixed research gates. Passing these gates never proves absence of overfitting., replay_evidence() (+8 more)

### Community 33 - "DhanGateway"
Cohesion: 0.15
Nodes (5): DhanGateway, One rate-limited, cached data adapter shared by paper and research., Reuse overlapping sourced responses; fetch only uncovered date intervals., test_empty_history_is_not_retained_forever(), test_retained_history_reuses_sqlite_without_provider_call()

### Community 34 - "test_backtest.py"
Cohesion: 0.23
Nodes (15): BacktestEngine, historical_fixture(), parametrize, Contract fixtures only for regression tests, never runtime market data., test_backtest_runs(), test_baseline_honors_each_participating_agent_veto(), test_fixed_contract_drift_blocks_headline_pnl(), test_next_bar_open_and_entry_bar_stop() (+7 more)

### Community 35 - "Options Paper Lab"
Cohesion: 0.14
Nodes (12): Operation and audit, Paper strategy portfolio v1, Shared selector and protection, Strategies, Agent learning: what exists and what is not proved, Automatic operation and credential refresh, Historical backtests: data, calculation and limitations, Options Paper Lab (+4 more)

### Community 36 - "Caveman"
Cohesion: 0.50
Nodes (3): Caveman, Project usage, Safety

### Community 37 - "TradingWorkspace.tsx"
Cohesion: 0.31
Nodes (12): AgentCanvas(), BacktestHistory(), BacktestOverview(), cash(), Data, eligible(), eventAge(), number() (+4 more)

### Community 38 - "Ponytail"
Cohesion: 0.50
Nodes (3): Ponytail, Project usage, Safety

### Community 39 - "assess_specialists"
Cohesion: 0.33
Nodes (10): _age_seconds(), assess_specialists(), _finite(), Any, Deterministic specialist-agent evidence for a paper candidate. These are…, Assess specialist evidence for one candidate without placing an order., base_contract(), base_signal() (+2 more)

### Community 40 - "Backtest and learning checkpoint — September 14, 2026"
Cohesion: 0.17
Nodes (11): ATM±6 archive extension activated and completed, Backtest and learning checkpoint — September 14, 2026, Forward-comparison integrity and UI, Individual-agent audit and regime selection, Live decision workflow canvas, Runtime-contract defaults aligned — September 15, 2026, Subsequent learning-validation hardening, UI interaction and five-year cache run — September 15, 2026 (+3 more)

### Community 41 - "Trading Bot — Full Project Logic (Verified from Source)"
Cohesion: 0.17
Nodes (11): 10. BACKTEST RESULT (verified from DB only — no synthetic), 1. WHAT IT IS, 2. PROJECT STRUCTURE (verified), 3. DATA (verified from CSV reading), 4. BACKEND LOGIC (from main.py, ai.py, engine.py), 5. SELF-LEARNING RULES (from skill + code), 6. FEATURE SET (14 features, ai.py FEATURES tuple), 7. CURRENT STATE (verified from DB + endpoints + files) (+3 more)

### Community 42 - "json_safe"
Cohesion: 0.73
Nodes (6): dashboard(), learning_model(), redacted(), strategies(), websocket(), json_safe()

### Community 43 - "compilerOptions"
Cohesion: 0.18
Nodes (10): compilerOptions, jsx, lib, module, moduleResolution, noEmit, skipLibCheck, strict (+2 more)

### Community 44 - "DhanHQ API Documentation — Full Export"
Cohesion: 0.20
Nodes (9): Conditional and Multi Order, Data APIs, DhanHQ API, DhanHQ API Documentation — Full Export, Expired Options Data, Historical Data, Market Quote, Option Chain (+1 more)

### Community 45 - "graphify reference: extra exports and benchmark"
Cohesion: 0.22
Nodes (8): graphify reference: extra exports and benchmark, Step 6b - Wiki (only if --wiki flag), Step 7 - Neo4j export (only if --neo4j or --neo4j-push flag), Step 7a - FalkorDB export (only if --falkordb or --falkordb-push flag), Step 7b - SVG export (only if --svg flag), Step 7c - GraphML export (only if --graphml flag), Step 7d - MCP server (only if --mcp flag), Step 8 - Token reduction benchmark (only if total_words > 5000)

### Community 46 - "test_adaptive_learning.py"
Cohesion: 0.15
Nodes (16): Persistable state; only fresh observed bids may call this function. ATR must…, update_exit(), extract_features(), ratio(), MLTradeQualityModel, number(), Caller supplies a completed causal row; missing volume/Greeks stay missing., Regularized logistic probability estimate; portable JSON, no pickle loading. (+8 more)

### Community 48 - "test_learning_validation.py"
Cohesion: 0.47
Nodes (8): account(), check(), parametrize, Controlled validation inputs only; never persisted as trading evidence., test_different_observed_no_trade_coverage_is_rejected(), test_malformed_or_estimated_evidence_cannot_promote(), test_omitting_trade_days_from_both_account_calendars_is_rejected(), test_reconciled_accounts_include_observed_no_trade_sessions()

### Community 49 - "Binary Response"
Cohesion: 0.22
Nodes (9): 52-Week High/Low Packet, Binary Response, Circuit Limit Packet, Market Status Packet, Message Codes, OHLC Packet, Previous Close Packet, Response Header (+1 more)

### Community 50 - "Behavioral Guidelines"
Cohesion: 0.25
Nodes (7): 1. Think Before Coding, 2. Simplicity First, 3. Surgical Changes, 4. Goal-Driven Execution, Behavioral Guidelines, graphify, Persistent user requirements

### Community 51 - "Paper trading and research architecture contract"
Cohesion: 0.25
Nodes (7): Account and authority, Agent responsibilities, Data-to-decision path, Execution realism, Learning and promotion gates, Paper trading and research architecture contract, Session lifecycle

### Community 52 - "autonomous_agent.py"
Cohesion: 0.18
Nodes (9): Paper research coordinator. Execution belongs exclusively to the portfolio…, exchange_timestamp(), event(), pipeline_from_events(), Any, Create one JSON-safe, auditable event for a real engine cycle., test_pipeline_carries_event_provenance_for_live_workflow(), test_dhan_quote_timestamp_uses_day_first_and_requires_actual_timestamp() (+1 more)

### Community 53 - "EventBus"
Cohesion: 0.32
Nodes (3): EventBus, Any, Small process-local event bus used by the dashboard WebSocket. The trading…

### Community 54 - "Order Management"
Cohesion: 0.25
Nodes (8): Cancel Order, Get Order Book, Get Order by Correlation ID, Get Order by ID, Modify Order, Order Management, Place Order, Slice Order (Large Quantities)

### Community 55 - "Installation"
Cohesion: 0.25
Nodes (8): ChatGPT, Claude Code, Claude Web, Codex, Cursor, Custom, Installation, OpenCode

### Community 56 - "Connect your client"
Cohesion: 0.25
Nodes (8): ChatGPT, Claude Code, Claude Web, Codex, Connect your client, Cursor, Custom, OpenCode

### Community 57 - "Paper engine remediation — updated 13 September 2026"
Cohesion: 0.25
Nodes (7): Changes implemented and checked, Durable observation recording — September 13, Operating constraints verified from the running service, Paper engine remediation — updated 13 September 2026, September 13 implementation update, Verification and current evidence, Work still required

### Community 58 - "Deploy Your First Strategy"
Cohesion: 0.29
Nodes (7): Deploy Your First Strategy, Step 1 — Create a new strategy, Step 2 — Write the strategy, Step 3 — Set your credentials in Variables, Step 4 — Add the SDK to Dependencies, Step 5 — Select a compute tier, Step 6 — Save and deploy

### Community 59 - "Learning evidence monitor"
Cohesion: 0.29
Nodes (6): AI reviewer, Current risk requirements, Learning evidence monitor, Overfitting controls, Run and verify, What the monitor establishes

### Community 60 - "Behavioral Guidelines"
Cohesion: 0.33
Nodes (5): 1. Think Before Coding, 2. Simplicity First, 3. Surgical Changes, 4. Goal-Driven Execution, Behavioral Guidelines

### Community 61 - "graphify reference: query, path, explain"
Cohesion: 0.33
Nodes (5): For /graphify explain, For /graphify path, graphify reference: query, path, explain, Step 0 — Constrained query expansion (REQUIRED before traversal), Step 1 — Traversal

### Community 62 - "Paper learning and adaptive exits"
Cohesion: 0.33
Nodes (5): Adaptive exits, Entry-quality learning, Historical data learning and net cost verification (Updated), Paper learning and adaptive exits, Storage and scope

### Community 63 - "calendar_info"
Cohesion: 0.53
Nodes (4): calendar_info(), Published NSE derivatives closures used as a shared portfolio entry gate. This…, test_calendar_does_not_claim_unknown_year_or_complete_bse_coverage(), test_published_holiday_prevents_regular_entries()

### Community 64 - "quote_is_fresh"
Cohesion: 0.29
Nodes (3): PaperBroker, quote_is_fresh(), test_rest_snapshot_last_trade_does_not_prove_fresh_book()

### Community 65 - "Market Data"
Cohesion: 0.33
Nodes (6): Binary Response, Full Packet, Market Data, Quote Packet, Response Header, Ticker Packet

### Community 66 - "Modify Order"
Cohesion: 0.33
Nodes (6): Example Request, Modify Order, Path Parameters, Request Body Parameters, Response Fields, Status Codes

### Community 67 - "Modify Conditional Order"
Cohesion: 0.33
Nodes (6): Example Request, Modify Conditional Order, Path Parameters, Request Body Parameters, Response Fields, Status Codes

### Community 68 - "Modify Order"
Cohesion: 0.33
Nodes (6): Example Request, Modify Order, Path Parameters, Request Body Parameters, Response Fields, Status Codes

### Community 69 - "Modify Super Order"
Cohesion: 0.33
Nodes (6): Example Request, Modify Super Order, Path Parameters, Request Body Parameters, Response Fields, Status Codes

### Community 70 - "dependencies"
Cohesion: 0.33
Nodes (6): dependencies, react, react-dom, typescript, vite, @vitejs/plugin-react

### Community 72 - "greek_scenario"
Cohesion: 0.27
Nodes (7): _finite(), greek_scenario(), OptionSelector, Return a unit-checked local Greek scenario, or an explicit unavailable result.…, test_greek_scenario_blocks_unverified_units_or_missing_values(), test_greek_scenario_does_not_double_count_observed_option_candles(), test_greek_scenario_is_unit_checked_and_reports_lot_value()

### Community 73 - "Backtest and dashboard audit — 13 September 2026"
Cohesion: 0.40
Nodes (4): Backtest and dashboard audit — 13 September 2026, Remaining evidence limits, Running-system verification, Verified defects and corrections

### Community 74 - "Response Structure"
Cohesion: 0.40
Nodes (5): 200 Level, 20 Level, Response Header, Response Header, Response Structure

### Community 75 - "Authentication APIs"
Cohesion: 0.40
Nodes (5): Access Token, API Key & Secret, Authentication APIs, Partners, Setup Static IP

### Community 76 - "Version 2.0"
Cohesion: 0.40
Nodes (5): Breaking Changes, Bug Fixes, Improvements, New Features, Version 2.0

### Community 77 - "Calculate Margin"
Cohesion: 0.40
Nodes (5): Calculate Margin, Example Request, Request Body Parameters, Response Fields, Status Codes

### Community 78 - "Calculate Multi-Order Margin"
Cohesion: 0.40
Nodes (5): Calculate Multi-Order Margin, Example Request, Request Body Parameters, Response Fields, Status Codes

### Community 79 - "Cancel Order"
Cohesion: 0.40
Nodes (5): Cancel Order, Example Request, Path Parameters, Response Fields, Status Codes

### Community 80 - "Cancel Order"
Cohesion: 0.40
Nodes (5): Cancel Order, Example Request, Path Parameters, Response Fields, Status Codes

### Community 81 - "Cancel Super Order Leg"
Cohesion: 0.40
Nodes (5): Cancel Super Order Leg, Example Request, Path Parameters, Response Fields, Status Codes

### Community 82 - "Conditional and Multi Order"
Cohesion: 0.40
Nodes (5): Comparison Type, Conditional and Multi Order, Indicator Name, Operator, Status

### Community 83 - "Consume Consent"
Cohesion: 0.40
Nodes (5): Consume Consent, Example Request, Header Parameters, Query Parameters, Response Fields

### Community 84 - "Consume Consent"
Cohesion: 0.40
Nodes (5): Consume Consent, Example Request, Header Parameters, Query Parameters, Response Fields

### Community 85 - "Portfolio"
Cohesion: 0.40
Nodes (5): Convert Position, Exit All Positions, Get Holdings, Get Positions, Portfolio

### Community 86 - "Delete Conditional Order"
Cohesion: 0.40
Nodes (5): Delete Conditional Order, Example Request, Path Parameters, Response Fields, Status Codes

### Community 87 - "EDIS Status Inquiry"
Cohesion: 0.40
Nodes (5): EDIS Status Inquiry, Example Request, Path Parameters, Response Fields, Status Codes

### Community 88 - "Get Intraday Historical Data"
Cohesion: 0.40
Nodes (5): Example Request, Get Intraday Historical Data, Request Body Parameters, Response Fields, Status Codes

### Community 89 - "Ledger Report"
Cohesion: 0.40
Nodes (5): Example Request, Ledger Report, Query Parameters, Response Fields, Status Codes

### Community 90 - "Get Order by Correlation ID"
Cohesion: 0.40
Nodes (5): Example Request, Get Order by Correlation ID, Path Parameters, Response Fields, Status Codes

### Community 91 - "Get Order by ID"
Cohesion: 0.40
Nodes (5): Example Request, Get Order by ID, Path Parameters, Response Fields, Status Codes

### Community 92 - "Trade History"
Cohesion: 0.40
Nodes (5): Example Request, Path Parameters, Response Fields, Status Codes, Trade History

### Community 93 - "Get Trades for Order"
Cohesion: 0.40
Nodes (5): Example Request, Get Trades for Order, Path Parameters, Response Fields, Status Codes

### Community 94 - "Get Order by ID"
Cohesion: 0.40
Nodes (5): Example Request, Get Order by ID, Path Parameters, Response Fields, Status Codes

### Community 95 - "Get Past Trades by Security Id"
Cohesion: 0.40
Nodes (5): Example Request, Get Past Trades by Security Id, Path Parameters, Response Fields, Status Codes

### Community 96 - "Margin Calculator"
Cohesion: 0.40
Nodes (5): Example Request, Margin Calculator, Request Body Parameters, Response Fields, Status Codes

### Community 97 - "Order Estimator"
Cohesion: 0.40
Nodes (5): Example Request, Order Estimator, Request Body Parameters, Response Fields, Status Codes

### Community 98 - "Place Order"
Cohesion: 0.40
Nodes (5): Example Request, Place Order, Request Body Parameters, Response Fields, Status Codes

### Community 99 - "Manage Kill Switch"
Cohesion: 0.40
Nodes (5): Example Request, Manage Kill Switch, Query Parameters, Response Fields, Status Codes

### Community 100 - "Place Order"
Cohesion: 0.40
Nodes (5): Example Request, Place Order, Request Body Parameters, Response Fields, Status Codes

### Community 101 - "Place Super Order"
Cohesion: 0.40
Nodes (5): Example Request, Place Super Order, Request Body Parameters, Response Fields, Status Codes

### Community 102 - "Slice Order"
Cohesion: 0.40
Nodes (5): Example Request, Request Body Parameters, Response Fields, Slice Order, Status Codes

### Community 103 - "Generate Consent"
Cohesion: 0.40
Nodes (5): Example Request, Generate Consent, Header Parameters, Query Parameters, Response Fields

### Community 104 - "Generate eDIS Form"
Cohesion: 0.40
Nodes (5): Example Request, Generate eDIS Form, Request Body Parameters, Response Fields, Status Codes

### Community 105 - "Get Daily Historical Data"
Cohesion: 0.40
Nodes (5): Example Request, Get Daily Historical Data, Request Body Parameters, Response Fields, Status Codes

### Community 106 - "Historical Rolling Options Data"
Cohesion: 0.40
Nodes (5): Example Request, Historical Rolling Options Data, Request Body Parameters, Response Fields, Status Codes

### Community 107 - "Get Expiry List"
Cohesion: 0.40
Nodes (5): Example Request, Get Expiry List, Request Body Parameters, Response Fields, Status Codes

### Community 108 - "StrategyPortfolio.tsx"
Cohesion: 0.60
Nodes (4): Data, rupees(), StrategyPortfolio(), time()

### Community 109 - "graphify reference: add a URL and watch a folder"
Cohesion: 0.50
Nodes (3): For /graphify add, For --watch, graphify reference: add a URL and watch a folder

### Community 110 - "graphify reference: commit hook and native CLAUDE.md integration"
Cohesion: 0.50
Nodes (3): For git commit hook, For native CLAUDE.md integration, graphify reference: commit hook and native CLAUDE.md integration

### Community 111 - "graphify reference: incremental update and cluster-only"
Cohesion: 0.50
Nodes (3): For --cluster-only, For --update (incremental re-extraction), graphify reference: incremental update and cluster-only

### Community 112 - "package.json"
Cohesion: 0.25
Nodes (7): dependencies, caveman, omniroute, ponytail, caveman, omniroute, ponytail

### Community 113 - "RiskEngine"
Cohesion: 0.29
Nodes (8): available_risk(), One policy for paper and historical replay; data/fill adapters supply…, RiskEngine, test_daily_halt(), test_fees_cash_and_correlated_risk_are_shared(), test_invalid_risk_inputs_fail_closed(), test_position_limit(), test_shared_budget_uses_selected_limits_and_does_not_recycle_daily_profits()

### Community 114 - "add_features"
Cohesion: 0.36
Nodes (8): add_features(), adx(), atr(), ema(), rsi(), closed_session(), test_indicators_do_not_invent_index_volume(), test_vwap_resets_each_session()

### Community 115 - "agent_metrics.py"
Cohesion: 0.27
Nodes (9): _agent_trades(), _learn_from_outcomes(), _passes(), plan_agent_capabilities(), Restrict learning statistics to outcomes with recorded agent context., rollback_policies(), _stats(), test_negative_expectancy_and_different_session_coverage_rejected() (+1 more)

### Community 116 - "csv_adapter.py"
Cohesion: 0.50
Nodes (3): adapt_index_csv(), Backtest adapter: reads 5yr index CSV and creates option_quotes from DB…, Read NIFTY/SENSEX 5yr CSV, verify format, return underlying frame. Returns…

### Community 118 - "Access for Individual Traders"
Cohesion: 0.50
Nodes (4): Access for Individual Traders, Access Token, API Key & Secret, Step 2: Browser Based Login

### Community 119 - "Access Token Setup"
Cohesion: 0.50
Nodes (4): Access Token Setup, Step 1: Generate Your Access Token, Step 2: Configure the Token for Your Agent, Step 3: Verify the Configuration

### Community 120 - "Supported Agents"
Cohesion: 0.50
Nodes (4): Any SKILL.md-Supporting Agent, Claude Code, Codex, Supported Agents

### Community 121 - "Version 2.2"
Cohesion: 0.50
Nodes (4): Breaking Changes, Improvements, New Features, Version 2.2

### Community 122 - "Super Order"
Cohesion: 0.50
Nodes (4): Cancel Super Order Leg, Modify Super Order, Place Super Order, Super Order

### Community 123 - "Common Error Scenarios"
Cohesion: 0.50
Nodes (4): Common Error Scenarios, Expired Token, Invalid Security ID, Rate Limit Exceeded

### Community 124 - "Configure P&L Based Exit"
Cohesion: 0.50
Nodes (4): Configure P&L Based Exit, Example Request, Request Body Parameters, Status Codes

### Community 125 - "Connect Your Dhan Account"
Cohesion: 0.50
Nodes (4): Connect Your Dhan Account, Credentials you will need, Step 1 — Sign in to the Developer Portal, Step 2 — Connect your Dhan account

### Community 126 - "Convert Position"
Cohesion: 0.50
Nodes (4): Convert Position, Example Request, Request Body Parameters, Status Codes

### Community 127 - "EDIS Status & Inquiry"
Cohesion: 0.50
Nodes (4): EDIS Status & Inquiry, Response Fields, Response Fields, Response Fields

### Community 128 - "Lot Size Validation"
Cohesion: 0.50
Nodes (4): Example, Lot Size Validation, Supported Segments, What Gets Validated

### Community 129 - "Kill Switch Status"
Cohesion: 0.50
Nodes (4): Example Request, Kill Switch Status, Response Fields, Status Codes

### Community 130 - "Get LTP"
Cohesion: 0.50
Nodes (4): Example Request, Get LTP, Request Body Parameters, Status Codes

### Community 131 - "Get OHLC"
Cohesion: 0.50
Nodes (4): Example Request, Get OHLC, Request Body Parameters, Status Codes

### Community 132 - "Get Option Chain"
Cohesion: 0.50
Nodes (4): Example Request, Get Option Chain, Request Body Parameters, Status Codes

### Community 133 - "Get Order Book"
Cohesion: 0.50
Nodes (4): Example Request, Get Order Book, Response Fields, Status Codes

### Community 134 - "Get Positions"
Cohesion: 0.50
Nodes (4): Example Request, Get Positions, Response Fields, Status Codes

### Community 135 - "Get Full Quote"
Cohesion: 0.50
Nodes (4): Example Request, Get Full Quote, Request Body Parameters, Status Codes

### Community 136 - "Get Super Orders"
Cohesion: 0.50
Nodes (4): Example Request, Get Super Orders, Response Fields, Status Codes

### Community 137 - "Get Trade Book"
Cohesion: 0.50
Nodes (4): Example Request, Get Trade Book, Response Fields, Status Codes

### Community 138 - "Get Fund Limit"
Cohesion: 0.50
Nodes (4): Example Request, Get Fund Limit, Response Fields, Status Codes

### Community 139 - "Get Holdings"
Cohesion: 0.50
Nodes (4): Example Request, Get Holdings, Response Fields, Status Codes

### Community 140 - "Get Market Status"
Cohesion: 0.50
Nodes (4): Example Request, Get Market Status, Response Fields, Status Codes

### Community 141 - "Get Order Book"
Cohesion: 0.50
Nodes (4): Example Request, Get Order Book, Response Fields, Status Codes

### Community 142 - "Get Past Trades"
Cohesion: 0.50
Nodes (4): Example Request, Get Past Trades, Response Fields, Status Codes

### Community 143 - "Place Conditional Order"
Cohesion: 0.50
Nodes (4): Example Request, Place Conditional Order, Request Body Parameters, Status Codes

### Community 144 - "Place Multi Order"
Cohesion: 0.50
Nodes (4): Example Request, Place Multi Order, Request Body Parameters, Status Codes

### Community 145 - "Generate Token"
Cohesion: 0.50
Nodes (4): Example Request, Generate Token, Query Parameters, Response Fields

### Community 146 - "Modify IP"
Cohesion: 0.50
Nodes (4): Example Request, Modify IP, Request Body Parameters, Response Fields

### Community 147 - "Generate Consent"
Cohesion: 0.50
Nodes (4): Example Request, Generate Consent, Header Parameters, Response Fields

### Community 148 - "Renew Token"
Cohesion: 0.50
Nodes (4): Example Request, Header Parameters, Renew Token, Response Fields

### Community 149 - "Set IP"
Cohesion: 0.50
Nodes (4): Example Request, Request Body Parameters, Response Fields, Set IP

### Community 150 - "Generate T-PIN"
Cohesion: 0.50
Nodes (4): Example Request, Generate T-PIN, Response Fields, Status Codes

### Community 151 - "Get Conditional Order by ID"
Cohesion: 0.50
Nodes (4): Example Request, Get Conditional Order by ID, Path Parameters, Status Codes

### Community 152 - "Get Fund Limits"
Cohesion: 0.50
Nodes (4): Example Request, Get Fund Limits, Response Fields, Status Codes

### Community 153 - "Get Holdings"
Cohesion: 0.50
Nodes (4): Example Request, Get Holdings, Response Fields, Status Codes

### Community 154 - "Example Workflows"
Cohesion: 0.50
Nodes (4): Example Workflows, Monitor and Exit a Position, Options Strategy Execution, Place an Order with Pre-checks

### Community 155 - "Supported Values"
Cohesion: 0.50
Nodes (4): Exchange Segments, Order Types, Product Types, Supported Values

### Community 156 - "Funds"
Cohesion: 0.50
Nodes (4): Funds, Get Fund Limits, Margin Calculator, Multi-Order Margin Calculator

### Community 157 - "Market Data"
Cohesion: 0.50
Nodes (4): Get Full Quote (with Market Depth), Get LTP, Get OHLC, Market Data

### Community 158 - "Order Update"
Cohesion: 0.50
Nodes (4): Order Update, Response Fields, Response Fields, Response Fields

### Community 161 - "local_mutations"
Cohesion: 0.67
Nodes (3): middleware, Request, local_mutations()

### Community 163 - "audit_observation_db"
Cohesion: 0.39
Nodes (6): audit_observation_db(), main(), Audit recorded option observations without overstating historical coverage., Return a bounded, reproducible audit of a QuoteRecorder SQLite database., test_audit_rejects_non_recorder_database(), test_audit_reports_observations_without_claiming_replay_eligibility()

### Community 165 - "Establishing Connection"
Cohesion: 0.67
Nodes (3): 200 Level, 20 Level, Establishing Connection

### Community 166 - "Adding Instruments"
Cohesion: 0.67
Nodes (3): 200 Level, 20 Level, Adding Instruments

### Community 167 - "API Structure"
Cohesion: 0.67
Nodes (3): API Structure, Base URLs, Request Headers

### Community 168 - "Handling Rate Limits"
Cohesion: 0.67
Nodes (3): Best Practices, Handling Rate Limits, Python Example with Rate Limiting

### Community 169 - "Version 2.4"
Cohesion: 0.67
Nodes (3): Breaking Changes, New Features, Version 2.4

### Community 170 - "Install"
Cohesion: 0.67
Nodes (3): Claude Code or Codex (zero-install), Global install, Install

### Community 171 - "Indian Stocks"
Cohesion: 0.67
Nodes (3): Column Description, Indian Stocks, Segmentwise List

### Community 172 - "Historical Data"
Cohesion: 0.67
Nodes (3): Daily Data, Historical Data, Intraday Data

### Community 173 - "Request Messages"
Cohesion: 0.67
Nodes (3): Disconnect, Request Messages, Subscribe or Unsubscribe

### Community 174 - "Establishing Connection"
Cohesion: 0.67
Nodes (3): Establishing Connection, For Individual, For Partners

### Community 175 - "Order Confirmation"
Cohesion: 0.67
Nodes (3): Example Flow, Order Confirmation, What Gets Confirmed

### Community 176 - "Get P&L Based Exit"
Cohesion: 0.67
Nodes (3): Example Request, Get P&L Based Exit, Status Codes

### Community 177 - "Stop P&L Based Exit"
Cohesion: 0.67
Nodes (3): Example Request, Status Codes, Stop P&L Based Exit

### Community 178 - "Get IP"
Cohesion: 0.67
Nodes (3): Example Request, Get IP, Response Fields

### Community 179 - "Exit All Positions"
Cohesion: 0.67
Nodes (3): Example Request, Exit All Positions, Status Codes

### Community 180 - "Get All Conditional Orders"
Cohesion: 0.67
Nodes (3): Example Request, Get All Conditional Orders, Status Codes

### Community 181 - "Feed Disconnect"
Cohesion: 0.67
Nodes (3): Feed Disconnect, Response Fields, Response Fields

### Community 182 - "Option Chain"
Cohesion: 0.67
Nodes (3): Get Expiry List, Get Option Chain, Option Chain

### Community 183 - "Get P&L Based Exit"
Cohesion: 0.67
Nodes (3): Get P&L Based Exit, Response Fields, Response Fields

### Community 184 - "Historical Rolling Data"
Cohesion: 0.67
Nodes (3): Historical Rolling Data, Response Fields, Response Fields

### Community 185 - "LIMIT Order Defaults"
Cohesion: 0.67
Nodes (3): How It Works, LIMIT Order Defaults, Why LIMIT by Default

### Community 186 - "Setup TOTP"
Cohesion: 0.67
Nodes (3): How to Set Up TOTP, Setup TOTP, What is TOTP?

### Community 187 - "Version 2.5"
Cohesion: 0.67
Nodes (3): Improvements, New Features, Version 2.5

### Community 188 - "Version 2.1"
Cohesion: 0.67
Nodes (3): Improvements, New Features, Version 2.1

### Community 189 - "Structure"
Cohesion: 0.67
Nodes (3): Python, REST, Structure

### Community 190 - "Trade History"
Cohesion: 0.67
Nodes (3): Response Fields, Response Fields, Trade History

## Knowledge Gaps
- **851 isolated node(s):** `name`, `private`, `version`, `type`, `dev` (+846 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1149 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **18 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Getting Started` connect `Getting Started` to `DhanHQ API Documentation — Full Export`, `Binary Response`, `Order Management`, `Deploy Your First Strategy`, `Market Data`, `Modify Order`, `Modify Conditional Order`, `Modify Order`, `Modify Super Order`, `Response Structure`, `Authentication APIs`, `Version 2.0`, `Cancel Order`, `Conditional and Multi Order`, `Consume Consent`, `Consume Consent`, `Portfolio`, `EDIS Status Inquiry`, `Get Intraday Historical Data`, `Ledger Report`, `Get Order by Correlation ID`, `Get Order by ID`, `Trade History`, `Get Trades for Order`, `Get Order by ID`, `Get Past Trades by Security Id`, `Margin Calculator`, `Order Estimator`, `Place Order`, `Manage Kill Switch`, `Place Order`, `Place Super Order`, `Slice Order`, `Generate Consent`, `Generate eDIS Form`, `Get Daily Historical Data`, `Historical Rolling Options Data`, `Get Expiry List`, `Access for Individual Traders`, `Access Token Setup`, `Supported Agents`, `Version 2.2`, `Super Order`, `Common Error Scenarios`, `Connect Your Dhan Account`, `EDIS Status & Inquiry`, `Lot Size Validation`, `Kill Switch Status`, `Get LTP`, `Get OHLC`, `Get Option Chain`, `Get Order Book`, `Get Positions`, `Get Full Quote`, `Get Super Orders`, `Get Trade Book`, `Get Fund Limit`, `Get Holdings`, `Get Market Status`, `Get Order Book`, `Get Past Trades`, `Place Conditional Order`, `Place Multi Order`, `Generate Token`, `Modify IP`, `Generate Consent`, `Renew Token`, `Set IP`, `Generate T-PIN`, `Get Conditional Order by ID`, `Get Fund Limits`, `Get Holdings`, `Example Workflows`, `Supported Values`, `Funds`, `Market Data`, `Order Update`, `Establishing Connection`, `Adding Instruments`, `API Structure`, `Handling Rate Limits`, `Version 2.4`, `Install`, `Indian Stocks`, `Historical Data`, `Request Messages`, `Establishing Connection`, `Order Confirmation`, `Get P&L Based Exit`, `Stop P&L Based Exit`, `Get IP`, `Exit All Positions`, `Get All Conditional Orders`, `Feed Disconnect`, `Option Chain`, `Get P&L Based Exit`, `Historical Rolling Data`, `LIMIT Order Defaults`, `Setup TOTP`, `Version 2.5`, `Version 2.1`, `Structure`, `Trade History`, `Global Stocks`, `Feed Disconnect`, `For Partners`, `Version 2.3`, `Setting Up Postback`?**
  _High betweenness centrality (0.149) - this node is a cross-community bridge._
- **Why does `Store` connect `Store` to `test_paper.py`, `test_backtest.py`, `test_reconstruction.py`, `test_jobs.py`, `DhanGateway`, `AutonomousTradingAgent`, `ForwardComparison`, `main.py`, `test_adaptive_learning.py`, `test_paper_toggle_is_explicit_and_never_live`, `autonomous_agent.py`, `test_learning_monitor.py`, `LearningService`, `audit_individual_agents`, `test_runtime.py`, `cli.py`, `learn_from_outcomes`?**
  _High betweenness centrality (0.030) - this node is a cross-community bridge._
- **Why does `now_ist()` connect `now_ist` to `test_reconstruction.py`, `datetime`, `test_strategy_portfolio.py`, `AutonomousTradingAgent`, `ForwardComparison`, `main.py`, `DhanMarketData`, `post`, `test_learning_monitor.py`, `Store`, `LearningService`, `QuoteRecorder`, `test_runtime.py`, `learn_from_outcomes`, `ai.py`, `DhanGateway`, `test_backtest.py`, `json_safe`, `test_adaptive_learning.py`, `PaperEngine`, `autonomous_agent.py`, `quote_is_fresh`, `agent_metrics.py`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `Store` (e.g. with `AutonomousTradingAgent` and `account()`) actually correct?**
  _`Store` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `datetime` (e.g. with `test_completed_stall_requires_contiguous_bars()` and `test_cost_covering_stop_and_restart_never_loosen()`) actually correct?**
  _`datetime` has 10 INFERRED edges - model-reasoned connections that need verification._
- **What connects `name`, `private`, `version` to the rest of the system?**
  _851 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Getting Started` be split into smaller, more focused modules?**
  _Cohesion score 0.00816326530612245 - nodes in this community are weakly interconnected._