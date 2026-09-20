"""Bounded exact-contract research from same-day archived Dhan masters.

Run explicitly with --download to fetch candles; default execution is offline.
Prices remain observed. Candidate sizing uses a conservative fee scenario, then
completed trades are replayed with saved Dhan calculator receipts. Reports may
enter learning only after every strict evidence gate passes. No account,
credential, or live-engine setting is changed.
"""
import argparse
import copy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import zlib

import pandas as pd

from ..ai import LearningService
from ..config import current_credentials
from ..expectancy import CostModel
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
    start = str((pd.Timestamp(day) - pd.Timedelta("7 days")).date()) + " 09:14:00"
    end = day + " 15:30:00"
    selected = []
    session_rows = {}
    for symbol in ("NIFTY", "SENSEX"):
        index = next(r for r in master if r.get("SEM_INSTRUMENT_NAME") == "INDEX" and r.get("SM_SYMBOL_NAME") == symbol)
        raw = fetch(root / (symbol + "_underlying.json"), index["SEM_SMST_SECURITY_ID"], "IDX_I", "INDEX", start, end, False)
        frame = candles(raw, symbol)
        today = frame[frame.timestamp.dt.strftime("%Y-%m-%d") == day]
        session_rows[symbol] = today
    empty = [symbol for symbol, frame in session_rows.items() if frame.empty]
    if len(empty) == len(session_rows):
        save(root / "no_session.json", {
            "day": day,
            "status": "no_observed_market_session",
            "evidence": "Dhan returned no index candles for either NIFTY or SENSEX",
            "symbols": {symbol: len(frame) for symbol, frame in session_rows.items()},
        })
        return False
    if empty:
        raise ValueError(f"Inconsistent index coverage for {day}; no candles for {', '.join(empty)}")
    for symbol in ("NIFTY", "SENSEX"):
        today = session_rows[symbol]
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
    return True


def fee_scenario(day):
    # Explicit conservative transaction-rate scenario, not dated broker bills.
    # STT post-April-2026 source: NSE securities-transaction-tax page.
    rates = {"exchange": .0005, "stt": 0., "sebi": .000001, "ipft": .000001, "stamp_duty": .00003}
    return {"source": "https://dhan.co/pricing/; https://www.nseindia.com/static/products-services/equity-derivatives-securities-transaction-tax",
        "estimated": True, "valid_from": day, "valid_to": day, "brokerage": 20., "gst_rate": .18,
        "buy": rates, "sell": {**rates, "stt": .0015, "stamp_duty": 0.},
        "rounding": {**{k: 2 for k in rates}, "stt": 0, "stamp_duty": 0, "gst": 2},
        "limitations": "Exchange 0.05% and IPFT 0.0001% are scenario assumptions; historical charges are not certified."}


CHARGE_FIELDS = ("brokerage", "exchange", "stt", "sebi", "ipft", "stamp_duty", "gst", "total")


