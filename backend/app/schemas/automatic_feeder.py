from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.models.automatic_feeder import FeederEventSource, FeederEventStatus, FeedLevel

HHMM = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
    ),
]


class AutomaticFeederCurrentFeedRead(BaseModel):
    event_id: int
    source: FeederEventSource
    status: FeederEventStatus
    feed_level: FeedLevel
    free_output_value: float | None = None
    free_output_unit: str | None = None
    scheduled_at: datetime
    started_at: datetime | None = None


class AutomaticFeederRead(BaseModel):
    feed_level: FeedLevel
    free_output_value: float | None = None
    free_output_unit: str | None = None
    schedule_enabled: bool
    schedule: list[HHMM] = Field(min_length=3, max_length=3)
    current_feed: AutomaticFeederCurrentFeedRead | None = None
    last_feed_at: datetime | None = None
    next_feed_at: datetime | None = None


class AutomaticFeederUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feed_level: FeedLevel | None = None
    free_output_value: float | None = Field(default=None, ge=0)
    free_output_unit: str | None = Field(default=None, min_length=1, max_length=30)
    schedule_enabled: bool | None = None
    schedule: list[HHMM] | None = Field(default=None, min_length=3, max_length=3)

    @field_validator("schedule")
    @classmethod
    def schedule_times_must_be_unique(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len(set(value)) != len(value):
            raise ValueError("Ba thời điểm cho ăn phải khác nhau")
        return value

    @model_validator(mode="after")
    def validate_free_output(self) -> AutomaticFeederUpdate:
        if self.feed_level == FeedLevel.FREE:
            if self.free_output_value is None or not self.free_output_unit:
                raise ValueError("Mức FREE yêu cầu free_output_value và free_output_unit")
        elif self.feed_level is not None and (
            self.free_output_value is not None or self.free_output_unit is not None
        ):
            raise ValueError("Chỉ mức FREE được phép truyền free_output_value/free_output_unit")
        return self