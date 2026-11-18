import pytest

from app.mqtt import ingest


@pytest.fixture(autouse=True)
def _restore_ingest():
    """test_ingest.Env가 ingest의 db/notifier/broadcast를 갈아끼우므로, 다른 테스트에 새지 않게 되돌린다."""
    saved = ingest.db, ingest.notifier, ingest.broadcast
    yield
    ingest.db, ingest.notifier, ingest.broadcast = saved
