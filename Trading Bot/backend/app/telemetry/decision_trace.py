from typing import Any
from datetime import datetime, timezone
import uuid


AGENT_ORDER = [
    "Scanner", "Regime", "Setup", "Confirmation", "Option Selector", "EV", "Risk", "Execution"
]


def event(agent: str, symbol: str, status: str, summary: str, **payload: Any) -> dict[str, Any]:
    """Create one JSON-safe, auditable event for a real engine cycle."""
    return {"id":str(uuid.uuid4()),"timestamp":datetime.now(timezone.utc).isoformat(),
            "agent": agent, "symbol": symbol, "status": status, "summary": summary, **payload}


def pipeline_from_events(events: list[dict[str, Any]], symbol: str | None = None) -> list[dict[str, Any]]:
    if symbol:
        events = [item for item in events if item.get("symbol") == symbol]
    # A new scan starts a new decision chain. Do not mix yesterday's passes or
    # rejections into the current waiting/no-setup evaluation.
    starts=[i for i,item in enumerate(events) if item.get("agent")=="Scanner"]
    if starts: events=events[starts[-1]:]
    latest: dict[str, dict[str, Any]] = {}
    for item in reversed(events):
        agent = item.get("agent")
        if agent in AGENT_ORDER and agent not in latest:
            latest[agent] = item
    return [{
        "agent": agent,
        "status": latest.get(agent, {}).get("status", "WAITING"),
        "label": latest.get(agent, {}).get("summary", "Awaiting event"),
        "event_id": latest.get(agent, {}).get("id"),
        "timestamp": latest.get(agent, {}).get("timestamp"),
        "context": latest.get(agent, {}).get("context"),
        "evaluation": latest.get(agent, {}).get("evaluation"),
        "policy_version": latest.get(agent, {}).get("policy_version"),
    } for agent in AGENT_ORDER]
