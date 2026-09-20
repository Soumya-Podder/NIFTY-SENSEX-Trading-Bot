"""Audit recorded option observations without overstating historical coverage."""
import argparse
import json
import sqlite3
from pathlib import Path


OPTION_FIELDS = (
    "contract_id", "expiry", "strike", "option_type", "lot_size", "tick_size",
    "bid", "ask", "bid_qty", "ask_qty", "ltp", "volume", "oi",
    "metadata_source", "metadata_valid_from", "metadata_valid_to",
    "price_source", "charge_schedule", "source", "exchange_timestamp",
)


def audit_observation_db(path):
    """Return a bounded, reproducible audit of a QuoteRecorder SQLite database."""
    db_path = Path(path).resolve()
    if not db_path.is_file():
        raise FileNotFoundError(f"Observation database does not exist: {db_path}")
    connection = sqlite3.connect(db_path)
    try:
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "observations" not in tables or "recorder_runs" not in tables:
            raise ValueError("Database is not a QuoteRecorder observation database")

        option_count = connection.execute(
            "SELECT count(*) FROM observations WHERE kind='option_depth'"
        ).fetchone()[0]
        underlying_count = connection.execute(
            "SELECT count(*) FROM observations WHERE kind='underlying'"
        ).fetchone()[0]
        days = [
            row[0] for row in connection.execute(
                """SELECT DISTINCT substr(json_extract(payload, '$.exchange_timestamp'), 1, 10)
                   FROM observations
                   WHERE kind='option_depth'
                     AND json_extract(payload, '$.exchange_timestamp') IS NOT NULL
                   ORDER BY 1"""
            )
        ]
        symbols = {
            row[0]: row[1] for row in connection.execute(
                """SELECT json_extract(payload, '$.symbol'), count(*)
                   FROM observations
                   WHERE kind='option_depth'
                   GROUP BY 1 ORDER BY 1"""
            )
        }
        contracts = connection.execute(
            """SELECT count(DISTINCT json_extract(payload, '$.contract_id'))
               FROM observations WHERE kind='option_depth'"""
        ).fetchone()[0]
        missing = {}
        for field in OPTION_FIELDS:
            missing[field] = connection.execute(
                """SELECT count(*) FROM observations
                   WHERE kind='option_depth'
                     AND (json_extract(payload, '$.' || ?) IS NULL
                          OR json_extract(payload, '$.' || ?) = '')""",
                (field, field),
            ).fetchone()[0]
        runs = [
            {
                "id": row[0],
                "started_at": row[1],
                "ended_at": row[2],
                "clean_shutdown": bool(row[3]),
                "persisted": row[4],
                "dropped": row[5],
                "error": row[7],
            }
            for row in connection.execute(
                """SELECT id, started_at, ended_at, clean_shutdown, persisted,
                          dropped, last_drop, error
                   FROM recorder_runs ORDER BY started_at"""
            )
        ]
    finally:
        connection.close()

    dropped = sum(run["dropped"] for run in runs)
    complete_runs = all(run["clean_shutdown"] and not run["dropped"] and not run["error"]
                        for run in runs)
    eligible_for_contract_replay = False
    blockers = [
        "Recorded option_depth observations are quotes/depth, not one-minute OHLC candles.",
        "The database does not prove every expected exchange session or candidate contract was recorded.",
        "A charge_schedule and dated metadata validity interval are not stored on every observation.",
        "Convert only after a sourced candle/aggregation policy and coverage manifest are available.",
    ]
    if not days:
        blockers.insert(0, "No option observation exchange timestamps were found.")
    return {
        "database": str(db_path),
        "kind": "quote_recorder_observation_audit",
        "option_depth_rows": option_count,
        "underlying_rows": underlying_count,
        "distinct_contract_ids": contracts,
        "option_days": days,
        "symbols": symbols,
        "missing_option_fields": missing,
        "recorder_runs": runs,
        "dropped_rows": dropped,
        "all_runs_clean_without_drops": complete_runs,
        "eligible_for_fixed_contract_replay": eligible_for_contract_replay,
        "blockers": blockers,
    }


def main():
    parser = argparse.ArgumentParser(description="Audit recorded option observations")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit_observation_db(args.db)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
