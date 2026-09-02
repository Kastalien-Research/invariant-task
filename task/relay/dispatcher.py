"""Apply commands to jobs, log the resulting events, notify the sink.

A command is a dict:
    {"command_id": str, "type": str, "job_id": str, "payload": dict}

`handle` returns {"ok": True, "state": ..., "event_id": ...} on success or
{"ok": False, "error": CODE} on rejection.
"""
from __future__ import annotations

import uuid

from .model import err, ok
from .notifier import Notifier
from .store import Store


class Dispatcher:
    def __init__(self, store: Store, notifier: Notifier):
        self.store = store
        self.notifier = notifier

    def handle(self, command: dict) -> dict:
        ctype = command["type"]
        job_id = command["job_id"]
        command_id = command["command_id"]

        job = self.store.get_job(job_id)
        if ctype == "create":
            if job is not None:
                return err("JOB_EXISTS")
            new_state = "queued"
        else:
            if job is None:
                return err("JOB_NOT_FOUND")
            if ctype == "start":
                # (Re)start is always allowed; operators use it to kick a stuck job.
                new_state = "running"
            elif ctype == "complete":
                if job.state != "running":
                    return err("INVALID_TRANSITION")
                new_state = "succeeded"
            elif ctype == "fail":
                if job.state != "running":
                    return err("INVALID_TRANSITION")
                new_state = "failed"
            else:
                return err("UNKNOWN_COMMAND")

        event_id = str(uuid.uuid4())
        self.store.set_job_state(job_id, new_state)
        self.store.append_event(event_id, job_id, command_id, ctype, new_state)
        self.notifier.send(
            {"event_id": event_id, "job_id": job_id, "type": ctype, "state": new_state}
        )
        return ok(new_state, event_id)

    def pump(self) -> int:
        """Do any pending background work. Returns the number of items processed.

        Called periodically by the host process (a scheduler in production,
        the test harness in tests).
        """
        return 0
