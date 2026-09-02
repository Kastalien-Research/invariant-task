"""Job state machine.

    queued --start--> running --complete--> succeeded
                              --fail-----> failed

`succeeded`, `failed` and `cancelled` are terminal.
"""
from __future__ import annotations

from dataclasses import dataclass

STATES = ("queued", "running", "succeeded", "failed", "cancelled")
TERMINAL = frozenset({"succeeded", "failed", "cancelled"})


@dataclass(frozen=True)
class Job:
    job_id: str
    state: str

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL


def ok(state: str, event_id: str) -> dict:
    return {"ok": True, "state": state, "event_id": event_id}


def err(code: str) -> dict:
    return {"ok": False, "error": code}
