"""Fault injection for the sqlite connection.

Production never sets RELAY_FAULT. Tests and the operations harness set it to
make the process die at a precise point in its write sequence, so that
crash/restart behaviour is reproducible:

    RELAY_FAULT=commit:3   exit immediately after the 3rd commit completes
    RELAY_FAULT=write:3    exit immediately after the 3rd write statement
                           executes, before it is committed

Every durable write in relay goes through the connection returned by
`relay.store.connect`, which is what makes this counting exact. Keep it that
way: open sqlite only via `relay.store.connect`.
"""
from __future__ import annotations

import os
import sqlite3
import sys

_WRITE_VERBS = ("INSERT", "UPDATE", "DELETE", "REPLACE")


def _die(reason: str) -> None:
    sys.stderr.write(f"[relay.faults] simulated crash: {reason}\n")
    sys.stderr.flush()
    os._exit(137)


class FaultConnection:
    """Proxy around sqlite3.Connection that counts writes and commits."""

    def __init__(self, conn: sqlite3.Connection, spec: str):
        kind, _, n = spec.partition(":")
        if kind not in ("commit", "write") or not n.isdigit():
            raise ValueError(f"bad RELAY_FAULT spec: {spec!r}")
        self._conn = conn
        self._kind = kind
        self._target = int(n)
        self._writes = 0
        self._commits = 0

    # -- counting -----------------------------------------------------------
    def _saw_write(self) -> None:
        self._writes += 1
        if self._kind == "write" and self._writes == self._target:
            _die(f"after write #{self._writes}")

    def _saw_commit(self) -> None:
        self._commits += 1
        if self._kind == "commit" and self._commits == self._target:
            _die(f"after commit #{self._commits}")

    # -- sqlite3.Connection surface used by relay ---------------------------
    def execute(self, sql: str, params=()):
        verb = sql.lstrip().split(None, 1)[0].upper() if sql.strip() else ""
        was_in_tx = self._conn.in_transaction
        cur = self._conn.execute(sql, params)
        if verb in _WRITE_VERBS:
            self._saw_write()
            if not self._conn.in_transaction:
                # autocommit: the write is already durable
                self._saw_commit()
        elif verb == "COMMIT" or (verb == "END" and was_in_tx):
            self._saw_commit()
        return cur

    def commit(self) -> None:
        was_in_tx = self._conn.in_transaction
        self._conn.commit()
        if was_in_tx:
            self._saw_commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    @property
    def in_transaction(self) -> bool:
        return self._conn.in_transaction

    def __getattr__(self, name):
        return getattr(self._conn, name)


def wrap(conn: sqlite3.Connection) -> sqlite3.Connection | FaultConnection:
    spec = os.environ.get("RELAY_FAULT")
    if not spec:
        return conn
    return FaultConnection(conn, spec)
