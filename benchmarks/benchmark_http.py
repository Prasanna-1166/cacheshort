#!/usr/bin/env python3
"""Controlled HTTP benchmarking and load testing tool for CacheShort.

Evaluates end-to-end HTTP resolution performance, tail latencies (P50/P90/P95/P99),
and rate-limiting resilience across local and production deployments.

SAFETY:
- Uses conservative concurrency and request volume defaults.
- Automatically halts or records rate-limiting when HTTP 429 is detected.
- Never prints or stores raw API keys in logs or reports.
"""

import argparse
import asyncio
import os
import sys
import time
from typing import Any, Dict, List, Optional
import httpx


def calculate_percentiles(latencies_ms: List[float]) -> Dict[str, float]:
    """Calculate exact statistical distribution from measured latencies in milliseconds."""
    if not latencies_ms:
        return {
            "mean_ms": 0.0,
            "median_ms": 0.0,
            "p90_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
            "min_ms": 0.0,
            "max_ms": 0.0,
        }

    sorted_lat = sorted(latencies_ms)
    count = len(sorted_lat)

    mean_val = sum(sorted_lat) / count
    min_val = sorted_lat[0]
    max_val = sorted_lat[-1]

    def get_percentile(pct: float) -> float:
        idx = int(count * pct)
        idx = min(idx, count - 1)
        return sorted_lat[idx]

    return {
        "mean_ms": round(mean_val, 3),
        "median_ms": round(get_percentile(0.50), 3),
        "p90_ms": round(get_percentile(0.90), 3),
        "p95_ms": round(get_percentile(0.95), 3),
        "p99_ms": round(get_percentile(0.99), 3),
        "min_ms": round(min_val, 3),
        "max_ms": round(max_val, 3),
    }


async def run_http_benchmark(
    base_url: str,
    path: str = "/health",
    requests: int = 20,
    concurrency: int = 1,
    api_key: Optional[str] = None,
    timeout_sec: float = 5.0,
    follow_redirects: bool = False,
) -> Dict[str, Any]:
    """Execute controlled HTTP load test against target URL.

    Returns dictionary containing measured metrics, error counts, and latency distribution.
    """
    clean_base = base_url.rstrip("/")
    target_url = f"{clean_base}{path}" if path.startswith("/") else f"{clean_base}/{path}"

    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key

    semaphore = asyncio.Semaphore(max(1, concurrency))
    latencies_ms: List[float] = []
    status_counts: Dict[int, int] = {}
    error_counts: Dict[str, int] = {
        "timeouts": 0,
        "connection_errors": 0,
        "other_errors": 0,
    }
    rate_limited_halt: bool = False

    async with httpx.AsyncClient(timeout=timeout_sec, follow_redirects=follow_redirects) as client:

        async def worker(request_idx: int):
            nonlocal rate_limited_halt
            if rate_limited_halt:
                return

            async with semaphore:
                if rate_limited_halt:
                    return

                t_start = time.perf_counter()
                try:
                    resp = await client.get(target_url, headers=headers)
                    duration_ms = (time.perf_counter() - t_start) * 1000.0

                    status = resp.status_code
                    status_counts[status] = status_counts.get(status, 0) + 1

                    if status in (200, 307):
                        latencies_ms.append(duration_ms)
                    elif status == 429:
                        # Safety halt on rate limiting
                        rate_limited_halt = True
                except httpx.TimeoutException:
                    error_counts["timeouts"] += 1
                except httpx.ConnectError:
                    error_counts["connection_errors"] += 1
                except Exception:
                    error_counts["other_errors"] += 1

        t0 = time.perf_counter()
        tasks = [asyncio.create_task(worker(i)) for i in range(requests)]
        await asyncio.gather(*tasks)
        total_time_sec = time.perf_counter() - t0

    successful_requests = len(latencies_ms)
    failed_requests = sum(error_counts.values()) + sum(
        count for status, count in status_counts.items() if status not in (200, 307)
    )
    rate_limit_count = status_counts.get(429, 0)

    stats = calculate_percentiles(latencies_ms)
    rps = round(successful_requests / total_time_sec, 2) if total_time_sec > 0 else 0.0

    return {
        "target_url": target_url,
        "total_requests_configured": requests,
        "total_requests_sent": sum(status_counts.values()) + sum(error_counts.values()),
        "successful_requests": successful_requests,
        "failed_requests": failed_requests,
        "rate_limited_responses": rate_limit_count,
        "concurrency": concurrency,
        "total_time_seconds": round(total_time_sec, 4),
        "rps": rps,
        "status_distribution": status_counts,
        "error_distribution": error_counts,
        "latencies_ms": stats,
        "small_sample_warning": requests < 20,
    }


