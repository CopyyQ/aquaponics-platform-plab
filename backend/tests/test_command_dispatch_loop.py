import asyncio

import pytest

from app.core.config import settings
from app.jobs import runner


@pytest.mark.asyncio
async def test_command_dispatch_loop_survives_cycle_failure(monkeypatch) -> None:
    dispatch_calls = 0
    sleeps: list[float] = []

    async def fake_dispatch() -> int:
        nonlocal dispatch_calls
        dispatch_calls += 1
        if dispatch_calls == 1:
            raise RuntimeError("transient dispatcher failure")
        return 0

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) >= 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(runner, "dispatch_actuator_commands_once", fake_dispatch)
    monkeypatch.setattr(runner.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(settings, "actuator_command_dispatch_interval_seconds", 1.0)

    with pytest.raises(asyncio.CancelledError):
        await runner.run_command_dispatch_loop()

    assert dispatch_calls == 2
    assert sleeps == [1.0, 1.0]


@pytest.mark.asyncio
async def test_maintenance_cycle_does_not_inline_command_dispatch(monkeypatch) -> None:
    dispatch_calls = 0

    async def fake_dispatch() -> int:
        nonlocal dispatch_calls
        dispatch_calls += 1
        return 0

    async def ok_job(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(runner, "dispatch_actuator_commands_once", fake_dispatch)
    monkeypatch.setattr(runner, "scan_offline_state", ok_job)
    monkeypatch.setattr(runner, "timeout_actuator_commands", ok_job)
    monkeypatch.setattr(runner, "cleanup_auth_state", ok_job)
    monkeypatch.setattr(runner, "dispatch_operational_notifications", ok_job)
    monkeypatch.setattr(runner, "aggregate_period", ok_job)
    monkeypatch.setattr(runner, "evaluate_project_health", ok_job)

    succeeded = await runner.run_scheduler_cycle()

    assert succeeded is True
    assert dispatch_calls == 0
