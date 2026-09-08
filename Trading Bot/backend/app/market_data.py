import threading
import time
import io
import hashlib
import json
import asyncio
import uuid
import requests
import pandas as pd
from datetime import datetime, timezone
from typing import Any
from contextvars import ContextVar

HISTORY_CACHE_ONLY=ContextVar("history_cache_only",default=False)

from .telemetry.decision_trace import event
from .telemetry.event_bus import event_bus
from .session import local_time,now_ist,quote_is_fresh,session_state


def exchange_timestamp(value):
    if value is None or value=="": return None
    try:
        if isinstance(value,(int,float)):
            stamp=pd.to_datetime(value,unit="s",utc=True)
        else:
            stamp=pd.to_datetime(value,dayfirst=True) if "/" in str(value) else pd.Timestamp(value)
        if pd.isna(stamp): return None
        return (stamp.tz_localize("Asia/Kolkata") if stamp.tzinfo is None else stamp.tz_convert("Asia/Kolkata")).isoformat()
    except (ValueError,TypeError,OverflowError): return None


class DhanMarketData:
    """Dhan MarketFeed adapter. No tick is manufactured when the feed is down."""

    def __init__(self, client_id: str, access_token: str, symbols: str, gateway=None, store=None):
        self.client_id = client_id
        self.access_token = access_token
        self.symbol_names = [item.strip().upper() for item in symbols.split(",") if item.strip()]
        self.latest: dict[str, dict[str, Any]] = {}
        self.security_to_symbol: dict[str, str] = {}
        self.feed = None
        self.thread: threading.Thread | None = None
        self.error: str | None = None
        self.connected = False
        self.lock=threading.RLock()
        self.stopping=threading.Event()
        self.last_attempt=0.0
        self.gateway=gateway
        self.store=store
        self.last_sequence={}
        self.option_contracts={}
        self.option_quotes={}
        self.credential_generation=0
        self.last_packet_at=None
        self.reconfigure_lock=threading.RLock()

    def refresh_credentials(self,client_id,access_token,force=False):
        with self.reconfigure_lock:
            return self._refresh_credentials(client_id,access_token,force)

    def _refresh_credentials(self,client_id,access_token,force=False):
        if not force and (client_id,access_token)==(self.client_id,self.access_token): return False
        self.stop()
        if self.thread: self.thread.join(timeout=3)
        if self.thread and self.thread.is_alive():
            raise RuntimeError("Waiting for old market feed to stop before credential rotation")
        with self.lock:
            self.client_id,self.access_token=client_id,access_token
            self.latest.clear(); self.option_quotes.clear(); self.last_packet_at=None
            self.feed=None; self.thread=None; self.last_attempt=0
            self.stopping.clear(); self.credential_generation+=1
        self.start()
        return True

    def reconnect_if_idle(self):
        if not self.configured or session_state() not in {"ENTRY_WINDOW","MANAGE_ONLY"}: return False
        if time.monotonic()-self.last_attempt<30: return False
        if self.last_packet_at and (now_ist()-local_time(self.last_packet_at)).total_seconds()<30: return False
        return self.refresh_credentials(self.client_id,self.access_token,force=True)

    def subscribe_options(self,contracts):
        from dhanhq import MarketFeed
        desired={(8 if c["exchange"]=="BSE" else 2,str(c["security_id"])):dict(c) for c in contracts}
        with self.lock:
            old=set(self.option_contracts); new=set(desired)
            self.option_contracts=desired
            self.option_quotes={k:v for k,v in self.option_quotes.items() if k in {c["contract_id"] for c in contracts}}
            feed=self.feed
        if feed:
            if old-new: feed.unsubscribe_symbols([(ex,sid,MarketFeed.Full) for ex,sid in old-new])
            if new-old: feed.subscribe_symbols([(ex,sid,MarketFeed.Full) for ex,sid in new-old])

    def executable_quotes(self):
        with self.lock: return {k:dict(v) for k,v in self.option_quotes.items()}

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.access_token and self.symbol_names)

    def start(self) -> None:
        if not self.configured or self.stopping.is_set() or (self.thread and self.thread.is_alive()) or time.monotonic()-self.last_attempt<15:
            return
        self.last_attempt=time.monotonic()
        self.thread = threading.Thread(target=self._run, name="dhan-market-feed", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        try:
            from dhanhq import DhanContext, MarketFeed, dhanhq
            context = DhanContext(self.client_id, self.access_token)
            if self.gateway:
                instrument_df=self.gateway.master()
            else:
                response=requests.get("https://images.dhan.co/api-data/api-scrip-master.csv",timeout=(5,25))
                response.raise_for_status()
                instrument_df=pd.read_csv(io.StringIO(response.text),low_memory=False)
            if instrument_df is None:
                raise RuntimeError("Dhan security master unavailable")
            instruments = self._resolve_instruments(instrument_df, MarketFeed)
            if not instruments:
                raise RuntimeError("No configured symbols resolved in Dhan security master")
            self._load_initial_snapshot(dhanhq(context))
            if self.stopping.is_set(): return
            with self.lock:
                instruments += [(ex,sid,MarketFeed.Full) for ex,sid in self.option_contracts]
            class TimestampedFeed(MarketFeed):
                def utc_time(self, epoch_time):
                    # The SDK's default drops the date, making yesterday's tick ambiguous.
                    return datetime.fromtimestamp(epoch_time,timezone.utc).isoformat()
            self.feed = TimestampedFeed(context, instruments, "v2", on_connect=self._on_connect,
                                    on_message=self._on_message, on_error=self._on_error,on_close=self._on_close)
            self.feed.run()
        except Exception as exc:
            self._on_error(self.feed, exc)

    def _resolve_instruments(self, frame, market_feed) -> list[tuple[str, str, str]]:
        columns = {str(column).upper(): column for column in frame.columns}
        name_columns = [
            columns[name]
            for name in ("SM_SYMBOL_NAME", "SYMBOL_NAME", "SEM_TRADING_SYMBOL", "DISPLAY_NAME",
                         "SEM_CUSTOM_SYMBOL", "UNDERLYING_SYMBOL", "SYMBOL")
            if name in columns
        ]
        segment_column = next((columns[name] for name in ("SEM_SEGMENT", "SEGMENT", "EXM_SEGMENT",
                                                          "EXCH_SEGMENT", "EXCHANGE_SEGMENT") if name in columns), None)
        id_column = next((columns[name] for name in ("SEM_SMST_SECURITY_ID", "SECURITY_ID", "SECURITYID")
                          if name in columns), None)
        if not name_columns or not id_column:
            return []
        result = []
        for symbol in self.symbol_names:
            matches = frame.iloc[0:0]
            for name_column in name_columns:
                matches = frame[frame[name_column].astype(str).str.upper().eq(symbol)]
                if not matches.empty:
                    break
            if segment_column:
                index_matches = matches[matches[segment_column].astype(str).str.upper().isin({"I", "IDX_I", "INDEX"})]
                matches = index_matches if not index_matches.empty else matches
            if matches.empty:
                continue
            security_id = str(int(matches.iloc[0][id_column]))
            self.security_to_symbol[security_id] = symbol
            # Index spot monitoring needs timestamped ticker packets; a Full
            # subscription can connect without delivering index updates.
            result.append((market_feed.IDX, security_id, market_feed.Ticker))
        return result

    def _load_initial_snapshot(self, client) -> None:
        """Seed latest values from one broker quote call; live ticks replace them."""
        security_ids = [int(float(value)) for value in self.security_to_symbol]
        if not security_ids:
            return
        response = client.ticker_data({"IDX_I": security_ids})
        if not isinstance(response, dict) or response.get("status") != "success":
            return
        payload = response.get("data", {})
        payload = payload.get("data", payload) if isinstance(payload, dict) else {}
        rows = payload.get("IDX_I", {})
        timestamp = datetime.now(timezone.utc).isoformat()
        for security_id, values in rows.items():
            symbol = self.security_to_symbol.get(str(security_id))
            if not symbol or not isinstance(values, dict) or values.get("last_price") is None:
                continue
            self.latest[symbol] = {"symbol": symbol, "security_id": str(security_id),
                                   "timestamp": timestamp, "ltp": float(values["last_price"]),
                                   "open": None, "high": None, "low": None, "close": None,
                                   "volume": None, "oi": None, "change_pct": None,
                                   "last_trade_timestamp": None, "exchange_timestamp": None,
                                   "quote_update_timestamp": None,
                                   "source": "dhan_quote_snapshot"}

    def _on_connect(self, _feed) -> None:
        self.connected = True
        self.error = None

    def _on_close(self,*_args):
        self.connected=False

    def stop(self):
        self.stopping.set()
        if self.feed:
            try:
                self.feed._running=False
                if self.feed.loop.is_running():
                    asyncio.run_coroutine_threadsafe(self.feed.disconnect(),self.feed.loop).result(timeout=3)
            except Exception: pass
        self.connected=False

    def _on_error(self, _feed, exc: Exception) -> None:
        self.connected = False
        self.error = "Market feed error: "+type(exc).__name__+"; check current credentials and data access"

    def _on_message(self, _feed, payload: Any) -> None:
        if self.stopping.is_set() or (_feed is not None and _feed is not self.feed): return
        packets = payload if isinstance(payload, list) else [payload]
        for packet in packets:
            if not isinstance(packet, dict):
                continue
            security_id = str(packet.get("security_id", ""))
            received=datetime.now(timezone.utc).isoformat()
            self.last_packet_at=received
            key=(int(packet.get("exchange_segment",0)),security_id)
            with self.lock: contract=self.option_contracts.get(key)
            if contract and packet.get("type")=="Full Data":
                depth=packet.get("depth") or []
                bids=[d for d in depth if float(d.get("bid_price",0))>0 and int(d.get("bid_quantity",0))>0]
                asks=[d for d in depth if float(d.get("ask_price",0))>0 and int(d.get("ask_quantity",0))>0]
                bid=max(bids,key=lambda d:float(d["bid_price"])) if bids else {}
                ask=min(asks,key=lambda d:float(d["ask_price"])) if asks else {}
                quote={**contract,"timestamp":received,"quote_update_timestamp":received,
                    "exchange_timestamp":exchange_timestamp(packet.get("LTT")),"last_trade_timestamp":exchange_timestamp(packet.get("LTT")),
                    "source":"dhan_market_feed_depth","credential_generation":self.credential_generation,
                    "bid":float(bid.get("bid_price",0)),"bid_qty":int(bid.get("bid_quantity",0)),
                    "ask":float(ask.get("ask_price",0)),"ask_qty":int(ask.get("ask_quantity",0)),
                    "ltp":float(packet.get("LTP",0)),"volume":packet.get("volume"),"oi":packet.get("OI")}
                with self.lock: self.option_quotes[contract["contract_id"]]=quote
                if self.store:
                    self.store.put_record("market_events",f"depth:{received}:{contract['contract_id']}:{uuid.uuid4().hex}",
                        {"event_type":"option_depth","received_at":received,"raw":packet,"normalized":quote,"source":"dhan_market_feed"})
                continue
            symbol = self.security_to_symbol.get(security_id)
            if not symbol or key[0]!=0:
                continue
            ltp = float(packet["LTP"]) if packet.get("LTP") is not None else None
            if ltp is None: continue
            close = float(packet["close"]) if packet.get("close") not in (None, "") else None
            tick = {"symbol": symbol, "security_id": security_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "ltp": ltp,
                    "open": packet.get("open"), "high": packet.get("high"), "low": packet.get("low"),
                    "close": close, "volume": packet.get("volume"), "oi": packet.get("OI"),
                    "change_pct": ((ltp - close) / close * 100) if ltp is not None and close else None,
                    "source": "dhan_market_feed"}
            received=datetime.now(timezone.utc).isoformat()
            tick["timestamp"]=received
            tick["last_trade_timestamp"]=exchange_timestamp(packet.get("LTT"))
            tick["exchange_timestamp"]=tick["last_trade_timestamp"]
            tick["quote_update_timestamp"]=received
            if self.store:
                sequence=packet.get("sequence") or packet.get("seq")
                previous=self.last_sequence.get(security_id)
                try:
                    gap_status=("gap" if previous is not None and int(sequence)!=int(previous)+1 else "observed")
                    self.last_sequence[security_id]=int(sequence)
                except (TypeError,ValueError):
                    gap_status="unavailable"
                self.store.put_record("market_events",f"feed:{received}:{security_id}:{uuid.uuid4().hex}",
                    {"event_type":"market_feed","received_at":received,"symbol":symbol,
                     "security_id":security_id,"sequence":sequence,"previous_sequence":previous,
                     "sequence_status":gap_status,
                     "raw":packet,"normalized":tick,"source":"dhan_market_feed"})
            with self.lock:
                self.latest[symbol] = tick

    def snapshot(self) -> dict[str, Any]:
        self.start()
        with self.lock:
            symbols={k:{**v,"fresh":quote_is_fresh(v),"age_seconds":max(0,(now_ist()-local_time(v["timestamp"])).total_seconds())} for k,v in self.latest.items()}
            option_contracts=list(self.option_contracts.values()); option_quotes=list(self.option_quotes.values())
        state=session_state()
        return {"connected": self.connected, "configured": self.configured,"session":state,
                "live":state in {"ENTRY_WINDOW","MANAGE_ONLY"} and any(v["fresh"] for v in symbols.values()),
                "requested_symbols": self.symbol_names, "symbols": symbols,
                "source": "dhan_market_feed" if self.configured else "unavailable",
                "error": self.error,"last_packet_at":self.last_packet_at,
                "option_subscriptions":len(self.option_contracts),"option_depth_quotes":len(self.option_quotes),
                "options_by_symbol":{s:{"subscribed":sum(c["symbol"]==s for c in option_contracts),
                    "fresh_depth":sum(q["symbol"]==s and quote_is_fresh(q) for q in option_quotes)} for s in self.symbol_names},
                "credential_generation":self.credential_generation}


class DhanGateway:
    """One rate-limited, cached data adapter shared by paper and research."""
    def __init__(self,settings,store,credential_provider=None):
        from dhanhq import DhanContext,dhanhq
        self.settings=settings; self.store=store
        self.client=dhanhq(DhanContext(settings.dhan_client_id,settings.dhan_access_token))
        self.client.dhan_http.timeout=(5,15)
        self.locks={kind:threading.Lock() for kind in ("data","quote","chain")}
        self.last={kind:0.0 for kind in self.locks}
        self._master=None; self._master_day=None
        self.credential_provider=credential_provider
        self.credential_lock=threading.RLock()
        self.credentials=(settings.dhan_client_id,settings.dhan_access_token)
        self.credential_generation=0

    def refresh_credentials(self):
        if not getattr(self,"credential_provider",None): return False
        with self.credential_lock:
            values=self.credential_provider()
            if values==self.credentials: return False
            from dhanhq import DhanContext,dhanhq
            self.client=dhanhq(DhanContext(*values)); self.client.dhan_http.timeout=(5,15)
            self.credentials=values
            self.settings.dhan_client_id,self.settings.dhan_access_token=values
            self.credential_generation+=1
            return True

    @staticmethod
    def unwrap(response):
        if not isinstance(response,dict) or response.get("status")!="success":
            raise RuntimeError("Dhan data request failed: "+str(response.get("remarks","unknown") if isinstance(response,dict) else "invalid response")[:300])
        value=response.get("data",{})
        while isinstance(value,dict) and "data" in value and not any(k in value for k in ("timestamp","oc","ce","pe")):
            value=value["data"]
        return value

    def call(self,method,*args,kind="data",cache_seconds=0,cancel=None):
        name=method.__name__
        if cache_seconds<0 and name in {"expired_options_data","intraday_minute_data"}:
            return self.history_call(method,args,kind,cancel)
        return self._call(method,*args,kind=kind,cache_seconds=cache_seconds,cancel=cancel)

    def history_call(self,method,args,kind,cancel):
        """Reuse overlapping sourced responses; fetch only uncovered date intervals."""
        option=method.__name__=="expired_options_data"
        aidx,bidx=(8,9) if option else (3,4)
        start,end=str(args[aidx]),str(args[bidx])
        fields=list(args[7]) if option else ["open","high","low","close","volume"]
        identity=[v for i,v in enumerate(args) if i not in ({7,aidx,bidx} if option else {aidx,bidx})]
        family=hashlib.sha256((method.__name__+json.dumps(identity,sort_keys=True,default=str)).encode()).hexdigest()
        ranges=self.store.history_ranges(family,start,end,fields,include_expired=HISTORY_CACHE_ONLY.get())
        cursor=start; parts=[]
        side="ce" if option and args[6]=="CALL" else "pe"
        while cursor<end:
            if cancel and cancel(): raise InterruptedError("Cancelled")
            covering=[r for r in ranges if r[1]<=cursor<r[2]]
            chosen=max(covering,key=lambda r:r[2]) if covering else None
            raw=self.store.cache_get(chosen[0],include_expired=HISTORY_CACHE_ONLY.get()) if chosen else None
            if raw is not None:
                stop=min(end,chosen[2])
            else:
                if chosen: ranges.remove(chosen); continue
                stop=min([end]+[r[1] for r in ranges if r[1]>cursor])
                if HISTORY_CACHE_ONLY.get():
                    raise ValueError(f"Local historical candles missing for {method.__name__}: {cursor} to {stop}. Download/resume history or allow missing-data downloads. No historical API request was made.")
                request=list(args); request[aidx]=cursor; request[bidx]=stop
                raw=self._call(method,*request,kind=kind,cache_seconds=-1,cancel=cancel)
                series=(raw.get(side) or {}) if option else raw
                stamps=series.get("timestamp",[])
                available=[f for f in fields if isinstance(series.get(f),list) and len(series[f])==len(stamps)]
                # Empty successful responses are negative-cache observations, not proof of a holiday.
                if not stamps: available=fields
                key=hashlib.sha256((method.__name__+json.dumps(tuple(request),sort_keys=True,default=str)).encode()).hexdigest()
                self.store.index_history(key,family,cursor,stop,available)
            series=(raw.get(side) or {}) if option else raw
            stamps=series.get("timestamp",[])
            lo=pd.Timestamp(cursor,tz="Asia/Kolkata").timestamp(); hi=pd.Timestamp(stop,tz="Asia/Kolkata").timestamp()
            indices=[i for i,t in enumerate(stamps) if lo<=t<hi]
            clipped={k:[v[i] for i in indices] for k,v in series.items() if isinstance(v,list) and len(v)==len(stamps)}
            if stamps and any(f not in clipped for f in fields):
                raise ValueError("Dhan historical response has missing or misaligned requested fields")
            parts.append(clipped); cursor=stop
        result={k:[v for p in parts for v in p.get(k,[])] for k in ["timestamp",*fields]}
        return {side:result} if option else result

    def _call(self,method,*args,kind="data",cache_seconds=0,cancel=None):
        self.refresh_credentials()
        generation=getattr(self,"credential_generation",0)
        if getattr(self,"credential_provider",None): method=getattr(self.client,method.__name__)
        def has_candles(value):
            return isinstance(value,dict) and bool(value.get("timestamp") or any(isinstance(value.get(side),dict) and value[side].get("timestamp") for side in ("ce","pe")))
        key=hashlib.sha256((method.__name__+json.dumps(args,sort_keys=True,default=str)).encode()).hexdigest()
        if cache_seconds>=0: key="runtime:"+str(getattr(self,"credential_generation",0))+":"+key
        if cache_seconds:
            cached=self.store.cache_get(key)
            if cached is not None:
                if cache_seconds<0 and has_candles(cached): self.store.retain_cache(key)
                return cached
        with self.locks[kind]:
            for attempt in range(3):
                if cancel and cancel(): raise InterruptedError("Cancelled")
                # Rebind every retry as well: a renewed .env must never leave
                # retries bound to the client carrying the expired token.
                self.refresh_credentials()
                generation=getattr(self,"credential_generation",0)
                if getattr(self,"credential_provider",None): method=getattr(self.client,method.__name__)
                delay={"data":.25,"quote":1.05,"chain":3.1}[kind]-(time.monotonic()-self.last[kind])
                if delay>0: time.sleep(delay)
                try:
                    result=self.unwrap(method(*args))
                    self.refresh_credentials()
                    if generation!=getattr(self,"credential_generation",0):
                        raise RuntimeError("Credentials changed during request; discard old response and retry")
                    self.last[kind]=time.monotonic()
                    if cache_seconds:
                        if cache_seconds>=0:
                            key="runtime:"+str(generation)+":"+hashlib.sha256((method.__name__+json.dumps(args,sort_keys=True,default=str)).encode()).hexdigest()
                        self.store.cache_put(key,result,86400 if cache_seconds<0 and not has_candles(result) else cache_seconds)
                    return result
                except Exception:
                    self.last[kind]=time.monotonic()
                    if attempt==2: raise
                    time.sleep(2**attempt)

    def master(self):
        day=str(now_ist().date())
        if self._master_day==day and self._master is not None: return self._master
        cache=self.store.cache_get("security_master:"+day)
        if cache is None:
            response=requests.get("https://images.dhan.co/api-data/api-scrip-master.csv",timeout=(5,25))
            response.raise_for_status()
            frame=pd.read_csv(io.StringIO(response.text),low_memory=False)
            cache=json.loads(frame.to_json(orient="records"))
            self.store.cache_put("security_master:"+day,cache,86400)
        self._master=pd.DataFrame(cache); self._master_day=day
        return self._master

    def underlyings(self):
        frame=self.master(); result=[]
        indices=frame[frame.SEM_INSTRUMENT_NAME.astype(str).eq("INDEX")]
        for symbol in ("NIFTY","SENSEX"):
            matches=indices[indices.SM_SYMBOL_NAME.astype(str).str.upper().eq(symbol)]
            if matches.empty: matches=indices[indices.SEM_TRADING_SYMBOL.astype(str).str.upper().eq(symbol)]
            if matches.empty: continue
            row=matches.iloc[0]
            result.append({"symbol":symbol,"security_id":str(int(row.SEM_SMST_SECURITY_ID)),
                           "exchange":str(row.SEM_EXM_EXCH_ID),"exchange_segment":str(row.SEM_EXM_EXCH_ID)+"_FNO"})
        return result

    def contracts(self,symbol):
        frame=self.master()
        matches=frame[frame.SEM_INSTRUMENT_NAME.astype(str).eq("OPTIDX") & frame.SEM_TRADING_SYMBOL.astype(str).str.startswith(symbol+"-")]
        result=[]
        for row in matches.itertuples(index=False):
            expiry=str(row.SEM_EXPIRY_DATE)[:10]
            if expiry<str(now_ist().date()): continue
            cid=f"{row.SEM_EXM_EXCH_ID}:{int(row.SEM_SMST_SECURITY_ID)}"
            result.append({"contract_id":cid,"security_id":str(int(row.SEM_SMST_SECURITY_ID)),"symbol":symbol,
                           "exchange":str(row.SEM_EXM_EXCH_ID),"expiry":expiry,"strike":float(row.SEM_STRIKE_PRICE),
                           "option_type":"CALL" if str(row.SEM_OPTION_TYPE)=="CE" else "PUT",
                           "lot_size":int(row.SEM_LOT_UNITS),"tick_size":float(row.SEM_TICK_SIZE)/100,
                           "identity_verified":True,"metadata_source":"dhan_security_master",
                           "metadata_observed_on":str(now_ist().date())})
        return result

    def chain(self,symbol,exclude_expiry_day=False):
        under=next(x for x in self.underlyings() if x["symbol"]==symbol)
        expiries=self.call(self.client.expiry_list,int(under["security_id"]),"IDX_I",cache_seconds=3600)
        if isinstance(expiries,dict): expiries=expiries.get("data",[])
        valid=sorted(str(x)[:10] for x in expiries if str(x)[:10]>=str(now_ist().date()))
        if exclude_expiry_day: valid=[x for x in valid if x>str(now_ist().date())]
        if not valid: return []
        expiry=valid[0]
        chain=self.call(self.client.option_chain,int(under["security_id"]),"IDX_I",expiry,kind="chain",cache_seconds=30)
        master={x["security_id"]:x for x in self.contracts(symbol) if x["expiry"]==expiry}
        received=now_ist().isoformat()
        spot=float(chain.get("last_price",0))
        strikes=[float(k) for k in chain.get("oc",{})]
        if not strikes or spot<=0: return []
        atm=min(strikes,key=lambda v:abs(v-spot)); result=[]; records=[]
        for strike,legs in chain["oc"].items():
            if float(strike)==atm: continue
            for key in ("ce","pe"):
                leg=legs.get(key) or {}; sid=str(leg.get("security_id",""))
                contract=master.get(sid)
                if not contract: continue
                greeks=leg.get("greeks") or {}
                row={**contract,"spot":spot,"ltp":leg.get("last_price"),"oi":leg.get("oi"),
                     "volume":leg.get("volume"),"iv":leg.get("implied_volatility"),
                     "delta":greeks.get("delta"),"gamma":greeks.get("gamma"),
                     "theta":greeks.get("theta"),"vega":greeks.get("vega"),
                     "greeks_source":"dhan_option_chain",
                     "greeks_observed_at":received,"is_atm":False,"strike_universe":strikes}
                records.extend([("contracts",row["contract_id"],contract),
                    ("contract_metadata",contract["metadata_observed_on"]+":"+row["contract_id"],contract)])
                result.append(row)
        if records: self.store.save_bundle(records)
        return result

    def quotes(self,contracts):
        if not contracts: return {}
        groups={}
        for c in contracts: groups.setdefault(c["exchange"]+"_FNO",[]).append(int(c["security_id"]))
        groups={k:sorted(set(v)) for k,v in groups.items()}
        raw=self.call(self.client.quote_data,groups,kind="quote")
        received=now_ist().isoformat(); result={}
        if self.store:
            self.store.put_record("market_events",f"quote:{received}:{uuid.uuid4().hex}",
                {"event_type":"quote_snapshot","received_at":received,"sequence_status":"unavailable",
                 "raw":raw,"source":"dhan_quote_snapshot"})
        for c in contracts:
            q=raw.get(c["exchange"]+"_FNO",{}).get(c["security_id"],{})
            if not q: continue
            bids=[b for b in q.get("depth",{}).get("buy",[]) if b.get("price",0)>0]
            asks=[a for a in q.get("depth",{}).get("sell",[]) if a.get("price",0)>0]
            bid=max(bids,key=lambda x:x["price"]) if bids else {}
            ask=min(asks,key=lambda x:x["price"]) if asks else {}
            stamp=exchange_timestamp(q.get("last_trade_time"))
            result[c["contract_id"]]={**c,"timestamp":received,"exchange_timestamp":stamp,
                "last_trade_timestamp":stamp,"quote_update_timestamp":None,
                "source":"dhan_quote","bid":float(bid.get("price",0)),"bid_qty":int(bid.get("quantity",0)),
                "ask":float(ask.get("price",0)),"ask_qty":int(ask.get("quantity",0)),
                "ltp":q.get("last_price"),"volume":q.get("volume"),"oi":q.get("oi")}
        return result

    def candles(self,symbol,start,end,cache_seconds=30,cancel=None):
        under=next(x for x in self.underlyings() if x["symbol"]==symbol)
        data=self.call(self.client.intraday_minute_data,under["security_id"],"IDX_I","INDEX",str(start),str(end),1,False,cache_seconds=cache_seconds,cancel=cancel)
        fields=("timestamp","open","high","low","close","volume")
        if not data.get("timestamp"): return pd.DataFrame(columns=[*fields,"symbol"])
        if any(len(data.get(k,[]))!=len(data["timestamp"]) for k in fields): raise ValueError("Incomplete underlying candles")
        frame=pd.DataFrame({k:data[k] for k in fields})
        frame["timestamp"]=pd.to_datetime(frame.timestamp,unit="s",utc=True).dt.tz_convert("Asia/Kolkata")
        frame["symbol"]=symbol
        return frame.drop_duplicates("timestamp").sort_values("timestamp")

    def contract_candles(self,contract,start,end):
        if not contract.get("identity_verified"): raise ValueError("Unverified option contract")
        data=self.call(self.client.intraday_minute_data,contract["security_id"],contract["exchange"]+"_FNO",
                       "OPTIDX",str(start),str(end),1,True,cache_seconds=30)
        fields=("timestamp","open","high","low","close","volume")
        stamps=data.get("timestamp",[])
        if not stamps: return pd.DataFrame(columns=fields)
        if any(len(data.get(k,[]))!=len(stamps) for k in fields): raise ValueError("Incomplete option candle arrays")
        frame=pd.DataFrame({k:data[k] for k in fields})
        frame["timestamp"]=pd.to_datetime(frame.timestamp,unit="s",utc=True).dt.tz_convert("Asia/Kolkata")
        if frame.timestamp.duplicated().any(): raise ValueError("Duplicate option candle timestamps")
        return frame.sort_values("timestamp")