def print_benchmark_results(results: Dict[str, Any]) -> None:
    """Print human-readable statistical benchmark report."""
    print("\n" + "=" * 70)
    print(" CACHESHORT HTTP BENCHMARK RESULTS")
    print("=" * 70)
    print(f"Target URL:              {results['target_url']}")
    print(f"Configured Requests:     {results['total_requests_configured']}")
    print(f"Sent Requests:           {results['total_requests_sent']}")
    print(f"Successful (200/307):    {results['successful_requests']}")
    print(f"Failed Requests:         {results['failed_requests']}")
    print(f"HTTP 429 Rate Limited:   {results['rate_limited_responses']}")
    print(f"Concurrency Level:       {results['concurrency']}")
    print(f"Total Elapsed Time:      {results['total_time_seconds']:.4f} s")
    print(f"Measured Throughput:     {results['rps']} req/sec")
    print("-" * 70)
    print("STATUS CODE BREAKDOWN:")
    for code, count in sorted(results["status_distribution"].items()):
        print(f"  HTTP {code}: {count}")
    if sum(results["error_distribution"].values()) > 0:
        print("ERROR BREAKDOWN:")
        for err_type, count in results["error_distribution"].items():
            if count > 0:
                print(f"  {err_type}: {count}")
    print("-" * 70)
    print("LATENCY DISTRIBUTION (Milliseconds):")
    lats = results["latencies_ms"]
    print(f"  Min:                   {lats['min_ms']:.3f} ms")
    print(f"  Mean:                  {lats['mean_ms']:.3f} ms")
    print(f"  Median (P50):          {lats['median_ms']:.3f} ms")
    print(f"  P90:                   {lats['p90_ms']:.3f} ms")
    print(f"  P95:                   {lats['p95_ms']:.3f} ms")
    print(f"  P99:                   {lats['p99_ms']:.3f} ms")
    print(f"  Max:                   {lats['max_ms']:.3f} ms")

    if results["small_sample_warning"]:
        print("-" * 70)
        print("NOTE: Sample count is under 20 requests. Tail percentiles (P95/P99)")
        print("are approximate due to small sample size.")
    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Controlled HTTP benchmark tool for CacheShort."
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://127.0.0.1:8000",
        help="Base URL of target CacheShort deployment (default: http://127.0.0.1:8000)",
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default="/health",
        help="Endpoint path to test (e.g. /health, /<short_code>, /api/cache/stats)",
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=20,
        help="Total requests to execute (default: 20, max: 500)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Concurrent worker count (default: 1, max: 10)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Optional API key for protected endpoints (can also use CACHESHORT_API_KEY env var)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Per-request timeout in seconds (default: 5.0)",
    )

    args = parser.parse_args()

    # Safety limits
    capped_requests = max(1, min(args.requests, 500))
    capped_concurrency = max(1, min(args.concurrency, 10))
    api_key = args.api_key or os.environ.get("CACHESHORT_API_KEY")

    try:
        results = asyncio.run(
            run_http_benchmark(
                base_url=args.base_url,
                path=args.endpoint,
                requests=capped_requests,
                concurrency=capped_concurrency,
                api_key=api_key,
                timeout_sec=args.timeout,
            )
        )
        print_benchmark_results(results)
    except Exception as e:
        print(f"Benchmark execution failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
