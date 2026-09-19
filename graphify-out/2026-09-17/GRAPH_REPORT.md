# Graph Report - trading_bot_full  (2026-09-17)

## Corpus Check
- 116 files · ~139,145 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1921 nodes · 3438 edges · 194 communities (181 shown, 13 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 89 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `b1148fe5`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Getting Started
- main.py
- test_paper.py
- test_strategy_portfolio.py
- main.tsx
- test_jobs.py
- Allowed and Restricted Operations
- AutonomousTradingAgent
- test_reconstruction.py
- ForwardComparison
- now_ist
- Dhan MCP Architecture Flow
- What You Must Do When Invoked
- test_backtest.py
- test_learning_monitor.py
- frontend/package.json
- test_execution_integrity.py
- LearningService
- jobs.py
- PlanRiskPolicy
- DhanMarketData
- reconstruction.py
- DhanGateway
- Store
- DecisionPipeline
- models.py
- PaperBroker
- LLMClient
- audit_individual_agents
- Self-Learning System Status
- compilerOptions
- engine.py
- session_state
- Options Paper Lab
- test_runtime.py
- local_time
- QuoteRecorder
- PaperEngine
- assess_specialists
- Backtest and learning checkpoint — September 14, 2026
- Trading Bot — Full Project Logic (Verified from Source)
- DhanHQ API Documentation — Full Export
- graphify reference: extra exports and benchmark
- MLTradeQualityModel
- replay_evidence
- Binary Response
- Paper trading and research architecture contract
- ExperimentStore
- EventBus
- Order Management
- Installation
- Connect your client
- Paper engine remediation — updated 13 September 2026
- paper_performance.py
- Deploy Your First Strategy
- Learning evidence monitor
- graphify reference: query, path, explain
- Paper learning and adaptive exits
- Market Data
- Modify Order
- Modify Conditional Order
- Modify Order
- Modify Super Order
- datetime
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
- graphify reference: add a URL and watch a folder
- graphify reference: commit hook and native CLAUDE.md integration
- graphify reference: incremental update and cluster-only
- dependencies
- config.py
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
- Persistent user requirements
- graphify reference: GitHub clone and cross-repo merge
- graphify reference: transcribe video and audio
- Trading bot source snapshot
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
- extraction-spec.md
- README.md
- Global Stocks
- Feed Disconnect
- For Partners
- Version 2.3
- Setting Up Postback

## God Nodes (most connected - your core abstractions)
1. `Getting Started` - 352 edges
2. `Store` - 77 edges
3. `now_ist()` - 67 edges
4. `Allowed and Restricted Operations` - 39 edges
5. `local_time()` - 35 edges
6. `LearningService` - 34 edges
7. `session_state()` - 33 edges
8. `Settings` - 32 edges
9. `PaperEngine` - 32 edges
10. `Dhan MCP Architecture Flow` - 31 edges

## Surprising Connections (you probably didn't know these)
- `test_coordinator_has_no_independent_order_authority()` --uses--> `AutonomousTradingAgent`  [INFERRED]
  Trading Bot/backend/tests/test_execution_integrity.py → Trading Bot/backend/app/autonomous_agent.py
- `lifespan()` --uses--> `MultiStrategyPaperEngine`  [INFERRED]
  Trading Bot/backend/app/main.py → Trading Bot/backend/app/portfolio_engine.py
- `test_failed_fit_still_consumes_holdout()` --uses--> `MLTradeQualityModel`  [INFERRED]
  Trading Bot/backend/tests/test_learning_monitor.py → Trading Bot/backend/app/ai.py
- `AutonomousTradingAgent` --uses--> `LearningService`  [INFERRED]
  Trading Bot/backend/app/autonomous_agent.py → Trading Bot/backend/app/ai.py
- `MultiStrategyPaperEngine` --uses--> `LearningService`  [INFERRED]
  Trading Bot/backend/app/portfolio_engine.py → Trading Bot/backend/app/ai.py

## Import Cycles
- None detected.

## Communities (194 total, 13 thin omitted)

### Community 0 - "Getting Started"
Cohesion: 0.01
Nodes (245): 1. Create an Account, 2. Generate API Credentials, 3. Install the SDK, 4. Initialize the Client, 5. Place Your First Order, A Few Things to Know, Adding Credits, Adding Instruments (+237 more)

### Community 1 - "main.py"
Cohesion: 0.05
Nodes (84): get, middleware, post, Request, dataset_metadata(), Header inspection is an eligibility hint, not verified historical coverage., history_row(), Read models for reports: retain audit data without presenting partial profit as… (+76 more)

### Community 2 - "test_paper.py"
Cohesion: 0.23
Nodes (21): exchange_timestamp(), parametrize, test_failed_persistence_restores_account_and_prevents_ghost_fill(), contract(), enter(), quote(), Isolated accounting fixtures; none are loaded by the runtime or dashboard., test_account_persists_and_partial_exits_reconcile() (+13 more)

### Community 3 - "test_strategy_portfolio.py"
Cohesion: 0.10
Nodes (28): MultiStrategyPaperEngine, evaluate_strategies(), rank_opportunities(), Rank only eligible offers; statistical support precedes observation economics.…, Return the current day's deterministic strategy preference order., regime_strategy_policy(), signal_for(), candidate() (+20 more)

### Community 4 - "main.tsx"
Cohesion: 0.08
Nodes (34): Data, LearningMonitor(), active(), AgentLessons(), api(), App(), ArchiveManifest(), AuditDetails() (+26 more)

### Community 5 - "test_jobs.py"
Cohesion: 0.11
Nodes (24): dataset_path(), archive_manifest(), download_history(), Resolve a user-selected range without treating an explicit zero year as one…, Archive source observations only; never run a strategy or update learning., Describe the retained source pass without claiming complete exchange coverage., resolve_backtest_budgets(), resolve_backtest_start() (+16 more)

### Community 6 - "Allowed and Restricted Operations"
Cohesion: 0.05
Nodes (37): Allowed, Allowed and Restricted Operations, Architecture, Blocked, Checking Fund Limits, Code Scanner, Common Flags and How to Fix Them, Compatible clients (+29 more)

### Community 7 - "AutonomousTradingAgent"
Cohesion: 0.08
Nodes (20): AgentState, AutonomousTradingAgent, get_autonomous_agent(), Start the autonomous agent loop., Stop the autonomous agent., Main agent loop - runs every 2 seconds during market hours., Background learning loop - retrains models periodically., Pre-market preparation: load models, validate data, check risk limits. (+12 more)

### Community 8 - "test_reconstruction.py"
Cohesion: 0.10
Nodes (32): estimate_gap_exit(), Exploratory missing-price liquidation; never an observed candle or live fill., Use only the preceding minute, then liquidate instead of inventing a path., merge_series(), Quarantine conflicting duplicate candles permanently, independent of fetch…, ResearchReplay, outcome_lessons(), Observed associations and hypotheses; not causal proof or deployed policies. (+24 more)

### Community 9 - "ForwardComparison"
Cohesion: 0.12
Nodes (4): FixedLearning, ForwardComparison, Prospective reference account. No real-order authority or additive profit…, ReferenceEngine

### Community 10 - "now_ist"
Cohesion: 0.14
Nodes (12): Causal paper exit state. A stop is a request, never a guaranteed fill., extract_features(), Entry-quality learning from causal, net-cost outcomes. No order authority., Caller supplies a completed causal row; missing volume/Greeks stay missing., Paper research coordinator. Execution belongs exclusively to the portfolio…, Three paper hypotheses, one selector, one atomic portfolio authority., Bounded, asynchronous recording of normalized observations, never credentials., now_ist() (+4 more)

### Community 11 - "Dhan MCP Architecture Flow"
Cohesion: 0.06
Nodes (31): 1. You, 2. MCP Client, 3. Tool Call to mcp.dhan.co, 4. Dhan MCP Server, 5. DEXT, 6. Exchange, Alerts, Dhan MCP Architecture Flow (+23 more)

### Community 12 - "What You Must Do When Invoked"
Cohesion: 0.08
Nodes (24): For /graphify add and --watch, For /graphify query, For the commit hook and native CLAUDE.md integration, For --update and --cluster-only, /graphify, Honesty Rules, Interpreter guard for subcommands, Part A - Structural extraction for code files (+16 more)

### Community 13 - "test_backtest.py"
Cohesion: 0.16
Nodes (17): metrics(), learn_from_outcomes(), _passes(), Every outcome is logged. Promotion requires fresh, full chronological replays., _stats(), test_cancel_before_learning_commit_leaves_no_policy_or_ledger(), test_every_backtest_run_records_learning_for_every_agent(), test_full_validation_promotes_at_most_one_and_records_both_windows() (+9 more)

### Community 14 - "test_learning_monitor.py"
Cohesion: 0.12
Nodes (18): build_evidence(), evidence_fingerprint(), explain_evidence(), LearningMonitor, Evidence monitor. No order, training, parameter-edit or promotion tools., Read the authoritative file for EVERY call; never retain an expired key., Heartbeat counters are activity, not new learning or changed evidence quality., Fixed research gates. Passing these gates never proves absence of overfitting. (+10 more)

### Community 15 - "frontend/package.json"
Cohesion: 0.08
Nodes (23): react, react-dom, dependencies, react, react-dom, typescript, vite, @vitejs/plugin-react (+15 more)

### Community 16 - "test_execution_integrity.py"
Cohesion: 0.33
Nodes (5): Failure injection against isolated E-drive databases; no runtime imports., test_coordinator_has_no_independent_order_authority(), test_health_detects_stuck_execution_worker(), test_raw_index_prices_cannot_become_verified_options(), test_structural_stop_is_not_tightened_to_force_risk_budget()

### Community 17 - "LearningService"
Cohesion: 0.17
Nodes (19): Persistable state; only fresh observed bids may call this function. ATR must…, update_exit(), LearningService, position(), Synthetic fixtures test mechanics, never trading performance evidence., test_completed_stall_requires_contiguous_bars(), test_cost_covering_stop_and_restart_never_loosen(), test_missing_option_atr_does_not_invent_trailing_volatility() (+11 more)

### Community 18 - "jobs.py"
Cohesion: 0.16
Nodes (13): main(), Read one row per exact option contract/minute, with repeated underlying OHLCV., read_contract_csv(), BacktestConfig, BacktestJobs, Durable, single-worker backtests; browser lifetime never owns a running job., dhan_plan_research(), dhan_research() (+5 more)

### Community 19 - "PlanRiskPolicy"
Cohesion: 0.15
Nodes (20): BacktestEngine, PlanRiskPolicy, Plan v1 risk envelope. Values are frozen configuration, not learned parameters., historical_fixture(), Contract fixtures only for regression tests, never runtime market data., test_backtest_runs(), test_fixed_contract_drift_blocks_headline_pnl(), test_next_bar_open_and_entry_bar_stop() (+12 more)

### Community 20 - "DhanMarketData"
Cohesion: 0.12
Nodes (7): Exception, DhanMarketData, Any, Seed latest values from one broker quote call; live ticks replace them., Dhan MarketFeed adapter. No tick is manufactured when the feed is down., test_websocket_packets_are_bounded_and_do_not_write_database(), test_stream_rotation_drops_old_prices_and_old_callbacks()

### Community 21 - "reconstruction.py"
Cohesion: 0.13
Nodes (14): scope(), Source validation. Rolling moneyness must never masquerade as a fixed contract., _valid_bar(), Dhan rolling candles -> fixed-strike intraday research, never verified net…, CostModel, Only a dated source schedule can price a historical order., Standard Dhan index option round-trip charges (₹40 brokerage + STT + turnover +…, execution_context() (+6 more)

### Community 22 - "DhanGateway"
Cohesion: 0.23
Nodes (4): DhanGateway, One rate-limited, cached data adapter shared by paper and research., Reuse overlapping sourced responses; fetch only uncovered date intervals., test_expiry_day_is_skipped_for_paper_policy()

### Community 23 - "Store"
Cohesion: 0.17
Nodes (3): Reserve unseen symbol history atomically, including across app processes., Store, test_paper_toggle_is_explicit_and_never_live()

### Community 24 - "DecisionPipeline"
Cohesion: 0.16
Nodes (11): DecisionPipeline, finite(), Shared baseline decision; executable premium protection is a later gate., Apply frozen policy to a causally produced candidate, without future labels., once_per_session(), fixture, parametrize, test_baseline_honors_each_participating_agent_veto() (+3 more)

### Community 25 - "models.py"
Cohesion: 0.09
Nodes (26): Enum, str, Decision, Direction, ExpectancyResult, FeatureSnapshot, OptionContract, BaseModel (+18 more)

### Community 27 - "LLMClient"
Cohesion: 0.06
Nodes (20): AsyncClient, create_llm_client(), FailureAnalyst, get_analysts(), HypothesisGenerator, LLMClient, MarketAnalyst, Async OpenRouter client with retries, timeout, and structured output parsing. (+12 more)

### Community 28 - "audit_individual_agents"
Cohesion: 0.23
Nodes (17): audit_individual_agents(), _day(), _finite(), _loss_investigation(), _matches_agent(), _model_rows(), _overfitting_gate(), Any (+9 more)

### Community 29 - "Self-Learning System Status"
Cohesion: 0.12
Nodes (15): API Endpoints, Backend Services, Configuration (.env), CORRECTED (2026-09-12), CORRECTED MULTI-STRATEGY UNDERSTANDING (2026-09-12), Current Model Status, Data Status, Dynamic Market Evaluation (+7 more)

### Community 30 - "compilerOptions"
Cohesion: 0.13
Nodes (14): DOM, DOM.Iterable, ES2020, src, compilerOptions, jsx, lib, module (+6 more)

### Community 31 - "engine.py"
Cohesion: 0.16
Nodes (20): Chronological, shared-cash replay. Every position retains a fixed contract ID., historical_signals(), Causal portfolio-rule replay with the same seven-day warmup as the live scanner., add_features(), adx(), atr(), ema(), rsi() (+12 more)

### Community 32 - "session_state"
Cohesion: 0.43
Nodes (5): calendar_info(), Published NSE derivatives closures used as a shared portfolio entry gate. This…, session_state(), test_calendar_does_not_claim_unknown_year_or_complete_bse_coverage(), test_published_holiday_prevents_regular_entries()

### Community 33 - "Options Paper Lab"
Cohesion: 0.14
Nodes (12): Operation and audit, Paper strategy portfolio v1, Shared selector and protection, Strategies, Agent learning: what exists and what is not proved, Automatic operation and credential refresh, Historical backtests: data, calculation and limitations, Options Paper Lab (+4 more)

### Community 34 - "test_runtime.py"
Cohesion: 0.20
Nodes (16): BaseSettings, model_validator, Settings, plan_account(), signal(), test_plan_daily_reset_preserves_weekly_pause_and_previous_day_result(), test_empty_history_is_not_retained_forever(), test_retained_history_reuses_sqlite_without_provider_call() (+8 more)

### Community 35 - "local_time"
Cohesion: 0.18
Nodes (11): execution_health(), Worker liveness is independent of market-data availability and strategy edge., local_time(), Broker, parametrize, Isolated lifecycle evidence; fake accounts never reach the live broker., running(), test_alive_thread_with_old_cycle_is_stale() (+3 more)

### Community 36 - "QuoteRecorder"
Cohesion: 0.18
Nodes (5): Path, QuoteRecorder, test_failed_writer_stops_accepting_observations(), test_queue_overflow_and_storage_limit_are_not_silent(), test_quote_round_trip_is_durable_and_does_not_record_credentials()

### Community 37 - "PaperEngine"
Cohesion: 0.19
Nodes (4): ExpectancyEngine, Broker-sourced charges and empirical expectancy; no invented fee percentages., Observed NET outcomes; fees are already included and never deducted twice.…, PaperEngine

### Community 38 - "assess_specialists"
Cohesion: 0.33
Nodes (10): _age_seconds(), assess_specialists(), _finite(), Any, Deterministic specialist-agent evidence for a paper candidate. These are…, Assess specialist evidence for one candidate without placing an order., base_contract(), base_signal() (+2 more)

### Community 39 - "Backtest and learning checkpoint — September 14, 2026"
Cohesion: 0.17
Nodes (11): ATM±6 archive extension activated and completed, Backtest and learning checkpoint — September 14, 2026, Forward-comparison integrity and UI, Individual-agent audit and regime selection, Live decision workflow canvas, Runtime-contract defaults aligned — September 15, 2026, Subsequent learning-validation hardening, UI interaction and five-year cache run — September 15, 2026 (+3 more)

### Community 40 - "Trading Bot — Full Project Logic (Verified from Source)"
Cohesion: 0.17
Nodes (11): 10. BACKTEST RESULT (verified from DB only — no synthetic), 1. WHAT IT IS, 2. PROJECT STRUCTURE (verified), 3. DATA (verified from CSV reading), 4. BACKEND LOGIC (from main.py, ai.py, engine.py), 5. SELF-LEARNING RULES (from skill + code), 6. FEATURE SET (14 features, ai.py FEATURES tuple), 7. CURRENT STATE (verified from DB + endpoints + files) (+3 more)

### Community 41 - "DhanHQ API Documentation — Full Export"
Cohesion: 0.20
Nodes (9): Conditional and Multi Order, Data APIs, DhanHQ API, DhanHQ API Documentation — Full Export, Expired Options Data, Historical Data, Market Quote, Option Chain (+1 more)

### Community 42 - "graphify reference: extra exports and benchmark"
Cohesion: 0.22
Nodes (8): graphify reference: extra exports and benchmark, Step 6b - Wiki (only if --wiki flag), Step 7 - Neo4j export (only if --neo4j or --neo4j-push flag), Step 7a - FalkorDB export (only if --falkordb or --falkordb-push flag), Step 7b - SVG export (only if --svg flag), Step 7c - GraphML export (only if --graphml flag), Step 7d - MCP server (only if --mcp flag), Step 8 - Token reduction benchmark (only if total_words > 5000)

### Community 43 - "MLTradeQualityModel"
Cohesion: 0.25
Nodes (5): metrics(), MLTradeQualityModel, number(), One fixed model/threshold, purged 70/30 day split, optional FULL replay. A…, Regularized logistic probability estimate; portable JSON, no pickle loading.

### Community 44 - "replay_evidence"
Cohesion: 0.32
Nodes (11): replay_evidence(), test_legacy_synthetic_verified_report_cannot_train_or_promote(), test_profitable_research_or_missing_costs_cannot_pass_replay(), account(), check(), parametrize, Controlled validation inputs only; never persisted as trading evidence., test_different_observed_no_trade_coverage_is_rejected() (+3 more)

### Community 45 - "Binary Response"
Cohesion: 0.22
Nodes (9): 52-Week High/Low Packet, Binary Response, Circuit Limit Packet, Market Status Packet, Message Codes, OHLC Packet, Previous Close Packet, Response Header (+1 more)

### Community 46 - "Paper trading and research architecture contract"
Cohesion: 0.25
Nodes (7): Account and authority, Agent responsibilities, Data-to-decision path, Execution realism, Learning and promotion gates, Paper trading and research architecture contract, Session lifecycle

### Community 47 - "ExperimentStore"
Cohesion: 0.22
Nodes (3): ExperimentStore, All reference-account writes remain in an isolated namespace., test_reference_writes_are_isolated()

### Community 48 - "EventBus"
Cohesion: 0.32
Nodes (3): EventBus, Any, Small process-local event bus used by the dashboard WebSocket. The trading…

### Community 49 - "Order Management"
Cohesion: 0.25
Nodes (8): Cancel Order, Get Order Book, Get Order by Correlation ID, Get Order by ID, Modify Order, Order Management, Place Order, Slice Order (Large Quantities)

### Community 50 - "Installation"
Cohesion: 0.25
Nodes (8): ChatGPT, Claude Code, Claude Web, Codex, Cursor, Custom, Installation, OpenCode

### Community 51 - "Connect your client"
Cohesion: 0.25
Nodes (8): ChatGPT, Claude Code, Claude Web, Codex, Connect your client, Cursor, Custom, OpenCode

### Community 52 - "Paper engine remediation — updated 13 September 2026"
Cohesion: 0.25
Nodes (7): Changes implemented and checked, Durable observation recording — September 13, Operating constraints verified from the running service, Paper engine remediation — updated 13 September 2026, September 13 implementation update, Verification and current evidence, Work still required

### Community 53 - "paper_performance.py"
Cohesion: 0.38
Nodes (4): Get current agent status for dashboard., Closed-position attribution; counts are not causal proof of learning., summarize_paper_episodes(), test_closed_net_outcomes_are_attributed_without_counting_partial_fills_or_backtests()

### Community 54 - "Deploy Your First Strategy"
Cohesion: 0.29
Nodes (7): Deploy Your First Strategy, Step 1 — Create a new strategy, Step 2 — Write the strategy, Step 3 — Set your credentials in Variables, Step 4 — Add the SDK to Dependencies, Step 5 — Select a compute tier, Step 6 — Save and deploy

### Community 55 - "Learning evidence monitor"
Cohesion: 0.29
Nodes (6): AI reviewer, Current risk requirements, Learning evidence monitor, Overfitting controls, Run and verify, What the monitor establishes

### Community 56 - "graphify reference: query, path, explain"
Cohesion: 0.33
Nodes (5): For /graphify explain, For /graphify path, graphify reference: query, path, explain, Step 0 — Constrained query expansion (REQUIRED before traversal), Step 1 — Traversal

### Community 57 - "Paper learning and adaptive exits"
Cohesion: 0.33
Nodes (5): Adaptive exits, Entry-quality learning, Historical data learning and net cost verification (Updated), Paper learning and adaptive exits, Storage and scope

### Community 58 - "Market Data"
Cohesion: 0.33
Nodes (6): Binary Response, Full Packet, Market Data, Quote Packet, Response Header, Ticker Packet

### Community 59 - "Modify Order"
Cohesion: 0.33
Nodes (6): Example Request, Modify Order, Path Parameters, Request Body Parameters, Response Fields, Status Codes

### Community 60 - "Modify Conditional Order"
Cohesion: 0.33
Nodes (6): Example Request, Modify Conditional Order, Path Parameters, Request Body Parameters, Response Fields, Status Codes

### Community 61 - "Modify Order"
Cohesion: 0.33
Nodes (6): Example Request, Modify Order, Path Parameters, Request Body Parameters, Response Fields, Status Codes

### Community 62 - "Modify Super Order"
Cohesion: 0.33
Nodes (6): Example Request, Modify Super Order, Path Parameters, Request Body Parameters, Response Fields, Status Codes

### Community 63 - "datetime"
Cohesion: 0.10
Nodes (13): datetime, adapt_index_csv(), Backtest adapter: reads 5yr index CSV and creates option_quotes from DB…, Read NIFTY/SENSEX 5yr CSV, verify format, return underlying frame. Returns…, CircuitBreaker, Local paper API supervisor, started before the session by Windows Task…, account(), fixture (+5 more)

### Community 64 - "Backtest and dashboard audit — 13 September 2026"
Cohesion: 0.40
Nodes (4): Backtest and dashboard audit — 13 September 2026, Remaining evidence limits, Running-system verification, Verified defects and corrections

### Community 65 - "Response Structure"
Cohesion: 0.40
Nodes (5): 200 Level, 20 Level, Response Header, Response Header, Response Structure

### Community 66 - "Authentication APIs"
Cohesion: 0.40
Nodes (5): Access Token, API Key & Secret, Authentication APIs, Partners, Setup Static IP

### Community 67 - "Version 2.0"
Cohesion: 0.40
Nodes (5): Breaking Changes, Bug Fixes, Improvements, New Features, Version 2.0

### Community 68 - "Calculate Margin"
Cohesion: 0.40
Nodes (5): Calculate Margin, Example Request, Request Body Parameters, Response Fields, Status Codes

### Community 69 - "Calculate Multi-Order Margin"
Cohesion: 0.40
Nodes (5): Calculate Multi-Order Margin, Example Request, Request Body Parameters, Response Fields, Status Codes

### Community 70 - "Cancel Order"
Cohesion: 0.40
Nodes (5): Cancel Order, Example Request, Path Parameters, Response Fields, Status Codes

### Community 71 - "Cancel Order"
Cohesion: 0.40
Nodes (5): Cancel Order, Example Request, Path Parameters, Response Fields, Status Codes

### Community 72 - "Cancel Super Order Leg"
Cohesion: 0.40
Nodes (5): Cancel Super Order Leg, Example Request, Path Parameters, Response Fields, Status Codes

### Community 73 - "Conditional and Multi Order"
Cohesion: 0.40
Nodes (5): Comparison Type, Conditional and Multi Order, Indicator Name, Operator, Status

### Community 74 - "Consume Consent"
Cohesion: 0.40
Nodes (5): Consume Consent, Example Request, Header Parameters, Query Parameters, Response Fields

### Community 75 - "Consume Consent"
Cohesion: 0.40
Nodes (5): Consume Consent, Example Request, Header Parameters, Query Parameters, Response Fields

### Community 76 - "Portfolio"
Cohesion: 0.40
Nodes (5): Convert Position, Exit All Positions, Get Holdings, Get Positions, Portfolio

### Community 77 - "Delete Conditional Order"
Cohesion: 0.40
Nodes (5): Delete Conditional Order, Example Request, Path Parameters, Response Fields, Status Codes

### Community 78 - "EDIS Status Inquiry"
Cohesion: 0.40
Nodes (5): EDIS Status Inquiry, Example Request, Path Parameters, Response Fields, Status Codes

### Community 79 - "Get Intraday Historical Data"
Cohesion: 0.40
Nodes (5): Example Request, Get Intraday Historical Data, Request Body Parameters, Response Fields, Status Codes

### Community 80 - "Ledger Report"
Cohesion: 0.40
Nodes (5): Example Request, Ledger Report, Query Parameters, Response Fields, Status Codes

### Community 81 - "Get Order by Correlation ID"
Cohesion: 0.40
Nodes (5): Example Request, Get Order by Correlation ID, Path Parameters, Response Fields, Status Codes

### Community 82 - "Get Order by ID"
Cohesion: 0.40
Nodes (5): Example Request, Get Order by ID, Path Parameters, Response Fields, Status Codes

### Community 83 - "Trade History"
Cohesion: 0.40
Nodes (5): Example Request, Path Parameters, Response Fields, Status Codes, Trade History

### Community 84 - "Get Trades for Order"
Cohesion: 0.40
Nodes (5): Example Request, Get Trades for Order, Path Parameters, Response Fields, Status Codes

### Community 85 - "Get Order by ID"
Cohesion: 0.40
Nodes (5): Example Request, Get Order by ID, Path Parameters, Response Fields, Status Codes

### Community 86 - "Get Past Trades by Security Id"
Cohesion: 0.40
Nodes (5): Example Request, Get Past Trades by Security Id, Path Parameters, Response Fields, Status Codes

### Community 87 - "Margin Calculator"
Cohesion: 0.40
Nodes (5): Example Request, Margin Calculator, Request Body Parameters, Response Fields, Status Codes

### Community 88 - "Order Estimator"
Cohesion: 0.40
Nodes (5): Example Request, Order Estimator, Request Body Parameters, Response Fields, Status Codes

### Community 89 - "Place Order"
Cohesion: 0.40
Nodes (5): Example Request, Place Order, Request Body Parameters, Response Fields, Status Codes

### Community 90 - "Manage Kill Switch"
Cohesion: 0.40
Nodes (5): Example Request, Manage Kill Switch, Query Parameters, Response Fields, Status Codes

### Community 91 - "Place Order"
Cohesion: 0.40
Nodes (5): Example Request, Place Order, Request Body Parameters, Response Fields, Status Codes

### Community 92 - "Place Super Order"
Cohesion: 0.40
Nodes (5): Example Request, Place Super Order, Request Body Parameters, Response Fields, Status Codes

### Community 93 - "Slice Order"
Cohesion: 0.40
Nodes (5): Example Request, Request Body Parameters, Response Fields, Slice Order, Status Codes

### Community 94 - "Generate Consent"
Cohesion: 0.40
Nodes (5): Example Request, Generate Consent, Header Parameters, Query Parameters, Response Fields

### Community 95 - "Generate eDIS Form"
Cohesion: 0.40
Nodes (5): Example Request, Generate eDIS Form, Request Body Parameters, Response Fields, Status Codes

### Community 96 - "Get Daily Historical Data"
Cohesion: 0.40
Nodes (5): Example Request, Get Daily Historical Data, Request Body Parameters, Response Fields, Status Codes

### Community 97 - "Historical Rolling Options Data"
Cohesion: 0.40
Nodes (5): Example Request, Historical Rolling Options Data, Request Body Parameters, Response Fields, Status Codes

### Community 98 - "Get Expiry List"
Cohesion: 0.40
Nodes (5): Example Request, Get Expiry List, Request Body Parameters, Response Fields, Status Codes

### Community 99 - "graphify reference: add a URL and watch a folder"
Cohesion: 0.50
Nodes (3): For /graphify add, For --watch, graphify reference: add a URL and watch a folder

### Community 100 - "graphify reference: commit hook and native CLAUDE.md integration"
Cohesion: 0.50
Nodes (3): For git commit hook, For native CLAUDE.md integration, graphify reference: commit hook and native CLAUDE.md integration

### Community 101 - "graphify reference: incremental update and cluster-only"
Cohesion: 0.50
Nodes (3): For --cluster-only, For --update (incremental re-extraction), graphify reference: incremental update and cluster-only

### Community 102 - "dependencies"
Cohesion: 0.50
Nodes (3): omniroute, dependencies, omniroute

### Community 103 - "config.py"
Cohesion: 0.31
Nodes (7): download_index_candles(), main(), Download raw 5-year historical market data from Dhan directly into local…, Download continuous minute candles from Dhan in chunks with permanent SQLite…, current_credentials(), The project's .env is authoritative over inherited, possibly stale credentials., test_env_rotation_overrides_inherited_old_value()

### Community 107 - "Access for Individual Traders"
Cohesion: 0.50
Nodes (4): Access for Individual Traders, Access Token, API Key & Secret, Step 2: Browser Based Login

### Community 108 - "Access Token Setup"
Cohesion: 0.50
Nodes (4): Access Token Setup, Step 1: Generate Your Access Token, Step 2: Configure the Token for Your Agent, Step 3: Verify the Configuration

### Community 109 - "Supported Agents"
Cohesion: 0.50
Nodes (4): Any SKILL.md-Supporting Agent, Claude Code, Codex, Supported Agents

### Community 110 - "Version 2.2"
Cohesion: 0.50
Nodes (4): Breaking Changes, Improvements, New Features, Version 2.2

### Community 111 - "Super Order"
Cohesion: 0.50
Nodes (4): Cancel Super Order Leg, Modify Super Order, Place Super Order, Super Order

### Community 112 - "Common Error Scenarios"
Cohesion: 0.50
Nodes (4): Common Error Scenarios, Expired Token, Invalid Security ID, Rate Limit Exceeded

### Community 113 - "Configure P&L Based Exit"
Cohesion: 0.50
Nodes (4): Configure P&L Based Exit, Example Request, Request Body Parameters, Status Codes

### Community 114 - "Connect Your Dhan Account"
Cohesion: 0.50
Nodes (4): Connect Your Dhan Account, Credentials you will need, Step 1 — Sign in to the Developer Portal, Step 2 — Connect your Dhan account

### Community 115 - "Convert Position"
Cohesion: 0.50
Nodes (4): Convert Position, Example Request, Request Body Parameters, Status Codes

### Community 116 - "EDIS Status & Inquiry"
Cohesion: 0.50
Nodes (4): EDIS Status & Inquiry, Response Fields, Response Fields, Response Fields

### Community 117 - "Lot Size Validation"
Cohesion: 0.50
Nodes (4): Example, Lot Size Validation, Supported Segments, What Gets Validated

### Community 118 - "Kill Switch Status"
Cohesion: 0.50
Nodes (4): Example Request, Kill Switch Status, Response Fields, Status Codes

### Community 119 - "Get LTP"
Cohesion: 0.50
Nodes (4): Example Request, Get LTP, Request Body Parameters, Status Codes

### Community 120 - "Get OHLC"
Cohesion: 0.50
Nodes (4): Example Request, Get OHLC, Request Body Parameters, Status Codes

### Community 121 - "Get Option Chain"
Cohesion: 0.50
Nodes (4): Example Request, Get Option Chain, Request Body Parameters, Status Codes

### Community 122 - "Get Order Book"
Cohesion: 0.50
Nodes (4): Example Request, Get Order Book, Response Fields, Status Codes

### Community 123 - "Get Positions"
Cohesion: 0.50
Nodes (4): Example Request, Get Positions, Response Fields, Status Codes

### Community 124 - "Get Full Quote"
Cohesion: 0.50
Nodes (4): Example Request, Get Full Quote, Request Body Parameters, Status Codes

### Community 125 - "Get Super Orders"
Cohesion: 0.50
Nodes (4): Example Request, Get Super Orders, Response Fields, Status Codes

### Community 126 - "Get Trade Book"
Cohesion: 0.50
Nodes (4): Example Request, Get Trade Book, Response Fields, Status Codes

### Community 127 - "Get Fund Limit"
Cohesion: 0.50
Nodes (4): Example Request, Get Fund Limit, Response Fields, Status Codes

### Community 128 - "Get Holdings"
Cohesion: 0.50
Nodes (4): Example Request, Get Holdings, Response Fields, Status Codes

### Community 129 - "Get Market Status"
Cohesion: 0.50
Nodes (4): Example Request, Get Market Status, Response Fields, Status Codes

### Community 130 - "Get Order Book"
Cohesion: 0.50
Nodes (4): Example Request, Get Order Book, Response Fields, Status Codes

### Community 131 - "Get Past Trades"
Cohesion: 0.50
Nodes (4): Example Request, Get Past Trades, Response Fields, Status Codes

### Community 132 - "Place Conditional Order"
Cohesion: 0.50
Nodes (4): Example Request, Place Conditional Order, Request Body Parameters, Status Codes

### Community 133 - "Place Multi Order"
Cohesion: 0.50
Nodes (4): Example Request, Place Multi Order, Request Body Parameters, Status Codes

### Community 134 - "Generate Token"
Cohesion: 0.50
Nodes (4): Example Request, Generate Token, Query Parameters, Response Fields

### Community 135 - "Modify IP"
Cohesion: 0.50
Nodes (4): Example Request, Modify IP, Request Body Parameters, Response Fields

### Community 136 - "Generate Consent"
Cohesion: 0.50
Nodes (4): Example Request, Generate Consent, Header Parameters, Response Fields

### Community 137 - "Renew Token"
Cohesion: 0.50
Nodes (4): Example Request, Header Parameters, Renew Token, Response Fields

### Community 138 - "Set IP"
Cohesion: 0.50
Nodes (4): Example Request, Request Body Parameters, Response Fields, Set IP

### Community 139 - "Generate T-PIN"
Cohesion: 0.50
Nodes (4): Example Request, Generate T-PIN, Response Fields, Status Codes

### Community 140 - "Get Conditional Order by ID"
Cohesion: 0.50
Nodes (4): Example Request, Get Conditional Order by ID, Path Parameters, Status Codes

### Community 141 - "Get Fund Limits"
Cohesion: 0.50
Nodes (4): Example Request, Get Fund Limits, Response Fields, Status Codes

### Community 142 - "Get Holdings"
Cohesion: 0.50
Nodes (4): Example Request, Get Holdings, Response Fields, Status Codes

### Community 143 - "Example Workflows"
Cohesion: 0.50
Nodes (4): Example Workflows, Monitor and Exit a Position, Options Strategy Execution, Place an Order with Pre-checks

### Community 144 - "Supported Values"
Cohesion: 0.50
Nodes (4): Exchange Segments, Order Types, Product Types, Supported Values

### Community 145 - "Funds"
Cohesion: 0.50
Nodes (4): Funds, Get Fund Limits, Margin Calculator, Multi-Order Margin Calculator

### Community 146 - "Market Data"
Cohesion: 0.50
Nodes (4): Get Full Quote (with Market Depth), Get LTP, Get OHLC, Market Data

### Community 147 - "Order Update"
Cohesion: 0.50
Nodes (4): Order Update, Response Fields, Response Fields, Response Fields

### Community 153 - "Establishing Connection"
Cohesion: 0.67
Nodes (3): 200 Level, 20 Level, Establishing Connection

### Community 154 - "Adding Instruments"
Cohesion: 0.67
Nodes (3): 200 Level, 20 Level, Adding Instruments

### Community 155 - "API Structure"
Cohesion: 0.67
Nodes (3): API Structure, Base URLs, Request Headers

### Community 156 - "Handling Rate Limits"
Cohesion: 0.67
Nodes (3): Best Practices, Handling Rate Limits, Python Example with Rate Limiting

### Community 157 - "Version 2.4"
Cohesion: 0.67
Nodes (3): Breaking Changes, New Features, Version 2.4

### Community 158 - "Install"
Cohesion: 0.67
Nodes (3): Claude Code or Codex (zero-install), Global install, Install

### Community 159 - "Indian Stocks"
Cohesion: 0.67
Nodes (3): Column Description, Indian Stocks, Segmentwise List

### Community 160 - "Historical Data"
Cohesion: 0.67
Nodes (3): Daily Data, Historical Data, Intraday Data

### Community 161 - "Request Messages"
Cohesion: 0.67
Nodes (3): Disconnect, Request Messages, Subscribe or Unsubscribe

### Community 162 - "Establishing Connection"
Cohesion: 0.67
Nodes (3): Establishing Connection, For Individual, For Partners

### Community 163 - "Order Confirmation"
Cohesion: 0.67
Nodes (3): Example Flow, Order Confirmation, What Gets Confirmed

### Community 164 - "Get P&L Based Exit"
Cohesion: 0.67
Nodes (3): Example Request, Get P&L Based Exit, Status Codes

### Community 165 - "Stop P&L Based Exit"
Cohesion: 0.67
Nodes (3): Example Request, Status Codes, Stop P&L Based Exit

### Community 166 - "Get IP"
Cohesion: 0.67
Nodes (3): Example Request, Get IP, Response Fields

### Community 167 - "Exit All Positions"
Cohesion: 0.67
Nodes (3): Example Request, Exit All Positions, Status Codes

### Community 168 - "Get All Conditional Orders"
Cohesion: 0.67
Nodes (3): Example Request, Get All Conditional Orders, Status Codes

### Community 169 - "Feed Disconnect"
Cohesion: 0.67
Nodes (3): Feed Disconnect, Response Fields, Response Fields

### Community 170 - "Option Chain"
Cohesion: 0.67
Nodes (3): Get Expiry List, Get Option Chain, Option Chain

### Community 171 - "Get P&L Based Exit"
Cohesion: 0.67
Nodes (3): Get P&L Based Exit, Response Fields, Response Fields

### Community 172 - "Historical Rolling Data"
Cohesion: 0.67
Nodes (3): Historical Rolling Data, Response Fields, Response Fields

### Community 173 - "LIMIT Order Defaults"
Cohesion: 0.67
Nodes (3): How It Works, LIMIT Order Defaults, Why LIMIT by Default

### Community 174 - "Setup TOTP"
Cohesion: 0.67
Nodes (3): How to Set Up TOTP, Setup TOTP, What is TOTP?

### Community 175 - "Version 2.5"
Cohesion: 0.67
Nodes (3): Improvements, New Features, Version 2.5

### Community 176 - "Version 2.1"
Cohesion: 0.67
Nodes (3): Improvements, New Features, Version 2.1

### Community 177 - "Structure"
Cohesion: 0.67
Nodes (3): Python, REST, Structure

### Community 178 - "Trade History"
Cohesion: 0.67
Nodes (3): Response Fields, Response Fields, Trade History

## Knowledge Gaps
- **832 isolated node(s):** `name`, `private`, `version`, `type`, `dev` (+827 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Getting Started` connect `Getting Started` to `DhanHQ API Documentation — Full Export`, `Binary Response`, `Order Management`, `Deploy Your First Strategy`, `Market Data`, `Modify Order`, `Modify Conditional Order`, `Modify Order`, `Modify Super Order`, `Response Structure`, `Authentication APIs`, `Version 2.0`, `Cancel Order`, `Conditional and Multi Order`, `Consume Consent`, `Consume Consent`, `Portfolio`, `EDIS Status Inquiry`, `Get Intraday Historical Data`, `Ledger Report`, `Get Order by Correlation ID`, `Get Order by ID`, `Trade History`, `Get Trades for Order`, `Get Order by ID`, `Get Past Trades by Security Id`, `Margin Calculator`, `Order Estimator`, `Place Order`, `Manage Kill Switch`, `Place Order`, `Place Super Order`, `Slice Order`, `Generate Consent`, `Generate eDIS Form`, `Get Daily Historical Data`, `Historical Rolling Options Data`, `Get Expiry List`, `Access for Individual Traders`, `Access Token Setup`, `Supported Agents`, `Version 2.2`, `Super Order`, `Common Error Scenarios`, `Connect Your Dhan Account`, `EDIS Status & Inquiry`, `Lot Size Validation`, `Kill Switch Status`, `Get LTP`, `Get OHLC`, `Get Option Chain`, `Get Order Book`, `Get Positions`, `Get Full Quote`, `Get Super Orders`, `Get Trade Book`, `Get Fund Limit`, `Get Holdings`, `Get Market Status`, `Get Order Book`, `Get Past Trades`, `Place Conditional Order`, `Place Multi Order`, `Generate Token`, `Modify IP`, `Generate Consent`, `Renew Token`, `Set IP`, `Generate T-PIN`, `Get Conditional Order by ID`, `Get Fund Limits`, `Get Holdings`, `Example Workflows`, `Supported Values`, `Funds`, `Market Data`, `Order Update`, `Establishing Connection`, `Adding Instruments`, `API Structure`, `Handling Rate Limits`, `Version 2.4`, `Install`, `Indian Stocks`, `Historical Data`, `Request Messages`, `Establishing Connection`, `Order Confirmation`, `Get P&L Based Exit`, `Stop P&L Based Exit`, `Get IP`, `Exit All Positions`, `Get All Conditional Orders`, `Feed Disconnect`, `Option Chain`, `Get P&L Based Exit`, `Historical Rolling Data`, `LIMIT Order Defaults`, `Setup TOTP`, `Version 2.5`, `Version 2.1`, `Structure`, `Trade History`, `Global Stocks`, `Feed Disconnect`, `For Partners`, `Version 2.3`, `Setting Up Postback`?**
  _High betweenness centrality (0.181) - this node is a cross-community bridge._
- **Why does `Store` connect `Store` to `main.py`, `test_paper.py`, `local_time`, `test_runtime.py`, `test_jobs.py`, `config.py`, `AutonomousTradingAgent`, `test_reconstruction.py`, `now_ist`, `test_backtest.py`, `test_learning_monitor.py`, `ExperimentStore`, `LearningService`, `PlanRiskPolicy`, `audit_individual_agents`, `datetime`?**
  _High betweenness centrality (0.028) - this node is a cross-community bridge._
- **Why does `now_ist()` connect `now_ist` to `session_state`, `main.py`, `test_strategy_portfolio.py`, `QuoteRecorder`, `PaperEngine`, `local_time`, `config.py`, `AutonomousTradingAgent`, `ForwardComparison`, `MLTradeQualityModel`, `test_backtest.py`, `test_learning_monitor.py`, `LearningService`, `paper_performance.py`, `DhanGateway`, `Store`, `PaperBroker`?**
  _High betweenness centrality (0.021) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `Store` (e.g. with `AutonomousTradingAgent` and `account()`) actually correct?**
  _`Store` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `datetime` (e.g. with `test_completed_stall_requires_contiguous_bars()` and `test_cost_covering_stop_and_restart_never_loosen()`) actually correct?**
  _`datetime` has 10 INFERRED edges - model-reasoned connections that need verification._
- **What connects `name`, `private`, `version` to the rest of the system?**
  _832 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Getting Started` be split into smaller, more focused modules?**
  _Cohesion score 0.00816326530612245 - nodes in this community are weakly interconnected._