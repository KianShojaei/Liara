"""SQLite persistence: sessions, timeline, proposals, audit log, incidents, metric snapshots.

Kept deliberately small: a single connection guarded by a lock, JSON payload columns,
and an append-only audit table (no UPDATE/DELETE path exists for it in code).
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY, created_at TEXT NOT NULL, title TEXT, mode TEXT, project_path TEXT, app_name TEXT
);
CREATE TABLE IF NOT EXISTS timeline (
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL, seq INTEGER NOT NULL, ts TEXT NOT NULL,
  kind TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS timeline_session ON timeline(session_id, seq);
CREATE TABLE IF NOT EXISTS proposals (
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  status TEXT NOT NULL, tool TEXT NOT NULL, args TEXT NOT NULL, tier TEXT NOT NULL,
  title TEXT NOT NULL, summary TEXT NOT NULL, impact TEXT NOT NULL, idempotency_key TEXT UNIQUE,
  approval_token_hash TEXT, result TEXT, verification TEXT, incident_id TEXT
);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
  tool TEXT, tier TEXT, proposal_id TEXT, session_id TEXT, outcome TEXT NOT NULL, detail TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS incidents (
  id TEXT PRIMARY KEY, session_id TEXT, app_name TEXT NOT NULL, opened_at TEXT NOT NULL,
  closed_at TEXT, status TEXT NOT NULL, trigger TEXT NOT NULL, summary TEXT, evidence TEXT,
  hypotheses TEXT, remediation TEXT, fix_brief TEXT
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS human_tokens (proposal_id TEXT PRIMARY KEY, token TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT, app_name TEXT NOT NULL, ts REAL NOT NULL, payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS snapshots_app ON snapshots(app_name, ts);
"""

