"""Rebuild research labels from a saved report and its local exact-contract CSV. No API calls."""
import argparse
from copy import deepcopy
from pathlib import Path
import json
import hashlib
import pandas as pd
from .data import read_contract_csv
from ..market_structure import analyze_structure
from ..outcome_evidence import label_outcomes, evidence_records
from ..store import Store, json_safe


def rebuild(store, data_root, report_id):
    report = deepcopy(store.get_record("reports", report_id, {}))
    if not report:
        raise ValueError("Saved report not found")
    root = Path(data_root).resolve()
    path = Path(report.get("config", {}).get("dataset", ""))
    path = (path if path.is_absolute() else root/path).resolve()
    if not path.is_relative_to(root) or path.suffix.lower() != ".csv" or not path.is_file():
        raise ValueError("Report requires an existing exact-contract CSV inside this project's data directory")
    cfg=report.get("config", {})
    underlying=[]
    manifest_path=path.parent/"manifest.json"
    if manifest_path.is_file():
        manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
        for name, digest in manifest.get("input_hashes", {}).items():
            source=(path.parent/name).resolve()
            if source.parent != path.parent or hashlib.sha256(source.read_bytes()).hexdigest() != digest:
                raise ValueError("Archived input checksum changed")
        from .observed_session import candles
        for symbol in ("NIFTY", "SENSEX"):
            source=path.parent/(symbol+"_underlying.json")
            if source.is_file():
                underlying.append(candles(json.loads(source.read_text(encoding="utf-8")),symbol))
    warm=pd.concat(underlying,ignore_index=True) if underlying else pd.DataFrame()
    session=warm[(warm.timestamp.dt.strftime("%Y-%m-%d")>=cfg["from"]) & (warm.timestamp.dt.strftime("%Y-%m-%d")<=cfg["to"])] if not warm.empty else None
    frame, _ = read_contract_csv(path,cfg,underlying_frame=session)
    # Preserve the report/account results. Add independent research records only.
    label_outcomes(frame, report.get("trades", []))
    entries = evidence_records(report)
    snapshots = []
    for symbol, group in (warm if not warm.empty else frame).groupby("symbol"):
        as_of = group.timestamp.max()+pd.Timedelta(minutes=1)
        snapshot = analyze_structure(group, as_of, symbol)
        snapshot.update(status="STALE", reason="Historical replay evidence; not live market data", source_report=report_id)
        if snapshot.get("as_of"):
            snapshots.append(("market_structure", symbol+":"+snapshot["as_of"], snapshot))
    store.save_bundle([*entries, *snapshots])
    return {"report_id": report_id, "trades": len(report.get("trades", [])), "eligible_records": len(entries),
            "excluded_records": len(report.get("trades", []))-len(entries),
            "records": [{"scope": e[2]["scope"], "direction": e[2]["direction"], "barrier": e[2]["barrier"]} for e in entries],
            "snapshots": [{"symbol": s[2]["symbol"], "as_of": s[2]["as_of"], "zones": len(s[2]["zones"])} for s in snapshots]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-id", required=True, nargs="+")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    store = Store(root/"backend"/"trading_bot.db")
    results = [rebuild(store, root/"data", identifier) for identifier in args.report_id]
    target = root/"data"/"research"/"market_evidence_summary.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(json_safe(results), indent=2), encoding="utf-8")
    print(json.dumps(json_safe(results), indent=2))


if __name__ == "__main__":
    main()
