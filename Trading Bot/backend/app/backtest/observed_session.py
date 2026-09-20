"""Bounded exact-contract research from a same-day archived Dhan master.

Run explicitly with --download to fetch candles; default execution is offline.
Prices are observed. Fees are an explicit scenario, so results cannot train or
promote models. No account, credential, or live-engine settings are changed.
"""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import zlib

import pandas as pd

from ..config import current_credentials, settings
from ..risk import PlanRiskPolicy
from ..store import json_safe, Store
from .data import _valid_bar, read_contract_csv
from .engine import BacktestConfig, BacktestEngine
from .reports import report_from_run

PROJECT = Path(__file__).resolve().parents[3]
MODES = ("orb_retest", "trend_pullback", "range_rejection", "portfolio")
FIELDS = ("open", "high", "low", "close", "volume")


def save(path, value):
    path.write_text(json.dumps(json_safe(value), indent=2, allow_nan=False), encoding="utf-8")


def candles(raw, symbol):
    stamps = raw.get("timestamp", [])
    if any(len(raw.get(k, [])) != len(stamps) for k in FIELDS):
        raise ValueError(f"{symbol}: mismatched candle arrays")
    frame = pd.DataFrame({k: raw.get(k, []) for k in FIELDS})
    frame["timestamp"] = pd.to_datetime(stamps, unit="s", utc=True).tz_convert("Asia/Kolkata")
    frame["symbol"] = symbol
    if frame.timestamp.duplicated().any():
        raise ValueError(f"{symbol}: duplicate timestamps")
    if (frame.timestamp.dt.second != 0).any():
        raise ValueError(f"{symbol}: candles must start on a minute boundary")
    for row in frame.to_dict("records"):
        _valid_bar(row)
    return frame.sort_values("timestamp")


def fetch(path, security_id, segment, instrument, start, end, oi):
    request={"security_id":str(security_id),"segment":segment,"instrument":instrument,
             "start":start,"end":end,"interval":1,"oi":oi}
    receipt=path.with_suffix(".request.json")
    if path.exists() and receipt.exists() and json.loads(receipt.read_text())==request:
        return json.loads(path.read_text(encoding="utf-8"))
    from dhanhq import DhanContext, dhanhq
    # Re-read the authoritative file for every request, including after rotation.
    client = dhanhq(DhanContext(*current_credentials()))
    client.dhan_http.timeout = (5, 20)
    response = client.intraday_minute_data(str(security_id), segment, instrument, start, end, 1, oi)
    if response.get("status") != "success":
        raise RuntimeError(f"Dhan historical request failed for {security_id}; no prices substituted")
    raw = response.get("data") or {}
    save(path, raw)
    save(receipt, request)
    time.sleep(.35)
    return raw


def download(day, root, database):
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        record = db.execute("SELECT payload FROM history_cache WHERE key=?", ("security_master:" + day,)).fetchone()
    if record is None:
        raise ValueError("No archived security master for this date; today's metadata cannot replace it")
    master = json.loads(zlib.decompress(record[0]))
    save(root / "master.json", master)
    # Dhan omits the candle exactly at fromDate in observed responses. Ask
    # one minute earlier, then select the session using source timestamps.
    start = str((pd.Timestamp(day) - pd.Timedelta(days=7)).date()) + " 09:14:00"
    end = day + " 15:30:00"
    selected = []
    for symbol in ("NIFTY", "SENSEX"):
        index = next(r for r in master if r.get("SEM_INSTRUMENT_NAME") == "INDEX" and r.get("SM_SYMBOL_NAME") == symbol)
        raw = fetch(root / (symbol + "_underlying.json"), index["SEM_SMST_SECURITY_ID"], "IDX_I", "INDEX", start, end, False)
        frame = candles(raw, symbol)
        today = frame[frame.timestamp.dt.strftime("%Y-%m-%d") == day]
        if today.empty:
            raise ValueError(f"{symbol}: no index candles for {day}")
        options = [r for r in master if r.get("SEM_INSTRUMENT_NAME") == "OPTIDX" and
                   str(r.get("SEM_TRADING_SYMBOL", "")).startswith(symbol + "-") and str(r.get("SEM_EXPIRY_DATE"))[:10] > day]
        expiry = min(str(r["SEM_EXPIRY_DATE"])[:10] for r in options)
        options = [r for r in options if str(r["SEM_EXPIRY_DATE"])[:10] == expiry]
        strikes = sorted({float(r["SEM_STRIKE_PRICE"]) for r in options})
        # Acquisition covers ATM +/-6 at every observed point. This does not
        # select a trade: the replay uses only completed-bar evidence.
        lo = min(range(len(strikes)), key=lambda i: abs(strikes[i] - today.low.min()))
        hi = min(range(len(strikes)), key=lambda i: abs(strikes[i] - today.high.max()))
        universe = set(strikes[max(0, lo-6):hi+7])
        for row in options:
            if float(row["SEM_STRIKE_PRICE"]) not in universe:
                continue
            exchange = row["SEM_EXM_EXCH_ID"]
            sid = str(int(row["SEM_SMST_SECURITY_ID"]))
            selected.append({"symbol": symbol, "exchange": exchange, "security_id": sid,
                "contract_id": exchange + ":" + sid, "expiry": expiry,
                "strike": float(row["SEM_STRIKE_PRICE"]), "lot_size": int(row["SEM_LOT_UNITS"]),
                "tick_size": float(row["SEM_TICK_SIZE"])/100,
                "option_type": "CALL" if row["SEM_OPTION_TYPE"] == "CE" else "PUT",
                "metadata_source": "archived_dhan_security_master:" + day})
    save(root / "contracts.json", selected)
    for n, contract in enumerate(selected, 1):
        path = root / (contract["contract_id"].replace(":", "_") + ".json")
        fetch(path, contract["security_id"], contract["exchange"] + "_FNO", "OPTIDX", day + " 09:14:00", end, True)
        print(f"Downloaded/cached {n}/{len(selected)} exact contracts", flush=True)


