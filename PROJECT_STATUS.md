# Trading bot source snapshot

This repository contains the current NIFTY/SENSEX paper-trading implementation.
Start with [the application README](Trading%20Bot/README.md) and
[the strategy specification](Trading%20Bot/MULTI_STRATEGY_PAPER.md).

## Status at 9 September 2026

- Three rule-based paper strategies are implemented: opening-range retest,
  trend pullback and range rejection, with a shared selector and risk manager.
- Real-money order authority is disabled. Strategies remain unvalidated paper
  observations, with no guarantee of daily profit.
- Thorough individual-strategy backtests and the requested learning integration
  are unfinished. Existing historical reports cover the earlier ORB baseline.
- A small shared-rule refactor is present; it does not complete the individual
  strategy replay integration.
- The local service was stopped following database/storage I/O errors. A source
  upload does not verify database recovery or readiness to resume trading.
- Credentials, account databases, market-data downloads, recovery copies,
  installed dependencies and generated builds are excluded from version control.

Follow the persistent operating requirements in AGENTS.md. Supply credentials
locally in `Trading Bot/.env`; never commit that file.
