import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.core.config import Settings


BASE = {
    "secret_key": "s" * 64,
    "database_url": "postgresql+asyncpg://u:p@localhost/db",
    "default_admin_password": "Password@123",
}


def test_settings_require_fernet_key(monkeypatch) -> None:
    monkeypatch.delenv("FERNET_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None, **BASE)


def test_settings_reject_invalid_fernet_key(monkeypatch) -> None:
    monkeypatch.delenv("FERNET_KEY", raising=False)

    with pytest.raises(ValidationError, match="FERNET_KEY"):
        Settings(_env_file=None, fernet_key="not-a-valid-fernet-key", **BASE)


def test_settings_accept_valid_auth_security_defaults(monkeypatch) -> None:
    for name in (
        "FERNET_KEY",
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        "AUTH_SESSION_DAYS",
        "LOGIN_RATE_LIMIT_IDENTITY_ATTEMPTS",
        "LOGIN_RATE_LIMIT_IP_ATTEMPTS",
        "LOGIN_RATE_LIMIT_WINDOW_SECONDS",
        "LOGIN_RATE_LIMIT_BLOCK_SECONDS",
        "AUTH_RATE_LIMIT_RETENTION_HOURS",
        "AUTH_SESSION_RETENTION_DAYS",
    ):
        monkeypatch.delenv(name, raising=False)
    key = Fernet.generate_key().decode()

    config = Settings(_env_file=None, fernet_key=key, **BASE)

    assert config.fernet_key == key
    assert config.access_token_expire_minutes == 30
    assert config.auth_session_days == 30
    assert config.login_rate_limit_identity_attempts == 5
    assert config.login_rate_limit_ip_attempts == 30
    assert config.login_rate_limit_window_seconds == 600
    assert config.login_rate_limit_block_seconds == 900
    assert config.auth_rate_limit_retention_hours == 24
    assert config.auth_session_retention_days == 90


def test_env_example_documents_auth_and_outbox_security_defaults() -> None:
    from pathlib import Path

    env_path = Path(__file__).resolve().parents[1] / ".env.example"
    values = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value

    assert values["ACCESS_TOKEN_EXPIRE_MINUTES"] == "30"
    assert values["AUTH_SESSION_DAYS"] == "30"
    assert values["LOGIN_RATE_LIMIT_IDENTITY_ATTEMPTS"] == "5"
    assert values["LOGIN_RATE_LIMIT_IP_ATTEMPTS"] == "30"
    assert values["LOGIN_RATE_LIMIT_WINDOW_SECONDS"] == "600"
    assert values["LOGIN_RATE_LIMIT_BLOCK_SECONDS"] == "900"
    assert values["ACTUATOR_COMMAND_DISPATCH_INTERVAL_SECONDS"] == "1"
    assert values["ACTUATOR_COMMAND_PUBLISH_MAX_ATTEMPTS"] == "7"
    assert values["ACTUATOR_COMMAND_PUBLISH_TIMEOUT_SECONDS"] == "5"
    assert "FERNET_KEY" in values


def test_settings_reject_wildcard_cors_with_credentialed_auth(monkeypatch) -> None:
    monkeypatch.delenv("FERNET_KEY", raising=False)

    with pytest.raises(ValidationError, match="explicit CORS origins"):
        Settings(
            _env_file=None,
            fernet_key=Fernet.generate_key().decode(),
            cors_origins=["*"],
            **BASE,
        )