def fee_scenario(day):
    # Explicit conservative transaction-rate scenario, not dated broker bills.
    # STT post-April-2026 source: NSE securities-transaction-tax page.
    rates = {"exchange": .0005, "stt": 0., "sebi": .000001, "ipft": .000001, "stamp_duty": .00003}
    return {"source": "https://dhan.co/pricing/; https://www.nseindia.com/static/products-services/equity-derivatives-securities-transaction-tax",
        "estimated": True, "valid_from": day, "valid_to": day, "brokerage": 20., "gst_rate": .18,
        "buy": rates, "sell": {**rates, "stt": .0015, "stamp_duty": 0.},
        "rounding": {**{k: 2 for k in rates}, "stt": 0, "stamp_duty": 0, "gst": 2},
        "limitations": "Exchange 0.05% and IPFT 0.0001% are scenario assumptions; historical charges are not certified."}


def prepare(day, root):
    contracts = json.loads((root / "contracts.json").read_text(encoding="utf-8"))
    underlying = {s: candles(json.loads((root / (s + "_underlying.json")).read_text()), s) for s in ("NIFTY", "SENSEX")}
    expected = pd.date_range(day + " 09:15", day + " 15:05", freq="min", tz="Asia/Kolkata")
    for symbol, frame in underlying.items():
        missing = expected.difference(frame.timestamp)
        if len(missing):
            raise ValueError(f"{symbol}: {len(missing)} missing session minutes; cannot replay this date")
    rows = []; coverage = []
    for contract in contracts:
        raw = json.loads((root / (contract["contract_id"].replace(":", "_") + ".json")).read_text())
        option = candles(raw, contract["symbol"])
        oi = raw.get("open_interest", [])
        if len(oi) != len(option):
            raise ValueError(f"{contract['contract_id']}: open-interest observations unavailable")
        # Match OI by source timestamp; candle sorting must not realign values.
        oi_by_time = dict(zip(pd.to_datetime(raw.get("timestamp", []), unit="s", utc=True).tz_convert("Asia/Kolkata"), oi))
        option["oi"] = option.timestamp.map(oi_by_time)
        option = option[option.timestamp.isin(expected)]
        coverage.append({"contract_id": contract["contract_id"], "symbol": contract["symbol"],
                         "observed_minutes": len(option), "missing_minutes": len(expected.difference(option.timestamp))})
        spot = underlying[contract["symbol"]].set_index("timestamp")
        for bar in option.to_dict("records"):
            if bar["oi"] < 0:
                raise ValueError("Negative open interest")
            stamp = bar["timestamp"]
            rows.append({**contract, **bar, "timestamp": stamp.isoformat(),
                "metadata_valid_from": day, "metadata_valid_to": day,
                "price_source": "dhan_charts_intraday_exact_security_id",
                "charge_schedule": json.dumps(fee_scenario(day)),
                **{"underlying_" + f: spot.loc[stamp, f] for f in FIELDS}})
    if not rows:
        raise ValueError("No observed contract candles")
    csv = root / "contracts.csv"
    pd.DataFrame(rows).to_csv(csv, index=False)
    session_underlying=pd.concat([f[f.timestamp.isin(expected)] for f in underlying.values()],ignore_index=True)
    frame, csv_digest = read_contract_csv(csv, {"session_exit": "15:05"}, underlying_frame=session_underlying)
    inputs={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [csv, root / "contracts.json", root / "NIFTY_underlying.json", root / "SENSEX_underlying.json"]}
    digest=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()
    warm = pd.concat([f[f.timestamp < expected[0]] for f in underlying.values()], ignore_index=True)
    warm["option_quotes"] = [[] for _ in range(len(warm))]
    manifest = {"day": day, "dataset": str(csv), "sha256": digest, "csv_sha256": csv_digest,
        "input_hashes": inputs, "contracts": len(contracts),
        "coverage": coverage, "rows": len(rows), "warmup_rows": len(warm),
        "price_evidence": "Observed exact-contract candles; no interpolated prices",
        "fee_evidence": fee_scenario(day), "learning_eligible": False,
        "limitations": ["One observed session, not five-year or out-of-sample validation.",
            "Archive universe is near expiry and the session's ATM +/-6 envelope; not every listed contract.",
            "A same-day archived master does not establish intraday publication timing.",
            "Missing option minutes retain observed index bars with empty option quotes; no prices are filled forward.",
            "Minute candles cannot reconstruct bid/ask depth, latency or partial fills."]}
    save(root / "manifest.json", manifest)
    return pd.concat([warm, frame], ignore_index=True), manifest


