# Graph Report - trading_bot_full  (2026-09-25)

## Corpus Check
- 126 files · ~150,668 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 14 file(s) not represented in the graph (top: .csv 4, .bat 4, (none) 3)

## Summary
- 2123 nodes · 3868 edges · 209 communities (181 shown, 18 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 131 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `a7ace7d4`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Getting Started
- test_paper.py
- ._run
- test_reconstruction.py
- DecisionPipeline
- test_backtest.py
- Allowed and Restricted Operations
- test_strategy_portfolio.py
- AutonomousTradingAgent
- ForwardComparison
- jobs.py
- Dhan MCP Architecture Flow
- main.py
- What You Must Do When Invoked
- DhanMarketData
- local_time
- test_jobs.py
- DhanGateway
- historical_gateway
- main.tsx
- test_learning_monitor.py
- strategy_portfolio.py
- Store
- LearningService
- frontend/package.json
- audit_individual_agents
- QuoteRecorder
- BacktestEngine
- LLMClient
- observed_session.py
- test_atm6_extension_preserves_fields_and_near_bucket
- Self-Learning System Status
- now_ist
- resolve_backtest_budgets
- PaperEngine
- Options Paper Lab
- Caveman
- TradingWorkspace.tsx
- Ponytail
- assess_specialists
- Backtest and learning checkpoint — September 14, 2026
- Trading Bot — Full Project Logic (Verified from Source)
- PaperBroker
- compilerOptions
- DhanHQ API Documentation — Full Export
- graphify reference: extra exports and benchmark
- ai.py
- test_coordinator_watchdog_restarts_dead_workers_without_order_authority
- test_archive_request_matrix_uses_persisted_scope
- Binary Response
- Behavioral Guidelines
- Paper trading and research architecture contract
- summarize_paper_episodes
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
- test_runtime.py
- test_empty_history_is_not_retained_forever
- Market Data
- Modify Order
- Modify Conditional Order
- Modify Order
- Modify Super Order
- dependencies
- datetime
- Exact-contract backtest evidence — 21 September 2026
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
- test_retained_history_reuses_sqlite_without_provider_call
- TelegramNotifier
- portfolio_engine.py
- plan_account
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
- test_learning_validation.py
- Trading bot source snapshot
- ExperimentStore
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
- DhanBroker
- CostModel

## God Nodes (most connected - your core abstractions)
1. `Getting Started` - 352 edges
2. `Store` - 83 edges
3. `now_ist()` - 71 edges
4. `LearningService` - 40 edges
5. `PaperEngine` - 39 edges
6. `Allowed and Restricted Operations` - 39 edges
7. `Settings` - 36 edges
8. `local_time()` - 35 edges
9. `session_state()` - 34 edges
10. `DhanGateway` - 32 edges

## Surprising Connections (you probably didn't know these)
- `test_coordinator_has_no_independent_order_authority()` --uses--> `AutonomousTradingAgent`  [INFERRED]
  Trading Bot/backend/tests/test_execution_integrity.py → Trading Bot/backend/app/autonomous_agent.py
- `lifespan()` --uses--> `MultiStrategyPaperEngine`  [INFERRED]
  Trading Bot/backend/app/main.py → Trading Bot/backend/app/portfolio_engine.py
- `training_gate_results()` --uses--> `CostModel`  [INFERRED]
  Trading Bot/backend/app/ai.py → Trading Bot/backend/app/expectancy.py
- `BacktestEngine` --uses--> `MLTradeQualityModel`  [INFERRED]
  Trading Bot/backend/app/backtest/engine.py → Trading Bot/backend/app/ai.py
- `test_failed_fit_still_consumes_holdout()` --uses--> `MLTradeQualityModel`  [INFERRED]
  Trading Bot/backend/tests/test_learning_monitor.py → Trading Bot/backend/app/ai.py

## Import Cycles
- None detected.

## Communities (209 total, 18 thin omitted)

### Community 0 - "Getting Started"
Cohesion: 0.01
Nodes (245): 1. Create an Account, 2. Generate API Credentials, 3. Install the SDK, 4. Initialize the Client, 5. Place Your First Order, A Few Things to Know, Adding Credits, Adding Instruments (+237 more)

### Community 1 - "test_paper.py"
Cohesion: 0.23
Nodes (21): exchange_timestamp(), account(), contract(), enter(), fixture, quote(), Isolated accounting fixtures; none are loaded by the runtime or dashboard., test_account_persists_and_partial_exits_reconcile() (+13 more)

### Community 2 - "._run"
Cohesion: 0.24
Nodes (9): BacktestJobs, before_commit(), cancelled(), ml_replay(), progress(), replay(), download_history(), Archive source observations only; never run a strategy or update learning. (+1 more)

### Community 3 - "test_reconstruction.py"
Cohesion: 0.06
Nodes (41): estimate_gap_exit(), Exploratory missing-price liquidation; never an observed candle or live fill., Use only the preceding minute, then liquidate instead of inventing a path., merge_series(), Quarantine conflicting duplicate candles permanently, independent of fetch…, ResearchReplay, _agent_trades(), _learn_from_outcomes() (+33 more)

### Community 4 - "DecisionPipeline"
Cohesion: 0.06
Nodes (38): Enum, str, Decision, Direction, ExpectancyResult, FeatureSnapshot, OptionContract, BaseModel (+30 more)

### Community 5 - "test_backtest.py"
Cohesion: 0.12
Nodes (19): learn_from_outcomes(), plan_agent_capabilities(), Every outcome is logged. Promotion requires fresh, full chronological replays., once_per_session(), fixture, test_cancel_before_learning_commit_leaves_no_policy_or_ledger(), test_every_backtest_run_records_learning_for_every_agent(), test_full_validation_promotes_at_most_one_and_records_both_windows() (+11 more)

### Community 6 - "Allowed and Restricted Operations"
Cohesion: 0.05
Nodes (37): Allowed, Allowed and Restricted Operations, Architecture, Blocked, Checking Fund Limits, Code Scanner, Common Flags and How to Fix Them, Compatible clients (+29 more)

### Community 7 - "test_strategy_portfolio.py"
Cohesion: 0.09
Nodes (33): MultiStrategyPaperEngine, evaluate_strategies(), rank_opportunities(), Rank only eligible offers; statistical support precedes observation economics.…, Return the current day's deterministic strategy preference order., regime_strategy_policy(), signal_for(), candidate() (+25 more)

### Community 8 - "AutonomousTradingAgent"
Cohesion: 0.08
Nodes (19): AgentState, AutonomousTradingAgent, Start the autonomous agent loop., Stop the autonomous agent., Keep coordinator workers alive without creating another execution authority., Main agent loop - runs every 2 seconds during market hours., Background learning loop - retrains models periodically., Pre-market preparation: load models, validate data, check risk limits. (+11 more)

### Community 9 - "ForwardComparison"
Cohesion: 0.13
Nodes (3): FixedLearning, ForwardComparison, ReferenceEngine

### Community 10 - "jobs.py"
Cohesion: 0.14
Nodes (17): main(), Source validation. Rolling moneyness must never masquerade as a fixed contract., Read one row per exact option contract/minute, with repeated underlying OHLCV., read_contract_csv(), _valid_bar(), Durable, single-worker backtests; browser lifetime never owns a running job., dhan_plan_research(), dhan_research() (+9 more)

### Community 11 - "Dhan MCP Architecture Flow"
Cohesion: 0.06
Nodes (31): 1. You, 2. MCP Client, 3. Tool Call to mcp.dhan.co, 4. Dhan MCP Server, 5. DEXT, 6. Exchange, Alerts, Dhan MCP Architecture Flow (+23 more)

### Community 12 - "main.py"
Cohesion: 0.05
Nodes (77): get, middleware, post, Request, dataset_metadata(), Header inspection is an eligibility hint, not verified historical coverage., history_row(), Read models for reports: retain audit data without presenting partial profit as… (+69 more)

### Community 13 - "What You Must Do When Invoked"
Cohesion: 0.08
Nodes (24): For /graphify add and --watch, For /graphify query, For the commit hook and native CLAUDE.md integration, For --update and --cluster-only, /graphify, Honesty Rules, Interpreter guard for subcommands, Part A - Structural extraction for code files (+16 more)

### Community 14 - "DhanMarketData"
Cohesion: 0.09
Nodes (10): Exception, DhanMarketData, Any, Return the underlying and its option books from one locked observation., Seed latest values from one broker quote call; live ticks replace them., Dhan MarketFeed adapter. No tick is manufactured when the feed is down., test_websocket_packets_are_bounded_and_do_not_write_database(), test_execution_snapshot_returns_underlying_and_options_atomically() (+2 more)

### Community 15 - "local_time"
Cohesion: 0.18
Nodes (12): Causal paper exit state. A stop is a request, never a guaranteed fill., Persistable state; only fresh observed bids may call this function. ATR must…, update_exit(), local_time(), Broker, parametrize, Isolated lifecycle evidence; fake accounts never reach the live broker., running() (+4 more)

### Community 16 - "test_jobs.py"
Cohesion: 0.21
Nodes (10): dataset_path(), Resolve a user-selected range without treating an explicit zero year as one…, resolve_backtest_start(), manager(), test_completed_report_survives_manager_restart(), test_dataset_path_cannot_escape_data_folder(), test_download_job_does_not_replace_reports_or_teach_agents(), test_interrupted_and_failed_jobs_are_not_spinners() (+2 more)

### Community 17 - "DhanGateway"
Cohesion: 0.19
Nodes (4): DhanGateway, One rate-limited, cached data adapter shared by paper and research., Reuse overlapping sourced responses; fetch only uncovered date intervals., test_expiry_day_is_skipped_for_paper_policy()

### Community 18 - "historical_gateway"
Cohesion: 0.32
Nodes (7): historical_gateway(), test_history_cache_does_not_hide_misaligned_fields(), test_history_reuses_overlaps_field_subsets_and_restart(), expired_options_data(), fetch(), test_local_history_only_stops_without_network_and_retains_empty_observations(), intraday_minute_data()

### Community 19 - "main.tsx"
Cohesion: 0.15
Nodes (17): active(), AgentLessons(), api(), App(), ArchiveManifest(), AuditDetails(), Chart(), Data (+9 more)

### Community 20 - "test_learning_monitor.py"
Cohesion: 0.10
Nodes (18): build_evidence(), evidence_fingerprint(), explain_evidence(), LearningMonitor, Evidence monitor. No order, training, parameter-edit or promotion tools., Read the authoritative file for EVERY call; never retain an expired key., Heartbeat counters are activity, not new learning or changed evidence quality., Isolated synthetic evidence tests, never performance evidence. (+10 more)

### Community 21 - "strategy_portfolio.py"
Cohesion: 0.22
Nodes (14): historical_signals(), Causal portfolio-rule replay with the same seven-day warmup as the live scanner., add_features(), adx(), atr(), ema(), rsi(), opening_range_retest() (+6 more)

### Community 23 - "LearningService"
Cohesion: 0.13
Nodes (21): LearningService, parametrize, Synthetic fixtures test mechanics, never trading performance evidence., test_incomplete_or_estimated_reports_do_not_fit_models(), test_net_cost_and_future_feature_exclusions(), test_promotion_waits_for_next_session_and_freezes_across_restart(), replay(), test_purged_holdout_not_reused_and_no_promotion_without_full_replay() (+13 more)

### Community 24 - "frontend/package.json"
Cohesion: 0.11
Nodes (17): react, react-dom, @types/react, @types/react-dom, typescript, vite, @vitejs/plugin-react, devDependencies (+9 more)

### Community 25 - "audit_individual_agents"
Cohesion: 0.23
Nodes (17): audit_individual_agents(), _day(), _finite(), _loss_investigation(), _matches_agent(), _model_rows(), _overfitting_gate(), Any (+9 more)

### Community 26 - "QuoteRecorder"
Cohesion: 0.11
Nodes (13): Path, audit_observation_db(), main(), Audit recorded option observations without overstating historical coverage., Return a bounded, reproducible audit of a QuoteRecorder SQLite database., QuoteRecorder, test_audit_rejects_non_recorder_database(), test_audit_reports_observations_without_claiming_replay_eligibility() (+5 more)

### Community 27 - "BacktestEngine"
Cohesion: 0.14
Nodes (22): BacktestConfig, BacktestEngine, PlanRiskPolicy, Plan v1 risk envelope. Values are frozen configuration, not learned parameters., historical_fixture(), Contract fixtures only for regression tests, never runtime market data., test_backtest_runs(), test_fixed_contract_drift_blocks_headline_pnl() (+14 more)

### Community 28 - "LLMClient"
Cohesion: 0.06
Nodes (20): AsyncClient, create_llm_client(), FailureAnalyst, get_analysts(), HypothesisGenerator, LLMClient, MarketAnalyst, Async OpenRouter client with retries, timeout, and structured output parsing. (+12 more)

### Community 29 - "observed_session.py"
Cohesion: 0.16
Nodes (24): candles(), download(), fee_scenario(), fetch(), inject_receipts(), isolated_replay_frame(), main(), prepare() (+16 more)

### Community 30 - "test_atm6_extension_preserves_fields_and_near_bucket"
Cohesion: 0.33
Nodes (3): archive_manifest(), Describe the retained source pass without claiming complete exchange coverage., test_atm6_extension_preserves_fields_and_near_bucket()

### Community 31 - "Self-Learning System Status"
Cohesion: 0.12
Nodes (15): API Endpoints, Backend Services, Configuration (.env), CORRECTED (2026-09-12), CORRECTED MULTI-STRATEGY UNDERSTANDING (2026-09-12), Current Model Status, Data Status, Dynamic Market Evaluation (+7 more)

### Community 32 - "now_ist"
Cohesion: 0.18
Nodes (11): One fixed model/threshold, purged 70/30 day split, optional FULL replay. A…, Prospective reference account. No real-order authority or additive profit…, calendar_info(), Published NSE derivatives closures used as a shared portfolio entry gate. This…, Bounded, asynchronous recording of normalized observations, never credentials., execution_health(), Worker liveness is independent of market-data availability and strategy edge., now_ist() (+3 more)

### Community 33 - "resolve_backtest_budgets"
Cohesion: 0.40
Nodes (4): resolve_backtest_budgets(), parametrize, test_backtest_budgets_are_not_capped_by_paper_settings(), test_invalid_backtest_budgets_remain_rejected()

### Community 34 - "PaperEngine"
Cohesion: 0.17
Nodes (3): ExpectancyEngine, Observed NET outcomes; fees are already included and never deducted twice.…, PaperEngine

### Community 35 - "Options Paper Lab"
Cohesion: 0.13
Nodes (13): Operation and audit, Paper strategy portfolio v1, Shared selector and protection, Strategies, Agent learning: what exists and what is not proved, Automatic operation and credential refresh, Historical backtests: data, calculation and limitations, Optional Telegram paper alerts (+5 more)

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

### Community 43 - "compilerOptions"
Cohesion: 0.18
Nodes (10): compilerOptions, jsx, lib, module, moduleResolution, noEmit, skipLibCheck, strict (+2 more)

### Community 44 - "DhanHQ API Documentation — Full Export"
Cohesion: 0.20
Nodes (9): Conditional and Multi Order, Data APIs, DhanHQ API, DhanHQ API Documentation — Full Export, Expired Options Data, Historical Data, Market Quote, Option Chain (+1 more)

### Community 45 - "graphify reference: extra exports and benchmark"
Cohesion: 0.22
Nodes (8): graphify reference: extra exports and benchmark, Step 6b - Wiki (only if --wiki flag), Step 7 - Neo4j export (only if --neo4j or --neo4j-push flag), Step 7a - FalkorDB export (only if --falkordb or --falkordb-push flag), Step 7b - SVG export (only if --svg flag), Step 7c - GraphML export (only if --graphml flag), Step 7d - MCP server (only if --mcp flag), Step 8 - Token reduction benchmark (only if total_words > 5000)

### Community 46 - "ai.py"
Cohesion: 0.12
Nodes (19): extract_features(), ratio(), metrics(), MLTradeQualityModel, number(), Entry-quality learning from causal, net-cost outcomes. No order authority., Regularized logistic probability estimate; portable JSON, no pickle loading., Caller supplies a completed causal row; missing volume/Greeks stay missing. (+11 more)

### Community 49 - "Binary Response"
Cohesion: 0.22
Nodes (9): 52-Week High/Low Packet, Binary Response, Circuit Limit Packet, Market Status Packet, Message Codes, OHLC Packet, Previous Close Packet, Response Header (+1 more)

### Community 50 - "Behavioral Guidelines"
Cohesion: 0.25
Nodes (7): 1. Think Before Coding, 2. Simplicity First, 3. Surgical Changes, 4. Goal-Driven Execution, Behavioral Guidelines, graphify, Persistent user requirements

### Community 51 - "Paper trading and research architecture contract"
Cohesion: 0.25
Nodes (7): Account and authority, Agent responsibilities, Data-to-decision path, Execution realism, Learning and promotion gates, Paper trading and research architecture contract, Session lifecycle

### Community 52 - "summarize_paper_episodes"
Cohesion: 0.28
Nodes (4): Get current agent status for dashboard., Closed-position attribution; counts are not causal proof of learning., summarize_paper_episodes(), test_closed_net_outcomes_are_attributed_without_counting_partial_fills_or_backtests()

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

### Community 63 - "test_runtime.py"
Cohesion: 0.13
Nodes (15): BaseSettings, model_validator, download_index_candles(), main(), Download raw 5-year historical market data from Dhan directly into local…, Download continuous minute candles from Dhan in chunks with permanent SQLite…, current_credentials(), The project's .env is authoritative over inherited, possibly stale credentials. (+7 more)

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

### Community 71 - "datetime"
Cohesion: 0.09
Nodes (17): datetime, adapt_index_csv(), Backtest adapter: reads 5yr index CSV and creates option_quotes from DB…, Read NIFTY/SENSEX 5yr CSV, verify format, return underlying frame. Returns…, CircuitBreaker, plan_exit(), Shared ordered exit policy; the execution adapter supplies only observed values., Local paper API supervisor, started before the session by Windows Task… (+9 more)

### Community 72 - "Exact-contract backtest evidence — 21 September 2026"
Cohesion: 0.15
Nodes (12): Data and execution evidence, Decision, Exact-contract backtest evidence — 21 September 2026, External fee references, Fixed controls, Learning status, Rejected coverage, Remaining evidence limits (+4 more)

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

### Community 114 - "TelegramNotifier"
Cohesion: 0.18
Nodes (3): Optional, non-blocking Telegram notifications for the paper account., TelegramNotifier, test_disabled_or_unconfigured_telegram_never_queues()

### Community 115 - "portfolio_engine.py"
Cohesion: 0.17
Nodes (12): get_autonomous_agent(), Paper research coordinator. Execution belongs exclusively to the portfolio…, Get or create the singleton autonomous agent., Three paper hypotheses, one selector, one atomic portfolio authority., event(), pipeline_from_events(), Any, Create one JSON-safe, auditable event for a real engine cycle. (+4 more)

### Community 117 - "plan_account"
Cohesion: 0.26
Nodes (14): parametrize, test_failed_persistence_restores_account_and_prevents_ghost_fill(), plan_account(), signal(), quote(), test_plan_daily_reset_preserves_weekly_pause_and_previous_day_result(), test_disabled_evidence_collection_cannot_start_with_zero_outcomes(), test_evidence_mode_does_not_override_negative_supported_edge() (+6 more)

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

### Community 161 - "test_learning_validation.py"
Cohesion: 0.47
Nodes (8): account(), check(), parametrize, Controlled validation inputs only; never persisted as trading evidence., test_different_observed_no_trade_coverage_is_rejected(), test_malformed_or_estimated_evidence_cannot_promote(), test_omitting_trade_days_from_both_account_calendars_is_rejected(), test_reconciled_accounts_include_observed_no_trade_sessions()

### Community 163 - "ExperimentStore"
Cohesion: 0.22
Nodes (3): ExperimentStore, All reference-account writes remain in an isolated namespace., test_reference_writes_are_isolated()

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

### Community 211 - "CostModel"
Cohesion: 0.11
Nodes (13): close_position(), broker_cost_receipts(), Observe exact Dhan calculator totals for one simulated round trip., close(), CostModel, Standard Dhan index option round-trip charges (₹40 brokerage + STT + turnover +…, Only a dated source schedule can price a historical order., execution_context() (+5 more)

## Knowledge Gaps
- **862 isolated node(s):** `name`, `private`, `version`, `type`, `dev` (+857 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1181 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **18 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Getting Started` connect `Getting Started` to `DhanHQ API Documentation — Full Export`, `Binary Response`, `Order Management`, `Deploy Your First Strategy`, `Market Data`, `Modify Order`, `Modify Conditional Order`, `Modify Order`, `Modify Super Order`, `Response Structure`, `Authentication APIs`, `Version 2.0`, `Cancel Order`, `Conditional and Multi Order`, `Consume Consent`, `Consume Consent`, `Portfolio`, `EDIS Status Inquiry`, `Get Intraday Historical Data`, `Ledger Report`, `Get Order by Correlation ID`, `Get Order by ID`, `Trade History`, `Get Trades for Order`, `Get Order by ID`, `Get Past Trades by Security Id`, `Margin Calculator`, `Order Estimator`, `Place Order`, `Manage Kill Switch`, `Place Order`, `Place Super Order`, `Slice Order`, `Generate Consent`, `Generate eDIS Form`, `Get Daily Historical Data`, `Historical Rolling Options Data`, `Get Expiry List`, `Access for Individual Traders`, `Access Token Setup`, `Supported Agents`, `Version 2.2`, `Super Order`, `Common Error Scenarios`, `Connect Your Dhan Account`, `EDIS Status & Inquiry`, `Lot Size Validation`, `Kill Switch Status`, `Get LTP`, `Get OHLC`, `Get Option Chain`, `Get Order Book`, `Get Positions`, `Get Full Quote`, `Get Super Orders`, `Get Trade Book`, `Get Fund Limit`, `Get Holdings`, `Get Market Status`, `Get Order Book`, `Get Past Trades`, `Place Conditional Order`, `Place Multi Order`, `Generate Token`, `Modify IP`, `Generate Consent`, `Renew Token`, `Set IP`, `Generate T-PIN`, `Get Conditional Order by ID`, `Get Fund Limits`, `Get Holdings`, `Example Workflows`, `Supported Values`, `Funds`, `Market Data`, `Order Update`, `Establishing Connection`, `Adding Instruments`, `API Structure`, `Handling Rate Limits`, `Version 2.4`, `Install`, `Indian Stocks`, `Historical Data`, `Request Messages`, `Establishing Connection`, `Order Confirmation`, `Get P&L Based Exit`, `Stop P&L Based Exit`, `Get IP`, `Exit All Positions`, `Get All Conditional Orders`, `Feed Disconnect`, `Option Chain`, `Get P&L Based Exit`, `Historical Rolling Data`, `LIMIT Order Defaults`, `Setup TOTP`, `Version 2.5`, `Version 2.1`, `Structure`, `Trade History`, `Global Stocks`, `Feed Disconnect`, `For Partners`, `Version 2.3`, `Setting Up Postback`?**
  _High betweenness centrality (0.120) - this node is a cross-community bridge._
- **Why does `Store` connect `Store` to `test_paper.py`, `test_reconstruction.py`, `test_backtest.py`, `AutonomousTradingAgent`, `jobs.py`, `main.py`, `local_time`, `test_jobs.py`, `historical_gateway`, `test_learning_monitor.py`, `LearningService`, `audit_individual_agents`, `observed_session.py`, `ExperimentStore`, `test_runtime.py`, `test_empty_history_is_not_retained_forever`, `test_retained_history_reuses_sqlite_without_provider_call`, `portfolio_engine.py`, `plan_account`?**
  _High betweenness centrality (0.027) - this node is a cross-community bridge._
- **Why does `now_ist()` connect `now_ist` to `test_reconstruction.py`, `test_backtest.py`, `test_strategy_portfolio.py`, `AutonomousTradingAgent`, `ForwardComparison`, `jobs.py`, `main.py`, `local_time`, `DhanGateway`, `test_learning_monitor.py`, `Store`, `LearningService`, `QuoteRecorder`, `PaperEngine`, `PaperBroker`, `ai.py`, `summarize_paper_episodes`, `test_runtime.py`, `portfolio_engine.py`?**
  _High betweenness centrality (0.020) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `Store` (e.g. with `AutonomousTradingAgent` and `test_incomplete_or_estimated_reports_do_not_fit_models()`) actually correct?**
  _`Store` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `datetime` (e.g. with `test_completed_stall_requires_contiguous_bars()` and `test_cost_covering_stop_and_restart_never_loosen()`) actually correct?**
  _`datetime` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `LearningService` (e.g. with `AutonomousTradingAgent` and `BacktestJobs`) actually correct?**
  _`LearningService` has 4 INFERRED edges - model-reasoned connections that need verification._
- **What connects `name`, `private`, `version` to the rest of the system?**
  _862 weakly-connected nodes found - possible documentation gaps or missing edges._