def broker_cost_receipts(trade, calculator, day):
    """Observe exact Dhan calculator totals for one simulated round trip."""
    age=(pd.Timestamp.now(tz="Asia/Kolkata").date() - pd.Timestamp(day).date()).days
    if not 0 <= age <= 15:
        raise ValueError("Dhan's current calculator cannot certify a trade more than 15 days old")
    contract={"exchange":trade["exchange"],"security_id":str(trade["security_id"]),
              "lot_size":int(trade["lot_size"])}
    qty=int(trade["quantity"] if "quantity" in trade else trade["qty"])
    buy=calculator.quote_buy(contract,float(trade["entry"]),qty)
    round_trip=calculator.quote(contract,float(trade["entry"]),float(trade["exit"]),qty)
    sell={name:round(float(round_trip[name])-float(buy[name]),8) for name in CHARGE_FIELDS}
    buy_adjustment=float(buy.get("broker_rounding_adjustment",
        buy["total"]-sum(float(buy[name]) for name in CHARGE_FIELDS if name!="total")))
    round_adjustment=float(round_trip.get("broker_rounding_adjustment",
        round_trip["total"]-sum(float(round_trip[name]) for name in CHARGE_FIELDS if name!="total")))
    sell_adjustment=round(round_adjustment-buy_adjustment,8)
    if any(value < 0 for value in sell.values()) or abs(buy["total"]+sell["total"]-round_trip["total"])>.001:
        raise ValueError("Dhan calculator receipts do not reconcile")
    observed_at=datetime.now(timezone.utc).isoformat()
    common={"source":CostModel.endpoint,"kind":"broker_calculator_receipt","trade_day":day,
            "observed_at":observed_at,"pricing_source":"https://dhan.co/pricing/",
            "continuity_basis":"Dhan states pricing changes are notified 15 days in advance"}
    entry={**{name:float(buy[name]) for name in CHARGE_FIELDS},**common,
           "broker_rounding_adjustment":buy_adjustment,
           "request_fingerprint":buy["request_fingerprint"],"side":"buy",
           "price":float(trade["entry"]),"quantity":qty}
    exit={**sell,**common,"broker_rounding_adjustment":sell_adjustment,
          "request_fingerprint":round_trip["request_fingerprint"],"side":"sell",
          "price":float(trade["exit"]),"quantity":qty,
          "derived_from":"round-trip total minus matching one-leg buy total"}
    return {
        CostModel.historical_key("buy",trade["entry"],qty):entry,
        CostModel.historical_key("sell",trade["exit"],qty):exit,
    }


def inject_receipts(frame, by_contract):
    for quotes in frame.option_quotes:
        for quote in quotes or []:
            observed=by_contract.get(quote["contract_id"])
            if observed:
                quote["charge_schedule"].setdefault("observed_costs",{}).update(observed)


def isolated_replay_frame(frame):
    """Copy nested quote evidence so one strategy cannot affect another."""
    working=frame.copy(deep=True)
    if "option_quotes" in working:
        working["option_quotes"]=[copy.deepcopy(quotes) for quotes in frame["option_quotes"]]
    return working


