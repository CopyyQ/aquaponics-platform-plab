"""automatic feeder backend

Revision ID: v2_automatic_feeder
Revises: v1
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "v2_automatic_feeder"
down_revision: str | None = "v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "actuator_commands",
        sa.Column(
            "command_type",
            sa.String(length=30),
            server_default="SET_STATE",
            nullable=False,
        ),
    )
    op.add_column(
        "actuator_commands",
        sa.Column(
            "command_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )

    op.create_table(
        "automatic_feeder_configs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("actuator_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "feed_level",
            sa.String(length=20),
            server_default="LEVEL_1",
            nullable=False,
        ),
        sa.Column("free_output_value", sa.Float(), nullable=True),
        sa.Column("free_output_unit", sa.String(length=30), nullable=True),
        sa.Column(
            "schedule_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "feed_level IN ('LEVEL_1','LEVEL_2','LEVEL_3','FREE')",
            name=op.f("ck_automatic_feeder_configs_feed_level_allowed"),
        ),
        sa.CheckConstraint(
            "(free_output_value IS NULL AND free_output_unit IS NULL) OR "
            "(free_output_value IS NOT NULL AND free_output_unit IS NOT NULL)",
            name=op.f("ck_automatic_feeder_configs_free_output_pair"),
        ),
        sa.ForeignKeyConstraint(
            ["actuator_id"],
            ["actuators.id"],
            name=op.f("fk_automatic_feeder_configs_actuator_id_actuators"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_automatic_feeder_configs")
        ),
        sa.UniqueConstraint(
            "actuator_id",
            name="uq_automatic_feeder_configs_actuator_id",
        ),
    )
    op.create_index(
        op.f("ix_automatic_feeder_configs_actuator_id"),
        "automatic_feeder_configs",
        ["actuator_id"],
        unique=False,
    )

    op.create_table(
        "automatic_feeder_schedule_slots",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("feeder_config_id", sa.BigInteger(), nullable=False),
        sa.Column("slot_number", sa.Integer(), nullable=False),
        sa.Column("feed_time", sa.Time(), nullable=False),
        sa.CheckConstraint(
            "slot_number BETWEEN 1 AND 3",
            name=op.f(
                "ck_automatic_feeder_schedule_slots_slot_number_range"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["feeder_config_id"],
            ["automatic_feeder_configs.id"],
            name=op.f(
                "fk_automatic_feeder_schedule_slots_feeder_config_id_automatic_feeder_configs"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_automatic_feeder_schedule_slots")
        ),
        sa.UniqueConstraint(
            "feeder_config_id",
            "slot_number",
            name="uq_automatic_feeder_schedule_slots_config_slot",
        ),
        sa.UniqueConstraint(
            "feeder_config_id",
            "feed_time",
            name="uq_automatic_feeder_schedule_slots_config_time",
        ),
    )
    op.create_index(
        op.f("ix_automatic_feeder_schedule_slots_feeder_config_id"),
        "automatic_feeder_schedule_slots",
        ["feeder_config_id"],
        unique=False,
    )

    op.create_table(
        "automatic_feeder_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("actuator_id", sa.BigInteger(), nullable=False),
        sa.Column("command_id", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("feed_level", sa.String(length=20), nullable=False),
        sa.Column("free_output_value", sa.Float(), nullable=True),
        sa.Column("free_output_unit", sa.String(length=30), nullable=True),
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "ended_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="SCHEDULED",
            nullable=False,
        ),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('SCHEDULE','MANUAL')",
            name=op.f("ck_automatic_feeder_events_source_allowed"),
        ),
        sa.CheckConstraint(
            "feed_level IN ('LEVEL_1','LEVEL_2','LEVEL_3','FREE')",
            name=op.f("ck_automatic_feeder_events_feed_level_allowed"),
        ),
        sa.CheckConstraint(
            "status IN ('SCHEDULED','RUNNING','COMPLETED','FAILED','MISSED')",
            name=op.f("ck_automatic_feeder_events_status_allowed"),
        ),
        sa.CheckConstraint(
            "(free_output_value IS NULL AND free_output_unit IS NULL) OR "
            "(free_output_value IS NOT NULL AND free_output_unit IS NOT NULL)",
            name=op.f("ck_automatic_feeder_events_free_output_pair"),
        ),
        sa.ForeignKeyConstraint(
            ["actuator_id"],
            ["actuators.id"],
            name=op.f("fk_automatic_feeder_events_actuator_id_actuators"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["command_id"],
            ["actuator_commands.id"],
            name=op.f(
                "fk_automatic_feeder_events_command_id_actuator_commands"
            ),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_automatic_feeder_events")
        ),
        sa.UniqueConstraint(
            "actuator_id",
            "scheduled_at",
            name="uq_automatic_feeder_events_actuator_scheduled",
        ),
    )
    op.create_index(
        op.f("ix_automatic_feeder_events_actuator_id"),
        "automatic_feeder_events",
        ["actuator_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_automatic_feeder_events_command_id"),
        "automatic_feeder_events",
        ["command_id"],
        unique=False,
    )
    op.create_index(
        "ix_automatic_feeder_events_status_scheduled",
        "automatic_feeder_events",
        ["status", "scheduled_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_automatic_feeder_events_status_scheduled",
        table_name="automatic_feeder_events",
    )
    op.drop_index(
        op.f("ix_automatic_feeder_events_command_id"),
        table_name="automatic_feeder_events",
    )
    op.drop_index(
        op.f("ix_automatic_feeder_events_actuator_id"),
        table_name="automatic_feeder_events",
    )
    op.drop_table("automatic_feeder_events")
    op.drop_index(
        op.f("ix_automatic_feeder_schedule_slots_feeder_config_id"),
        table_name="automatic_feeder_schedule_slots",
    )
    op.drop_table("automatic_feeder_schedule_slots")
    op.drop_index(
        op.f("ix_automatic_feeder_configs_actuator_id"),
        table_name="automatic_feeder_configs",
    )
    op.drop_table("automatic_feeder_configs")
    op.drop_column("actuator_commands", "command_payload")
    op.drop_column("actuator_commands", "command_type")