def run_suite(day, root, publish=False):
    frame, manifest = prepare(day, root)
    policy = PlanRiskPolicy(trade_risk=600, loss_allocation=600, emergency_reserve=200)
    cfg = BacktestConfig(initial_capital=30000, risk_per_trade=600,
        daily_loss_limit=settings.daily_loss_limit_rupees,
        correlated_risk_limit=600, max_positions=1, plan_policy=policy, adaptive_exits=True,
        entry_cutoff="14:30", exit_at="15:05", trade_from=day)
    summaries = []
    for mode in MODES:
        print("Replaying " + mode, flush=True)
        result = BacktestEngine(replace(cfg, strategy_mode=mode)).run(frame)
        result.update(coverage=manifest["coverage"], learning_eligible=False,
                      assumptions=manifest["limitations"] + [manifest["fee_evidence"]["limitations"]])
        config = {"source": "observed_session", "dataset": manifest["dataset"], "dataset_id": manifest["sha256"],
            "from": day, "to": day, "capital": 30000, "risk_per_trade": 600,
            "daily_loss_limit": settings.daily_loss_limit_rupees, "correlated_risk_limit": 600, "strategy_mode": mode,
            "entry_cutoff": "14:30", "session_exit": "15:05"}
        report = report_from_run(result, config)
        identifier = "observed-" + day + "-" + mode + "-" + manifest["sha256"][:10]
        report.update(run_id=identifier, created_at=datetime.now(timezone.utc).isoformat(),
                      ml_learning={"status": "EXCLUDED_RESEARCH", "reason": "One-session research with estimated fees; no training or promotion"})
        save(root / (mode + "_report.json"), report)
        if publish:
            store = Store(PROJECT / "backend" / "trading_bot.db")
            store.save_bundle([("reports", identifier, report), ("jobs", identifier,
                {"id": identifier, "report_id": identifier, "status": report["status"], "progress": 100,
                 "message": "Observed session replay; estimated fees; excluded from learning", "config": config,
                 "created_at": report["created_at"], "updated_at": report["created_at"]})])
            if mode == "portfolio":
                store.put_record("backtest", "latest", {"report_id": identifier})
        summaries.append({"strategy": mode, "report_id": identifier, "status": report["status"], "metrics": report["metrics"], "issues": report["issues"]})
    save(root / "suite.json", {"manifest": manifest, "results": summaries, "learning_eligible": False})
    print(json.dumps(json_safe(summaries), ensure_ascii=True), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", required=True)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--publish", action="store_true", help="Save reports to the dashboard; never modifies the paper account")
    args = parser.parse_args()
    day = pd.Timestamp(args.day).date().isoformat()
    if not "2026-04-01" <= day <= datetime.now().date().isoformat():
        parser.error("The explicit fee scenario supports past sessions from April 2026 only")
    root = PROJECT / "data" / "backtest_inputs" / day
    root.mkdir(parents=True, exist_ok=True)
    if args.download:
        download(day, root, PROJECT / "backend" / "trading_bot.db")
    run_suite(day, root, args.publish)


if __name__ == "__main__":
    main()
