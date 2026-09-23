from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Identity, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.project import Project


class ProjectPublicSettings(Base, TimestampMixin):
    __tablename__ = "project_public_settings"
    __table_args__ = (
        UniqueConstraint("aquaponics_system_id", name="uq_aquaponics_system_public_settings_system_id"),
        UniqueConstraint("public_slug", name="uq_project_public_settings_public_slug"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    project_id: Mapped[int] = mapped_column(
        "aquaponics_system_id",
        BigInteger,
        ForeignKey("aquaponics_systems.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    public_slug: Mapped[str] = mapped_column(String(120), nullable=False)
    project: Mapped["Project"] = relationship()


class ProjectNotificationSettings(Base, TimestampMixin):
    __tablename__ = "project_notification_settings"
    __table_args__ = (
        UniqueConstraint(
            "aquaponics_system_id",
            name="uq_aquaponics_system_notification_settings_system_id",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    project_id: Mapped[int] = mapped_column(
        "aquaponics_system_id",
        BigInteger,
        ForeignKey("aquaponics_systems.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # General alert visibility remains separate from Telegram delivery so the
    # system Settings page can keep controlling the in-app alert channel.
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    in_app_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    # Telegram intentionally has only one channel switch plus recovery opt-in.
    # OPEN is always sent when Telegram is enabled; risk-level routing,
    # escalation, reminders and replay policies are not configurable.
    telegram_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    notify_alert_recovered: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )

    last_health_status: Mapped[str | None] = mapped_column(String(30))
    last_health_fingerprint: Mapped[str | None] = mapped_column(String(64))
    last_health_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    last_health_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_health_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    project: Mapped["Project"] = relationship()


class ProjectNotificationRecipient(Base, TimestampMixin):
    __tablename__ = "project_notification_recipients"
    __table_args__ = (
        UniqueConstraint(
            "aquaponics_system_id",
            "telegram_chat_id",
            name="uq_aquaponics_system_notification_recipient_chat",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    project_id: Mapped[int] = mapped_column(
        "aquaponics_system_id",
        BigInteger,
        ForeignKey("aquaponics_systems.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    telegram_chat_id: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    project: Mapped["Project"] = relationship()
