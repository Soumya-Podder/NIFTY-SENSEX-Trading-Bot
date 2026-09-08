from app.options import greek_scenario


def test_greek_scenario_is_unit_checked_and_reports_lot_value():
    contract = {
        "delta": .5, "gamma": .002, "vega": 28.5, "theta": -15.2,
        "lot_size": 10, "greek_units": {
            "delta": "premium_per_index_point",
            "gamma": "premium_per_index_point_squared",
            "vega": "premium_per_iv_decimal",
            "theta": "premium_per_day",
        }, "greeks_source": "fixture", "greeks_observed_at": "2026-09-07T10:00:00+05:30",
    }
    result = greek_scenario(contract, 10, .01, 1)
    assert result["available"] is True
    assert result["per_option_unit"] == .5 * 10 + .5 * .002 * 100 + 28.5 * .01 - 15.2
    assert result["per_lot"] == result["per_option_unit"] * 10


def test_greek_scenario_does_not_double_count_observed_option_candles():
    result = greek_scenario({}, 10, .01, 1, actual_option_path=True)
    assert result == {"available": False, "reason": "actual_option_candles_already_include_greek_effects",
                      "double_counting": True}


def test_greek_scenario_blocks_unverified_units_or_missing_values():
    result = greek_scenario({"delta": .5, "lot_size": 10}, 10, .01, 1)
    assert result["available"] is False
    assert result["reason"] == "greek_units_unverified"
