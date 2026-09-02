"""I4: crash/restart preserves intended state.

For every commit point k and every write point k in the reference sequence,
kill the process there, restart, let recovery run, replay the client's
commands as a retrying client would, and check the world is consistent.
"""
import pytest

from harness import cmd, committed_event_ids, read_events, read_jobs, run_life

SEQ = ["create", "start", "complete"]
MAX_POINTS = 16


def _scenario(sink, db, fault):
    cmds = [cmd(t, "j1", command_id=f"k-{t}") for t in SEQ]
    steps = [{"handle": c} for c in cmds] + [{"pump": 2}]
    life1 = run_life(db, sink.url, steps, fault=fault)
    if not life1.crashed:
        return None  # fault point beyond the end of the sequence
    # At the crash instant: nothing announced that was not committed.
    assert sink.distinct_event_ids() <= committed_event_ids(db), f"[{fault}] phantom notification before commit"
    # Restart: recovery, then the client retries everything.
    life2 = run_life(db, sink.url, [{"pump": 3}] + [{"handle": c} for c in cmds] + [{"pump": 3}])
    assert life2.exit_code == 0, f"[{fault}] {life2.stderr}"
    for i in range(1, 4):
        assert life2.exception(i) is None, f"[{fault}] replay raised: {life2.exception(i)}"
    events = read_events(db)
    assert [e["type"] for e in events] == SEQ, f"[{fault}] one event per logical command expected, got {[e['type'] for e in events]}"
    assert read_jobs(db)["j1"] == "succeeded", f"[{fault}] state not implied by log"
    assert sink.distinct_event_ids() == committed_event_ids(db), f"[{fault}] announced != committed"
    return True


@pytest.mark.parametrize("k", range(1, MAX_POINTS + 1))
def test_crash_after_commit_k(sink, db, k):
    if _scenario(sink, db, f"commit:{k}") is None:
        pytest.skip("no such commit point")


@pytest.mark.parametrize("k", range(1, MAX_POINTS + 1))
def test_crash_after_write_k(sink, db, k):
    if _scenario(sink, db, f"write:{k}") is None:
        pytest.skip("no such write point")
