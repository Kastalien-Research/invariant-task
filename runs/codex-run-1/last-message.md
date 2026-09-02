Implemented the reliable dispatcher rework.

- Added transactional command idempotency and durable result replay.
- Made terminal states absorbing and added `cancel`.
- Added a SQLite durable outbox with at-least-once delivery through `pump()`.
- Ensured notifier failures cannot fail or roll back `handle()`.
- Added restart, ambiguous-delivery, concurrency, and retry coverage.
- Documented the design in [NOTES.md](/Users/b.c.nims/dev/employment-ops-home/mechanize/invariant-task/runs/codex-run-1/work/NOTES.md).

Verification: `uv run --extra dev pytest` — **17 passed**. Fault-injection and simultaneous-caller probes also passed.