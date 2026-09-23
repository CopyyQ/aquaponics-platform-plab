from sqlalchemy import inspect

from app.models.actuator import ActuatorCommand


def test_actuator_command_has_outbox_fields_and_due_index() -> None:
    columns = {column.name for column in inspect(ActuatorCommand).columns}
    assert {
        "publish_attempt_count",
        "last_publish_attempt_at",
        "next_publish_attempt_at",
        "publish_failure_reason",
    } <= columns

    indexes = {
        (index.name, tuple(column.name for column in index.columns))
        for index in ActuatorCommand.__table__.indexes
    }
    assert (
        "ix_actuator_commands_status_next_publish_attempt",
        ("status", "next_publish_attempt_at"),
    ) in indexes
