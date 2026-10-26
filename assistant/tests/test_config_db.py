import pytest

from assistant.core import db
from assistant.core.config import ConfigError, get_settings
from assistant.core.notebooks import create_notebook, get_notebook, list_notebooks


def test_every_model_has_required_fields():
    for role, m in get_settings().models.items():
        assert m.id, role
        assert m.rpm > 0, role
        assert m.max_in_flight > 0, role


def test_data_dir_override(tmp_path):
    assert get_settings().data_dir == (tmp_path / "data").resolve()


def test_missing_api_key_is_a_clear_error(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "")
    get_settings.cache_clear()
    with pytest.raises(ConfigError, match="NVIDIA_API_KEY"):
        _ = get_settings().api_key


def test_init_db_is_idempotent():
    db.init_db()
    db.init_db()
    versions = [r[0] for r in db.connect().execute("SELECT version FROM schema_version")]
    assert versions == sorted(set(versions)) and 1 in versions


def test_notebooks():
    nb = create_notebook("  Biologie — S1 ")
    assert nb.name == "Biologie — S1"
    assert get_notebook(nb.id) == nb
    assert [n.id for n in list_notebooks()] == [nb.id]
    with pytest.raises(ValueError):
        create_notebook("   ")
