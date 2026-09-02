"""Durable state for relay, backed by sqlite.

Convention: this module is the only place that opens sqlite. Everything
durable goes through a connection from `connect()`, and multi-statement
writes go through `Store.tx()`.
"""
from __future__ import annotations

import contextlib
import json
import sqlite3
import time
from typing import Iterator

from . import faults
from .model import Job

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    state  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id   TEXT NOT NULL UNIQUE,
    job_id     TEXT NOT NULL,
    command_id TEXT NOT NULL,
    type       TEXT NOT NULL,
    state      TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS commands (
    command_id  TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    result_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
    event_id          TEXT PRIMARY KEY,
    notification_json TEXT NOT NULL,
    delivered         INTEGER NOT NULL DEFAULT 0,
    attempts          INTEGER NOT NULL DEFAULT 0
);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    return faults.wrap(conn)


class Store:
    def __init__(self, path: str):
        self.path = path
        self.conn = connect(path)
        for stmt in SCHEMA.strip().split(";"):
            if stmt.strip():
                self.conn.execute(stmt)

    @contextlib.contextmanager
    def tx(self) -> Iterator[None]:
        """Run the block atomically. Nested use is not supported."""
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        else:
            self.conn.execute("COMMIT")

    # -- jobs ---------------------------------------------------------------
    def get_job(self, job_id: str) -> Job | None:
        row = self.conn.execute("SELECT job_id, state FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return Job(*row) if row else None

    def set_job_state(self, job_id: str, state: str) -> None:
        self.conn.execute(
            "INSERT INTO jobs (job_id, state) VALUES (?, ?) "
            "ON CONFLICT(job_id) DO UPDATE SET state = excluded.state",
            (job_id, state),
        )

    # -- events -------------------------------------------------------------
    def append_event(self, event_id: str, job_id: str, command_id: str, type_: str, state: str) -> None:
        self.conn.execute(
            "INSERT INTO events (event_id, job_id, command_id, type, state, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (event_id, job_id, command_id, type_, state, time.time()),
        )

    def read_events(self, job_id: str | None = None) -> list[dict]:
        if job_id is None:
            rows = self.conn.execute("SELECT seq, event_id, job_id, command_id, type, state FROM events ORDER BY seq").fetchall()
        else:
            rows = self.conn.execute(
                "SELECT seq, event_id, job_id, command_id, type, state FROM events WHERE job_id = ? ORDER BY seq",
                (job_id,),
            ).fetchall()
        keys = ("seq", "event_id", "job_id", "command_id", "type", "state")
        return [dict(zip(keys, r)) for r in rows]

    # -- commands (idempotency) --------------------------------------------
    def get_command(self, command_id: str) -> tuple[str, dict] | None:
        row = self.conn.execute(
            "SELECT fingerprint, result_json FROM commands WHERE command_id = ?", (command_id,)
        ).fetchone()
        return (row[0], json.loads(row[1])) if row else None

    def put_command(self, command_id: str, fingerprint: str, result: dict) -> None:
        self.conn.execute(
            "INSERT INTO commands (command_id, fingerprint, result_json) VALUES (?, ?, ?)",
            (command_id, fingerprint, json.dumps(result, sort_keys=True)),
        )

    # -- outbox -------------------------------------------------------------
    def outbox_put(self, event_id: str, notification: dict) -> None:
        self.conn.execute(
            "INSERT INTO outbox (event_id, notification_json) VALUES (?, ?)",
            (event_id, json.dumps(notification, sort_keys=True)),
        )

    def outbox_pending(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT notification_json FROM outbox WHERE delivered = 0 ORDER BY rowid"
        ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def outbox_mark_delivered(self, event_id: str) -> None:
        self.conn.execute(
            "UPDATE outbox SET delivered = 1, attempts = attempts + 1 WHERE event_id = ?", (event_id,)
        )

    def outbox_mark_attempt(self, event_id: str) -> None:
        self.conn.execute("UPDATE outbox SET attempts = attempts + 1 WHERE event_id = ?", (event_id,))

    def close(self) -> None:
        self.conn.close()
