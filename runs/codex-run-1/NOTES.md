# Relay reliability changes

- Added a durable command ledger keyed by `command_id`. It stores a canonical
  command envelope and the original result, so identical retries return that
  result without another transition, event, or notification. Reuse with a
  different type, job, or payload returns `IDEMPOTENCY_KEY_REUSED`. Rejections
  are recorded too, so their results cannot change on retry.
- Made command handling transactional with `BEGIN IMMEDIATE`. The job
  projection, event, outbox item, and command result now commit together. A
  second process rechecks the command ledger after acquiring the writer lock,
  preventing simultaneous retries from producing duplicate events.
- Made terminal states absorbing and added `cancel` transitions from both
  `queued` and `running`.
- Added a durable SQLite outbox. `handle` makes one best-effort delivery pass
  only after committing, and notifier failures do not escape from `handle`.
  `pump()` sends pending events in log order and marks each delivered only
  after the notifier returns successfully. A crash or ambiguous send can cause
  a safe duplicate, while an uncommitted event can never be selected.
- Added reliability coverage for command retries and key reuse, persisted
  rejections, terminal transitions, cancellation, sink outages, restart
  recovery, and ambiguous delivery failures.

Verification used `uv run --extra dev pytest`; all 17 tests passed. Additional
fault-injection checks killed the process after each transactional write and
immediately after commit: pre-commit deaths rolled everything back, while the
post-commit death recovered the job, event, command result, and pending outbox
item. A simultaneous two-caller probe also produced one event and one
notification with the same returned result for both callers.
