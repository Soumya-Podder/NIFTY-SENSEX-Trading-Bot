from app.telemetry.decision_trace import pipeline_from_events


def test_pipeline_carries_event_provenance_for_live_workflow():
    events=[
        {"id":"scan","timestamp":"2026-09-15T09:15:00+05:30","agent":"Scanner","symbol":"NIFTY","status":"PASS","summary":"Completed candle","context":"closed_bar","evaluation":{"last_bar":"2026-09-15T09:14:00+05:30"},"policy_version":3},
        {"id":"regime","timestamp":"2026-09-15T09:15:01+05:30","agent":"Regime","symbol":"NIFTY","status":"REJECTED","summary":"Range regime","context":"adx","policy_version":3},
    ]
    chain=pipeline_from_events(events,"NIFTY")
    assert chain[0]["event_id"]=="scan" and chain[0]["timestamp"].endswith("09:15:00+05:30")
    assert chain[0]["evaluation"]["last_bar"].endswith("09:14:00+05:30") and chain[0]["policy_version"]==3
    assert chain[1]["event_id"]=="regime" and chain[1]["context"]=="adx"
    assert chain[2]["event_id"] is None and chain[2]["timestamp"] is None
