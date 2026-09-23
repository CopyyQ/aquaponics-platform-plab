from sqlalchemy import inspect

from app.models.auth_session import AuthRateLimitBucket, UserSession


def test_user_session_schema_contract() -> None:
    mapper = inspect(UserSession)
    columns = {column.name for column in mapper.columns}

    assert UserSession.__tablename__ == "user_sessions"
    assert {
        "id",
        "public_id",
        "user_id",
        "refresh_token_hash",
        "created_at",
        "expires_at",
        "last_refreshed_at",
        "revoked_at",
        "revoke_reason",
        "ip_hash",
        "user_agent_hash",
    } <= columns
    assert mapper.columns.refresh_token_hash.unique is True


def test_auth_rate_limit_bucket_schema_contract() -> None:
    mapper = inspect(AuthRateLimitBucket)
    columns = {column.name for column in mapper.columns}

    assert AuthRateLimitBucket.__tablename__ == "auth_rate_limit_buckets"
    assert {
        "id",
        "bucket_type",
        "bucket_key_hash",
        "failure_count",
        "window_started_at",
        "blocked_until",
        "updated_at",
    } <= columns

    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in AuthRateLimitBucket.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("bucket_type", "bucket_key_hash") in unique_columns

    check_constraints = {
        str(constraint.sqltext)
        for constraint in AuthRateLimitBucket.__table__.constraints
        if constraint.__class__.__name__ == "CheckConstraint"
    }
    assert "bucket_type IN ('LOGIN_IDENTITY_IP','LOGIN_IP')" in check_constraints
