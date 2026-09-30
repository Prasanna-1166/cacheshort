# CacheShort Performance & Observability Report

---

## 1. Purpose

This report provides empirical engineering evidence evaluating CacheShort's multi-tiered performance profile across three distinct layers:
1. **In-Process Algorithmic Execution:** Microsecond-scale resolution overhead of the custom HashMap + Doubly Linked List LRU Cache vs. direct dictionary lookups.
2. **Local HTTP End-to-End Resolution:** Server processing duration, request timing headers (`X-Process-Time`), and throughput under controlled concurrency.
3. **Live Production Deployment (Render + Supabase):** Real-world latency distributions across public health checks and warm URL redirect endpoints.

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
| **Deployment URL** | `http://127.0.0.1:8000` | `https://cacheshort-api.onrender.com` |
| **Report Date** | 2026-09-30 | 2026-09-30 |

---

## 3. Methodology & Statistical Principles

- **Timing Precision:** Python `time.perf_counter_ns()` (in-process micro-benchmarks) and `time.perf_counter()` (HTTP client benchmarks).
- **Statistical Percentiles:** Calculated from sorted response latency arrays (P50/Median, P90, P95, P99, Min, Max, Mean).
- **Rate Limiting Safety:** Controlled concurrency ($c=1$) and capped request volume ($N=10$) preventing volumetric overload or 429 cascades.
- **Cache-State Integrity:** A cache hit is defined strictly as a key residing in the in-memory LRU table.
- **Measurement Boundaries:**
  - **In-Process Benchmark:** Measures purely CPU and in-memory data structure traversal overhead.
  - **Server Processing Time (`X-Process-Time`):** Measures server-side ASGI request handling duration excluding client-to-server network transit.
  - **HTTP Benchmark Latency:** Measures complete end-to-end client round-trip time (DNS + TLS handshake + WAN network transit + server processing + response transfer).

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
*Measured via `benchmarks/benchmark_http.py` against `https://cacheshort-api.onrender.com` ($c=1$, $N=10$).*

| Metric | Production `/health` ($c=1$) | Production Warm Redirect `/{short_code}` ($c=1$) |
| :--- | :--- | :--- |
| **Execution Status** | **MEASURED** | **MEASURED** |
| **Configured Requests**| 10 | 10 |
| **Sent Requests** | 10 | 10 |
| **Successful Requests**| 10 (HTTP 200) | 10 (HTTP 307) |
| **HTTP 429 Rate Limited** | 0 | 0 |
| **Total Elapsed Time** | 10.9941 s | 4.6183 s |
| **Measured Throughput** | 0.91 req/sec | 2.17 req/sec |
| **Min Latency** | 965.806 ms | 281.071 ms |
| **Mean Latency** | 1099.333 ms | 461.744 ms |
| **Median (P50)** | 1043.448 ms | 350.265 ms |
| **P90 Latency** | 1595.793 ms | 1140.800 ms |
| **P95 Latency** | 1595.793 ms | 1140.800 ms |
| **P99 Latency** | 1595.793 ms | 1140.800 ms |
| **Max Latency** | 1595.793 ms | 1140.800 ms |

---

### Tier 4: Server-Side Processing Duration (`X-Process-Time`)
*Individual verified responses observed during warm-cache execution:*

| Request Index | Status Code | Header `X-Process-Time` | Server Processing Duration |
| :--- | :---: | :---: | :---: |
| **Request 1** | `HTTP 307` | `0.001297` | ~1.30 ms |
| **Request 2** | `HTTP 307` | `0.001482` | ~1.48 ms |
| **Request 3** | `HTTP 307` | `0.002788` | ~2.79 ms |
| **Individual Probe**| `HTTP 307` | `0.001624` | ~1.62 ms |

---

## 5. Engineering Analysis & Architectural Evolution

1. **Clear Separation of Latency Boundaries:**
   - **In-Process Algorithmic Lookup:** The custom LRU Cache executes in **~1.34 µs** in-memory.
   - **Server-Side Application Processing (`X-Process-Time`):** On warm cache redirects, server-side processing completes in **~1.3–2.8 ms**, which is consistent with the documented cache-hit path where database read queries are avoided.
   - **Client-Observed End-to-End HTTP Latency:** End-to-end client latency on production averaged **~461.7 ms** for warm redirects and **~1099.3 ms** for `/health` (legacy deep probe). The vast majority of client-observed duration reflects geographic WAN internet transit between the client location and the Render cloud container.
   - **Scientific Caution:** Client-side HTTP latency encompasses the complete network path (DNS, TLS negotiation, cross-continent routing, Cloudflare proxying, server processing). It must not be conflated with raw database or server processing latency.

2. **Phase 6 Health & Readiness Architectural Decoupling:**
   - **Legacy `/health` (Phase 5 Observation):** In Phase 5, `/health` performed a synchronous database health probe (`SELECT 1;`) via the connection pool on every invocation, yielding server-side processing times of ~695 ms and P50 client latency of **1043.4 ms**.
   - **Phase 6 Liveness (`GET /health`):** Architecturally redesigned into a pure shallow in-memory liveness probe with **zero database queries**. It reads process uptime and LRU cache metrics directly from RAM, yielding near-instantaneous sub-millisecond server processing (`X-Process-Time` ~1–2 ms).
   - **Phase 6 Readiness (`GET /health/ready`):** Retains explicit database connectivity validation via `DatabaseManager.check_health()`, intentionally isolating network-bound PostgreSQL pool verification from regular orchestrator liveness checks.

---

## 6. System Limitations

1. **Process-Local Memory Cache:**
   - LRU cache and sliding-window rate limiters reside in process memory. Each worker maintains an independent cache.
2. **Single Worker Concurrency:**
   - Uvicorn runs under `--workers 1` to guarantee local cache state consistency.
3. **Sample Size Notice:**
   - The production benchmark was intentionally conducted with a controlled volume of 10 requests at concurrency 1 to prevent rate-limit exhaustion. Tail percentiles (P90/P95/P99) are approximate due to the conservative sample size.
4. **Network Variability:**
   - Production HTTP measurements are subject to public internet routing, Cloudflare edge caching behavior, and Render free-tier container wake states.

---

## 7. Reproduction Commands

### Run In-Process Benchmark:
```bash
python benchmarks/benchmark_resolution.py
```

### Run Local HTTP Benchmark:
```bash
python benchmarks/benchmark_http.py --base-url http://127.0.0.1:8000 --endpoint /health --requests 20 --concurrency 1
```

### Run Controlled Production Benchmark:
```bash
# Health endpoint benchmark
python benchmarks/benchmark_http.py --base-url https://cacheshort-api.onrender.com --endpoint /health --requests 10 --concurrency 1

# Warm redirect endpoint benchmark
python benchmarks/benchmark_http.py --base-url https://cacheshort-api.onrender.com --endpoint /DyZUQxU --requests 10 --concurrency 1
```
