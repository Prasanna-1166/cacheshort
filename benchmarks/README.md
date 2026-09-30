# CacheShort Benchmarking Suite

This benchmark suite evaluates the in-process performance characteristics of CacheShort's custom in-memory LRU Cache compared to baseline repository resolution.

---

## 1. Methodology & Workload

The benchmark script ([benchmark_resolution.py](file:///d:/python_project/benchmarks/benchmark_resolution.py)) executes automated evaluations:

- **Workload Volume:** 10,000 lookup requests per scenario.
- **Dataset Size:** 100 distinct pre-seeded short-to-original URL mappings.
- **Cache Configuration:** Custom HashMap + Doubly Linked List LRU Cache with capacity 1,000.
- **Timing Resolution:** Python `time.perf_counter_ns()` with nanosecond precision.

### Evaluated Scenarios

1. **Scenario A: In-Memory Repository Direct Resolution (MEASURED)**
   - Measures raw in-process dictionary retrieval and access counter update.
2. **Scenario B: Custom LRU Cache-Hit Resolution (MEASURED)**
   - Measures in-memory LRU cache hit resolution including HashMap lookup, doubly linked list node movement to MRU position, thread lock synchronization (`threading.RLock`), and metric counter updates.
3. **Scenario C: Live Hosted PostgreSQL Resolution (UNMEASURED / OPTIONAL)**
   - Measures live round-trip query time against remote Supabase PostgreSQL when `DATABASE_URL` is configured.

---

## 2. Environment Specifications

- **OS:** Windows (AMD64)
- **Runtime:** Python 3.12.10
- **Synchronization:** Python `threading.RLock` protecting custom Doubly Linked List + Dict HashMap.

---

## 3. Actual Measured Results (10,000 Requests)

### In-Process Measurements (Local Machine)

| Metric | Scenario A: In-Memory Repository (MEASURED) | Scenario B: LRU Cache Hit (MEASURED) | Scenario C: Hosted PostgreSQL |
| :--- | :--- | :--- | :--- |
| **Status** | **MEASURED** | **MEASURED** | **UNMEASURED (Pending DB credentials)** |
| **Requests Processed** | 10,000 | 10,000 | — |
| **Elapsed Time** | 0.0129 s | 0.0165 s | Unmeasured |
| **Throughput** | 776,054 req/sec | 604,744 req/sec | Unmeasured |
| **Mean Latency** | 0.983 µs (0.0010 ms) | 1.337 µs (0.0013 ms) | Unmeasured |
| **Median (P50)** | 0.800 µs (0.0008 ms) | 1.200 µs (0.0012 ms) | Unmeasured |
| **P95 Latency** | 1.200 µs (0.0012 ms) | 1.600 µs (0.0016 ms) | Unmeasured |
| **P99 Latency** | 1.500 µs (0.0015 ms) | 2.000 µs (0.0020 ms) | Unmeasured |

---

## 4. Benchmark Interpretation & Engineering Analysis

### Why Raw Dictionary Lookup is Faster than LRU Cache
A bare in-memory dictionary lookup in Scenario A exhibits slightly lower microsecond latency (~0.98 µs vs ~1.34 µs) than the custom LRU cache. This is expected and normal because the LRU cache performs additional necessary operations on every read:
1. HashMap pointer lookup
2. Doubly linked list node unlinking (`node.prev.next = node.next`, etc.)
3. Re-insertion at the MRU head position
4. Thread synchronization (`threading.RLock`)
5. Metrics accounting (`_hits += 1`)

The purpose of the LRU cache is **not** to outperform an unbounded raw in-memory dictionary in micro-benchmarks. Its architectural purpose is to:
- Enforce a **strictly bounded memory footprint** (`CACHE_CAPACITY`) preventing Out-Of-Memory (OOM) failures under millions of URLs.
- **Eliminate remote database round-trips** (which involve network traversal, socket I/O, SQL parsing, and disk access) for frequently requested URLs.

> **Important:** Local cache measurements demonstrate microsecond-scale in-process lookup overhead. Remote PostgreSQL latency is environment-dependent and must be measured against the actual deployment before making a quantitative speedup claim.

---

## 5. How to Run

### Run Local In-Process Benchmark:
```bash
python benchmarks/benchmark_resolution.py
```

### Run With Live Supabase PostgreSQL:
Set your `DATABASE_URL` in `.env` and execute:
```bash
python benchmarks/benchmark_resolution.py
```
If `DATABASE_URL` is present and valid, Scenario C will automatically benchmark real database round-trips and output the measured statistics.
