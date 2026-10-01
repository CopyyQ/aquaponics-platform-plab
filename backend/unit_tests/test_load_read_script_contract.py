from __future__ import annotations

import json

import pytest

from scripts.load_read_endpoints import (
    MAX_CONCURRENCY,
    LoadConfig,
    percentile,
    summarize,
    validate_config,
)


def _config(**overrides: object) -> LoadConfig:
    values: dict[str, object] = {
        "base_url": "http://127.0.0.1:8100",
        "endpoint": "/api/v1/sensor-models/1",
        "duration_seconds": 2.0,
        "rps": 20.0,
        "concurrency": 4,
        "timeout_seconds": 2.0,
        "warmup_requests": 1,
    }
    values.update(overrides)
    return LoadConfig(**values)  # type: ignore[arg-type]


def test_load_driver_requires_token_from_environment() -> None:
    with pytest.raises(ValueError, match="AQUAPONICS_LOAD_TOKEN"):
        validate_config(_config(), environ={})


def test_load_driver_bounds_concurrency() -> None:
    with pytest.raises(ValueError, match="concurrency"):
        validate_config(
            _config(concurrency=MAX_CONCURRENCY + 1),
            environ={"AQUAPONICS_LOAD_TOKEN": "secret-token"},
        )


def test_load_driver_reports_p50_p95_p99_and_throughput() -> None:
    result = summarize(
        config=_config(),
        latencies_ms=[1.0, 2.0, 3.0, 4.0, 100.0],
        status_codes=[200, 200, 200, 429, 500],
        transport_error_count=1,
        wall_seconds=2.0,
        scheduled_requests=6,
    )

    assert result.success_count == 3
    assert result.rate_limited_count == 1
    assert result.http_error_count == 1
    assert result.transport_error_count == 1
    assert result.completed_requests == 6
    assert result.throughput_rps == 3.0
    assert result.latency_ms_p50 == pytest.approx(3.0)
    assert result.latency_ms_p95 is not None
    assert result.latency_ms_p99 is not None


def test_load_driver_result_never_contains_bearer_token() -> None:
    token = "super-secret-load-token"
    validate_config(_config(), environ={"AQUAPONICS_LOAD_TOKEN": token})
    result = summarize(
        config=_config(),
        latencies_ms=[2.0],
        status_codes=[200],
        transport_error_count=0,
        wall_seconds=1.0,
        scheduled_requests=1,
    )

    rendered = json.dumps(result.as_json_dict())
    assert token not in rendered


def test_percentile_rejects_invalid_quantile() -> None:
    with pytest.raises(ValueError, match="quantile"):
        percentile([1.0], 1.1)