SNAPSHOT_RING_SIZE = 720  # at 20s per sample this is 4 hours per app


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Store:
    def __init__(self, path: Path | str):
        self._path = str(path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---------------------------------------------------------------- utils

    def _run(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _rows(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def _one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        rows = self._rows(sql, params)
        return rows[0] if rows else None

    @staticmethod
    def _decode(row: dict[str, Any], *fields: str) -> dict[str, Any]:
        for field in fields:
            if row.get(field):
                try:
                    row[field] = json.loads(row[field])
                except (TypeError, ValueError):
                    pass
        return row

    # ----------------------------------------------------------------- meta

    def get_or_create_secret(self, key: str = "approval_secret") -> bytes:
        """Process-independent HMAC secret so the CLI/MCP and the web backend share approvals."""
        import secrets

        with self._lock:
            row = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            if row:
                return bytes.fromhex(row["value"])
            value = secrets.token_hex(32)
            self._conn.execute("INSERT INTO meta VALUES (?,?)", (key, value))
            self._conn.commit()
            return bytes.fromhex(value)

    # Human channel: raw approval tokens live only here (local DB on the operator's machine)
    # and are popped on first read, so an approval is single-use across processes.

    def put_human_token(self, proposal_id: str, token: str) -> None:
        self._run(
            "INSERT OR REPLACE INTO human_tokens VALUES (?,?,?)", (proposal_id, token, now_iso())
        )

    def pop_human_token(self, proposal_id: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT token FROM human_tokens WHERE proposal_id=?", (proposal_id,)
            ).fetchone()
            self._conn.execute("DELETE FROM human_tokens WHERE proposal_id=?", (proposal_id,))
            self._conn.commit()
            return row["token"] if row else None

    # ------------------------------------------------------------- sessions

    def create_session(
        self, *, title: str = "", mode: str = "chat", project_path: str = "", app_name: str = ""
    ) -> dict[str, Any]:
        session = {
            "id": new_id("ses"),
            "created_at": now_iso(),
            "title": title,
            "mode": mode,
            "project_path": project_path,
            "app_name": app_name,
        }
        self._run("INSERT INTO sessions VALUES (?,?,?,?,?,?)", tuple(session.values()))
        return session

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM sessions WHERE id=?", (session_id,))

    def update_session(self, session_id: str, **fields: Any) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        self._run(f"UPDATE sessions SET {cols} WHERE id=?", (*fields.values(), session_id))

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._rows("SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?", (limit,))

    # ------------------------------------------------------------- timeline

    def append_event(self, session_id: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            seq = self._conn.execute(
                "SELECT COALESCE(MAX(seq),0)+1 FROM timeline WHERE session_id=?", (session_id,)
            ).fetchone()[0]
            event = {
                "id": new_id("evt"),
                "session_id": session_id,
                "seq": seq,
                "ts": now_iso(),
                "kind": kind,
                "payload": payload,
            }
            self._conn.execute(
                "INSERT INTO timeline VALUES (?,?,?,?,?,?)",
                (
                    event["id"],
                    session_id,
                    seq,
                    event["ts"],
                    kind,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            self._conn.commit()
            return event

    def timeline(self, session_id: str, after_seq: int = 0) -> list[dict[str, Any]]:
        rows = self._rows(
            "SELECT * FROM timeline WHERE session_id=? AND seq>? ORDER BY seq",
            (session_id, after_seq),
        )
        return [self._decode(r, "payload") for r in rows]

    # ------------------------------------------------------------ proposals

    def create_proposal(self, proposal: dict[str, Any]) -> dict[str, Any]:
        ts = now_iso()
        row = {**proposal, "created_at": ts, "updated_at": ts}
        self._run(
            "INSERT INTO proposals (id, session_id, created_at, updated_at, status, tool, args, tier, title, summary, impact, idempotency_key, approval_token_hash, result, verification, incident_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                row["id"],
                row["session_id"],
                ts,
                ts,
                row["status"],
                row["tool"],
                json.dumps(row["args"], ensure_ascii=False),
                row["tier"],
                row["title"],
                row["summary"],
                json.dumps(row.get("impact", {}), ensure_ascii=False),
                row.get("idempotency_key"),
                row.get("approval_token_hash"),
                None,
                None,
                row.get("incident_id"),
            ),
        )
        return row

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        row = self._one("SELECT * FROM proposals WHERE id=?", (proposal_id,))
        return self._decode(row, "args", "impact", "result", "verification") if row else None

    def update_proposal(self, proposal_id: str, **fields: Any) -> None:
        encoded = {
            k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
            for k, v in fields.items()
        }
        encoded["updated_at"] = now_iso()
        cols = ", ".join(f"{k}=?" for k in encoded)
        self._run(f"UPDATE proposals SET {cols} WHERE id=?", (*encoded.values(), proposal_id))

    def list_proposals(
        self, session_id: str | None = None, status: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        sql, params = "SELECT * FROM proposals WHERE 1=1", []
        if session_id:
            sql, params = sql + " AND session_id=?", params + [session_id]
        if status:
            sql, params = sql + " AND status=?", params + [status]
        rows = self._rows(sql + " ORDER BY created_at DESC LIMIT ?", (*params, limit))
        return [self._decode(r, "args", "impact", "result", "verification") for r in rows]

    # ---------------------------------------------------------------- audit

    def audit(
        self,
        *,
        actor: str,
        action: str,
        outcome: str,
        detail: dict[str, Any] | None = None,
        tool: str | None = None,
        tier: str | None = None,
        proposal_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        self._run(
            "INSERT INTO audit (ts, actor, action, tool, tier, proposal_id, session_id, outcome, detail) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                now_iso(),
                actor,
                action,
                tool,
                tier,
                proposal_id,
                session_id,
                outcome,
                json.dumps(detail or {}, ensure_ascii=False),
            ),
        )

    def audit_log(self, limit: int = 200, session_id: str | None = None) -> list[dict[str, Any]]:
        if session_id:
            rows = self._rows(
                "SELECT * FROM audit WHERE session_id=? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            )
        else:
            rows = self._rows("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))
        return [self._decode(r, "detail") for r in rows]

    # ------------------------------------------------------------ incidents

    def create_incident(
        self, *, app_name: str, trigger: str, session_id: str | None = None, summary: str = ""
    ) -> dict[str, Any]:
        incident = {
            "id": new_id("inc"),
            "session_id": session_id,
            "app_name": app_name,
            "opened_at": now_iso(),
            "closed_at": None,
            "status": "open",
            "trigger": trigger,
            "summary": summary,
            "evidence": None,
            "hypotheses": None,
            "remediation": None,
            "fix_brief": None,
        }
        self._run(
            "INSERT INTO incidents VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", tuple(incident.values())
        )
        return incident

    def update_incident(self, incident_id: str, **fields: Any) -> None:
        encoded = {
            k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
            for k, v in fields.items()
        }
        cols = ", ".join(f"{k}=?" for k in encoded)
        self._run(f"UPDATE incidents SET {cols} WHERE id=?", (*encoded.values(), incident_id))

    def get_incident(self, incident_id: str) -> dict[str, Any] | None:
        row = self._one("SELECT * FROM incidents WHERE id=?", (incident_id,))
        return (
            self._decode(row, "evidence", "hypotheses", "remediation", "fix_brief") if row else None
        )

    def list_incidents(
        self, app_name: str | None = None, status: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        sql, params = "SELECT * FROM incidents WHERE 1=1", []
        if app_name:
            sql, params = sql + " AND app_name=?", params + [app_name]
        if status:
            sql, params = sql + " AND status=?", params + [status]
        rows = self._rows(sql + " ORDER BY opened_at DESC LIMIT ?", (*params, limit))
        return [self._decode(r, "evidence", "hypotheses", "remediation", "fix_brief") for r in rows]

    def open_incident_for(self, app_name: str) -> dict[str, Any] | None:
        rows = self.list_incidents(app_name=app_name, status="open", limit=1)
        return rows[0] if rows else None

    # ------------------------------------------------------------ snapshots

    def add_snapshot(self, app_name: str, ts: float, payload: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO snapshots (app_name, ts, payload) VALUES (?,?,?)",
                (app_name, ts, json.dumps(payload)),
            )
            self._conn.execute(
                "DELETE FROM snapshots WHERE app_name=? AND id NOT IN (SELECT id FROM snapshots WHERE app_name=? ORDER BY ts DESC LIMIT ?)",
                (app_name, app_name, SNAPSHOT_RING_SIZE),
            )
            self._conn.commit()

    def snapshots(
        self, app_name: str, since_ts: float = 0, limit: int = SNAPSHOT_RING_SIZE
    ) -> list[dict[str, Any]]:
        rows = self._rows(
            "SELECT ts, payload FROM snapshots WHERE app_name=? AND ts>=? ORDER BY ts DESC LIMIT ?",
            (app_name, since_ts, limit),
        )
        return [{"ts": r["ts"], **json.loads(r["payload"])} for r in reversed(rows)]
