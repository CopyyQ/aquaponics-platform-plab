import importlib
import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, UniqueConstraint


def _feeder_module():
    spec = importlib.util.find_spec("app.models.automatic_feeder")
    assert spec is not None, "automatic feeder persistence module is missing"
    return importlib.import_module("app.models.automatic_feeder")


def _constraint_names(table, kind):
    return {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, kind)
    }


def test_automatic_feeder_models_define_expected_tables_and_enums() -> None:
    module = _feeder_module()

    assert module.AutomaticFeederConfig.__tablename__ == "automatic_feeder_configs"
    assert module.AutomaticFeederScheduleSlot.__tablename__ == "automatic_feeder_schedule_slots"
    assert module.AutomaticFeederEvent.__tablename__ == "automatic_feeder_events"
    assert {item.value for item in module.FeedLevel} == {
        "LEVEL_1",
        "LEVEL_2",
        "LEVEL_3",
        "FREE",
    }
    assert {item.value for item in module.FeederEventSource} == {"SCHEDULE", "MANUAL"}
    assert {item.value for item in module.FeederEventStatus} == {
        "SCHEDULED",
        "RUNNING",
        "COMPLETED",
        "FAILED",
        "MISSED",
    }


def test_feeder_config_is_one_to_one_with_actuator() -> None:
    module = _feeder_module()
    table = module.AutomaticFeederConfig.__table__

    assert table.c.actuator_id.nullable is False
    assert "uq_automatic_feeder_configs_actuator_id" in _constraint_names(
        table, UniqueConstraint
    )
    fk = next(iter(table.c.actuator_id.foreign_keys))
    assert fk.target_fullname == "actuators.id"
    assert fk.ondelete == "CASCADE"


def test_schedule_slot_constraints_enforce_three_unique_times() -> None:
    module = _feeder_module()
    table = module.AutomaticFeederScheduleSlot.__table__

    unique_names = _constraint_names(table, UniqueConstraint)
    check_names = _constraint_names(table, CheckConstraint)
    assert "uq_automatic_feeder_schedule_slots_config_slot" in unique_names
    assert "uq_automatic_feeder_schedule_slots_config_time" in unique_names
    assert "ck_automatic_feeder_schedule_slots_slot_number_range" in check_names


def test_event_is_idempotent_per_actuator_and_scheduled_time() -> None:
    module = _feeder_module()
    table = module.AutomaticFeederEvent.__table__

    unique_names = _constraint_names(table, UniqueConstraint)
    assert "uq_automatic_feeder_events_actuator_scheduled" in unique_names
    assert table.c.scheduled_at.nullable is False
    assert table.c.command_id.nullable is True


def test_feeder_schema_is_in_v2_migration_not_released_v1() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    assert script.get_current_head() == "v2_automatic_feeder"
    v1_source = Path("alembic/versions/v1_baseline.py").read_text(encoding="utf-8")
    v2_source = Path("alembic/versions/v2_automatic_feeder.py").read_text(encoding="utf-8")
    for table_name in (
        "automatic_feeder_configs",
        "automatic_feeder_schedule_slots",
        "automatic_feeder_events",
    ):
        assert table_name not in v1_source
        assert f'op.create_table(\n        "{table_name}"' in v2_source
    assert "op.add_column(" in v2_source
    assert '"actuator_commands"' in v2_source