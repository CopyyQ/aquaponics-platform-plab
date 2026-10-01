"""Bounded async load driver for authenticated read-only API endpoints.

Credentials are read from an environment variable only and are never rendered
in output. The driver intentionally supports GET requests only so it cannot
mutate application state during performance checks.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

MAX_CONCURRENCY = 100
MAX_RPS = 1000
MAX_DURATION_SECONDS = 300
DEFAULT_TOKEN_ENV = "AQUAPONICS_LOAD_TOKEN"


@dataclass(frozen=True)
class LoadConfig:
    base_url: str
    endpoint: str
    duration_seconds: float = 10.0
    rps: float = 50.0
    concurrency: int = 10
    timeout_seconds: float = 5.0
    warmup_requests: int = 5
    token_env: str = DEFAULT_TOKEN_ENV
    output_json: Path | None = None


@dataclass(frozen=True)
class LoadResult:
    endpoint: str
    target_rps: float
    concurrency: int
    scheduled_requests: int
    completed_requests: int
    success_count: int
    rate_limited_count: int
    http_error_count: int
    transport_error_count: int
    wall_seconds: float
    throughput_rps: float
    latency_ms_min: float | None
    latency_ms_mean: float | None
    latency_ms_p50: float | None
    latency_ms_p95: float | None
    latency_ms_p99: float | None
    latency_ms_max: float | None

    def as_json_dict(self) -> dict[str, Any]:
        return asdict(self)


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must be between 0 and 1")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = quantile * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def validate_config(config: LoadConfig, environ: dict[str, str] | None = None) -> str:
    env = environ if environ is not None else os.environ
    token = env.get(config.token_env, "")
    if not token:
        raise ValueError(
            f"Missing bearer token in environment variable {config.token_env!r}"
        )
    if not config.base_url.startswith(("http://", "https://")):
        raise ValueError("base_url must start with http:// or https://")
    if not config.endpoint.startswith("/"):
        raise ValueError("endpoint must start with '/'")
    if not 0 < config.duration_seconds <= MAX_DURATION_SECONDS:
        raise ValueError(
            f"duration_seconds must be > 0 and <= {MAX_DURATION_SECONDS}"
        )
    if not 0 < config.rps <= MAX_RPS:
        raise ValueError(f"rps must be > 0 and <= {MAX_RPS}")
    if not 1 <= config.concurrency <= MAX_CONCURRENCY:
        raise ValueError(
            f"concurrency must be between 1 and {MAX_CONCURRENCY}"
        )
    if not 0 < config.timeout_seconds <= 60:
        raise ValueError("timeout_seconds must be > 0 and <= 60")
    if not 0 <= config.warmup_requests <= 100:
        raise ValueError("warmup_requests must be between 0 and 100")
    return token


def summarize(
    *,
    config: LoadConfig,
    latencies_ms: list[float],
    status_codes: list[int],
    transport_error_count: int,
    wall_seconds: float,
    scheduled_requests: int,
) -> LoadResult:
    completed = len(status_codes) + transport_error_count
    successes = sum(200 <= status < 300 for status in status_codes)
    rate_limited = sum(status == 429 for status in status_codes)
    http_errors = sum(
        not (200 <= status < 300) and status != 429 for status in status_codes
    )
    mean = sum(latencies_ms) / len(latencies_ms) if latencies_ms else None
    return LoadResult(
        endpoint=config.endpoint,
        target_rps=config.rps,
        concurrency=config.concurrency,
        scheduled_requests=scheduled_requests,
        completed_requests=completed,
        success_count=successes,
        rate_limited_count=rate_limited,
        http_error_count=http_errors,
        transport_error_count=transport_error_count,
        wall_seconds=wall_seconds,
        throughput_rps=completed / wall_seconds if wall_seconds > 0 else 0.0,
        latency_ms_min=min(latencies_ms) if latencies_ms else None,
        latency_ms_mean=mean,
        latency_ms_p50=percentile(latencies_ms, 0.50),
        latency_ms_p95=percentile(latencies_ms, 0.95),
        latency_ms_p99=percentile(latencies_ms, 0.99),
        latency_ms_max=max(latencies_ms) if latencies_ms else None,
    )


async def run_load(config: LoadConfig, token: str) -> LoadResult:
    url = config.base_url.rstrip("/") + config.endpoint
    queue: asyncio.Queue[int | None] = asyncio.Queue(
        maxsize=max(config.concurrency * 2, 1)
    )
    latencies_ms: list[float] = []
    status_codes: list[int] = []
    transport_error_count = 0
    scheduled_requests = max(1, int(config.duration_seconds * config.rps))
    limits = httpx.Limits(
        max_connections=config.concurrency,
        max_keepalive_connections=config.concurrency,
    )
    timeout = httpx.Timeout(config.timeout_seconds)

    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
        limits=limits,
        follow_redirects=False,
    ) as client:
        for _ in range(config.warmup_requests):
            try:
                await client.get(url)
            except httpx.HTTPError:
                # Warmup is deliberately excluded from the measured result.
                pass

        async def worker() -> None:
            nonlocal transport_error_count
            while True:
                item = await queue.get()
                if item is None:
                    queue.task_done()
                    return
                started = time.perf_counter()
                try:
                    response = await client.get(url)
                except httpx.HTTPError:
                    transport_error_count += 1
                else:
                    status_codes.append(response.status_code)
                    latencies_ms.append((time.perf_counter() - started) * 1000)
                finally:
                    queue.task_done()

        workers = [
            asyncio.create_task(worker()) for _ in range(config.concurrency)
        ]
        started_wall = time.perf_counter()
        interval = 1.0 / config.rps
        for index in range(scheduled_requests):
            due = started_wall + index * interval
            delay = due - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            await queue.put(index)

        await queue.join()
        wall_seconds = time.perf_counter() - started_wall
        for _ in workers:
            await queue.put(None)
        await queue.join()
        await asyncio.gather(*workers)

    return summarize(
        config=config,
        latencies_ms=latencies_ms,
        status_codes=status_codes,
        transport_error_count=transport_error_count,
        wall_seconds=wall_seconds,
        scheduled_requests=scheduled_requests,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run bounded GET-only load against one authenticated API endpoint."
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("AQUAPONICS_LOAD_BASE_URL", ""),
        help="API origin, e.g. http://127.0.0.1:8100",
    )
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--duration-seconds", type=float, default=10.0)
    parser.add_argument("--rps", type=float, default=50.0)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument("--warmup-requests", type=int, default=5)
    parser.add_argument(
        "--token-env",
        default=DEFAULT_TOKEN_ENV,
        help="Environment variable that contains the bearer token.",
    )
    parser.add_argument("--output-json", type=Path)
    return parser


async def async_main(args: argparse.Namespace) -> int:
    config = LoadConfig(
        base_url=args.base_url,
        endpoint=args.endpoint,
        duration_seconds=args.duration_seconds,
        rps=args.rps,
        concurrency=args.concurrency,
        timeout_seconds=args.timeout_seconds,
        warmup_requests=args.warmup_requests,
        token_env=args.token_env,
        output_json=args.output_json,
    )
    token = validate_config(config)
    result = await run_load(config, token)
    payload = result.as_json_dict()
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    print(rendered)
    if config.output_json is not None:
        config.output_json.parent.mkdir(parents=True, exist_ok=True)
        config.output_json.write_text(rendered + "\n", encoding="utf-8")
    return 0 if result.success_count > 0 else 2


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return asyncio.run(async_main(args))
    except ValueError as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
