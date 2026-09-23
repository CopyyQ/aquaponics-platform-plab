from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


RiskLevel = Literal["LOW", "LOW_MEDIUM", "MEDIUM", "HIGH", "VERY_HIGH", "EXTREME"]
TargetType = Literal["SENSOR", "ACTUATOR"]
TechnicalSeverity = Literal["WARNING", "CRITICAL"]


class ScenarioBranch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^[A-Z0-9_]{2,80}$")
    label: str = Field(min_length=1, max_length=255)
    enabled: bool = True
    evaluator_type: Literal[
        "THRESHOLD", "THRESHOLD_BANDS", "RANGE_BANDS", "DIGITAL_STATE",
        "THRESHOLD_DURATION", "BASELINE_DEVIATION", "WINDOW_DURATION",
        "TREND", "MULTI_CONDITION",
    ]
    condition_config: dict[str, Any]
    risk_level: RiskLevel = "MEDIUM"
    message: str | None = Field(default=None, max_length=2000)
    consequence: str | None = Field(default=None, max_length=4000)
    recommended_action: str | None = Field(default=None, max_length=4000)


class ScenarioCatalogCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_template_id: int = Field(gt=0)
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,99}$")
    name: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=4000)


class ScenarioCatalogUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    is_active: bool | None = None


class ScenarioCatalogItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_enabled: bool | None = None
    branches: list[ScenarioBranch] | None = None
    notes: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def unique_branch_keys(self):
        if self.branches is not None:
            keys = [branch.key for branch in self.branches]
            if len(keys) != len(set(keys)):
                raise ValueError("Mỗi nhánh điều kiện phải có key duy nhất")
        return self


class ScenarioCatalogItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    target_type: TargetType
    resource_code: str
    sensor_model_id: int | None
    actuator_model_id: int | None
    model_code: str
    model_name: str
    name: str
    is_enabled: bool
    branches: list[ScenarioBranch]
    source_reference: str
    notes: str | None


class ScenarioCatalogRead(BaseModel):
    id: int
    public_id: UUID
    device_template_id: int
    code: str
    name: str
    description: str | None
    is_active: bool
    items: list[ScenarioCatalogItemRead]
