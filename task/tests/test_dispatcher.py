from conftest import cmd


def test_create_queues_job(dispatcher, store):
    res = dispatcher.handle(cmd("create", "j1"))
    assert res["ok"] and res["state"] == "queued"
    assert store.get_job("j1").state == "queued"


def test_start_runs_job(dispatcher, store):
    dispatcher.handle(cmd("create", "j1"))
    res = dispatcher.handle(cmd("start", "j1"))
    assert res["ok"] and res["state"] == "running"


def test_complete_succeeds_job(dispatcher, store):
    dispatcher.handle(cmd("create", "j1"))
    dispatcher.handle(cmd("start", "j1"))
    res = dispatcher.handle(cmd("complete", "j1"))
    assert res["ok"] and res["state"] == "succeeded"
    assert store.get_job("j1").terminal


def test_fail_fails_job(dispatcher, store):
    dispatcher.handle(cmd("create", "j1"))
    dispatcher.handle(cmd("start", "j1"))
    res = dispatcher.handle(cmd("fail", "j1"))
    assert res["ok"] and res["state"] == "failed"


def test_complete_requires_running(dispatcher):
    dispatcher.handle(cmd("create", "j1"))
    res = dispatcher.handle(cmd("complete", "j1"))
    assert res == {"ok": False, "error": "INVALID_TRANSITION"}


def test_unknown_job_rejected(dispatcher):
    res = dispatcher.handle(cmd("start", "nope"))
    assert res == {"ok": False, "error": "JOB_NOT_FOUND"}


def test_duplicate_create_rejected(dispatcher):
    dispatcher.handle(cmd("create", "j1"))
    assert dispatcher.handle(cmd("create", "j1")) == {"ok": False, "error": "JOB_EXISTS"}


def test_each_transition_is_notified(dispatcher, notifier):
    dispatcher.handle(cmd("create", "j1"))
    dispatcher.handle(cmd("start", "j1"))
    dispatcher.handle(cmd("complete", "j1"))
    assert [n["state"] for n in notifier.sent] == ["queued", "running", "succeeded"]
    assert all(n["job_id"] == "j1" and n["event_id"] for n in notifier.sent)


def test_event_log_records_history(dispatcher, store):
    dispatcher.handle(cmd("create", "j1"))
    dispatcher.handle(cmd("create", "j2"))
    dispatcher.handle(cmd("start", "j1"))
    events = store.read_events("j1")
    assert [e["type"] for e in events] == ["create", "start"]
    assert [e["type"] for e in store.read_events("j2")] == ["create"]
