"""Reject simulated option evidence even when a legacy report says verified."""
from copy import deepcopy

_FIELDS = {"source", "price_source", "metadata_source", "contract_id", "quality"}
_MARKERS = ("black_scholes", "black-scholes", "synthetic", "dynamic:")


def has_synthetic_options(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _FIELDS and isinstance(item, str):
                if any(marker in item.lower() for marker in _MARKERS):
                    return True
            if isinstance(item, (dict, list, tuple)) and has_synthetic_options(item):
                return True
    elif isinstance(value, (list, tuple)):
        return any(has_synthetic_options(item) for item in value)
    return False


def reviewed_report(report):
    """Invalidate legacy presentation without destroying the original audit record."""
    if not has_synthetic_options(report):
        return report
    result=deepcopy(report)
    result.update(quality="synthetic_unvalidated", status="invalidated",
                  learning_eligible=False, original_quality=report.get("quality"))
    result["issues"]=list(result.get("issues", []))+[
        "INVALIDATED: synthetic option prices were previously labelled verified. This report cannot establish performance or train a trading model."]
    result["metrics"]={key:None for key in result.get("metrics", {})}
    result["gross_metrics"]={}
    for key in ("equity", "gross_equity", "drawdown", "daily", "agent_performance"):
        if key in result: result[key]=[]
    result["attribution"]={}
    for trade in result.get("trades", []):
        trade["quality"]="synthetic_unvalidated"
    return result
