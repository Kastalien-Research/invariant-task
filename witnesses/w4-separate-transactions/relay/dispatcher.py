"""WITNESS w4-separate-transactions: the outbox row is written in a second transaction after the event commits

Apply commands to jobs, log the resulting events, notify the sink.

A command is a dict:
    {"command_id": str, "type": str, "job_id": str, "payload": dict}

`handle` returns {"ok": True, "state": ..., "event_id": ...} on success or
{"ok": False, "error": CODE} on rejection.

Design:
- Every command's outcome (accepted or rejected) is recorded under its
  command_id with a fingerprint of (type, job_id, payload). A replay with a
  matching fingerprint returns the recorded outcome; a mismatch is
  IDEMPOTENCY_KEY_REUSED. Recorded in the same transaction as the effect.
- State change, event, outbox row and command record commit atomically.
- Delivery is a separate, best-effort step (`pump`) that can run any number
  of times: send, then mark delivered. A crash between the two redelivers,
  which the sink tolerates by event_id.
"""
from __future__ import annotations

import json
import uuid

from .model import TERMINAL, err, ok
from .notifier import Notifier, NotifyError
from .store import Store

TRANSITIONS = {
    ("queued", "start"): "running",
    ("running", "complete"): "succeeded",
    ("running", "fail"): "failed",
    ("queued", "cancel"): "cancelled",
    ("running", "cancel"): "cancelled",
}
KNOWN = {"create", "start", "complete", "fail", "cancel"}


def _fingerprint(command: dict) -> str:
    return json.dumps(
        {"type": command["type"], "job_id": command["job_id"], "payload": command.get("payload", {})},
        sort_keys=True,
    )


class Dispatcher:
    def __init__(self, store: Store, notifier: Notifier):
        self.store = store
        self.notifier = notifier

    def _decide(self, command: dict) -> tuple[dict | None, str | None]:
        """Return (rejection, None) or (None, new_state)."""
        ctype = command["type"]
        job = self.store.get_job(command["job_id"])
        if ctype not in KNOWN:
            return err("UNKNOWN_COMMAND"), None
        if ctype == "create":
            return (err("JOB_EXISTS"), None) if job is not None else (None, "queued")
        if job is None:
            return err("JOB_NOT_FOUND"), None
        if job.state in TERMINAL:
            return err("INVALID_TRANSITION"), None
        new_state = TRANSITIONS.get((job.state, ctype))
        if new_state is None:
            return err("INVALID_TRANSITION"), None
        return None, new_state

    def handle(self, command: dict) -> dict:
        command_id = command["command_id"]
        fp = _fingerprint(command)

        with self.store.tx():
            prior = self.store.get_command(command_id)
            if prior is not None:
                prior_fp, prior_result = prior
                return prior_result if prior_fp == fp else err("IDEMPOTENCY_KEY_REUSED")

            rejection, new_state = self._decide(command)
            if rejection is not None:
                self.store.put_command(command_id, fp, rejection)
                result = rejection
            else:
                assert new_state is not None
                event_id = str(uuid.uuid4())
                job_id = command["job_id"]
                self.store.set_job_state(job_id, new_state)
                self.store.append_event(event_id, job_id, command_id, command["type"], new_state)
                result = ok(new_state, event_id)
                self.store.put_command(command_id, fp, result)
                pending_outbox = (event_id, {"event_id": event_id, "job_id": job_id, "type": command["type"], "state": new_state})

        if result["ok"]:
            self.store.outbox_put(*pending_outbox)  # second transaction
        self.pump()
        return result

    def pump(self) -> int:
        """Deliver pending notifications. Safe to call any number of times."""
        delivered = 0
        for notification in self.store.outbox_pending():
            try:
                self.notifier.send(notification)
            except NotifyError:
                self.store.outbox_mark_attempt(notification["event_id"])
                continue
            self.store.outbox_mark_delivered(notification["event_id"])
            delivered += 1
        return delivered
