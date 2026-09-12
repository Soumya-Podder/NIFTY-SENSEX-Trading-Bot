import json
import sqlite3
import time
import zlib
import math
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class Store:
    def __init__(self, path="trading_bot.db"):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("CREATE TABLE IF NOT EXISTS records(namespace TEXT NOT NULL,key TEXT NOT NULL,payload TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(namespace,key))")
            c.execute("CREATE TABLE IF NOT EXISTS history_cache(key TEXT PRIMARY KEY,payload BLOB NOT NULL,expires_at REAL NOT NULL)")
            c.execute("CREATE TABLE IF NOT EXISTS history_ranges(key TEXT PRIMARY KEY,family TEXT NOT NULL,start TEXT NOT NULL,end TEXT NOT NULL,fields TEXT NOT NULL)")
            c.execute("CREATE INDEX IF NOT EXISTS history_ranges_family ON history_ranges(family,start,end)")
            c.execute("CREATE TABLE IF NOT EXISTS decisions(id INTEGER PRIMARY KEY,ts TEXT,strategy_id TEXT,regime TEXT,setup_id TEXT,direction TEXT,decision TEXT,rejection_reason TEXT,payload_json TEXT)")
            c.execute("""CREATE TABLE IF NOT EXISTS learning_policies(
                agent TEXT PRIMARY KEY,
                version INTEGER NOT NULL,
                policy_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS learning_ledger(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                source TEXT NOT NULL,
                agent TEXT NOT NULL,
                policy_before INTEGER NOT NULL,
                policy_after INTEGER NOT NULL,
                sample_count INTEGER NOT NULL,
                wins INTEGER NOT NULL,
                losses INTEGER NOT NULL,
                pnl REAL NOT NULL,
                loss_pattern TEXT,
                proposed_adjustment TEXT NOT NULL,
                adjustment_status TEXT NOT NULL,
                validation_status TEXT NOT NULL,
                baseline_pnl REAL,
                candidate_pnl REAL,
                baseline_expectancy REAL,
                candidate_expectancy REAL,
                validation_samples INTEGER NOT NULL,
                metadata_json TEXT NOT NULL
            )""")

    @contextmanager
    def _conn(self, timeout=30):
        c = sqlite3.connect(self.path, timeout=timeout)
        try:
            c.execute(f"PRAGMA busy_timeout={int(timeout*1000)}")
            with c:
                yield c
        finally:
            c.close()

    def save_decision(self, p):
        with self._conn() as c:
            c.execute("INSERT INTO decisions(ts,strategy_id,regime,setup_id,direction,decision,rejection_reason,payload_json) VALUES(?,?,?,?,?,?,?,?)",
                      (p["timestamp"], p["strategy_id"], p["regime"]["regime"], p["setup"]["setup_id"], p["setup"]["direction"], p["decision"], p.get("rejection_reason"), json.dumps(p)))

    def active_learning_policies(self):
        with self._conn() as c:
            rows = c.execute("SELECT agent, version, policy_json FROM learning_policies").fetchall()
        policies = {}
        for agent, version, payload in rows:
            policy = json.loads(payload)
            # Preserve legacy audit history, but never execute its unvalidated filters.
            if policy.get("validator_version") != 4 or policy.get("validation_status") != "PROMOTED":
                continue
            if not policy.get("reviewed_at") or not policy.get("reviewed_by"):
                continue
            if policy.get("expires_at", "") < datetime.now(timezone.utc).isoformat():
                continue
            from .session import now_ist
            if policy.get("effective_from", "") > now_ist().date().isoformat():
                continue
            policy["version"] = version
            policies[agent] = policy
        return policies

    def record_learning(self, entries, promotions):
        with self._conn() as c:
            for entry in entries:
                c.execute("""INSERT INTO learning_ledger(
                    run_id, recorded_at, source, agent, policy_before, policy_after,
                    sample_count, wins, losses, pnl, loss_pattern,
                    proposed_adjustment, adjustment_status, validation_status,
                    baseline_pnl, candidate_pnl, baseline_expectancy,
                    candidate_expectancy, validation_samples, metadata_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    entry["run_id"], entry["recorded_at"], entry["source"], entry["agent"],
                    entry["policy_before"], entry["policy_after"], entry["sample_count"],
                    entry["wins"], entry["losses"], entry["pnl"], entry.get("loss_pattern"),
                    entry["proposed_adjustment"], entry["adjustment_status"], entry["validation_status"],
                    entry.get("baseline_pnl"), entry.get("candidate_pnl"),
                    entry.get("baseline_expectancy"), entry.get("candidate_expectancy"),
                    entry["validation_samples"], json.dumps(entry.get("metadata", {})),
                ))
            for promotion in promotions:
                c.execute("""INSERT INTO learning_policies(agent, version, policy_json, updated_at)
                    VALUES(?,?,?,?)
                    ON CONFLICT(agent) DO UPDATE SET version=excluded.version,
                    policy_json=excluded.policy_json, updated_at=excluded.updated_at""", (
                    promotion["agent"], promotion["version"], json.dumps(promotion["policy"]), promotion["updated_at"],
                ))

    def learning_snapshot(self):
        with self._conn() as c:
            policies = c.execute("SELECT agent, version, policy_json, updated_at FROM learning_policies").fetchall()
            latest = c.execute("""SELECT l.agent, l.run_id, l.recorded_at, l.policy_before,
                l.policy_after, l.sample_count, l.wins, l.losses, l.pnl,
                l.loss_pattern, l.proposed_adjustment, l.adjustment_status,
                l.validation_status, l.baseline_pnl, l.candidate_pnl,
                l.baseline_expectancy, l.candidate_expectancy, l.validation_samples, l.metadata_json
                FROM learning_ledger l
                INNER JOIN (SELECT agent, MAX(id) AS id FROM learning_ledger GROUP BY agent) x
                ON x.agent=l.agent AND x.id=l.id""").fetchall()
            history = c.execute("""SELECT id, run_id, recorded_at, source, agent,
                policy_before, policy_after, sample_count, wins, losses, pnl,
                loss_pattern, proposed_adjustment, adjustment_status,
                validation_status, baseline_pnl, candidate_pnl,
                baseline_expectancy, candidate_expectancy, validation_samples
                FROM learning_ledger ORDER BY id DESC LIMIT 100""").fetchall()
        state = {}
        for agent, version, payload, updated_at in policies:
            state[agent] = {"agent": agent, "policy_version": version, "policy": json.loads(payload), "updated_at": updated_at}
        latest_fields = ["agent", "run_id", "recorded_at", "policy_before", "policy_after", "sample_count", "wins", "losses", "pnl", "loss_pattern", "proposed_adjustment", "adjustment_status", "validation_status", "baseline_pnl", "candidate_pnl", "baseline_expectancy", "candidate_expectancy", "validation_samples"]
        for values in latest:
            item = dict(zip([*latest_fields,"metadata_json"], values))
            item["metadata"]=json.loads(item.pop("metadata_json"))
            state.setdefault(item["agent"], {"agent": item["agent"], "policy_version": 0, "policy": {}, "updated_at": None})
            state[item["agent"]].update(item)
        history_fields = ["id", "run_id", "recorded_at", "source", "agent", "policy_before", "policy_after", "sample_count", "wins", "losses", "pnl", "loss_pattern", "proposed_adjustment", "adjustment_status", "validation_status", "baseline_pnl", "candidate_pnl", "baseline_expectancy", "candidate_expectancy", "validation_samples"]
        return {"agents": state, "history": [dict(zip(history_fields, values)) for values in history]}

    def get_record(self, namespace, key, default=None):
        with self._conn() as c:
            row=c.execute("SELECT payload FROM records WHERE namespace=? AND key=?",(namespace,str(key))).fetchone()
        return json.loads(row[0]) if row else default

    def put_record(self, namespace, key, payload):
        self.save_bundle([(namespace,str(key),payload)])

    def save_bundle(self, items):
        stamp=datetime.now(timezone.utc).isoformat()
        items=list(items)
        account_write=any(namespace=="paper" and key=="account" for namespace,key,_ in items)
        attempts=1 if account_write else 3
        for attempt in range(attempts):
            try:
                with self._conn(timeout=.25 if account_write else 30) as c:
                    c.execute("BEGIN IMMEDIATE")
                    for namespace,key,payload in items:
                        c.execute("INSERT INTO records VALUES(?,?,?,?) ON CONFLICT(namespace,key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",
                                  (namespace,str(key),json.dumps(json_safe(payload),allow_nan=False),stamp))
                return
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < attempts-1:
                    time.sleep(0.25 * (attempt + 1))
                    continue
                raise

    def list_records(self, namespace, limit=100):
        with self._conn() as c:
            rows=c.execute("SELECT payload FROM records WHERE namespace=? ORDER BY updated_at DESC,key DESC LIMIT ?",(namespace,limit)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def reserve_ml_holdout(self, scope, start, end, run_id):
        """Reserve unseen symbol history atomically, including across app processes."""
        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            rows = c.execute("SELECT key,payload FROM records WHERE namespace='ml_holdouts'").fetchall()
            for key, payload in rows:
                old = json.loads(payload)
                if key.split("|")[0] == scope.split("|")[0] and old.get("test_end", "") >= start:
                    return False
            stamp = datetime.now(timezone.utc).isoformat()
            payload = json.dumps({"scope": scope, "test_from": start, "test_end": end, "run_id": run_id})
            c.execute("INSERT INTO records VALUES('ml_holdouts',?,?,?) ON CONFLICT(namespace,key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at", (scope, payload, stamp))
        return True

    def cache_get(self, key,include_expired=False):
        with self._conn() as c:
            row=c.execute("SELECT payload FROM history_cache WHERE key=? AND (? OR expires_at=0 OR expires_at>?)",(key,include_expired,time.time())).fetchone()
        return json.loads(zlib.decompress(row[0])) if row else None

    def index_history(self,key,family,start,end,fields):
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO history_ranges VALUES(?,?,?,?,?)",(key,family,start,end,json.dumps(fields)))

    def history_ranges(self,family,start,end,fields,include_expired=False):
        with self._conn() as c:
            rows=c.execute("SELECT r.key,r.start,r.end,r.fields FROM history_ranges r JOIN history_cache h ON h.key=r.key WHERE r.family=? AND r.start<? AND r.end>? AND (? OR h.expires_at=0 OR h.expires_at>?) ORDER BY r.start,r.end DESC",(family,end,start,include_expired,time.time())).fetchall()
        return [(key,a,b) for key,a,b,available in rows if set(fields)<=set(json.loads(available))]

    def cache_put(self, key, payload, ttl=86400*30):
        blob=zlib.compress(json.dumps(json_safe(payload),allow_nan=False).encode(),6)
        with self._conn() as c:
            c.execute("INSERT INTO history_cache VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,expires_at=excluded.expires_at",(key,blob,0 if ttl<0 else time.time()+ttl))

    def retain_cache(self,key):
        with self._conn() as c:
            c.execute("UPDATE history_cache SET expires_at=0 WHERE key=?",(key,))

    def cache_summary(self):
        with self._conn() as c:
            row=c.execute("SELECT COUNT(*),COALESCE(SUM(LENGTH(payload)),0),COALESCE(SUM(expires_at=0),0) FROM history_cache").fetchone()
        return {"responses":row[0],"compressed_bytes":row[1],"retained_responses":row[2],
                "storage":"backend/trading_bot.db · compressed SQLite history_cache", "retention":"Historical backtest responses retained without automatic expiry; quotes and metadata retain their refresh rules"}

    def record_event(self, event):
        self.put_record("events",event["id"],event)

    def pending_paper_feedback(self,limit=100):
        with self._conn() as c:
            rows=c.execute("""SELECT e.payload FROM records e WHERE e.namespace='episodes'
                AND NOT EXISTS (SELECT 1 FROM records l WHERE l.namespace='learning_runs' AND l.key='paper:'||e.key)
                ORDER BY e.updated_at LIMIT ?""",(limit,)).fetchall()
        return [json.loads(row[0]) for row in rows]


def json_safe(value):
    if isinstance(value,dict): return {str(k):json_safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [json_safe(v) for v in value]
    if hasattr(value,"isoformat"): return value.isoformat()
    if hasattr(value,"item"): return json_safe(value.item())
    if isinstance(value,float) and not math.isfinite(value): return None
    return value
