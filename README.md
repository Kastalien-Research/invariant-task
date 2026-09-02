# An RL task for invariant-preserving software changes

A runnable coding-agent task with a hidden grader. The agent is asked to
rework a small job dispatcher so that it is safe under retries, sink
outages, and crashes. Nine visible tests stay green through almost any
change; four hidden invariants do not.

**Capability measured:** making a locally plausible change to a stateful
service while preserving invariants that the obvious tests never exercise.
The task is designed so that an agent can pass every visible test and still
be wrong in four distinct ways, each of which is a shortcut that real
implementations take.

## Layout

```
task/          the environment the agent sees: relay/, tests/, PROMPT.md
grader/        hidden: four invariant tests, hold checks, grade.py, qualify.py
reference/     a solution that passes everything (overlay on task/)
witnesses/     six deliberately-wrong solutions, one shortcut each
runs/          real agent runs: transcript, diff, grade
scripts/       run-agent.sh <claude|codex> <name> [model]
```

Run the grader on the pristine task (expect 0/4):

```
cd grader && uv run --project ../task --extra dev python grade.py
```

Qualify the grader against reference and witnesses (expect QUALIFIED):

```
cd grader && uv run --project ../task --extra dev python qualify.py
```

## Initial state S0 and the requested change

`relay` is a job dispatcher: `Dispatcher.handle(command)` applies a
command to a job (`queued -> running -> succeeded | failed`), appends an
event to a sqlite log, and POSTs a notification to an external sink.
It is naive on purpose: no idempotency, `start` is allowed from any state,
notifier failures propagate out of `handle`, and nothing survives a crash.

The prompt (`task/PROMPT.md`) asks for five things, stated plainly:
idempotency by `command_id`, absorbing terminal states, at-least-once
delivery through a durable outbox that never vetoes the command, crash
safety with recovery through `pump()`, and a new `cancel` command. Keep
the existing tests green. Durable state only via `relay.store.connect`.

The invariants are spelled out in the prompt. Underspecification is a
different capability; this task measures preservation, not intent inference.

## The four invariants the grader enforces

| # | Invariant | What the hidden test does |
|---|---|---|
| I1 | Retries cannot create duplicate effects | Replays commands within a process and across a restart, including a rejected command replayed after the state moved on. Requires the *original* result back, one event per logical command, and `IDEMPOTENCY_KEY_REUSED` for same id with a different payload. |
| I2 | Terminal transitions cannot regress | Drives a job to each terminal state, then fires every command with fresh ids in a seeded random order. Requires `INVALID_TRANSITION`, unchanged state, no new event, and no notification. |
| I3 | Ancillary failure cannot veto the core operation | Sink returns 503 for a count-bounded window, and in a second case is unreachable for an entire process lifetime. Requires every command to commit and return ok, and every committed event to be announced once the sink is back. |
| I4 | Crash/restart preserves intended state | Kills the process after the k-th commit and after the k-th write, for every k. Restarts, recovers via `pump()`, replays the client's commands. Requires log-implied state, one event per command, no phantom notification, no lost notification. |

Notifications may be redelivered; the sink deduplicates on `event_id`.
The grader distinguishes redelivery (same id twice, allowed) from a
duplicate effect (two ids for one logical command, forbidden).

Hold predicates, checked before the invariants: the visible tests pass,
`tests/` and the fault hook are byte-identical to a lock, sqlite is opened
only through `store.py`, and the fault hook still kills the process.

## Why the visible tests are insufficient

Every visible test is one command, one process, one healthy sink. Every
invariant above is about a *pair* under a boundary: retry x commit,
terminal x late command, commit x sink outage, write x crash. A change can
pass all nine tests and violate all four invariants. S0 does exactly that.

## Grader structure

- `harness.py`: a sink HTTP server with count-bounded failure (never
  time-bounded, so retry loops with sleeps cannot outlast it), a subprocess
  "life" runner so every restart is a real process boundary, and DB readers
  that never go through the fault hook.
- `task/relay/faults.py`: the crash injector. `RELAY_FAULT=commit:k` exits
  after the k-th commit, `write:k` after the k-th write before commit. Every
  durable write in the task goes through this connection, which is what
  makes crash points exact and enumerable.
