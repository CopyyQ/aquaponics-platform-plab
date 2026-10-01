from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol

import orjson
from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)

class RedisRecordClient(Protocol):
    async def get(self, name: str) -> bytes | str | None: ...

    async def set(
        self,
        name: str,
        value: bytes,
        *,
        ex: int,
    ) -> Any: ...

    async def delete(self, *names: str | bytes) -> int: ...

    def scan_iter(
        self,
        *,
        match: str,
        count: int = 100,
    ) -> AsyncIterator[bytes | str]: ...


class RecordCache:
    """Best-effort Redis cache for serialized backend read models.

    PostgreSQL remains the source of truth. Every cache operation fails open so
    a Redis outage cannot make an otherwise healthy API read unavailable.
    """

    def __init__(
        self,
        client: RedisRecordClient | None,
        *,
        ttl_seconds: int,
    ) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds

    @classmethod
    def from_settings(cls) -> RecordCache:
        if not settings.redis_url:
            return cls(None, ttl_seconds=settings.catalog_record_cache_ttl_seconds)

        client = Redis.from_url(
            settings.redis_url,
            decode_responses=False,
            socket_connect_timeout=settings.redis_cache_socket_timeout_seconds,
            socket_timeout=settings.redis_cache_socket_timeout_seconds,
        )
        return cls(client, ttl_seconds=settings.catalog_record_cache_ttl_seconds)

    @property
    def enabled(self) -> bool:
        return self._client is not None

    async def get_model[TModel: BaseModel](
        self,
        key: str,
        model_type: type[TModel],
    ) -> TModel | None:
        if self._client is None:
            return None

        try:
            raw = await self._client.get(key)
        except (RedisError, OSError, TimeoutError):
            logger.warning("Redis record-cache read failed for key %s; using database", key)
            return None

        if raw is None:
            return None

        try:
            return model_type.model_validate(orjson.loads(raw))
        except (orjson.JSONDecodeError, ValidationError, TypeError, ValueError):
            logger.warning("Discarding invalid Redis record-cache payload for key %s", key)
            await self.delete(key)
            return None

    async def set_model(self, key: str, value: BaseModel) -> None:
        if self._client is None:
            return

        payload = orjson.dumps(value.model_dump(mode="json"))
        try:
            await self._client.set(key, payload, ex=self._ttl_seconds)
        except (RedisError, OSError, TimeoutError):
            logger.warning("Redis record-cache write failed for key %s", key)

    async def delete(self, *keys: str) -> None:
        if self._client is None or not keys:
            return
        try:
            await self._client.delete(*keys)
        except (RedisError, OSError, TimeoutError):
            logger.warning("Redis record-cache invalidation failed for %d key(s)", len(keys))

    async def delete_pattern(self, pattern: str) -> None:
        if self._client is None:
            return

        try:
            keys = [key async for key in self._client.scan_iter(match=pattern, count=100)]
            if keys:
                await self._client.delete(*keys)
        except (RedisError, OSError, TimeoutError):
            logger.warning("Redis record-cache pattern invalidation failed for %s", pattern)


record_cache = RecordCache.from_settings()


async def cache_aside[TModel: BaseModel](
    key: str,
    model_type: type[TModel],
    loader: Callable[[], Awaitable[TModel]],
    *,
    cache: RecordCache | None = None,
) -> TModel:
    selected_cache = cache or record_cache
    cached = await selected_cache.get_model(key, model_type)
    if cached is not None:
        return cached

    value = await loader()
    await selected_cache.set_model(key, value)
    return value
