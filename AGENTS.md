# Persistent user requirements

- Dhan credentials in `Trading Bot/.env` are authoritative. Before diagnosing authentication or using trading data, check for updated credentials and ensure the running REST client and WebSocket have reloaded them. Never print secrets. Do not keep retrying an expired in-memory token when the file contains its replacement.
- Paper trading must start monitoring at 09:15 IST on market days and request session liquidation at 15:05 IST. Start the service before the session. Opening-range formation and existing entry/risk limits still apply. Never invent a fill to meet a closing deadline when quotes/liquidity are unavailable; show pending exits and keep managing them.
- Paper trading is authorized. Real-money order authority remains disabled. Evidence collection must be labelled unvalidated paper observation, never a proven edge.
- Verify the complete data-to-decision-to-paper-entry/exit path, including credential rotation, session boundaries, freshness, restart recovery and visible current agent status.
