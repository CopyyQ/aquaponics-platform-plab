from datetime import datetime
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


TELEGRAM_CHAT_ID_PATTERN = re.compile(r"^(?:-100|-)?[1-9][0-9]{4,19}$")


class NotificationRecipientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    telegram_chat_id: str = Field(min_length=1, max_length=64)
    enabled: bool = True

    @field_validator("name", "telegram_chat_id", mode="before")
    @classmethod
    def trim_text(cls, value: object) -> str:
        return str(value).strip()

    @model_validator(mode="after")
    def validate_chat_id(self) -> "NotificationRecipientCreate":
        if not TELEGRAM_CHAT_ID_PATTERN.fullmatch(self.telegram_chat_id):
            raise ValueError("Telegram Chat ID phải là một định danh số hợp lệ")
        return self


class NotificationRecipientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    telegram_chat_id: str | None = Field(default=None, min_length=1, max_length=64)
    enabled: bool | None = None

    @field_validator("name", "telegram_chat_id", mode="before")
    @classmethod
    def trim_optional_text(cls, value: object) -> object:
        return str(value).strip() if value is not None else value

    @model_validator(mode="after")
    def validate_chat_id(self) -> "NotificationRecipientUpdate":
        if self.telegram_chat_id is not None and not TELEGRAM_CHAT_ID_PATTERN.fullmatch(
            self.telegram_chat_id
        ):
            raise ValueError("Telegram Chat ID phải là một định danh số hợp lệ")
        return self


class NotificationRecipientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    system_id: int = Field(validation_alias="project_id")
    name: str
    telegram_chat_id: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class NotificationSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    telegram_enabled: bool
    notify_alert_recovered: bool = True


class NotificationSettingsRead(NotificationSettingsUpdate):
    telegram_bot_configured: bool
    recipients: list[NotificationRecipientRead]


class TestMessageResult(BaseModel):
    sent: bool
    detail: str
