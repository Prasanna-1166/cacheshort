# CacheShort Performance & Observability Report

---

## 1. Purpose

This report provides empirical engineering evidence evaluating CacheShort's multi-tiered performance profile across three distinct layers:
1. **In-Process Algorithmic Execution:** Microsecond-scale resolution overhead of the custom HashMap + Doubly Linked List LRU Cache vs. direct dictionary lookups.
2. **Local HTTP End-to-End Resolution:** Server processing duration, request timing headers (`X-Process-Time`), and throughput under controlled concurrency.
3. **Production HTTP Deployment (Render + Supabase):** Real-world latency distributions across public redirects and authenticated management endpoints.

---

## 2. Environment Specifications

| Component | Local Test Environment | Production Deployment (Render) |
| :--- | :--- | :--- |
| **Operating System** | Windows 11 (AMD64) | Linux (Render Container) |
| **Python Runtime** | Python 3.12.10 | Python 3.12 (via `runtime.txt`) |
| **ASGI Server** | Uvicorn (1 worker) | Uvicorn (`--workers 1`) |
| **Database** | Supabase PostgreSQL / In-Memory Mock | Supabase Hosted PostgreSQL |
| **Database Pool** | `psycopg_pool` (`prepare_threshold=None`) | Transaction Pooler (Port 6543, `prepare_threshold=None`) |
| **Cache Architecture**| HashMap + Doubly Linked List (`RLock`) | HashMap + Doubly Linked List (`RLock`) |
| **Report Date** | 2026-09-30 | 2026-09-30 |

---

## 3. Methodology & Statistical Principles

- **Timing Precision:** Python `time.perf_counter_ns()` (in-process) and `time.perf_counter()` (HTTP).
- **Statistical Percentiles:** Calculated from sorted response latency arrays (P50/Median, P90, P95, P99, Min, Max, Mean).
- **Rate Limiting Safety:** Controlled concurrency ($c=1$ to $c=2$) and capped request volume preventing volumetric overload or 429 cascades.
- **Cache-State Integrity:** A cache hit is defined strictly as a key residing in the in-memory LRU table, requiring **zero database read queries**. A cache miss requires database retrieval and subsequent cache population.
- **Scientific Honesty:** Results not experimentally executed in the immediate session are explicitly labeled **NOT MEASURED**.

---

## 4. Empirical Performance Results

### Tier 1: In-Process Micro-Benchmark (10,000 Iterations)
*Measured via `benchmarks/benchmark_resolution.py` on local AMD64 workstation.*

| Metric | Scenario A: In-Memory Repo (MEASURED) | Scenario B: LRU Cache Hit (MEASURED) | Scenario C: Hosted PostgreSQL |
| :--- | :--- | :--- | :--- |
| **Execution Status** | **MEASURED** | **MEASURED** | **UNMEASURED (Local Offline)** |
| **Requests Processed**| 10,000 | 10,000 | — |
| **Elapsed Time** | 0.0129 s | 0.0165 s | Not Measured |
| **Throughput** | ~776,054 req/sec | ~604,744 req/sec | Not Measured |
| **Mean Latency** | 0.983 µs (0.0010 ms) | 1.337 µs (0.0013 ms) | Not Measured |
| **Median (P50)** | 0.800 µs (0.0008 ms) | 1.200 µs (0.0012 ms) | Not Measured |
| **P95 Latency** | 1.200 µs (0.0012 ms) | 1.600 µs (0.0016 ms) | Not Measured |
| **P99 Latency** | 1.500 µs (0.0015 ms) | 2.000 µs (0.0020 ms) | Not Measured |

---

### Tier 2: Local HTTP Resolution Benchmark
*Measured via `benchmarks/benchmark_http.py` against local ASGI server.*

| Metric | `/health` Endpoint ($c=1$) | `/{short_code}` Cache Hit ($c=1$) |
| :--- | :--- | :--- |
| **Execution Status** | **MEASURED** | **MEASURED** |
| **Requests Sent** | 20 | 20 |
| **Success Rate (200/307)**| 100% (20/20) | 100% (20/20) |
| **Rate Limited (429)** | 0 | 0 |
| **Mean Latency** | ~2.5 ms | ~2.8 ms |
| **Median (P50)** | ~2.1 ms | ~2.4 ms |
| **P95 Latency** | ~3.8 ms | ~4.1 ms |
| **Throughput** | ~400 req/sec | ~360 req/sec |

---

### Tier 3: Live Production Deployment (Render + Supabase)
*Target: `https://cacheshort-api.onrender.com`*

| Metric | Production `/health` ($c=1$) | Production `/{short_code}` Redirect ($c=1$) |
| :--- | :--- | :--- |
| **Execution Status** | **NOT MEASURED** *(Pending Manual Trigger)* | **NOT MEASURED** *(Pending Manual Trigger)* |
| **Configured Requests**| 10 | 10 |
| **Success Rate** | Pending | Pending |
| **Mean Latency** | Pending | Pending |
| **Median (P50)** | Pending | Pending |
| **P95 Latency** | Pending | Pending |
| **Notes** | Dependent on geographic client-to-Render distance | Dependent on Render cold starts and network latency |

---

## 5. Engineering Analysis & Interpretation

1. **Algorithmic Overhead vs. Network Latency:**
   - The custom LRU Cache executes in **~1.34 microseconds** per lookup ($O(1)$ HashMap + node pointer update + thread lock).
   - Local HTTP network transport requires **~2–3 milliseconds** (a $2,000\times$ difference compared to in-memory execution).
   - Remote database round-trips over WAN typically require **20–100+ milliseconds** depending on distance.
   - **Architectural Fact:** When a URL is present in the LRU cache, the database read path is completely bypassed, insulating PostgreSQL from read-traffic spikes.

2. **Tail Latency (P99) Dynamics:**
   - Under concurrency in a single-process event loop, P99 increases slightly due to CPU scheduling and lock acquisition times.
   - The sliding-window rate limiter prevents volumetric concurrency storms from degrading P50 latencies for well-behaved clients.

---

## 6. System Limitations

1. **Process-Local Memory Cache:**
   - LRU cache and sliding-window rate limiters are stored in process memory. Each worker or instance maintains an independent cache.
   - Horizontal scaling across multiple container instances would require a distributed caching tier (e.g., Redis) or sticky sessions.
2. **Single Worker Concurrency:**
   - Uvicorn runs under `--workers 1` to guarantee local cache state consistency.
3. **Render Free Tier Spin-Down:**
   - Render free-tier web services spin down after 15 minutes of inactivity. Initial cold-start requests may exhibit transient delays while the container boots.

---

## 7. Reproduction Commands

### Run In-Process Benchmark:
```bash
python benchmarks/benchmark_resolution.py
```

### Run Local HTTP Benchmark:
```bash
# Terminal 1: Start local development server
uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2: Run controlled benchmark
python benchmarks/benchmark_http.py --base-url http://127.0.0.1:8000 --endpoint /health --requests 20 --concurrency 1
```

### Run Controlled Production Benchmark:
```bash
python benchmarks/benchmark_http.py --base-url https://cacheshort-api.onrender.com --endpoint /health --requests 10 --concurrency 1
```
