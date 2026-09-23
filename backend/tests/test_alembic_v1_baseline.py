from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def disposable_runtime_fixture():
    yield


def test_alembic_history_is_single_v1_baseline() -> None:
    versions = Path("alembic/versions")
    revisions = sorted(
        path
        for path in versions.glob("*.py")
        if path.name != "__init__.py"
    )
    assert [path.name for path in revisions] == ["v1_baseline.py"]

    module_spec = spec_from_file_location("v1_baseline", revisions[0])
    assert module_spec is not None
    assert module_spec.loader is not None
    module = module_from_spec(module_spec)
    module_spec.loader.exec_module(module)

    assert module.revision == "v1"
    assert module.down_revision is None


def test_alembic_env_has_no_legacy_revision_compatibility_filters() -> None:
    source = Path("alembic/env.py").read_text(encoding="utf-8")
    assert "COMPATIBILITY_NAMES" not in source
    assert "ARCHIVE_TABLES" not in source
    assert "include_object=" not in source


def test_v1_baseline_creates_deferred_alert_rule_revision_fk() -> None:
    source = Path("alembic/versions/v1_baseline.py").read_text(encoding="utf-8")
    expected = (
        "op.create_foreign_key('fk_alert_rules_current_revision_id_alert_rule_revisions', "
        "'alert_rules', 'alert_rule_revisions', ['current_revision_id'], ['id'], "
        "ondelete='SET NULL')"
    )
    assert expected in source


def test_v1_baseline_is_frozen_explicit_ddl() -> None:
    source = Path("alembic/versions/v1_baseline.py").read_text(encoding="utf-8")
    assert "op.create_table(" in source
    assert "op.create_index(" in source
    assert "Base.metadata.create_all" not in source
    assert "command.stamp" not in source
    assert "from app.models" not in source
    assert "import app.models" not in source
    assert "V1 baseline downgrade is intentionally unsupported" in source
    downgrade_source = source.split("def downgrade() -> None:", 1)[1]
    assert "raise RuntimeError(" in downgrade_source
    assert "op.drop_table(" not in downgrade_source

def test_v1_baseline_contains_project_scenario_schema() -> None:
    source = Path("alembic/versions/v1_baseline.py").read_text(encoding="utf-8")
    for required in (
        'op.create_table(\n        "project_scenarios"',
        'op.create_table(\n        "project_scenario_items"',
        'op.create_table(\n        "project_scenario_branches"',
        '"project_scenario_branch_id"',
        '"resolution_reason"',
    ):
        assert required in source
