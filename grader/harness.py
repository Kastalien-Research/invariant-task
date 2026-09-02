"""Grader-side harness: a controllable sink, subprocess 'lives', DB readers.

A *life* is one process lifetime of the dispatcher running a scripted
sequence of steps. Crashes are injected through RELAY_FAULT (see
task/relay/faults.py); a new life on the same DB file is a restart.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_TASK_DIR = HERE.parent / "task"


def task_dir() -> Path:
    return Path(os.environ.get("RELAY_TASK_DIR", DEFAULT_TASK_DIR)).resolve()


# --------------------------------------------------------------------------
# Sink
# --------------------------------------------------------------------------
@dataclass
class Sink:
    hits: list[dict] = field(default_factory=list)
    _fail_budget: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _server: ThreadingHTTPServer | None = None
    _thread: threading.Thread | None = None

    def fail_next(self, n: int) -> None:
        """The next n POSTs get a 503. Count-bounded, never time-bounded."""
        with self._lock:
            self._fail_budget = n

    @property
    def url(self) -> str:
        assert self._server is not None
        return f"http://127.0.0.1:{self._server.server_address[1]}/notify"

    def distinct_event_ids(self) -> set[str]:
        with self._lock:
            return {h["event_id"] for h in self.hits}

    def start(self) -> "Sink":
        sink = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # quiet
                pass

            def do_POST(self):
                n = int(self.headers.get("content-length", "0"))
                body = json.loads(self.rfile.read(n) or b"{}")
                with sink._lock:
                    if sink._fail_budget > 0:
                        sink._fail_budget -= 1
                        status = 503
                    else:
                        sink.hits.append(body)
                        status = 200
                self.send_response(status)
                self.send_header("content-length", "0")
                self.end_headers()

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()


# --------------------------------------------------------------------------
# Commands and lives
# --------------------------------------------------------------------------
def cmd(type_: str, job_id: str, command_id: str | None = None, **payload) -> dict:
    return {"command_id": command_id or str(uuid.uuid4()), "type": type_, "job_id": job_id, "payload": payload}


@dataclass
class LifeResult:
    exit_code: int
    records: list[dict]
    stderr: str

    def result(self, step: int) -> dict | None:
        for r in self.records:
            if r["step"] == step:
                return r.get("result")
        return None

    def exception(self, step: int) -> str | None:
        for r in self.records:
            if r["step"] == step:
                return r.get("exception")
        return None

    @property
    def crashed(self) -> bool:
        return self.exit_code == 137


def run_life(db: Path, sink_url: str, steps: list[dict], fault: str | None = None, timeout: float = 60) -> LifeResult:
    out = db.parent / f"life-{uuid.uuid4().hex}.jsonl"
    script = db.parent / f"script-{uuid.uuid4().hex}.json"
    script.write_text(json.dumps(steps))
    env = {k: v for k, v in os.environ.items() if k != "RELAY_FAULT"}
    if fault:
        env["RELAY_FAULT"] = fault
    proc = subprocess.run(
        [sys.executable, str(HERE / "life.py"), "--task", str(task_dir()), "--db", str(db),
         "--sink", sink_url, "--script", str(script), "--out", str(out)],
        env=env, capture_output=True, text=True, timeout=timeout,
    )
    records = []
    if out.exists():
        for line in out.read_text().splitlines():
            if line.strip():
                records.append(json.loads(line))
    return LifeResult(proc.returncode, records, proc.stderr)


# --------------------------------------------------------------------------
# DB readers (grader side, never fault-wrapped)
# --------------------------------------------------------------------------
def read_jobs(db: Path) -> dict[str, str]:
    if not db.exists():
        return {}
    with sqlite3.connect(db) as c:
        return dict(c.execute("SELECT job_id, state FROM jobs").fetchall())


def read_events(db: Path) -> list[dict]:
    if not db.exists():
        return []
    with sqlite3.connect(db) as c:
        rows = c.execute("SELECT seq, event_id, job_id, command_id, type, state FROM events ORDER BY seq").fetchall()
    keys = ("seq", "event_id", "job_id", "command_id", "type", "state")
    return [dict(zip(keys, r)) for r in rows]


def committed_event_ids(db: Path) -> set[str]:
    return {e["event_id"] for e in read_events(db)}
