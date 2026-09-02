"""I5: one undeliverable notification cannot block the others.

The sink permanently rejects every notification for one job (a poison
payload). Every committed event of every *other* job must still be
announced, in the same life and after a restart, and handle must keep
accepting commands for all jobs.
"""
from harness import cmd, committed_event_ids, read_events, run_life


def _others(db, poison_job):
    return {e["event_id"] for e in read_events(db) if e["job_id"] != poison_job}


def test_poisoned_job_does_not_block_other_jobs(sink, db):
    sink.reject_forever("px")
    cmds = [cmd("create", "px"), cmd("create", "j1"), cmd("start", "j1"), cmd("complete", "j1"),
            cmd("start", "px"), cmd("create", "j2"), cmd("cancel", "j2")]
    life = run_life(db, sink.url, [{"handle": c} for c in cmds] + [{"pump": 5}])
    assert life.exit_code == 0, life.stderr
    for i in range(len(cmds)):
        assert life.result(i)["ok"] is True, (i, life.result(i))
    missing = _others(db, "px") - sink.distinct_event_ids()
    assert not missing, f"announcements blocked behind the poisoned job: {missing}"
    assert sink.distinct_event_ids() <= committed_event_ids(db)


def test_poisoned_job_does_not_block_other_jobs_after_restart(sink, db):
    sink.reject_forever("px")
    dead = "http://127.0.0.1:9/notify"
    cmds = [cmd("create", "px"), cmd("create", "j1"), cmd("start", "j1")]
    life = run_life(db, dead, [{"handle": c} for c in cmds])
    assert life.exit_code == 0, life.stderr
    life2 = run_life(db, sink.url, [{"pump": 5}])
    assert life2.exit_code == 0, life2.stderr
    missing = _others(db, "px") - sink.distinct_event_ids()
    assert not missing, f"announcements blocked behind the poisoned job after restart: {missing}"
