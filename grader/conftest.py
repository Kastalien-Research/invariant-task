import pytest

from harness import Sink


@pytest.fixture
def sink():
    s = Sink().start()
    yield s
    s.stop()


@pytest.fixture
def db(tmp_path):
    return tmp_path / "relay.db"
