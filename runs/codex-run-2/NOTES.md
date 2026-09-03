# Relay dispatcher changes

The dispatcher now makes each command decision in a `BEGIN IMMEDIATE`
SQLite transaction. The transaction records the canonical command request and
its result, updates the job, appends the event, and inserts an outbox row. This
keeps concurrent processes from accepting the same `command_id` twice and
ensures a crash cannot leave the job, event log, command result, and outbox out
of sync.

Command results, including rejections, are durable. Reusing a `command_id` with
the same type, job, and payload returns that stored result without changing
state, appending an event, or attempting notification. Reusing it for a
different request returns `IDEMPOTENCY_KEY_REUSED`.

Terminal jobs are checked before command dispatch, so `succeeded`, `failed`,
and `cancelled` cannot transition again. `cancel` was added for queued and
running jobs.

Notifications are no longer part of the command transaction. Committed events
are read from the durable outbox by `Dispatcher.pump()`. Successful sends are
marked delivered; failures stay pending, and the pump continues with every
other item so one rejected notification cannot block the queue. A crash after
send but before the delivered mark can cause a safe duplicate with the same
`event_id`. `handle()` calls `pump()` opportunistically after accepting a
command to preserve prompt delivery, but suppresses all background delivery
errors; periodic host calls to `pump()` provide recovery.

Verification performed:

- Existing suite: `pytest -q` — 9 passed.
- Focused checks for successful and rejected command replay, key reuse,
  cancellation, absorbing terminal states, per-item notification failure, and
  restart delivery.
- Subprocess fault-injection checks at each durable write and immediately after
  commit. Pre-commit crashes left no job or event; the post-commit crash left a
  consistent job/event and a notification delivered by `pump()` after restart.

`uv run --extra dev pytest` could not initialize in this sandbox because the
installed `uv` binary panicked while accessing macOS system configuration.
The already-installed pytest environment was used instead.
