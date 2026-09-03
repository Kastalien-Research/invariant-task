# NOTES

## What changed

### `relay/store.py`
Two tables added, no changes to existing ones:

- `commands(command_id PK, fingerprint, result, created_at)` is the
  idempotency record. `fingerprint` is the canonical JSON of the command
  minus its id (`type`, `job_id`, `payload`); `result` is the JSON response
  that was returned to the caller.
- `outbox(event_id PK -> events, attempts, last_error)` holds committed
  events the sink has not acknowledged. It stores only the id; the
  notification body is read back from `events` so nothing is duplicated.

New methods: `get_command`, `record_command`, `enqueue_notification`,
`pending_notifications`, `mark_delivered`, `mark_delivery_failed`.

### `relay/model.py`
Added a `TRANSITIONS` table (`command type -> (allowed source states, target
state)`) and the `cancel` edges (`queued|running -> cancelled`). No terminal
state appears in any source set, which is what makes terminal states
absorbing. `start` from `running` remains allowed, as before.

### `relay/dispatcher.py`
`handle` now runs one `BEGIN IMMEDIATE` transaction that:

1. looks up `command_id` in `commands`. Same fingerprint: return the stored
   result. Different fingerprint: return `IDEMPOTENCY_KEY_REUSED`. Neither
   path writes anything.
2. otherwise decides the command against `TRANSITIONS`, and on acceptance
   writes the job state, the event, and the outbox row.
3. records the response in `commands` (rejections too, so a retried
   rejection returns the same rejection).

Only after that commits does `handle` try to send its own notification,
inside a `try/except Exception`. Success deletes the outbox row (a single
autocommit statement); failure bumps `attempts`/`last_error` and returns
normally. `handle` never raises for a sink problem and never rolls back
because of one.

`pump()` walks the outbox oldest-first and attempts every row
independently, so a notification the sink rejects does not block the ones
behind it. It returns the number the sink accepted, so `while pump(): ...`
terminates. It is also the whole recovery story: on restart nothing needs
rebuilding, because every committed event that was not acknowledged still
has its outbox row.

## Why this is crash safe

All durable effects of a command land in one sqlite transaction, so the
process dying at any instruction leaves the log, the job table, the outbox
and the idempotency record either all present or all absent. The sink is
contacted strictly after commit, so an uncommitted event can never be
announced. The outbox row is removed strictly after the sink accepts, so a
committed event is re-announced until acknowledged. A crash between the
send and the delete produces a redelivery of the same `event_id`, which
the task allows.

## Decisions worth knowing

- **Rejections are recorded for idempotency.** "Returns the original
  result" was read literally: a `complete` rejected with
  `INVALID_TRANSITION` and retried later with the same `command_id` still
  gets `INVALID_TRANSITION`, even if the job is now `running`.
- **`create` on an existing job stays `JOB_EXISTS`** in every state,
  including terminal ones, because the existing test pins that code and it
  is an existence check rather than a transition. All other commands on a
  terminal job get `INVALID_TRANSITION`.
- **`handle` attempts only its own event, not the job's backlog.** Trying
  older pending rows first would let one permanently rejected notification
  delay every later one for that job, which requirement 3 forbids. Per-job
  ordering across a sink outage is therefore not guaranteed; the sink
  deduplicates on `event_id` and ordering was not required.
- **No backoff or dead-lettering.** Every committed event must eventually
  be announced, so nothing is ever dropped. `attempts`/`last_error` are
  kept for operators to see a stuck row.
- **`jobs` is not rebuilt from `events` on restart.** It cannot diverge:
  both are written in the same transaction. A rebuild step would add a
  write per `pump()` for nothing.

## Tests added (`tests/test_reliability.py`, `tests/crash_driver.py`)

Existing tests are untouched and pass. New in-process tests cover retries
(same and different payload, across a restart, of a rejection), absorbing
terminal states for every terminal state and every command, `cancel` from
both allowed states, and the outbox (sink down, backlog drained by `pump`,
a poisoned notification not blocking others, non-`NotifyError` exceptions
contained).

The crash test drives `tests/crash_driver.py` in a subprocess under
`RELAY_FAULT=write:N` and `RELAY_FAULT=commit:N` for every `N` up to 60,
with the sink up and with the sink down, then restarts and calls `pump()`.
For each of the roughly 85 distinct crash points reached it asserts that
the job table equals the fold of the event log, that the set of announced
`event_id`s equals the set of committed ones after `pump()` alone, that
the outbox is empty, and that replaying the whole command sequence with the
same `command_id`s afterwards adds no duplicate events and returns the
event ids already in the log.

```
uv run --extra dev pytest -q   # 28 passed
```
