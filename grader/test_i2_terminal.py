"""I2: terminal transitions cannot regress, and rejected commands do not notify."""
import random

import pytest

from harness import cmd, committed_event_ids, read_events, read_jobs, run_life

PATHS = {
    "succeeded": ["create", "start", "complete"],
    "failed": ["create", "start", "fail"],
    "cancelled_from_running": ["create", "start", "cancel"],
    "cancelled_from_queued": ["create", "cancel"],
}


@pytest.mark.parametrize("path", sorted(PATHS))
def test_terminal_state_is_absorbing(sink, db, path):
    drive = [{"handle": cmd(t, "j1")} for t in PATHS[path]]
    life = run_life(db, sink.url, drive + [{"pump": 2}])
    assert life.exit_code == 0, life.stderr
    for i in range(len(drive)):
        assert life.result(i) and life.result(i)["ok"] is True, life.result(i)
    terminal_state = read_jobs(db)["j1"]
    assert terminal_state in ("succeeded", "failed", "cancelled")
    n_events = len(read_events(db))
    n_hits = len(sink.hits)

    late = [cmd(t, "j1") for t in ("start", "complete", "fail", "cancel", "start")]
    random.Random(path).shuffle(late)
    life2 = run_life(db, sink.url, [{"handle": c} for c in late] + [{"pump": 3}])
    assert life2.exit_code == 0, life2.stderr
    for i, c in enumerate(late):
        assert life2.result(i) == {"ok": False, "error": "INVALID_TRANSITION"}, (c["type"], life2.result(i))
    assert read_jobs(db)["j1"] == terminal_state
    assert len(read_events(db)) == n_events, "rejected command appended an event"
    assert len(sink.hits) == n_hits, "rejected command emitted a notification"
    assert sink.distinct_event_ids() == committed_event_ids(db)
