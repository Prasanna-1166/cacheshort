"""Performance benchmark comparing in-process resolution mechanisms.

Measures:
1. In-memory repository baseline latency (bare dictionary lookup + counter update).
2. Custom LRU Cache-hit resolution latency (HashMap + Doubly Linked List reorder + thread lock + metrics).
3. (Optional) Live PostgreSQL database resolution if DATABASE_URL is configured.

NOTE:
A raw in-memory dictionary lookup is expected to have lower microsecond overhead than
the custom LRU cache because the LRU performs additional work:
- HashMap lookup
- Doubly linked list node detachment & MRU head insertion
- Thread-safe synchronization (threading.RLock)
- Observability metrics tracking (hits/misses/evictions)

The primary purpose of the LRU cache is NOT to outperform a raw dictionary,
but to enforce a bounded memory footprint and avoid remote database queries.
"""

import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project root to sys.path for standalone execution
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.cache.lru_cache import LRUCache
from app.core.config import get_settings
from app.database.connection import DatabaseManager
from app.database.repository import InMemoryURLRepository, PostgresURLRepository
from app.services.url_service import URLService


def compute_stats(latencies_ns: List[int], total_time_sec: float) -> Dict[str, float]:
    """Calculate statistical distribution for latency measurements."""
    sorted_lat = sorted(latencies_ns)
    count = len(sorted_lat)
    if count == 0:
        return {"total_requests": 0, "elapsed_seconds": 0.0, "rps": 0.0, "mean_us": 0.0, "median_us": 0.0, "p95_us": 0.0, "p99_us": 0.0}

    mean_us = (sum(sorted_lat) / count) / 1000.0
    median_us = sorted_lat[int(count * 0.50)] / 1000.0
    p95_us = sorted_lat[int(count * 0.95)] / 1000.0
    p99_us = sorted_lat[int(count * 0.99)] / 1000.0
    rps = count / total_time_sec if total_time_sec > 0 else 0.0

    return {
        "total_requests": count,
        "elapsed_seconds": total_time_sec,
        "rps": rps,
        "mean_us": mean_us,
        "median_us": median_us,
        "p95_us": p95_us,
        "p99_us": p99_us,
    }


def run_local_benchmark(
    iterations: int = 10000,
    cache_capacity: int = 1000,
) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, any]]:
    """Execute comparative benchmark between Cache-Hit and In-Memory Repository resolution."""
    repo = InMemoryURLRepository()
    cache = LRUCache(capacity=cache_capacity)
    service = URLService(repository=repo, cache=cache, base_url="http://benchserver")

    # Seed 100 distinct URLs into repository
    short_codes: List[str] = []
    for i in range(100):
        code = f"bench_{i:04d}"
        repo.create_url(short_code=code, original_url=f"https://example.com/target/{i}")
        short_codes.append(code)

    # -------------------------------------------------------------
    # Scenario A: In-Memory Repository Direct Resolution (MEASURED)
    # -------------------------------------------------------------
    repo_latencies_ns: List[int] = []
    t0 = time.perf_counter_ns()
    for i in range(iterations):
        target_code = short_codes[i % len(short_codes)]
        start = time.perf_counter_ns()
        record = repo.get_by_short_code(target_code)
        if record:
            repo.increment_access(target_code)
        end = time.perf_counter_ns()
        repo_latencies_ns.append(end - start)
    total_repo_time_sec = (time.perf_counter_ns() - t0) / 1e9

    # -------------------------------------------------------------
    # Scenario B: Custom LRU Cache-Hit Resolution (MEASURED)
    # -------------------------------------------------------------
    # Warm up cache with all 100 short codes
    for code in short_codes:
        service.resolve_short_code(code)

    cache.reset_metrics()
    cache_latencies_ns: List[int] = []
    t0 = time.perf_counter_ns()
    for i in range(iterations):
        target_code = short_codes[i % len(short_codes)]
        start = time.perf_counter_ns()
        url = service.resolve_short_code(target_code)
        end = time.perf_counter_ns()
        cache_latencies_ns.append(end - start)
    total_cache_time_sec = (time.perf_counter_ns() - t0) / 1e9

    repo_metrics = compute_stats(repo_latencies_ns, total_repo_time_sec)
    cache_metrics = compute_stats(cache_latencies_ns, total_cache_time_sec)
    cache_stats = cache.stats()

    return repo_metrics, cache_metrics, cache_stats


