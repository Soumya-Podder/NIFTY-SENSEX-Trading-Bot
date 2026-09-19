"""Entry-quality learning from causal, net-cost outcomes. No order authority."""
import hashlib
import json
import math
import threading
import asyncio
from datetime import timedelta
from typing import Optional
import numpy as np
import pandas as pd
import httpx
from .session import now_ist, local_time
from .config import settings
from .learning_validation import VERSION as GUARD_VERSION, MIN_TRAIN, MIN_TEST, MIN_DAYS, replay_evidence
from .provenance import has_synthetic_options

SCHEMA = "entry_features_v1"
FEATURES = ("adx", "atr_pct", "vwap_dist_atr", "relative_volume", "ema_slope_atr",
            "session_minute", "option_delta", "spread_pct", "rsi", "stop_pct", "option_atr_pct", "is_put")


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def extract_features(row, signal, contract, now):
    """Caller supplies a completed causal row; missing volume/Greeks stay missing."""
    atr, close = number(row.get("atr")), number(row.get("close"))
    def ratio(a, b):
        a, b = number(a), number(b)
        return a / b if a is not None and b is not None and b > 0 else None
    price = contract.get("ask", contract.get("close"))
    stamp = local_time(now)
    values = dict(adx=number(row.get("adx")), atr_pct=ratio(atr, close),
        vwap_dist_atr=number(row.get("vwap_distance_atr")), relative_volume=number(row.get("relative_volume")),
        ema_slope_atr=number(row.get("ema_slope_atr")), session_minute=stamp.hour*60+stamp.minute-555,
        option_delta=number(contract.get("delta")), spread_pct=number(contract.get("spread_pct")),
        rsi=number(row.get("rsi")), stop_pct=number(signal.get("stop_percent")),
        option_atr_pct=ratio(signal.get("option_atr"), price), is_put=int(signal["option_type"] == "PUT"))
    return {"schema": SCHEMA, "observed_at": stamp.isoformat(), "bar_at": str(row.get("timestamp")), "values": values}


def scope(trade):
    return "|".join(str(trade.get(k) or "unknown") for k in ("symbol", "strategy_version", "exit_policy"))


class MLTradeQualityModel:
    """Regularized logistic probability estimate; portable JSON, no pickle loading."""
    def __init__(self, artifact):
        self.artifact = artifact

    @staticmethod
    def matrix(features):
        return np.array([[np.nan if number(f["values"].get(k)) is None else float(f["values"][k]) for k in FEATURES] for f in features])

    @classmethod
    def fit(cls, features, labels):
        from sklearn.linear_model import LogisticRegression
        x = cls.matrix(features)
        medians = [float(np.median(x[np.isfinite(x[:, i]), i])) if np.isfinite(x[:, i]).any() else 0. for i in range(len(FEATURES))]
        z = np.concatenate((np.where(np.isnan(x), medians, x), np.isnan(x).astype(float)), axis=1)
        mean, scale = z.mean(axis=0), z.std(axis=0)
        scale[scale == 0] = 1
        model = LogisticRegression(C=.1, max_iter=1000, random_state=17).fit((z-mean)/scale, labels)
        return cls({"schema": SCHEMA, "features": list(FEATURES), "medians": medians,
                    "mean": mean.tolist(), "scale": scale.tolist(), "coef": model.coef_[0].tolist(),
                    "intercept": float(model.intercept_[0]), "threshold": .55,
                    "algorithm": "regularized_logistic_regression", "label": "completed_net_pnl_positive"})

    def predict(self, feature):
        if feature.get("schema") != SCHEMA:
            raise ValueError("Entry feature schema mismatch")
        if sum(number(feature.get("values", {}).get(k)) is not None for k in FEATURES) < 6:
            raise ValueError("Insufficient observed entry features")
        a = self.artifact
        x = self.matrix([feature])[0]
        z = np.concatenate((np.where(np.isnan(x), a["medians"], x), np.isnan(x).astype(float)))
        score = float(np.dot((z-np.array(a["mean"]))/a["scale"], a["coef"]) + a["intercept"])
        return 1/(1+math.exp(-max(-700, min(700, score))))


