Implemented the dispatcher hardening:

- Transactional command idempotency with durable cached results.
- `IDEMPOTENCY_KEY_REUSED` detection.
- Absorbing terminal states.
- `cancel` from queued/running states.
- Durable SQLite outbox with isolated retries via `pump()`.
- Crash-safe atomic job/event/command/outbox writes.
- Opportunistic notification without allowing failures to affect `handle()`.

Validation: `pytest -q` passes all 9 existing tests, plus focused restart, sink-failure, idempotency, and crash-injection checks.

Details are in [NOTES.md](/Users/b.c.nims/dev/employment-ops-home/mechanize/invariant-task/runs/codex-run-2/work/NOTES.md). `uv` panicked in the sandbox, so the installed pytest environment was used.