from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def disposable_runtime_fixture():
    yield


def test_bootstrap_uses_alembic_upgrade_not_create_all_or_stamp() -> None:
    source = Path("scripts/bootstrap_fresh_database.py").read_text(encoding="utf-8")
    assert 'command.upgrade(config, "head")' in source
    assert "create_all" not in source
    assert "command.stamp" not in source
    assert "from app.core.database import Base" not in source
    assert "from app import models" not in source


def test_bootstrap_does_not_print_database_credentials() -> None:
    source = Path("scripts/bootstrap_fresh_database.py").read_text(encoding="utf-8")
    assert "settings.database_url" not in source
