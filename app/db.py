"""SQLite persistence for sandbox workflow state and the tamper-evident audit log.

Source evidence (the CSV records) is never stored here and never modified:
only case status, proposed actions, sandbox follow-ups and audit entries.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

_LOCK = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    case_id     TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS actions (
    action_id        TEXT PRIMARY KEY,
    action_type      TEXT NOT NULL,
    case_id          TEXT NOT NULL,
    target           TEXT NOT NULL,
    amount           INTEGER NOT NULL,
    payload          TEXT NOT NULL,
    status           TEXT NOT NULL,
    proposed_by      TEXT NOT NULL,
    proposed_at      TEXT NOT NULL,
    prev_case_status TEXT NOT NULL,
    decided_by       TEXT,
    decided_role     TEXT,
    decided_at       TEXT,
    decision_note    TEXT,
    executed_at      TEXT,
    result           TEXT
);
CREATE TABLE IF NOT EXISTS followups (
    followup_id  TEXT PRIMARY KEY,
    action_id    TEXT NOT NULL,
    case_id      TEXT NOT NULL,
    courier      TEXT NOT NULL,
    amount       INTEGER NOT NULL,
    draft_text   TEXT NOT NULL,
    status       TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    actor        TEXT NOT NULL,
    role         TEXT NOT NULL,
    event        TEXT NOT NULL,
    object_type  TEXT NOT NULL,
    object_id    TEXT NOT NULL,
    outcome      TEXT NOT NULL,
    evidence_ids TEXT NOT NULL,
    details      TEXT NOT NULL,
    prev_hash    TEXT NOT NULL,
    hash         TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    """Open a connection, commit on success, and always close it."""
    conn = sqlite3.connect(config.db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init() -> None:
    with _LOCK, connect() as conn:
        conn.executescript(SCHEMA)


def reset_sandbox_state() -> None:
    """Clear derived workflow state when a dataset is (re)loaded. The audit log is kept."""
    with _LOCK, connect() as conn:
        conn.execute("DELETE FROM cases")
        conn.execute("DELETE FROM actions")
        conn.execute("DELETE FROM followups")


def query(sql: str, params: tuple = ()) -> list[dict]:
    with _LOCK, connect() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def execute(sql: str, params: tuple = ()) -> None:
    with _LOCK, connect() as conn:
        conn.execute(sql, params)


def _entry_hash(prev_hash: str, fields: dict) -> str:
    canonical = json.dumps(fields, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()


def audit(actor: str, role: str, event: str, object_type: str, object_id: str,
          outcome: str, evidence_ids: list[str] | None = None, details: dict | None = None) -> dict:
    """Append one entry to the hash-chained audit log and return it."""
    with _LOCK, connect() as conn:
        last = conn.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        prev_hash = last["hash"] if last else "GENESIS"
        fields = {
            "ts": now(),
            "actor": actor,
            "role": role,
            "event": event,
            "object_type": object_type,
            "object_id": object_id,
            "outcome": outcome,
            "evidence_ids": json.dumps(evidence_ids or []),
            "details": json.dumps(details or {}, sort_keys=True),
        }
        h = _entry_hash(prev_hash, fields)
        cur = conn.execute(
            "INSERT INTO audit (ts, actor, role, event, object_type, object_id, outcome, evidence_ids, details, prev_hash, hash)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (fields["ts"], actor, role, event, object_type, object_id, outcome,
             fields["evidence_ids"], fields["details"], prev_hash, h),
        )
        return {"seq": cur.lastrowid, **fields, "prev_hash": prev_hash, "hash": h}


def audit_entries(limit: int | None = None) -> list[dict]:
    sql = "SELECT * FROM audit ORDER BY seq DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = query(sql)
    for r in rows:
        r["evidence_ids"] = json.loads(r["evidence_ids"])
        r["details"] = json.loads(r["details"])
    return rows


def verify_audit_chain() -> dict:
    """Recompute every hash; any edited or deleted row breaks the chain."""
    rows = query("SELECT * FROM audit ORDER BY seq ASC")
    prev = "GENESIS"
    for r in rows:
        fields = {k: r[k] for k in ("ts", "actor", "role", "event", "object_type", "object_id",
                                    "outcome", "evidence_ids", "details")}
        if r["prev_hash"] != prev or _entry_hash(prev, fields) != r["hash"]:
            return {"valid": False, "entries": len(rows), "broken_at_seq": r["seq"]}
        prev = r["hash"]
    return {"valid": True, "entries": len(rows), "head_hash": prev}
