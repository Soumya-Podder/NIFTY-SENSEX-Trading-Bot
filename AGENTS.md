# Persistent user requirements

- Daily paper profit goal is ₹1,000 or more, measured net of estimated charges. This is a target, never a guaranteed daily return.
- Daily paper loss limit and hard daily halt are ₹800. Configure ₹600 planned loss allocation plus ₹200 execution reserve in `Trading Bot/.env`; retain the existing per-trade and trade-count limits unless the user changes them. These requirements supersede the earlier ₹1,200 daily-loss setting.
- Maximum paper risk per trade is ₹600; the correlated open-risk limit is also ₹600, with the existing one-position cap.

- Dhan credentials in `Trading Bot/.env` are authoritative. Before diagnosing authentication or using trading data, check for updated credentials and ensure the running REST client and WebSocket have reloaded them. Never print secrets. Do not keep retrying an expired in-memory token when the file contains its replacement.
- Paper trading must start monitoring at 09:15 IST on market days and request session liquidation at 15:05 IST. Start the service before the session. Opening-range formation and existing entry/risk limits still apply. Never invent a fill to meet a closing deadline when quotes/liquidity are unavailable; show pending exits and keep managing them.
- Paper trading is authorized. Real-money order authority remains disabled. Evidence collection must be labelled unvalidated paper observation, never a proven edge.
- Verify the complete data-to-decision-to-paper-entry/exit path, including credential rotation, session boundaries, freshness, restart recovery and visible current agent status.
