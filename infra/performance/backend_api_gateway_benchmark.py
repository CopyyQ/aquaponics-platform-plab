#!/usr/bin/env python3
"""Concurrent HTTP benchmark for the Aquaponics backend API gateway.

Uses only the Python standard library so it can run directly on the deployment
host without installing a load-testing package.
"""

from __future__ import annotations

import argparse
import http.client
import json
import math
import queue
import statistics
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class BenchmarkResult:
    url: str
    requests: int
    concurrency: int
    succeeded: int
    failed: int
    error_rate: float
    elapsed_seconds: float
    requests_per_second: float
    min_ms: float
    mean_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil((pct / 100.0) * len(ordered)) - 1))
    return ordered[index]


def make_connection(scheme: str, host: str, port: int, timeout: float):
    if scheme == "https":
        return http.client.HTTPSConnection(host, port, timeout=timeout)
    return http.client.HTTPConnection(host, port, timeout=timeout)


def one_request(connection, path: str, expected_status: int, expected_text: str) -> tuple[bool, float, str]:
    started = time.perf_counter()
    try:
        connection.request("GET", path, headers={"Connection": "keep-alive"})
        response = connection.getresponse()
        body = response.read().decode("utf-8", errors="replace")
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        ok = response.status == expected_status and expected_text in body
        detail = "" if ok else f"status={response.status}, body={body[:160]!r}"
        return ok, elapsed_ms, detail
    except Exception as exc:  # benchmark must record transport failures
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return False, elapsed_ms, f"{type(exc).__name__}: {exc}"


def run_benchmark(
    url: str,
    total_requests: int,
    concurrency: int,
    warmup: int,
    timeout: float,
    expected_status: int,
    expected_text: str,
) -> tuple[BenchmarkResult, list[str]]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must use http:// or https:// and include a host")
    if total_requests <= 0 or concurrency <= 0:
        raise ValueError("requests and concurrency must be positive")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    warmup_connection = make_connection(parsed.scheme, parsed.hostname, port, timeout)
    try:
        for _ in range(warmup):
            ok, _, detail = one_request(
                warmup_connection, path, expected_status, expected_text
            )
            if not ok:
                raise RuntimeError(f"warmup failed: {detail}")
    finally:
        warmup_connection.close()

    jobs: queue.Queue[int] = queue.Queue()
    for request_id in range(total_requests):
        jobs.put(request_id)

    timings: list[float] = []
    errors: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        connection = make_connection(parsed.scheme, parsed.hostname, port, timeout)
        try:
            while True:
                try:
                    jobs.get_nowait()
                except queue.Empty:
                    return

                ok, elapsed_ms, detail = one_request(
                    connection, path, expected_status, expected_text
                )
                with lock:
                    timings.append(elapsed_ms)
                    if not ok:
                        errors.append(detail)
                jobs.task_done()

                if not ok:
                    connection.close()
                    connection = make_connection(
                        parsed.scheme, parsed.hostname, port, timeout
                    )
        finally:
            connection.close()

    started = time.perf_counter()
    threads = [
        threading.Thread(target=worker, name=f"bench-{index}", daemon=True)
        for index in range(min(concurrency, total_requests))
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    elapsed = time.perf_counter() - started

    failed = len(errors)
    succeeded = total_requests - failed
    successful_timings = timings if timings else [0.0]

    result = BenchmarkResult(
        url=url,
        requests=total_requests,
        concurrency=concurrency,
        succeeded=succeeded,
        failed=failed,
        error_rate=(failed / total_requests) * 100.0,
        elapsed_seconds=elapsed,
        requests_per_second=(total_requests / elapsed) if elapsed > 0 else 0.0,
        min_ms=min(successful_timings),
        mean_ms=statistics.fmean(successful_timings),
        p50_ms=percentile(successful_timings, 50),
        p95_ms=percentile(successful_timings, 95),
        p99_ms=percentile(successful_timings, 99),
        max_ms=max(successful_timings),
    )
    return result, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8100/health")
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, default=25)
    parser.add_argument("--warmup", type=int, default=25)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--expected-status", type=int, default=200)
    parser.add_argument("--expected-text", default='"status":"ok"')
    parser.add_argument("--max-error-rate", type=float, default=0.0)
    parser.add_argument("--max-p95-ms", type=float, default=100.0)
    parser.add_argument("--max-p99-ms", type=float, default=250.0)
    parser.add_argument("--min-rps", type=float, default=100.0)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()

    result, errors = run_benchmark(
        url=args.url,
        total_requests=args.requests,
        concurrency=args.concurrency,
        warmup=args.warmup,
        timeout=args.timeout,
        expected_status=args.expected_status,
        expected_text=args.expected_text,
    )

    payload = asdict(result)
    payload["thresholds"] = {
        "max_error_rate_pct": args.max_error_rate,
        "max_p95_ms": args.max_p95_ms,
        "max_p99_ms": args.max_p99_ms,
        "min_rps": args.min_rps,
    }
    payload["sample_errors"] = errors[:5]

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print(json.dumps(payload, ensure_ascii=False, indent=2))

    failures: list[str] = []
    if result.error_rate > args.max_error_rate:
        failures.append(
            f"error_rate {result.error_rate:.3f}% > {args.max_error_rate:.3f}%"
        )
    if result.p95_ms > args.max_p95_ms:
        failures.append(f"p95 {result.p95_ms:.2f}ms > {args.max_p95_ms:.2f}ms")
    if result.p99_ms > args.max_p99_ms:
        failures.append(f"p99 {result.p99_ms:.2f}ms > {args.max_p99_ms:.2f}ms")
    if result.requests_per_second < args.min_rps:
        failures.append(
            f"rps {result.requests_per_second:.2f} < {args.min_rps:.2f}"
        )

    if failures:
        print("PERFORMANCE_GATE=FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("PERFORMANCE_GATE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