- `grade.py`: holds, then I1..I4, binary each, no partial credit inside an
  invariant.
- `qualify.py`: the grader is qualified before any agent run. S0 must fail
  all four; the reference must pass all four; each witness must fail
  exactly its declared set.

## Known shortcut surfaces

Listed before running any agent; confirmed or refuted in the runs section.

| Shortcut | Looks like | Caught by |
|---|---|---|
| In-memory `seen` set for idempotency | passes visible tests, passes I1 within a life | I1 replay across restart |
| State check as idempotency (`if already running: return`) | most replays look fine | I1 same id, different payload; original result not returned |
| Only record successful commands | replays of rejections recompute | I1 rejected command replayed after state moved |
| `try: notify() except: pass` | never vetoes | I3 delivery after outage; I4 nothing to recover |
| Commit, notify inline, roll back on failure | "transactional" | I3 command must commit |
| Event and outbox in separate transactions | outbox exists | I4 crash after first commit |
| Mark outbox delivered before send | fewer redeliveries | I4 crash between mark and send |
| Terminal guard skips the write but still emits | state is right | I2 no notification for rejected command |
| Pump stops at the first failed send (keeps log order) | ordered, simple | I5 poisoned job blocks the rest |
| Edit a visible test | green | H2 hash lock |

Each of these is a witness under `witnesses/`, except the ones that are
strict subsets of another.

## Agent runs

Task instance 1 (lock 674555e: I1..I4, prompt without the rejection sentence).
Both agents ran with the operator's global tooling loaded (see affordance
note below). Full transcripts, diffs and grade reports are under `runs/`.

| run | agent | wall clock | visible | I1 | I2 | I3 | I4 | I5 (added later) |
|---|---|---|---|---|---|---|---|---|
| codex-run-1 | Codex, gpt-5.6-sol, reasoning high | 6m26s | 17/17 (added 8) | pass | pass | pass | pass | **fail** |
| claude-run-1 | Claude Code, claude-fable-5-1 | 9m26s | 23/23 (added 14) | pass | pass | pass | pass | **fail** |

Both solutions are good. Both use a `commands` ledger with a fingerprint of
(type, job_id, payload), record rejections as well as successes, commit the
job row, event, outbox row and command record in one `BEGIN IMMEDIATE`
transaction, and deliver after commit with mark-after-send. Codex added a
second ledger check inside the transaction for concurrent retriers. Neither
took any of the nine shortcuts listed above.

**The failure both produced.** Both `pump()` implementations stop at the
first failed send. Codex: `except Exception: break`. Claude, in its
docstring: "Stops at the first sink failure so per-job ordering is
preserved." Under a sink that permanently rejects one payload, every
notification behind it, for every job, is never delivered, and the block
survives restart because the outbox is durable. Two frontier models, same
decision, same stated rationale.

**Classification.** Not a capability failure. The prompt said every
committed event is announced "once the sink is reachable again", which
never covers a reachable sink rejecting one payload, and the grader had no
test for it. Ordering-preserving retry is a defensible reading of that
contract. This is a contract gap and an evaluator gap, found by reading
the diffs rather than the grade.

Grader defects found in instance 1, both mine:

- H2 flagged Codex's *added* test file as tampering with `tests/`. The
  lock now covers only the locked files; adding tests is allowed.
- `qualify.py` overlaid witnesses on S0 instead of on the reference they
  derive from, so all six failed everything on the first qualification.

Affordance note: `claude -p` loaded the operator's global CLAUDE.md,
skills and agent definitions (the run spawned a "verifier" subagent), and
`codex exec` loaded the operator's AGENTS.md and MCP servers. Instance-2
runs use isolated configs: `--setting-sources project --strict-mcp-config`
for Claude and a CODEX_HOME holding only auth and model for Codex.

## What changed after observing the failures

_(filled in after the runs)_

## Provenance

The domain is a distillation of a coordination service I run
([claude-teams-hub](https://github.com/Kastalien-Research/claude-teams-hub)),
whose event-sourced command path enforces the same four properties:
idempotency keys bound to payload, revision guards, absorbing states, and
ancillary publication that must not veto the write. The full-scale version
of this task is a hub issue; this repo is the version you can run in five
minutes.