def metrics(trades):
    values = [float(t["pnl"]) for t in trades]
    losses = -sum(v for v in values if v < 0)
    gains = sum(v for v in values if v > 0)
    return {"trades": len(values), "days": len({str(t["entry_ts"])[:10] for t in trades}),
            "net_pnl": sum(values), "expectancy": sum(values)/len(values) if values else 0,
            "profit_factor": gains/losses if losses else None,
            "wins": sum(v > 0 for v in values), "losses": sum(v < 0 for v in values)}


class LearningService:
    _locks = {}
    _guard = threading.Lock()

    def __init__(self, store):
        self.store = store
        with self._guard:
            self.lock = self._locks.setdefault(str(store.path), threading.Lock())

    def train(self, report, run_id, replay=None):
        """One fixed model/threshold, purged 70/30 day split, optional FULL replay.

        A filter-only result cannot auto-promote: vetoes change later account
        admission. Full replay must re-run sizing, fees, daily locks and exits.
        """
        if not self.lock.acquire(blocking=False):
            return {"status": "BUSY"}
        try:
            return self._train(report, run_id, replay)
        except Exception as exc:
            failed = {"run_id": run_id, "created_at": now_ist().isoformat(), "status": "TRAINING_FAILED",
                      "models": [], "error_type": type(exc).__name__,
                      "reason": "Training did not finish; reserved holdouts remain consumed."}
            self.store.save_bundle([("ml_runs", run_id, failed), ("ml_state", "latest", failed)])
            raise
        finally:
            self.lock.release()

    def _train(self, report, run_id, replay):
        now = now_ist()
        outcomes = report.get("trades", [])
        synthetic = has_synthetic_options(report)
        eligible = []
        for t in outcomes:
            f = t.get("entry_features") or {}
            try:
                valid = (not synthetic and report.get("learning_eligible") is not False and not report.get("estimation")
                    and t.get("learning_eligible") is not False and not t.get("estimated_exit")
                    and report.get("quality") in {"verified", "research_net"} and report.get("pnl_basis", "net") == "net" and t.get("quality") in {"verified", "research_net"} and not t.get("partial") and
                    f.get("schema") == SCHEMA and isinstance(f.get("values"), dict) and
                    sum(number(f["values"].get(k)) is not None for k in FEATURES) >= 6 and
                    all(number(t.get(k)) is not None for k in ("pnl", "gross_pnl", "costs")) and t["costs"] >= 0 and
                    abs(t["pnl"]-(t["gross_pnl"]-t["costs"])) < .01 and
                    local_time(f["bar_at"]) + timedelta(minutes=1) <= local_time(f["observed_at"]) <= local_time(t["entry_ts"]) <= local_time(t["exit_ts"]) and
                    local_time(t["entry_ts"]) < local_time(t.get("outcome_observed_at", t["exit_ts"])) < now)
            except (ValueError, TypeError, KeyError):
                valid = False
            if valid:
                eligible.append(t)
        result = {"run_id": run_id, "created_at": now.isoformat(), "status": "INSUFFICIENT_EVIDENCE",
                  "eligible_trades": len(eligible), "excluded_trades": len(outcomes)-len(eligible), "models": [],
                  "input_report_quality": report.get("quality"), "source_report_id": report.get("run_id", run_id),
                  "dataset_id": report.get("config", {}).get("dataset_id"),
                  "dataset_fingerprint": hashlib.sha256(json.dumps(eligible, sort_keys=True, default=str).encode()).hexdigest(),
                  "reason": "Require causal entry features, completed verified net-cost trades and independent session history"}
        if synthetic:
            result.update(status="REJECTED_SYNTHETIC_DATA", reason="Legacy synthetic option outcomes are quarantined from training and promotion")
        for key in sorted({scope(t) for t in eligible}):
            group = sorted([t for t in eligible if scope(t) == key], key=lambda t: local_time(t["entry_ts"]))
            # Deduplicate positions; reports can contain repeated partial fills.
            unique = {(str(t.get("signal_id", t.get("id"))), str(t["entry_ts"]), str(t.get("contract_id"))): t for t in group}
            group = sorted(unique.values(), key=lambda t: local_time(t["entry_ts"]))
            days = sorted({str(t["entry_ts"])[:10] for t in group})
            n_group = len(group)
            min_days = MIN_DAYS
            if len(days) < min_days:
                result["models"].append({"scope": key, "status": "INSUFFICIENT_SESSIONS", "days": len(days)})
                continue
            boundary = days[int(len(days)*.7)]
            train = [t for t in group if str(t.get("outcome_observed_at",t["exit_ts"]))[:10] < boundary]
            test = [t for t in group if str(t["entry_ts"])[:10] >= boundary]
            min_train = MIN_TRAIN
            min_test = MIN_TEST
            if len(train) < min_train or len(test) < min_test or len({t["pnl"] > 0 for t in train}) != 2:
                result["models"].append({"scope": key, "status": "INSUFFICIENT_TRADES", "train": len(train), "test": len(test)})
                continue
            test_end = max(str(t["exit_ts"])[:10] for t in test)
            if not self.store.reserve_ml_holdout(key, boundary, test_end, run_id):
                result["models"].append({"scope": key, "status": "HOLDOUT_ALREADY_USED", "reason": "New unseen test sessions required; no repeated tuning on the same holdout"})
                continue
            model = MLTradeQualityModel.fit([t["entry_features"] for t in train], [t["pnl"] > 0 for t in train])
            a = model.artifact
            a.update(scope=key, trained_through=max(str(t["exit_ts"]) for t in train), test_from=boundary, test_end=test_end)
            predicted = [model.predict(t["entry_features"]) for t in test]
            selected = [t for t, p in zip(test, predicted) if p >= a["threshold"]]
            evaluated, baseline = metrics(selected), metrics(test)
            evaluated["brier"] = sum((p-int(t["pnl"] > 0))**2 for t, p in zip(test, predicted))/len(test)
            train_predictions = [model.predict(t["entry_features"]) for t in train]
            train_brier = sum((p-int(t["pnl"] > 0))**2 for t, p in zip(train, train_predictions))/len(train)
            item = {"scope": key, "status": "REJECTED", "train_trades": len(train), "test_trades": len(test),
                    "test_from": boundary, "test_end": test_end, "filter_metrics": evaluated, "baseline": baseline,
                    "train_brier": train_brier, "holdout_brier_gap": evaluated["brier"] - train_brier,
                    "threshold": a["threshold"], "fitted": True, "guard_version": GUARD_VERSION, "reason": "Holdout filter evidence failed"}
            
            min_eval_trades = MIN_TEST
            min_eval_days = 10
            min_eval_losses = 3
            qualifies = evaluated["trades"] >= min_eval_trades and evaluated["days"] >= min_eval_days and evaluated["losses"] >= min_eval_losses and evaluated["profit_factor"] > 1.25 and evaluated["expectancy"] > 0
            if qualifies:
                item.update(status="FILTER_VALIDATED_REPLAY_REQUIRED", reason="Full account replay required before automatic promotion")
                if replay:
                    candidate_run, baseline_run = replay(a, boundary, test_end)
                    candidate_trades = candidate_run.get("trades", [])
                    m, base = metrics(candidate_trades), metrics(baseline_run.get("trades", []))
                    guard = replay_evidence(candidate_run, baseline_run, boundary, test_end, 1 + len(self.store.list_records("ml_runs", 10000)))
                    item.update(replay_metrics=m, replay_baseline=base, overfitting_checks=guard)
                    if (guard["passed"] and candidate_run.get("quality") in {"verified", "research_net"} and baseline_run.get("quality") in {"verified", "research_net"} and not candidate_run.get("issues") and not baseline_run.get("issues") and
                        m["trades"] >= min_eval_trades and m["days"] >= min_eval_days and m["losses"] >= 1 and m["profit_factor"] > 1.1 and
                        m["expectancy"] > 0 and m["net_pnl"] > base["net_pnl"]):
                        identifier = hashlib.sha256(json.dumps(a, sort_keys=True).encode()).hexdigest()[:24]
                        effective = (now.date()+timedelta(days=1)).isoformat()
                        record = {**item, "id": identifier, "artifact": a, "status": "VALIDATED_PENDING_SESSION",
                                  "effective_from": effective, "expires_at": (now+timedelta(days=30)).isoformat(),
                                  "created_at": now.isoformat(), "run_id": run_id, "evidence": "UNVALIDATED_PAPER",
                                  "reason": "Passed unseen full account replay; eligible next session"}
                        self.store.save_bundle([("ml_models", identifier, record), ("ml_champions", key, {"model_id": identifier})])
                        item = {k: v for k, v in record.items() if k != "artifact"}
                    else:
                        item.update(status="REJECTED_REPLAY", reason="Full account replay did not demonstrate sufficient net improvement")
            result["models"].append(item)
        if any(m["status"] == "VALIDATED_PENDING_SESSION" for m in result["models"]):
            result.update(status="VALIDATED_PENDING_SESSION", reason="Validated models are scheduled for a later session")
        elif result["models"]:
            result.update(status="NO_PROMOTION", reason="Inspect per-scope validation results")
        self.store.save_bundle([("ml_runs", run_id, result), ("ml_state", "latest", result)])
        return result

    def freeze(self, now):
        day = str(local_time(now).date())
        existing = self.store.get_record("ml_sessions", day)
        if existing is not None:
            return existing
        models = {}
        for pointer in self.store.list_records("ml_champions", 100):
            record = self.store.get_record("ml_models", pointer["model_id"], {})
            if record.get("overfitting_checks", {}).get("version") == GUARD_VERSION and record.get("overfitting_checks", {}).get("passed") and record.get("effective_from", "9999") <= day and record.get("expires_at", "") > local_time(now).isoformat():
                models[record["scope"]] = record["id"]
        frozen = {"session": day, "models": models, "frozen_at": local_time(now).isoformat()}
        self.store.put_record("ml_sessions", day, frozen)
        return frozen

    def score(self, signal, frozen):
        identifier = frozen.get("models", {}).get(scope(signal))
        if not identifier:
            return {"status": "NO_VALIDATED_MODEL", "probability": None, "allowed": True,
                    "reason": "Baseline paper observation; no learned probability claimed"}
        record = self.store.get_record("ml_models", identifier, {})
        if record.get("overfitting_checks", {}).get("version") != GUARD_VERSION or not record.get("overfitting_checks", {}).get("passed"):
            return {"status": "MODEL_VALIDATION_REQUIRED", "probability": None, "allowed": False}
        if record.get("expires_at", "") <= now_ist().isoformat():
            return {"status": "MODEL_EXPIRED", "probability": None, "allowed": False}
        try:
            probability = MLTradeQualityModel(record["artifact"]).predict(signal["entry_features"])
            threshold = record["artifact"]["threshold"]
            return {"status": "PASS" if probability >= threshold else "REJECTED", "allowed": probability >= threshold,
                    "model_id": identifier, "probability": probability, "threshold": threshold,
                    "label": "Estimated probability of positive net exit; not a guarantee"}
        except (KeyError, ValueError, TypeError):
            return {"status": "MODEL_ERROR", "probability": None, "allowed": False}

    def status(self):
        models = [{**{k: v for k, v in m.items() if k != "artifact"},
                   "feature_coefficients": dict(zip(FEATURES, m["artifact"]["coef"][:len(FEATURES)]))}
                  for m in self.store.list_records("ml_models", 30)]
        return {"schema": SCHEMA, "features": list(FEATURES), "models": models,
                "latest_training": self.store.get_record("ml_state", "latest", {"status": "NOT_TRAINED"}),
                "session": self.store.get_record("ml_sessions", str(now_ist().date()), {}),
                "evidence": "UNVALIDATED_PAPER", "training": self.lock.locked()}


