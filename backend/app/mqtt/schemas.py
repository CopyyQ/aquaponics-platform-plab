from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.telemetry import DeviceReadingInput


class MqttTelemetryPayload(BaseModel):
    sent_at: datetime
    readings: list[DeviceReadingInput] = Field(min_length=1, max_length=500)


class MqttStatusPayload(BaseModel):
    status: Literal["ONLINE", "OFFLINE"]
    sent_at: datetime
    ip: str | None = None
    firmware_version: str | None = None
    actuators: list["MqttActuatorStatus"] = Field(max_length=500)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_legacy_status(cls, value: object) -> object:
        if isinstance(value, str) and value.lower() in {"online", "offline"}:
            return value.upper()
        return value


class MqttActuatorStatus(BaseModel):
    actuator_code: str
    state: bool
    voltage_v: float | None = None
    current_a: float | None = None
    recorded_at: datetime | None = None

    @field_validator("voltage_v", "current_a")
    @classmethod
    def finite_electrical_value(cls, value: float | None) -> float | None:
        if value is not None and (
            value != value or value in (float("inf"), float("-inf"))
        ):
            raise ValueError("Giá trị điện phải là số hữu hạn")
        return value


class MqttCommandAckPayload(BaseModel):
    command_id: int
    actuator_code: str
    reported_state: bool
    status: Literal["ACKNOWLEDGED", "FAILED"]
    sent_at: datetime
