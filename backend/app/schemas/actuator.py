from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.automatic_feeder import FeedLevel


class ActuatorCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actuator_model_id: int = Field(gt=0)
    location: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class ActuatorUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class ActuatorModelSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str


class ActuatorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: int
    actuator_model_id: int | None
    actuator_model: ActuatorModelSummary | None
    sequence_number: int
    code: str
    name: str
    location: str | None
    notes: str | None
    is_enabled: bool
    desired_state: bool | None
    reported_state: bool | None
    last_command_at: datetime | None
    last_reported_at: datetime | None
    status_received_at: datetime | None
    voltage_v: float | None
    current_a: float | None
    electrical_recorded_at: datetime | None
    electrical_received_at: datetime | None
    electrical_alerts_enabled: bool
    voltage_lower_threshold: float | None
    voltage_upper_threshold: float | None
    voltage_low_message: str | None
    voltage_high_message: str | None
    voltage_low_risk_level: str | None
    voltage_high_risk_level: str | None
    current_lower_threshold: float | None
    current_upper_threshold: float | None
    current_low_message: str | None
    current_high_message: str | None
    current_low_risk_level: str | None
    current_high_risk_level: str | None
    disabled_at: datetime | None
    disabled_by_user_id: int | None
    disabled_reason: str | None
    removed_at: datetime | None
    removed_by_user_id: int | None
    removed_reason: str | None
    created_at: datetime
    updated_at: datetime


class ActuatorReadingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actuator_id: UUID
    voltage_v: float | None
    current_a: float | None
    recorded_at: datetime
    received_at: datetime
    quality: str


class AutomaticFeederCommandParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feed_level: FeedLevel | None = None
    free_output_value: float | None = Field(default=None, ge=0)
    free_output_unit: str | None = Field(default=None, min_length=1, max_length=30)


class ActuatorCommandCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_type: Literal["SET_STATE", "FEED"] = "SET_STATE"
    desired_state: bool | None = None
    params: AutomaticFeederCommandParams | None = None

    @model_validator(mode="after")
    def validate_command(self) -> "ActuatorCommandCreate":
        if self.command_type == "SET_STATE":
            if self.desired_state is None:
                raise ValueError("SET_STATE yêu cầu desired_state")
            if self.params is not None:
                raise ValueError("SET_STATE không nhận params")
        elif self.desired_state is False:
            raise ValueError("FEED không cho phép desired_state=false")
        return self


class ActuatorCommandRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    command_id: int
    actuator_id: UUID
    command_type: str
    params: dict
    desired_state: bool
    reported_state: bool | None
    status: str
    requested_at: datetime