def stable_receipt_digest(receipts):
    """Fingerprint economic evidence while excluding retrieval timestamps."""
    def stable(value):
        if isinstance(value,dict):
            return {key:stable(item) for key,item in sorted(value.items()) if key != "observed_at"}
        if isinstance(value,list):
            return [stable(item) for item in value]
        return value
    payload=json.dumps(json_safe(stable(receipts)),sort_keys=True,separators=(",",":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def verified_replay(frame, cfg, root, mode, calculator):
    working=isolated_replay_frame(frame)
    receipts={}
    for _ in range(3):
        result=BacktestEngine(replace(cfg,strategy_mode=mode)).run(working)
        missing=[trade for trade in result.get("trades",[]) if
                 trade.get("entry_charges",{}).get("kind")!="broker_calculator_receipt" or
                 trade.get("exit_charges",{}).get("kind")!="broker_calculator_receipt"]
        if not missing:
            result.update(learning_eligible=True,
                          fee_evidence="Completed trades use saved Dhan calculator receipts")
            for trade in result.get("trades",[]): trade["learning_eligible"]=True
            save(root/(mode+"_charge_receipts.json"),receipts)
            return result,receipts
        updates={}
        for trade in missing:
            observed=broker_cost_receipts(trade,calculator,str(trade["entry_ts"])[:10])
            updates.setdefault(trade["contract_id"],{}).update(observed)
            receipts.setdefault(trade["contract_id"],{}).update(observed)
        inject_receipts(working,updates)
    raise RuntimeError(f"{mode}: trade set did not stabilize after broker-cost reconciliation")


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
        coverage.append({"day":day,"contract_id": contract["contract_id"], "symbol": contract["symbol"],
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
    observed_symbols={row["symbol"] for row in rows}
    missing_symbols={"NIFTY","SENSEX"}-observed_symbols
    if missing_symbols:
        raise ValueError("No observed contract candles for " + ", ".join(sorted(missing_symbols)))
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
        "fee_evidence": fee_scenario(day), "learning_eligible": "requires_completed_trade_receipts",
        "limitations": ["One observed session, not five-year or out-of-sample validation.",
            "Archive universe is near expiry and the session's ATM +/-6 envelope; not every listed contract.",
            "A same-day archived master does not establish intraday publication timing.",
            "Missing option minutes retain observed index bars with empty option quotes; no prices are filled forward.",
            "Minute candles cannot reconstruct bid/ask depth, latency or partial fills."]}
    save(root / "manifest.json", manifest)
    return pd.concat([warm, frame], ignore_index=True), manifest


def prepare_days(days, root):
    if len(days)==1:
        return prepare(days[0],root)
    sessions=[]; manifests=[]; blockers=[]; warm=None
    for day in days:
        try:
            frame,manifest=prepare(day,PROJECT/"data"/"backtest_inputs"/day)
        except ValueError as exc:
            blockers.append({"day":day,"reason":str(exc)})
            continue
        if warm is None:
            warm=frame[frame.timestamp.dt.strftime("%Y-%m-%d")<day]
        sessions.append(frame[frame.timestamp.dt.strftime("%Y-%m-%d")==day])
        manifests.append(manifest)
    if blockers:
        save(root/"coverage_blockers.json", {"requested_days":days, "blockers":blockers,
            "status":"data_blocked", "created_at":datetime.now(timezone.utc).isoformat()})
        details="; ".join(item["day"]+": "+item["reason"] for item in blockers)
        raise ValueError("Incomplete observed option coverage: "+details)
    combined=pd.concat([warm,*sessions],ignore_index=True).sort_values(["timestamp","symbol"])
    digest=hashlib.sha256("".join(m["sha256"] for m in manifests).encode()).hexdigest()
    manifest={"days":days,"from":days[0],"to":days[-1],"sha256":digest,
        "dataset":str(root/"manifest.json"),"contracts":sum(m["contracts"] for m in manifests),
        "rows":sum(m["rows"] for m in manifests),
        "coverage":[row for m in manifests for row in m["coverage"]],
        "input_manifests":[str(PROJECT/"data"/"backtest_inputs"/day/"manifest.json") for day in days],
        "price_evidence":"Observed exact-contract Dhan candles; no interpolated option prices",
        "learning_eligible":"requires_completed_trade_receipts",
        "limitations":[f"{len(days)} observed sessions; this is not yet a long-horizon or out-of-sample validation.",
            "Each archived daily universe covers near-expiry ATM +/-6 across that session, not every listed contract.",
            "Same-day archived masters establish daily identity, not their intraday publication time.",
            "Missing option minutes retain observed index bars with empty quotes; no prices are filled forward.",
            "Minute candles cannot reconstruct bid/ask depth, latency or partial fills."]}
    save(root/"manifest.json",manifest)
    return combined,manifest


def run_suite(days, root, publish=False):
    frame, manifest = prepare_days(days,root)
    start,end=days[0],days[-1]
    policy = PlanRiskPolicy(trade_risk=600, loss_allocation=600, emergency_reserve=200)
    cfg = BacktestConfig(initial_capital=30000, risk_per_trade=600,
        daily_loss_limit=800,
        correlated_risk_limit=600, max_positions=1, plan_policy=policy, adaptive_exits=True,
        entry_cutoff="14:30", exit_at="15:05", trade_from=start)
    summaries = []; store=Store(PROJECT/"backend"/"trading_bot.db"); calculator=CostModel(store)
    for mode in MODES:
        print("Replaying " + mode, flush=True)
        result,receipts=verified_replay(frame,cfg,root,mode,calculator)
        receipt_digest=stable_receipt_digest(receipts)
        result.update(coverage=manifest["coverage"],
                      assumptions=manifest["limitations"] + [
                          "Candidate sizing reserves conservative scenario charges.",
                          "Completed trade costs are Dhan calculator observations retrieved within its stated 15-day pricing-notice interval; they are not actual contract notes."])
        config = {"source": "observed_session", "dataset": manifest["dataset"], "dataset_id": manifest["sha256"],
            "from": start, "to": end, "sessions":days, "capital": 30000, "risk_per_trade": 600,
            "daily_loss_limit": 800, "correlated_risk_limit": 600, "strategy_mode": mode,
            "entry_cutoff": "14:30", "session_exit": "15:05"}
        config["dataset_id"]=hashlib.sha256((config["dataset_id"]+receipt_digest).encode()).hexdigest()
        report = report_from_run(result, config)
        identifier = "observed-" + start + "-to-" + end + "-" + mode + "-" + config["dataset_id"][:10]
        report.update(run_id=identifier, created_at=datetime.now(timezone.utc).isoformat())
        report["ml_learning"]=LearningService(store).train(report,identifier)
        save(root / (mode + "_report.json"), report)
        if publish:
            store.save_bundle([("reports", identifier, report), ("jobs", identifier,
                {"id": identifier, "report_id": identifier, "status": report["status"], "progress": 100,
                 "message": "Observed exact-contract replay; Dhan cost receipts; learning gates audited", "config": config,
                 "created_at": report["created_at"], "updated_at": report["created_at"]})])
            if mode == "portfolio":
                store.put_record("backtest", "latest", {"report_id": identifier})
        learning=report["ml_learning"]
        summaries.append({"strategy": mode, "report_id": identifier,
            "status": report["status"], "quality": report["quality"],
            "trades": len(report["trades"]), "metrics": report["metrics"],
            "issues": report["issues"], "eligible_trades": learning.get("eligible_trades",0),
            "excluded_trades": learning.get("excluded_trades",0),
            "gate_audit": learning.get("gate_audit",{}), "models": learning.get("models",[])})
    save(root / "suite.json", {"manifest": manifest, "results": summaries,
        "training_gate_audit_complete": True,
        "eligible_trade_records_across_strategy_reports": sum(item["eligible_trades"] for item in summaries)})
    print(json.dumps(json_safe(summaries), ensure_ascii=True), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    dates=parser.add_mutually_exclusive_group(required=True)
    dates.add_argument("--day")
    dates.add_argument("--from",dest="from_day")
    parser.add_argument("--to",dest="to_day")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--publish", action="store_true", help="Save reports to the dashboard; never modifies the paper account")
    args = parser.parse_args()
    if args.from_day and not args.to_day: parser.error("--to is required with --from")
    if args.to_day and not args.from_day: parser.error("--to requires --from")
    start=pd.Timestamp(args.day or args.from_day).date().isoformat()
    end=pd.Timestamp(args.day or args.to_day).date().isoformat()
    if start>end: parser.error("--from must not be after --to")
    if not "2026-04-01" <= start <= end <= datetime.now().date().isoformat():
        parser.error("The explicit fee scenario supports past sessions from April 2026 only")
    requested_days=[stamp.date().isoformat() for stamp in pd.date_range(start,end,freq="B")]
    database=PROJECT/"backend"/"trading_bot.db"
    days=[]
    for day in requested_days:
        day_root=PROJECT/"data"/"backtest_inputs"/day
        day_root.mkdir(parents=True,exist_ok=True)
        if args.download:
            active=download(day,day_root,database)
        elif (day_root/"contracts.json").exists():
            active=True
        elif (day_root/"no_session.json").exists():
            active=False
        else:
            parser.error(f"No downloaded exact-contract data for {day}; run with --download")
        if active:
            days.append(day)
        elif len(requested_days) == 1:
            parser.error(f"Dhan returned no NIFTY or SENSEX index candles for {day}; no session can be replayed")
        else:
            print(f"Skipping {day}: Dhan returned no NIFTY or SENSEX index candles", flush=True)
    if not days:
        parser.error("No observed market sessions exist in the requested range")
    root=(PROJECT/"data"/"backtest_inputs"/days[0]) if len(days)==1 else \
         (PROJECT/"data"/"backtest_inputs"/(days[0]+"_to_"+days[-1]))
    root.mkdir(parents=True,exist_ok=True)
    try:
        run_suite(days,root,args.publish)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
