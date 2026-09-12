# Self-Learning System Status

## Overview
The trading bot is equipped with a self-learning system that can:
- Train machine learning models on historical trade data
- Generate and test research hypotheses via LLM analysis
- Dynamically evaluate market conditions
- Adapt entry/exit decisions based on learned probabilities

## Data Status
- **NIFTY 5-year 1-min data**: Present (39.3 MB) - E:\trading_bot_full\Trading Bot\data\NIFTY_5yr_1min.csv
- **SENSEX 5-year 1-min data**: Present (38.9 MB) - E:\trading_bot_full\Trading Bot\data\SENSEX_5yr_1min.csv

## Backend Services
- **Paper Trading Engine**: MultiStrategyPaperEngine active with ORB retest strategy
- **Backtest Engine**: ORB retest with contract-specific candles and structural protection
- **ML Learning System**: LearningService with regularized Logistic Regression
- **LLM Integration**: OpenRouter configured (nvidia/nemotron-3-ultra-550b-a55b:free)
- **Risk Management**: PlanRiskPolicy with position limits, daily loss halts, and cooldowns

## Learning Configuration
- **Minimum training trades**: 60 trades
- **Minimum context trades**: 20 trades
- **Minimum validation trades**: 30 trades
- **Minimum validation days**: 10 days
- **70/30 day split** for train/test validation
- **Holdout validation**: No repeated tuning on same holdout sessions

### Feature Set (14 features)
1. adx - Average Directional Index (trend strength)
2. atr_pct - ATR as percentage of close
3. vwap_dist_atr - VWAP distance in ATR units
4. relative_volume - Volume relative to average
5. ema_slope_atr - EMA slope in ATR units
6. session_minute - Minutes from session start (adjusted -555)
7. option_delta - Option delta value
8. spread_pct - Spread as percentage
9. rsi - Relative Strength Index
10. stop_pct - Stop loss as percentage
11. option_atr_pct - Option ATR as percentage of price
12. is_put - Whether option is PUT (1) or CALL (0)
13. (implicit) regime assessment from LLM
14. (implicit) market conditions from LLM analysis

## API Endpoints
| Endpoint | Method | Description |
|---|---|---|
| `/api/learning/train` | POST | Trigger model training with latest report |
| `/api/learning/model` | GET | Get current model status and artifacts |
| `/api/learning` | GET | Full learning snapshot (runs, candidates, policies) |
| `/api/llm/analyze/market` | POST | LLM market regime analysis |
| `/api/llm/generate/hypotheses` | POST | Generate research hypotheses from analysis |

## Current Model Status
- **Model**: Not yet trained (requires minimum 60 verified trades)
- **Status**: Awaiting training data accumulation
- **Next training**: Will trigger after 60+ completed trades with entry features

## LLM-Enhanced Capabilities
The system can now:
- **Analyze market regime**: trending_up/trending_down/ranging/volatile/transitioning
- **Generate research hypotheses**: testable statements with proposed backtest configs
- **Analyze failures**: identify recurring loss patterns by regime
- **Analyze individual trades**: thesis validation and exit quality assessment

## Self-Learning Workflow
1. **Data Collection**: Trades executed with entry features recorded
2. **Model Training**: `POST /api/learning/train` when 60+ verified trades exist
3. **Holdout Validation**: 70/30 day split, requires 30 test trades minimum
4. **Full Replay**: Optional account replay before promotion
5. **Promotion**: Validated models effective next session, expire after 30 days
6. **Scoring**: `GET /api/learning/model` returns probability for entry decisions

## Dynamic Market Evaluation
When trained, the system can:
- **Assess current regime**: LLM analyzes market snapshot (spot, regime, option chain)
- **Generate hypotheses**: New strategies proposed based on failure patterns
- **Score entries**: Model predicts probability of positive net PnL
- **Adaptive exits**: Model-informed exit decisions based on predicted probabilities

## Next Steps for Full Self-Learning
1. Allow trade execution to accumulate 60+ verified trades
2. Trigger training via `POST /api/learning/train`
3. Review model validation results via `GET /api/learning/model`
4. If validated, models will be effective from next session (auto-expires after 30 days)
5. LLM can generate new hypotheses when model evidence is insufficient
6. System dynamically adjusts entry/exit based on learned probabilities

## Configuration (.env)
Key parameters for learning behavior:
- `PAPER_COLLECT_EVIDENCE=true` - enables evidence collection below threshold
- `LEARNING_MIN_TRADES=60` - minimum trades for training
- `LLM_ENABLED=true` - LLM integration active
- `OPENROUTER_API_KEY` - configured (starts with `***`)