# ──────────────────────────────────────────────────────────────
# LLM Integration (OpenRouter)
# ──────────────────────────────────────────────────────────────

LLM_SYSTEM_PROMPT = """You are a quantitative trading analyst for an Indian index options paper trading system.
Your analyses are OBSERVATIONAL ONLY — you have no order authority, no risk control, and no execution capability.
All outputs must be structured JSON matching the requested schema. Be concise, specific, and evidence-based.
Never fabricate data. If data is insufficient, say so explicitly."""

MARKET_ANALYST_PROMPT = """Analyze the current market state for NIFTY/SENSEX index options trading.
Input includes: session phase, spot levels, regime classification, key levels (ORB high/low, VWAP, EMAs),
option chain snapshot (ATM straddle, IV, Greeks), and recent price action.

Return JSON with:
{
  "regime_assessment": "trending_up|trending_down|ranging|volatile|transitioning",
  "key_observations": ["specific, actionable observation 1", "..."],
  "risk_factors": ["specific risk 1", "..."],
  "opportunity_areas": ["specific setup condition 1", "..."],
  "confidence": 0.0-1.0,
  "data_quality": "complete|partial|insufficient"
}"""

FAILURE_ANALYST_PROMPT = """Analyze losing trades to identify recurring failure patterns.
Input: list of trades with entry/exit details, PnL, exit reason, market context, agent contexts.

Return JSON with:
{
  "patterns": [
    {"pattern": "descriptive name", "frequency": int, "total_pnl": float, "typical_exit_reason": "string",
     "market_conditions": "string", "actionable_insight": "string"}
  ],
  "regime_specific": {"trending": [...], "ranging": [...], "volatile": [...]},
  "top_loss_drivers": ["driver 1", "driver 2"],
  "data_sufficiency": "adequate|limited|insufficient"
}"""

