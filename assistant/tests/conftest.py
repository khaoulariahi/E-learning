import pytest

from assistant.core import db
from assistant.core.config import get_settings
from assistant.core.providers import base
from assistant.core.runtime import limiter, metrics


@pytest.fixture(autouse=True)
def tmp_settings(tmp_path, monkeypatch):
    """Every test gets its own data directory and database, a fake API key and fresh limiters."""
    monkeypatch.setenv("ASSISTANT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")
    monkeypatch.setattr(base, "RETRY_WAIT_MULTIPLIER", 0)
    monkeypatch.setattr(base, "RETRY_WAIT_MAX", 0)
    get_settings.cache_clear()
    metrics.flush()
    db.close_all()
    limiter._limiters.clear()
    base._openai_clients.clear()
    base._http_clients.clear()
    db.init_db()
    yield get_settings()
    metrics.flush()
    db.close_all()
    get_settings.cache_clear()