def run_postgres_benchmark(
    iterations: int = 100,
) -> Optional[Dict[str, float]]:
    """Execute live PostgreSQL benchmark if DATABASE_URL is configured."""
    settings = get_settings()
    if not settings.database_url:
        return None

    try:
        pool = DatabaseManager.initialize_pool(settings.database_url)
        if not pool or not DatabaseManager.check_health():
            return None

        repo = PostgresURLRepository(pool)
        # Seed test records
        short_codes = []
        for i in range(10):
            code = f"pg_bench_{i:04d}_{int(time.time())}"
            try:
                repo.create_url(short_code=code, original_url=f"https://example.com/pg/{i}")
                short_codes.append(code)
            except Exception:
                pass

        if not short_codes:
            return None

        pg_latencies_ns: List[int] = []
        t0 = time.perf_counter_ns()
        for i in range(iterations):
            target_code = short_codes[i % len(short_codes)]
            start = time.perf_counter_ns()
            record = repo.get_by_short_code(target_code)
            if record:
                repo.increment_access(target_code)
            end = time.perf_counter_ns()
            pg_latencies_ns.append(end - start)
        total_pg_time_sec = (time.perf_counter_ns() - t0) / 1e9

        return compute_stats(pg_latencies_ns, total_pg_time_sec)
    except Exception as e:
        print(f"PostgreSQL live benchmark skipped: {e}")
        return None
    finally:
        DatabaseManager.close_pool()


def main():
    iterations = 10000
    cache_capacity = 1000

    print("=" * 80)
    print(" CACHESHORT RESOLUTION BENCHMARK (Phase 2)")
    print("=" * 80)
    print(f"Workload:            {iterations:,} requests per scenario")
    print(f"Dataset:             100 distinct pre-seeded short codes")
    print(f"LRU Cache Capacity:  {cache_capacity:,} items\n")

    repo_metrics, cache_metrics, cache_stats = run_local_benchmark(
        iterations=iterations,
        cache_capacity=cache_capacity,
    )

    print("--- [SCENARIO A: In-Memory Repository Direct Resolution (MEASURED)] ---")
    print(f"  Requests Processed:  {repo_metrics['total_requests']:,}")
    print(f"  Elapsed Time:        {repo_metrics['elapsed_seconds']:.4f} s")
    print(f"  Throughput:          {repo_metrics['rps']:,.2f} req/sec")
    print(f"  Mean Latency:        {repo_metrics['mean_us']:.3f} µs ({repo_metrics['mean_us']/1000:.4f} ms)")
    print(f"  Median (P50):        {repo_metrics['median_us']:.3f} µs ({repo_metrics['median_us']/1000:.4f} ms)")
    print(f"  P95 Latency:         {repo_metrics['p95_us']:.3f} µs ({repo_metrics['p95_us']/1000:.4f} ms)")
    print(f"  P99 Latency:         {repo_metrics['p99_us']:.3f} µs ({repo_metrics['p99_us']/1000:.4f} ms)\n")

    print("--- [SCENARIO B: Custom LRU Cache-Hit Resolution (MEASURED)] ---")
    print(f"  Requests Processed:  {cache_metrics['total_requests']:,}")
    print(f"  Elapsed Time:        {cache_metrics['elapsed_seconds']:.4f} s")
    print(f"  Throughput:          {cache_metrics['rps']:,.2f} req/sec")
    print(f"  Mean Latency:        {cache_metrics['mean_us']:.3f} µs ({cache_metrics['mean_us']/1000:.4f} ms)")
    print(f"  Median (P50):        {cache_metrics['median_us']:.3f} µs ({cache_metrics['median_us']/1000:.4f} ms)")
    print(f"  P95 Latency:         {cache_metrics['p95_us']:.3f} µs ({cache_metrics['p95_us']/1000:.4f} ms)")
    print(f"  P99 Latency:         {cache_metrics['p99_us']:.3f} µs ({cache_metrics['p99_us']/1000:.4f} ms)\n")

    print("--- [SCENARIO C: Live PostgreSQL Database Resolution] ---")
    pg_metrics = run_postgres_benchmark(iterations=100)
    if pg_metrics:
        print("  Status:              MEASURED (Live PostgreSQL)")
        print(f"  Requests Processed:  {pg_metrics['total_requests']:,}")
        print(f"  Elapsed Time:        {pg_metrics['elapsed_seconds']:.4f} s")
        print(f"  Throughput:          {pg_metrics['rps']:,.2f} req/sec")
        print(f"  Mean Latency:        {pg_metrics['mean_us']:.3f} µs ({pg_metrics['mean_us']/1000:.4f} ms)")
        print(f"  Median (P50):        {pg_metrics['median_us']:.3f} µs ({pg_metrics['median_us']/1000:.4f} ms)")
    else:
        print("  Status:              UNMEASURED (DATABASE_URL is not configured in current environment)")
        print("  To benchmark against live Supabase PostgreSQL, set DATABASE_URL in .env and re-run.")
    print("\n" + "=" * 80)
    print("BENCHMARK INTERPRETATION:")
    print("Local cache measurements demonstrate microsecond-scale in-process lookup overhead.")
    print("Remote PostgreSQL latency is environment-dependent and must be measured against the")
    print("actual deployment before making a quantitative speedup claim.")
    print("=" * 80)


if __name__ == "__main__":
    main()
