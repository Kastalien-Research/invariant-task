# NOTES: making `relay` safe for retrying callers and a flaky sink

## What changed

### `relay/store.py`
- Two new tables, created alongside the existing ones (no migration of
  existing columns, so an old database opens unchanged):
  - `commands(command_id PK, fingerprint, result, created_at)`: one row per
    `command_id` ever handled. `fingerprint` is the canonical JSON of
    `(type, job_id, payload)` with sorted keys; `result` is the exact response
    dict returned to the caller.
  - `outbox(event_id PK -> events)`: a row means "committed but not yet
    acknowledged by the sink". Inserted in the same transaction as the event,
    deleted only after `Notifier.send` returns.
- New methods: `fingerprint()`, `get_command`, `record_command`,
  `enqueue_notification`, `pending_notifications` (joins `outbox` to `events`,
  ordered by `events.seq`), `mark_notified`.
- sqlite is still opened only through `connect()`; nothing else changed.

### `relay/dispatcher.py`
`handle` is now:

1. Compute the command fingerprint. If `command_id` is already recorded:
   same fingerprint -> return the stored result (no transaction, no writes,
   no notification); different fingerprint -> `IDEMPOTENCY_KEY_REUSED`.
2. Open one `BEGIN IMMEDIATE` transaction. Re-check step 1 under the write
   lock (protects against two processes handling the same retry at once).
3. Decide the outcome from the current job state (`_decide`, pure).
4. If accepted: upsert job state, append the event, insert the outbox row.
   Either way: record the command and its result. Commit.
5. After the commit, drain the outbox (`_deliver_pending`) best-effort.

`pump()` calls the same `_deliver_pending`: read outbox rows oldest first,
`send` each, delete the row on success, stop at the first failure. Any
exception from the notifier is swallowed; the row stays for the next call.

The transition table is now data (`TRANSITIONS`), with `cancel` allowed from
`queued` and `running`. `start` is still allowed from `running` (the
"kick a stuck job" behaviour the original comment documented). Terminal
states never appear as a source state, so every command on a terminal job is
`INVALID_TRANSITION` and nothing is written or announced.

### `relay/model.py`
Docstring only: added `cancel` to the state diagram.

### `tests/test_reliability.py` (new; existing tests untouched)
Covers replay, rejected-command replay, key reuse, absorbing terminal states
for all three finishers, cancel, sink-down `handle`, ordered backlog
delivery from `pump`, and four crash tests that run a child process under
`RELAY_FAULT` and inspect the sink log against the event log after restart:
crash after commit before notify, crash mid-transaction, crash after send
before ack (duplicate delivery of the same `event_id`), and "an uncommitted
event is never announced".

## Why this shape

- **One transaction per accepted command** is what makes crash safety
  trivial: job state, event, outbox row and command record either all exist
  or none do. `pump()` therefore never has to rebuild anything; the state
  implied by the log *is* the state, and the outbox is exactly the set of
  committed events the sink has not acknowledged.
- **Notify strictly after commit.** That is the only ordering that can never
  announce an uncommitted event. The price is the window between `send`
  succeeding and the outbox delete, where a crash causes one redelivery of
  the same `event_id`; the task allows that and the sink deduplicates.
- **`handle` still delivers inline** after the commit so the existing
  synchronous-notification test keeps passing and the sink sees events
  promptly. It drains the whole outbox in log order rather than sending just
  its own event, so a new event never overtakes a backlog left by an outage.
- **Rejections are recorded too.** "Return the original result" is only
  well-defined if the original result is stored, and a retry of a command
  that was rejected an hour ago must not silently succeed because the job
  moved in the meantime. Rejections still write no event and announce
  nothing.

## Judgment calls worth knowing about

- `create` on a job that already exists returns `JOB_EXISTS` in every state,
  including terminal ones, because the existing test pins that error for the
  duplicate-create case and `create` is not a transition. All other commands
  on a terminal job get `INVALID_TRANSITION`.
- `_deliver_pending` catches `Exception`, not just `NotifyError`, because the
  requirement is that a notifier failure of any kind never breaks `handle`.
  Nothing is logged because the codebase has no logging; the outbox row is
  the record.
- While the sink is down, `handle` still pays one failed `send` (up to the
  notifier timeout) per accepted command, the same latency the old code had.
  If that matters, the inline drain can be dropped and delivery left to
  `pump()` alone without touching correctness.
- Write counts per accepted command, for anyone driving `RELAY_FAULT`:
  4 writes inside the transaction (job, event, outbox, command) then
  `COMMIT`; then one autocommit `DELETE` per delivered notification.
  A rejected command is 1 write plus `COMMIT`. A replayed command is 0.
