"""I3: an ancillary (notifier) failure cannot veto the core operation."""
from harness import cmd, committed_event_ids, read_events, read_jobs, run_life


def test_sink_errors_do_not_fail_commands_and_are_delivered_later(sink, db):
    sink.fail_next(3)
    cmds = [cmd("create", "j1"), cmd("start", "j1"), cmd("complete", "j1")]
    life = run_life(db, sink.url, [{"handle": c} for c in cmds] + [{"pump": 5}])
    assert life.exit_code == 0, life.stderr
    for i in range(3):
        assert life.exception(i) is None, f"handle raised: {life.exception(i)}"
        assert life.result(i)["ok"] is True, life.result(i)
    assert [e["type"] for e in read_events(db)] == ["create", "start", "complete"]
    assert read_jobs(db)["j1"] == "succeeded"
    assert sink.distinct_event_ids() == committed_event_ids(db), "committed events were not all announced"


def test_sink_unreachable_for_a_whole_life_then_delivered_after_restart(sink, db):
    dead_url = "http://127.0.0.1:9/notify"  # discard port: connection refused
    cmds = [cmd("create", "j1"), cmd("start", "j1")]
    life1 = run_life(db, dead_url, [{"handle": c} for c in cmds] + [{"pump": 2}])
    assert life1.exit_code == 0, life1.stderr
    for i in range(2):
        assert life1.exception(i) is None, f"handle raised: {life1.exception(i)}"
        assert life1.result(i)["ok"] is True
    assert len(read_events(db)) == 2
    life2 = run_life(db, sink.url, [{"pump": 3}])
    assert life2.exit_code == 0, life2.stderr
    assert sink.distinct_event_ids() == committed_event_ids(db), "notifications lost across restart"
