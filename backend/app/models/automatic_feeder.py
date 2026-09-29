from __future__ import annotations

from datetime import datetime, time
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.actuator import Actuator, ActuatorCommand


class FeedLevel(StrEnum):
    LEVEL_1 = "LEVEL_1"
    LEVEL_2 = "LEVEL_2"
    LEVEL_3 = "LEVEL_3"
    FREE = "FREE"


class FeederEventSource(StrEnum):
    SCHEDULE = "SCHEDULE"
    MANUAL = "MANUAL"


class FeederEventStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    MISSED = "MISSED"


class AutomaticFeederConfig(Base, TimestampMixin):
    __tablename__ = "automatic_feeder_configs"
    __table_args__ = (
        UniqueConstraint(
            "actuator_id", name="uq_automatic_feeder_configs_actuator_id"
        ),
        CheckConstraint(
            "feed_level IN ('LEVEL_1','LEVEL_2','LEVEL_3','FREE')",
            name="feed_level_allowed",
        ),
        CheckConstraint(
            "(free_output_value IS NULL AND free_output_unit IS NULL) OR "
            "(free_output_value IS NOT NULL AND free_output_unit IS NOT NULL)",
            name="free_output_pair",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    actuator_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("actuators.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    feed_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default=FeedLevel.LEVEL_1.value, server_default=FeedLevel.LEVEL_1.value
    )
    free_output_value: Mapped[float | None] = mapped_column(Float)
    free_output_unit: Mapped[str | None] = mapped_column(String(30))
    schedule_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    actuator: Mapped[Actuator] = relationship(back_populates="feeder_config")
    slots: Mapped[list[AutomaticFeederScheduleSlot]] = relationship(
        back_populates="config",
        cascade="all, delete-orphan",
        order_by="AutomaticFeederScheduleSlot.slot_number",
    )


class AutomaticFeederScheduleSlot(Base):
    __tablename__ = "automatic_feeder_schedule_slots"
    __table_args__ = (
        UniqueConstraint(
            "feeder_config_id",
            "slot_number",
            name="uq_automatic_feeder_schedule_slots_config_slot",
        ),
        UniqueConstraint(
            "feeder_config_id",
            "feed_time",
            name="uq_automatic_feeder_schedule_slots_config_time",
        ),
        CheckConstraint(
            "slot_number BETWEEN 1 AND 3",
            name="slot_number_range",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    feeder_config_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("automatic_feeder_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    slot_number: Mapped[int] = mapped_column(Integer, nullable=False)
    feed_time: Mapped[time] = mapped_column(Time, nullable=False)

    config: Mapped[AutomaticFeederConfig] = relationship(back_populates="slots")


class AutomaticFeederEvent(Base, TimestampMixin):
    __tablename__ = "automatic_feeder_events"
    __table_args__ = (
        UniqueConstraint(
            "actuator_id",
            "scheduled_at",
            name="uq_automatic_feeder_events_actuator_scheduled",
        ),
        CheckConstraint(
            "source IN ('SCHEDULE','MANUAL')",
            name="source_allowed",
        ),
        CheckConstraint(
            "feed_level IN ('LEVEL_1','LEVEL_2','LEVEL_3','FREE')",
            name="feed_level_allowed",
        ),
        CheckConstraint(
            "status IN ('SCHEDULED','RUNNING','COMPLETED','FAILED','MISSED')",
            name="status_allowed",
        ),
        CheckConstraint(
            "(free_output_value IS NULL AND free_output_unit IS NULL) OR "
            "(free_output_value IS NOT NULL AND free_output_unit IS NOT NULL)",
            name="free_output_pair",
        ),
        Index(
            "ix_automatic_feeder_events_status_scheduled",
            "status",
            "scheduled_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    actuator_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("actuators.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    command_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("actuator_commands.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    feed_level: Mapped[str] = mapped_column(String(20), nullable=False)
    free_output_value: Mapped[float | None] = mapped_column(Float)
    free_output_unit: Mapped[str | None] = mapped_column(String(30))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=FeederEventStatus.SCHEDULED.value, server_default=FeederEventStatus.SCHEDULED.value
    )
    failure_reason: Mapped[str | None] = mapped_column(Text)

    actuator: Mapped[Actuator] = relationship(back_populates="feeder_events")
    command: Mapped[ActuatorCommand | None] = relationship()
