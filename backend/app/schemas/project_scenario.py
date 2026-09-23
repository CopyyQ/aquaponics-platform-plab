from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

RiskLevel = Literal["LOW", "LOW_MEDIUM", "MEDIUM", "HIGH", "VERY_HIGH", "EXTREME"]


class DeviceScenarioCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    clone_from_scenario_id: UUID | None = None


class DeviceScenarioMetadataUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)


class DeviceScenarioCloneRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)


class DeviceScenarioItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_enabled: bool | None = None
    notes: str | None = Field(default=None, max_length=4000)


class DeviceScenarioBranchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_key: str | None = Field(default=None, min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    evaluator_type: str = Field(min_length=1, max_length=50)
    condition_config: dict[str, Any]
    duration_seconds: int = Field(default=0, ge=0, le=86400)
    business_risk_level: RiskLevel
    message_template: str | None = Field(default=None, max_length=4000)
    consequence: str | None = Field(default=None, max_length=4000)
    recommended_action: str | None = Field(default=None, max_length=4000)
    is_enabled: bool = True
    position: int = Field(default=0, ge=0)


class DeviceScenarioBranchUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    evaluator_type: str | None = Field(default=None, min_length=1, max_length=50)
    condition_config: dict[str, Any] | None = None
    duration_seconds: int | None = Field(default=None, ge=0, le=86400)
    business_risk_level: RiskLevel | None = None
    message_template: str | None = Field(default=None, max_length=4000)
    consequence: str | None = Field(default=None, max_length=4000)
    recommended_action: str | None = Field(default=None, max_length=4000)
    is_enabled: bool | None = None
    position: int | None = Field(default=None, ge=0)


class DeviceScenarioResourceRead(BaseModel):
    id: UUID
    code: str
    name: str
    model_id: int | None
    is_enabled: bool


class DeviceScenarioBranchRead(BaseModel):
    id: UUID
    branch_key: str
    name: str
    evaluator_type: str
    condition_config: dict[str, Any]
    duration_seconds: int
    business_risk_level: RiskLevel
    message_template: str | None
    consequence: str | None
    recommended_action: str | None
    is_enabled: bool
    position: int
    created_at: datetime
    updated_at: datetime


class DeviceScenarioItemRead(BaseModel):
    id: UUID
    target_type: Literal["SENSOR", "ACTUATOR"]
    resource: DeviceScenarioResourceRead
    name: str
    is_enabled: bool
    branches: list[DeviceScenarioBranchRead]


class DeviceScenarioSummaryRead(BaseModel):
    id: UUID
    name: str
    description: str | None
    is_active: bool
    sensor_count: int
    actuator_count: int
    source_scenario_catalog_id: int | None
    cloned_from_scenario_id: UUID | None
    created_at: datetime
    updated_at: datetime


class DeviceScenarioDetailRead(DeviceScenarioSummaryRead):
    sensors: list[DeviceScenarioItemRead]
    actuators: list[DeviceScenarioItemRead]


class DeviceScenarioActivationRead(BaseModel):
    scenario: DeviceScenarioSummaryRead
    previous_scenario_id: UUID | None
    closed_incident_count: int = 0
    reevaluated_sensor_count: int = 0
    reevaluated_actuator_count: int = 0


# Internal compatibility aliases. OpenAPI component names remain DeviceScenario*.
ProjectScenarioCreate = DeviceScenarioCreate
ProjectScenarioMetadataUpdate = DeviceScenarioMetadataUpdate
ProjectScenarioCloneRequest = DeviceScenarioCloneRequest
ProjectScenarioItemUpdate = DeviceScenarioItemUpdate
ProjectScenarioBranchCreate = DeviceScenarioBranchCreate
ProjectScenarioBranchUpdate = DeviceScenarioBranchUpdate
ProjectScenarioResourceRead = DeviceScenarioResourceRead
ProjectScenarioBranchRead = DeviceScenarioBranchRead
ProjectScenarioItemRead = DeviceScenarioItemRead
ProjectScenarioSummaryRead = DeviceScenarioSummaryRead
ProjectScenarioDetailRead = DeviceScenarioDetailRead
ProjectScenarioActivationRead = DeviceScenarioActivationRead
