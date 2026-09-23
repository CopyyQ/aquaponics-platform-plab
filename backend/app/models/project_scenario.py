from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.actuator import Actuator
    from app.models.device import Device
    from app.models.project import Project
    from app.models.scenario_catalog import ScenarioCatalog, ScenarioCatalogItem
    from app.models.sensor import Sensor
    from app.models.user import User


class ProjectScenario(Base, TimestampMixin):
    __tablename__ = "project_scenarios"
    __table_args__ = (
        Index("ix_project_scenarios_aquaponics_system_id", "aquaponics_system_id"),
        Index("ix_project_scenarios_device_id", "device_id"),
        Index(
            "uq_project_scenarios_one_active_device",
            "device_id",
            unique=True,
            postgresql_where=text("is_active = true AND retired_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    public_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), default=uuid4, unique=True, nullable=False, index=True
    )
    project_id: Mapped[int] = mapped_column(
        "aquaponics_system_id",
        BigInteger,
        ForeignKey("aquaponics_systems.id", ondelete="RESTRICT"),
        nullable=False,
    )
    device_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("devices.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    source_scenario_catalog_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("scenario_catalogs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    cloned_from_scenario_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("project_scenarios.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project] = relationship()
    device: Mapped[Device] = relationship()
    source_scenario_catalog: Mapped[ScenarioCatalog | None] = relationship()
    cloned_from_scenario: Mapped[ProjectScenario | None] = relationship(
        remote_side=[id],
        foreign_keys=[cloned_from_scenario_id],
    )
    creator: Mapped[User | None] = relationship(foreign_keys=[created_by])
    updater: Mapped[User | None] = relationship(foreign_keys=[updated_by])
    items: Mapped[list[ProjectScenarioItem]] = relationship(
        back_populates="scenario",
        cascade="all, delete-orphan",
        order_by="ProjectScenarioItem.id",
    )


class ProjectScenarioItem(Base, TimestampMixin):
    __tablename__ = "project_scenario_items"
    __table_args__ = (
        CheckConstraint(
            "(target_type='SENSOR' AND sensor_id IS NOT NULL AND actuator_id IS NULL) "
            "OR (target_type='ACTUATOR' AND actuator_id IS NOT NULL AND sensor_id IS NULL)",
            name="project_scenario_item_target_matches_resource",
        ),
        Index("ix_project_scenario_items_scenario_id", "project_scenario_id"),
        Index(
            "uq_project_scenario_items_sensor",
            "project_scenario_id",
            "sensor_id",
            unique=True,
            postgresql_where=text(
                "sensor_id IS NOT NULL AND retired_at IS NULL"
            ),
        ),
        Index(
            "uq_project_scenario_items_actuator",
            "project_scenario_id",
            "actuator_id",
            unique=True,
            postgresql_where=text(
                "actuator_id IS NOT NULL AND retired_at IS NULL"
            ),
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    public_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), default=uuid4, unique=True, nullable=False, index=True
    )
    project_scenario_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("project_scenarios.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)
    sensor_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("sensors.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    actuator_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("actuators.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    source_scenario_catalog_item_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("scenario_catalog_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    scenario: Mapped[ProjectScenario] = relationship(back_populates="items")
    sensor: Mapped[Sensor | None] = relationship()
    actuator: Mapped[Actuator | None] = relationship()
    source_scenario_catalog_item: Mapped[ScenarioCatalogItem | None] = relationship()
    branches: Mapped[list[ProjectScenarioBranch]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="ProjectScenarioBranch.position, ProjectScenarioBranch.id",
    )


class ProjectScenarioBranch(Base, TimestampMixin):
    __tablename__ = "project_scenario_branches"
    __table_args__ = (
        CheckConstraint(
            "evaluator_type IN ("
            "'THRESHOLD','THRESHOLD_BANDS','RANGE_BANDS','DIGITAL_STATE',"
            "'THRESHOLD_DURATION','BASELINE_DEVIATION','WINDOW_DURATION',"
            "'TREND','MULTI_CONDITION')",
            name="project_scenario_branch_evaluator_type_allowed",
        ),
        CheckConstraint(
            "business_risk_level IN "
            "('EXTREME','VERY_HIGH','HIGH','MEDIUM','LOW_MEDIUM','LOW')",
            name="project_scenario_branch_risk_allowed",
        ),
        CheckConstraint(
            "duration_seconds >= 0",
            name="project_scenario_branch_duration_nonnegative",
        ),
        CheckConstraint(
            "position >= 0",
            name="project_scenario_branch_position_nonnegative",
        ),
        Index(
            "ix_project_scenario_branches_item_id",
            "project_scenario_item_id",
        ),
        Index(
            "uq_project_scenario_branches_active_key",
            "project_scenario_item_id",
            "branch_key",
            unique=True,
            postgresql_where=text("retired_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    public_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), default=uuid4, unique=True, nullable=False, index=True
    )
    project_scenario_item_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("project_scenario_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    branch_key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    evaluator_type: Mapped[str] = mapped_column(String(50), nullable=False)
    condition_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    duration_seconds: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    business_risk_level: Mapped[str] = mapped_column(String(30), nullable=False)
    message_template: Mapped[str | None] = mapped_column(Text)
    consequence: Mapped[str | None] = mapped_column(Text)
    recommended_action: Mapped[str | None] = mapped_column(Text)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    position: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    item: Mapped[ProjectScenarioItem] = relationship(back_populates="branches")
    creator: Mapped[User | None] = relationship(foreign_keys=[created_by])
    updater: Mapped[User | None] = relationship(foreign_keys=[updated_by])
