from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Identity, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.actuator_model import ActuatorModel
    from app.models.device_template import DeviceTemplate
    from app.models.sensor_model import SensorModel


class ScenarioCatalog(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "scenario_catalogs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    public_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), default=uuid4, unique=True, index=True, nullable=False
    )
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    device_template_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("device_templates.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))

    device_template: Mapped["DeviceTemplate"] = relationship(back_populates="scenario_catalogs")
    items: Mapped[list["ScenarioCatalogItem"]] = relationship(
        back_populates="catalog", cascade="all, delete-orphan", order_by="ScenarioCatalogItem.id"
    )


class ScenarioCatalogItem(Base, TimestampMixin):
    __tablename__ = "scenario_catalog_items"
    __table_args__ = (
        CheckConstraint(
            "(target_type = 'SENSOR' AND sensor_model_id IS NOT NULL AND actuator_model_id IS NULL) "
            "OR (target_type = 'ACTUATOR' AND actuator_model_id IS NOT NULL AND sensor_model_id IS NULL)",
            name="scenario_catalog_item_target_matches_model",
        ),
        UniqueConstraint(
            "scenario_catalog_id", "target_type", "resource_code",
            name="uq_scenario_catalog_resource_code",
        ),
        Index("ix_scenario_catalog_items_catalog_id", "scenario_catalog_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    scenario_catalog_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("scenario_catalogs.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)
    resource_code: Mapped[str] = mapped_column(String(80), nullable=False)
    sensor_model_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sensor_models.id", ondelete="RESTRICT"), index=True
    )
    actuator_model_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("actuator_models.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    branches: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    source_reference: Mapped[str] = mapped_column(
        String(255), default="Aquaponics source documents", server_default="Aquaponics source documents"
    )
    notes: Mapped[str | None] = mapped_column(Text)

    catalog: Mapped["ScenarioCatalog"] = relationship(back_populates="items")
    sensor_model: Mapped["SensorModel | None"] = relationship()
    actuator_model: Mapped["ActuatorModel | None"] = relationship()
