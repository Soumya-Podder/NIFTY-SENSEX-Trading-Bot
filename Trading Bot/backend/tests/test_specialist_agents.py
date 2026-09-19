from datetime import datetime, timezone

from app.specialist_agents import assess_specialists


def base_signal():
    return {"regime": "TREND_UP", "option_type": "CALL", "underlying_entry": 100,
            "feature_row": {"adx": 30, "ema_slope_atr": .4, "atr": 1, "vwap_distance_atr": .2}}


def base_contract():
    stamp = datetime.now(timezone.utc).isoformat()
    return {"timestamp": stamp, "quote_update_timestamp": stamp, "source": "dhan_quote", "bid": 10, "ask": 10.1, "bid_qty": 75, "ask_qty": 75,
            "lot_size": 75, "spread_pct": .01, "oi": 1000, "volume": 500,
            "gamma": .001, "theta": -.02, "iv": .15, "greeks_observed_at": stamp}


def test_specialist_matrix_records_missing_event_data_without_fabricating_a_clear_event():
    result = assess_specialists(base_signal(), base_contract(), datetime.now(timezone.utc), risk=300, reward=800)
    assert result["decision"] == "CALL"
    assert result["agents"]["News/Event Agent"]["status"] == "DATA_UNAVAILABLE"
    assert result["agents"]["Adversarial Agent"]["status"] == "PASS"
    assert result["authority"].startswith("EVIDENCE_ONLY")


def test_adversarial_agent_is_a_hard_veto_for_bad_execution_evidence():
    contract = base_contract()
    contract.update({"spread_pct": .08, "bid_qty": 0})
    result = assess_specialists(base_signal(), contract, datetime.now(timezone.utc), risk=300, reward=800)
    assert result["decision"] == "WAIT"
    assert "Liquidity Agent" in result["vetoes"]
    assert "Adversarial Agent" in result["vetoes"]
