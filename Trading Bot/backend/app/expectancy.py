"""Broker-sourced charges and empirical expectancy; no invented fee percentages."""
from datetime import datetime, timezone
import hashlib
import json
import math
import requests


class CostModel:
    endpoint = "https://openweb-api.dhan.co/brokerage"

    def __init__(self, store=None):
        self.store = store
        self.memory = {}

    def quote(self, contract, buy_price, sell_price, qty):
        if not all(math.isfinite(v) for v in (qty,buy_price,sell_price)) or qty <= 0 or min(buy_price, sell_price) < 0 or max(buy_price, sell_price) <= 0:
            raise ValueError("Invalid charge calculation inputs")
        lot=int(contract["lot_size"])
        if lot<=0 or qty%lot: raise ValueError("Quantity is not a contract lot multiple")
        body = {"source":"N","data":{
            "exchange":contract["exchange"],"segment":"D",
            "txn_type":"S" if sell_price else "B","qty":int(qty//lot),
            "window":"SHORT_TRADE" if sell_price else "ONLY_BUY",
            "security_id":str(contract["security_id"]),"sell_price":round(sell_price,2),
            "buy_price":round(buy_price,2),"product":"I","instrument":"OPTIDX","exchange1":""}}
        day=datetime.now(timezone.utc).date().isoformat()
        key="charges:"+hashlib.sha256((day+json.dumps(body,sort_keys=True)).encode()).hexdigest()
        cached=self.memory.get(key) or (self.store.cache_get(key) if self.store else None)
        if cached: return cached
        response=requests.post(self.endpoint,json=body,timeout=(4,8))
        response.raise_for_status()
        rows=response.json().get("data",[])
        if not isinstance(rows,list) or not rows: raise RuntimeError("Dhan charge estimator returned no calculation")
        raw=rows[0]
        expected_turnover=(round(buy_price,2)+round(sell_price,2))*qty
        if abs(float(raw.get("EXCHANGE_TURNOVER",-1))-expected_turnover)>.02:
            raise RuntimeError("Dhan charge estimator quantity/turnover mismatch")
        fields={"brokerage":"BROKERAGE","exchange":"EXCHANGE_CHARGES","stt":"STT_CHARGES",
                "sebi":"SEBI_CHARGES","ipft":"IPFT_CHARGES","stamp_duty":"STAMP_DUTY",
                "gst":"GST_CHARGES","total":"TOTAL_CHARGES_TAX"}
        if any(raw.get(field) is None for field in fields.values()):
            raise RuntimeError("Dhan charge response is incomplete")
        result={name:float(raw[field]) for name,field in fields.items()}
        if any(not math.isfinite(v) or v<0 for v in result.values()): raise RuntimeError("Invalid broker charges")
        result["broker_rounding_adjustment"]=result["total"]-sum(v for k,v in result.items() if k!="total")
        result.update(source=self.endpoint,as_of=day,kind="broker_estimate",quantity=int(qty))
        if len(self.memory)>2000: self.memory.clear()
        self.memory[key]=result
        if self.store: self.store.cache_put(key,result,ttl=3600)
        return result

    @staticmethod
    def historical(contract, price, qty, side, timestamp):
        """Only a dated source schedule can price a historical order."""
        schedule=contract.get("charge_schedule")
        day=str(timestamp)[:10]
        if not schedule or not schedule.get("source") or not (schedule.get("valid_from", "9999") <= day <= schedule.get("valid_to", "")):
            raise ValueError("historical_charge_schedule_missing")
        rates=schedule.get(side.lower(),{})
        names=("exchange","stt","sebi","ipft","stamp_duty")
        if any(name not in rates for name in names) or "brokerage" not in schedule or "gst_rate" not in schedule:
            raise ValueError("historical_charge_schedule_incomplete")
        values=[price,qty,*[float(rates[n]) for n in names],float(schedule["brokerage"]),float(schedule["gst_rate"])]
        if any(not math.isfinite(v) or v<0 for v in values) or price<=0 or qty<=0:
            raise ValueError("historical_charge_schedule_invalid")
        rounding=schedule.get("rounding",{})
        if any(name not in rounding or rounding[name] not in (0,2,4,6) for name in (*names,"gst")):
            raise ValueError("historical_charge_rounding_rules_missing")
        from decimal import Decimal, ROUND_HALF_UP
        def rounded(value,name):
            return float(Decimal(str(value)).quantize(Decimal(10)**-rounding[name],rounding=ROUND_HALF_UP))
        turnover=price*qty
        result={name:rounded(turnover*float(rates[name]),name) for name in names}
        result["brokerage"]=float(schedule["brokerage"])
        result["gst"]=rounded((result["brokerage"]+result["exchange"]+result["sebi"]+result["ipft"])*float(schedule["gst_rate"]),"gst")
        result["total"]=round(sum(result.values()),2)
        result.update(source=schedule["source"],as_of=day,kind="dated_schedule",quantity=qty)
        return result

    @staticmethod
    def estimate_round_trip(buy_price, sell_price, qty):
        """Standard Dhan index option round-trip charges (₹40 brokerage + STT + turnover + GST + stamp duty)."""
        buy_turnover = float(buy_price) * qty
        sell_turnover = float(sell_price) * qty
        turnover = buy_turnover + sell_turnover
        brokerage = 40.0
        stt = round(sell_turnover * 0.001, 2)
        exchange = round(turnover * 0.0005, 2)
        sebi = round(turnover * 0.000001, 2)
        stamp_duty = round(buy_turnover * 0.00003, 2)
        gst = round((brokerage + exchange + sebi) * 0.18, 2)
        return round(brokerage + stt + exchange + sebi + stamp_duty + gst, 2)


class ExpectancyEngine:
    def evaluate_net(self,outcomes,min_samples=30,min_days=10):
        """Observed NET outcomes; fees are already included and never deducted twice.

        Group by exit session so clustered trades are not independent samples.
        This conservative three-standard-error bound is a screening statistic,
        not calibrated entry probability or the final walk-forward acceptance gate.
        """
        values=[]; days={}
        for t in outcomes:
            value=t.get("pnl"); day=str(t.get("exit_ts", ""))[:10]
            if t.get("quality")!="verified" or not day or value is None or not math.isfinite(float(value)): continue
            value=float(value); values.append(value); days.setdefault(day,[]).append(value)
        result={"samples":len(values),"sessions":len(days),"expected_value_rupees":None,
                "lower_bound_rupees":None,"p_win":None,"average_net_win":None,"average_net_loss":None,
                "status":"REJECTED","reason":"Insufficient independent net-outcome evidence",
                "method":"exit_session_clustered_three_standard_error_screen"}
        if len(values)<min_samples or len(days)<min_days: return result
        wins=[v for v in values if v>0]; losses=[v for v in values if v<0]
        mean=sum(values)/len(values); groups=list(days.values()); count=len(groups)
        variance=count/(count-1)*sum((sum(g)-len(g)*mean)**2 for g in groups)/len(values)**2
        lower=mean-3*math.sqrt(variance)
        return {**result,"expected_value_rupees":mean,"lower_bound_rupees":lower,
                "p_win":len(wins)/len(values),"average_net_win":sum(wins)/len(wins) if wins else None,
                "average_net_loss":sum(losses)/len(losses) if losses else None,
                "status":"PASS" if lower>0 else "REJECTED",
                "reason":"Positive net-outcome lower bound" if lower>0 else "Net edge is not supported by session-clustered evidence"}

    def evaluate(self, outcomes, target_rupees, stop_rupees, costs, min_samples=30):
        values=[float(t["pnl"]) for t in outcomes if t.get("quality") == "verified" and t.get("pnl") is not None]
        if len(values)<min_samples:
            return {"status":"OBSERVATION","samples":len(values),"expected_value_rupees":None,
                    "reason":"Collecting paper evidence; no calibrated win probability yet"}
        p=sum(v>0 for v in values)/len(values)
        z=1.96; n=len(values)
        lower=(p+z*z/(2*n)-z*math.sqrt(p*(1-p)/n+z*z/(4*n*n)))/(1+z*z/n)
        ev=lower*target_rupees-(1-lower)*stop_rupees-costs
        return {"status":"PASS" if ev>0 else "REJECTED","samples":n,"p_win":p,
                "p_win_lower":lower,"expected_value_rupees":ev,"reason":"Conservative empirical expectancy"}
