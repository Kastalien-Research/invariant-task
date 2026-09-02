import pytest

from relay.dispatcher import Dispatcher
from relay.notifier import Notifier
from relay.store import Store


class RecordingNotifier(Notifier):
    """Captures notifications instead of POSTing them."""

    def __init__(self):
        super().__init__(sink_url="memory://")
        self.sent: list[dict] = []

    def send(self, notification: dict) -> None:
        self.sent.append(notification)


@pytest.fixture
def notifier():
    return RecordingNotifier()


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "relay.db"))
    yield s
    s.close()


@pytest.fixture
def dispatcher(store, notifier):
    return Dispatcher(store, notifier)


def cmd(type_, job_id, command_id=None, **payload):
    import uuid

    return {"command_id": command_id or str(uuid.uuid4()), "type": type_, "job_id": job_id, "payload": payload}
