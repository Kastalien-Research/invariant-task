"""I1: retries cannot create duplicate effects."""
from harness import cmd, committed_event_ids, read_events, read_jobs, run_life


def test_replay_in_same_life_returns_original_and_adds_nothing(sink, db):
    c1, c2, c3 = cmd("create", "j1"), cmd("start", "j1"), cmd("complete", "j1")
    rejected = cmd("complete", "j1")  # sent while queued -> INVALID_TRANSITION
    steps = [
        {"handle": c1}, {"handle": rejected}, {"handle": c2},
        {"handle": c2}, {"handle": c2},            # replays of start
        {"handle": c3}, {"handle": c1},            # complete, then replay create
        {"handle": rejected},                      # replay of a rejected command after state moved on
        {"pump": 3},
    ]
    life = run_life(db, sink.url, steps)
    assert life.exit_code == 0, life.stderr
    for i in range(8):
        assert life.exception(i) is None, f"step {i}: {life.exception(i)}"
    assert life.result(3) == life.result(2), "replay of start must return the original result"
    assert life.result(4) == life.result(2)
    assert life.result(6) == life.result(0), "replay of create must return the original result"
    assert life.result(7) == life.result(1), "replay of a rejected command must return the original rejection"
    events = read_events(db)
    assert [e["type"] for e in events] == ["create", "start", "complete"], events
    assert read_jobs(db)["j1"] == "succeeded"
    assert sink.distinct_event_ids() == committed_event_ids(db)


def test_replay_across_restart_adds_nothing(sink, db):
    c1, c2, c3 = cmd("create", "j1"), cmd("start", "j1"), cmd("complete", "j1")
    life1 = run_life(db, sink.url, [{"handle": c1}, {"handle": c2}, {"pump": 2}])
    assert life1.exit_code == 0, life1.stderr
    life2 = run_life(db, sink.url, [{"handle": c2}, {"handle": c1}, {"handle": c3}, {"pump": 2}])
    assert life2.exit_code == 0, life2.stderr
    assert life2.result(0) == life1.result(1), "replay of start after restart must return the original result"
    assert life2.result(1) == life1.result(0), "replay of create after restart must return the original result"
    assert life2.result(2)["ok"] is True
    assert [e["type"] for e in read_events(db)] == ["create", "start", "complete"]
    assert sink.distinct_event_ids() == committed_event_ids(db)


def test_same_id_different_payload_is_rejected(sink, db):
    c1 = cmd("create", "j1", command_id="k-1", priority=1)
    c1_other_payload = dict(c1, payload={"priority": 2})
    c1_other_type = dict(c1, type="start")
    life = run_life(db, sink.url, [{"handle": c1}, {"handle": c1_other_payload}, {"handle": c1_other_type}, {"pump": 2}])
    assert life.exit_code == 0, life.stderr
    assert life.result(0)["ok"] is True
    assert life.result(1) == {"ok": False, "error": "IDEMPOTENCY_KEY_REUSED"}
    assert life.result(2) == {"ok": False, "error": "IDEMPOTENCY_KEY_REUSED"}
    assert len(read_events(db)) == 1
    assert read_jobs(db)["j1"] == "queued"
    assert sink.distinct_event_ids() == committed_event_ids(db)
