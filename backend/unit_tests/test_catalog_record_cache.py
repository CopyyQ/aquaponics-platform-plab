from __future__ import annotations

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-test-secret-key-123456789")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/aquaponics_codex_cache_unit",
)
os.environ.setdefault("FERNET_KEY", "ulEXv2cI-PsZu2SBChJNe9tKYU19H9ElRuQO9nZTqpk=")
os.environ.setdefault("DEFAULT_ADMIN_PASSWORD", "test-only-admin-password")

from collections.abc import AsyncIterator
from fnmatch import fnmatch

import pytest
from pydantic import BaseModel
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.record_cache import RecordCache, cache_aside
from app.services.catalog_record_cache import (
    actuator_model_key,
    device_template_key,
    invalidate_device_template,
    invalidate_sensor_model,
    scenario_catalog_key,
    sensor_model_key,
)


class CachedRecord(BaseModel):
    id: int
    name: str


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.expirations: dict[str, int] = {}
        self.deleted: list[str] = []
        self.fail_get = False

    async def get(self, name: str) -> bytes | None:
        if self.fail_get:
            raise RedisConnectionError("redis unavailable")
        return self.values.get(name)

    async def set(self, name: str, value: bytes, *, ex: int) -> bool:
        self.values[name] = value
        self.expirations[name] = ex
        return True

    async def delete(self, *names: str | bytes) -> int:
        deleted = 0
        for raw_name in names:
            name = raw_name.decode() if isinstance(raw_name, bytes) else raw_name
            self.deleted.append(name)
            if name in self.values:
                deleted += 1
                self.values.pop(name)
                self.expirations.pop(name, None)
        return deleted

    async def scan_iter(
        self,
        *,
        match: str,
        count: int = 100,
    ) -> AsyncIterator[str]:
        del count
        for key in list(self.values):
            if fnmatch(key, match):
                yield key


@pytest.mark.asyncio
async def test_cache_aside_hit_does_not_call_database_loader() -> None:
    redis = FakeRedis()
    cache = RecordCache(redis, ttl_seconds=60)
    await cache.set_model(sensor_model_key(7), CachedRecord(id=7, name="pH"))

    loader_called = False

    async def loader() -> CachedRecord:
        nonlocal loader_called
        loader_called = True
        return CachedRecord(id=7, name="database")

    result = await cache_aside(
        sensor_model_key(7),
        CachedRecord,
        loader,
        cache=cache,
    )

    assert result == CachedRecord(id=7, name="pH")
    assert loader_called is False


@pytest.mark.asyncio
async def test_cache_aside_miss_loads_database_and_sets_ttl() -> None:
    redis = FakeRedis()
    cache = RecordCache(redis, ttl_seconds=45)

    async def loader() -> CachedRecord:
        return CachedRecord(id=8, name="DO")

    result = await cache_aside(
        sensor_model_key(8),
        CachedRecord,
        loader,
        cache=cache,
    )

    assert result == CachedRecord(id=8, name="DO")
    assert sensor_model_key(8) in redis.values
    assert redis.expirations[sensor_model_key(8)] == 45


@pytest.mark.asyncio
async def test_cache_aside_falls_back_to_database_when_redis_is_unavailable() -> None:
    redis = FakeRedis()
    redis.fail_get = True
    cache = RecordCache(redis, ttl_seconds=60)

    async def loader() -> CachedRecord:
        return CachedRecord(id=9, name="Water temperature")

    result = await cache_aside(
        sensor_model_key(9),
        CachedRecord,
        loader,
        cache=cache,
    )

    assert result == CachedRecord(id=9, name="Water temperature")


@pytest.mark.asyncio
async def test_sensor_model_invalidation_clears_embedded_template_and_scenario_records() -> None:
    redis = FakeRedis()
    cache = RecordCache(redis, ttl_seconds=60)
    records = {
        sensor_model_key(1): CachedRecord(id=1, name="sensor"),
        actuator_model_key(1): CachedRecord(id=1, name="actuator"),
        device_template_key(1): CachedRecord(id=1, name="template"),
        scenario_catalog_key(1): CachedRecord(id=1, name="scenario"),
    }
    for key, value in records.items():
        await cache.set_model(key, value)

    await invalidate_sensor_model(1, cache=cache)

    assert sensor_model_key(1) not in redis.values
    assert device_template_key(1) not in redis.values
    assert scenario_catalog_key(1) not in redis.values
    assert actuator_model_key(1) in redis.values


@pytest.mark.asyncio
async def test_device_template_invalidation_is_key_isolated_without_scenario_sync() -> None:
    redis = FakeRedis()
    cache = RecordCache(redis, ttl_seconds=60)
    for key in (
        device_template_key(1),
        device_template_key(2),
        scenario_catalog_key(1),
        sensor_model_key(1),
    ):
        await cache.set_model(key, CachedRecord(id=1, name=key))

    await invalidate_device_template(1, cache=cache)

    assert device_template_key(1) not in redis.values
    assert device_template_key(2) in redis.values
    assert scenario_catalog_key(1) in redis.values
    assert sensor_model_key(1) in redis.values