HYPOTHESIS_GENERATOR_PROMPT = """Generate research hypotheses from market analysis and failure patterns.
Input: market analyst output, failure analyst output, current strategy parameters.

Return JSON with:
{
  "hypotheses": [
    {"hypothesis": "specific testable statement", "rationale": "why this might work",
     "proposed_test": "backtest configuration or parameter change",
     "expected_impact": "positive|negative|neutral", "confidence": 0.0-1.0,
     "priority": "high|medium|low"}
  ],
  "parameter_suggestions": {"param_name": "suggested_value_or_range"},
  "requires_backtest": true
}"""

TRADE_ANALYST_PROMPT = """Analyze a completed trade for thesis validation and exit quality.
Input: trade details (entry/exit, PnL, Greeks at entry, market context, exit reason).

Return JSON with:
{
  "thesis_validated": true|false,
  "entry_quality": "good|fair|poor",
  "exit_quality": "good|fair|poor",
  "key_observations": ["observation 1", "..."],
  "lessons": ["lesson 1", "..."],
  "would_repeat": true|false
}"""


class LLMClient:
    """Async OpenRouter client with retries, timeout, and structured output parsing."""

    def __init__(self, api_key: str, model: str, timeout: float = 30.0, max_retries: int = 2):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        async with self._lock:
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(
                    base_url="https://openrouter.ai/api/v1",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    timeout=httpx.Timeout(self.timeout),
                )
            return self._client

    async def close(self):
        async with self._lock:
            if self._client and not self._client.is_closed:
                await self._client.aclose()
                self._client = None

    async def chat_completion(
        self,
        messages: list[dict],
        response_format: Optional[dict] = None,
        temperature: float = 0.3,
        max_tokens: int = 1500,
    ) -> dict:
        """Call OpenRouter chat completion with retries. Returns parsed JSON or raises."""
        if not self.api_key:
            raise ValueError("OpenRouter API key not configured")

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        client = await self._get_client()
        last_exc = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = await client.post("/chat/completions", json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return json.loads(content)
            except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
                continue
        raise RuntimeError(f"LLM call failed after {self.max_retries + 1} attempts: {last_exc}")

    async def analyze_market(self, market_state: dict) -> dict:
        messages = [
            {"role": "system", "content": LLM_SYSTEM_PROMPT},
            {"role": "user", "content": MARKET_ANALYST_PROMPT + "\n\nMarket State:\n" + json.dumps(market_state, default=str)},
        ]
        return await self.chat_completion(messages, response_format={"type": "json_object"})

    async def analyze_failures(self, trades: list[dict]) -> dict:
        messages = [
            {"role": "system", "content": LLM_SYSTEM_PROMPT},
            {"role": "user", "content": FAILURE_ANALYST_PROMPT + "\n\nTrades:\n" + json.dumps(trades, default=str)},
        ]
        return await self.chat_completion(messages, response_format={"type": "json_object"})

    async def generate_hypotheses(self, market_analysis: dict, failure_analysis: dict, strategy_params: dict) -> dict:
        messages = [
            {"role": "system", "content": LLM_SYSTEM_PROMPT},
            {"role": "user", "content": HYPOTHESIS_GENERATOR_PROMPT + "\n\nMarket Analysis:\n" + json.dumps(market_analysis, default=str)
             + "\n\nFailure Analysis:\n" + json.dumps(failure_analysis, default=str)
             + "\n\nStrategy Parameters:\n" + json.dumps(strategy_params, default=str)},
        ]
        return await self.chat_completion(messages, response_format={"type": "json_object"})

    async def analyze_trade(self, trade: dict) -> dict:
        messages = [
            {"role": "system", "content": LLM_SYSTEM_PROMPT},
            {"role": "user", "content": TRADE_ANALYST_PROMPT + "\n\nTrade:\n" + json.dumps(trade, default=str)},
        ]
        return await self.chat_completion(messages, response_format={"type": "json_object"})


def create_llm_client() -> Optional[LLMClient]:
    """Factory: returns LLMClient if enabled and configured, else None."""
    if not settings.llm_enabled or not settings.openrouter_api_key:
        return None
    return LLMClient(
        api_key=settings.openrouter_api_key,
        model=settings.openrouter_model,
        timeout=float(settings.llm_timeout_seconds),
        max_retries=settings.llm_max_retries,
    )


# ──────────────────────────────────────────────────────────────
# Enhanced Analyst Classes (LLM-powered when available)
# ──────────────────────────────────────────────────────────────

class MarketAnalyst:
    """Market regime and opportunity analysis. LLM-enhanced when configured."""
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client

    def analyze(self, state: dict) -> dict:
        base = {"role": "market_analyst", "authority": "none", "llm_enhanced": self.llm is not None}
        if not self.llm:
            return {**base, "observations": ["LLM not configured"], "regime_assessment": "unknown", "confidence": 0.0}
        try:
            # Run async in sync context for compatibility
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(self.llm.analyze_market(state))
            finally:
                loop.close()
            return {**base, **result}
        except Exception as exc:
            return {**base, "observations": [f"LLM error: {exc}"], "regime_assessment": "error", "confidence": 0.0}


class TradeAnalyst:
    """Post-trade thesis validation and exit quality analysis. LLM-enhanced when configured."""
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client

    def analyze(self, trade: dict) -> dict:
        base = {"role": "trade_analyst", "authority": "none", "llm_enhanced": self.llm is not None}
        if not self.llm:
            return {**base, "observations": ["LLM not configured"], "thesis_validated": None}
        try:
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(self.llm.analyze_trade(trade))
            finally:
                loop.close()
            return {**base, **result}
        except Exception as exc:
            return {**base, "observations": [f"LLM error: {exc}"], "thesis_validated": None}


class FailureAnalyst:
    """Losing trade pattern detection. LLM-enhanced when configured."""
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client

    def analyze(self, trades: list[dict]) -> dict:
        base = {"role": "failure_analyst", "authority": "none", "llm_enhanced": self.llm is not None}
        if not self.llm or not trades:
            return {**base, "patterns": [], "data_sufficiency": "insufficient"}
        try:
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(self.llm.analyze_failures(trades))
            finally:
                loop.close()
            return {**base, **result}
        except Exception as exc:
            return {**base, "patterns": [], "data_sufficiency": f"error: {exc}"}


class HypothesisGenerator:
    """Research hypothesis generation from analysis. LLM-enhanced when configured."""
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client

    def generate(self, analysis: dict) -> dict:
        base = {"role": "hypothesis_generator", "authority": "none", "requires_backtest": True, "llm_enhanced": self.llm is not None}
        if not self.llm:
            return {**base, "hypotheses": ["LLM not configured"]}
        try:
            market = analysis.get("market_analysis", {})
            failure = analysis.get("failure_analysis", {})
            strategy = analysis.get("strategy_params", {})
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(self.llm.generate_hypotheses(market, failure, strategy))
            finally:
                loop.close()
            return {**base, **result}
        except Exception as exc:
            return {**base, "hypotheses": [f"LLM error: {exc}"]}


# Backward-compatible stubs (used when LLM not configured)
class _StubMarketAnalyst:
    def analyze(self, state): return {"role": "market_analyst", "observations": [], "authority": "none"}
class _StubTradeAnalyst:
    def analyze(self, trade): return {"role": "trade_analyst", "observations": [], "authority": "none"}
class _StubFailureAnalyst:
    def analyze(self, trades): return {"role": "failure_analyst", "patterns": [], "authority": "none"}
class _StubHypothesisGenerator:
    def generate(self, analysis): return {"role": "hypothesis_generator", "hypotheses": [], "requires_backtest": True, "authority": "none"}


def get_analysts() -> dict:
    """Factory returning appropriate analyst instances based on LLM config."""
    llm = create_llm_client()
    if llm:
        return {
            "market": MarketAnalyst(llm),
            "trade": TradeAnalyst(llm),
            "failure": FailureAnalyst(llm),
            "hypothesis": HypothesisGenerator(llm),
            "llm_client": llm,
        }
    return {
        "market": _StubMarketAnalyst(),
        "trade": _StubTradeAnalyst(),
        "failure": _StubFailureAnalyst(),
        "hypothesis": _StubHypothesisGenerator(),
        "llm_client": None,
    }
