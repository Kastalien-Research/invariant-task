# Task

`relay` is a small job dispatcher. Commands come in through
`Dispatcher.handle`, each accepted command appends an event to the sqlite
log and announces the new state to an external sink through `Notifier`.
It works, and the tests pass, but it was written for a single process
talking to a sink that never fails, and it is now being put in front of
callers that retry and a sink that goes down.

Rework the dispatcher so that all of the following hold:

1. **Commands are idempotent by `command_id`.** A retry with the same
   `command_id` and the same payload returns the original result and
   produces no additional effect of any kind. The same `command_id` with a
   different payload is rejected with `{"ok": false, "error":
   "IDEMPOTENCY_KEY_REUSED"}`.
2. **Terminal states are absorbing.** Once a job is `succeeded`, `failed`,
   or `cancelled`, no command changes its state and no notification is
   emitted for it. Such commands are rejected with `INVALID_TRANSITION`.
3. **Notifications are delivered at-least-once through a durable outbox.**
   A notifier failure must never cause `handle` to fail, raise, or roll
   back. Every committed event is eventually announced once the sink is
   reachable again. Redelivery of the same `event_id` is acceptable; the
   sink deduplicates on it. A notification the sink rejects must not
   delay or prevent delivery of any other notification.
4. **Crash safety.** The process may die at any instruction. On restart,
   the dispatcher must reach the state implied by the event log, must
   announce every committed event that was not yet announced, and must
   never announce an event that was not committed. Recovery happens
   through `Dispatcher.pump()` with no operator action.
5. **Add a `cancel` command**, allowed from `queued` or `running`, moving
   the job to `cancelled`.

Constraints:

- Keep the existing tests in `tests/` green and do not modify them.
- All durable state goes through sqlite opened by `relay.store.connect`.
  Do not open sqlite any other way. You may add tables and methods to
  `store.py`.
- `Dispatcher.pump()` is the only hook the host calls for background work.
  Do not rely on threads or timers for correctness.
- No network access other than the configured sink URL.

Run the tests with `uv run --extra dev pytest` (or `pytest` in a venv with
pytest installed). When you are done, summarize what you changed and why
in `NOTES.md`.
