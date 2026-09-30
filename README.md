# CacheShort — LRU-Cache-Backed URL Shortener

An educational, high-performance URL-shortening backend built with FastAPI, PostgreSQL (hosted on Supabase), and a custom in-memory Least Recently Used (LRU) Cache implemented from scratch using a HashMap + Doubly Linked List with full observability metrics and sliding-window rate limiting.

---

## 1. Project Overview

**CacheShort** is designed to demonstrate clean backend architecture, data structure fundamentals, and caching mechanics. In high-throughput URL shortening services, lookups follow the Pareto distribution (80-90% of redirects hit a small subset of hot/viral URLs). Querying the database for every redirect creates unnecessary disk I/O and connection overhead. CacheShort solves this by placing an $O(1)$ LRU cache in front of the database.

---

## 2. Why LRU Cache is Used

URL redirection is a read-heavy workload:
- **Hot-key locality:** A fraction of newly created or trending short URLs generate the vast majority of traffic.
- **Eviction policy:** When the memory budget is reached, Least Recently Used (LRU) eviction discards items that haven't been accessed recently, keeping the "hot" URLs in memory.
- **Bounded memory footprint:** In-memory caching without capacity limits causes Out-Of-Memory (OOM) crashes. An LRU cache enforces a strict upper bound on memory usage.

---

## 3. Architecture

```
Client
  │
  ▼
Process-Local Sliding Window Rate Limiter
  │ (Exceed limit -> HTTP 429 + Retry-After)
  ▼
FastAPI REST API (Uvicorn)
  │
  ▼
Application Service Layer (URLService)
  │
  ▼
Custom In-Memory LRU Cache (HashMap + Doubly Linked List + Metrics)
  │
  ├── [HIT]  ───> Return cached original URL (O(1) in-memory, ZERO DB round-trips)
  │
  └── [MISS] ───> PostgreSQL (Supabase) via Repository Layer
                     │
                     ├── [Found] ───> Populate LRU Cache + Update DB Stats ───> Return original URL
                     └── [Not Found] > Return 404
```

### Key Architectural Characteristics
- **Cache-First Lookups:** Redirects check the custom LRU cache first. On a cache hit, the URL is returned immediately with **zero database queries or updates**. A database query occurs only on cache misses.
- **Observability Built-In:** Real-time thread-safe tracking of total lookups, hits, misses, evictions, and cache hit rates exposed via `/api/cache/stats`.
- **Process-Local Rate Limiting:** Sliding-window rate limiter protects endpoints against volumetric abuse, returning standard HTTP 429 and `Retry-After` headers.
- **Repository Isolation:** Database queries and connection details are isolated within `app.database.repository`, completely decoupled from the FastAPI routing and service layers.
- **Pure Custom Cache:** No external cache dependencies (no Redis, no `cachetools`, no `functools.lru_cache`).
- **Deterministic Uniqueness:** Short-code uniqueness is authoritatively enforced by the database's `UNIQUE` constraint, catching collision exceptions on insert and retrying gracefully.

---

## 4. Technology Stack

- **Language:** Python 3.12+
- **API Framework:** [FastAPI](https://fastapi.tiangolo.com/)
- **ASGI Server:** [Uvicorn](https://www.uvicorn.org/)
- **Data Validation & Settings:** [Pydantic v2](https://docs.pydantic.dev/) / `pydantic-settings`
- **Database:** PostgreSQL (hosted on [Supabase](https://supabase.com/))
- **Database Driver & Pool:** `psycopg` (v3) with `psycopg_pool.ConnectionPool`
- **Migrations:** Version-controlled SQL scripts compatible with Supabase CLI
- **Deployment Platform:** [Render](https://render.com/)
- **Testing:** [pytest](https://docs.pytest.org/), `httpx` (FastAPI TestClient)

---

## 5. Project Structure

```
d:/python_project/
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI application, lifespan & router registration
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── cache.py            # Cache metrics endpoint (/api/cache/stats)
│   │       ├── health.py           # Health check endpoint (/health)
│   │       └── urls.py             # URL creation, redirect & analytics endpoints
│   ├── cache/
│   │   ├── __init__.py
│   │   ├── node.py                 # Doubly Linked List Node
│   │   └── lru_cache.py            # Custom HashMap + Doubly Linked List LRU Cache with metrics
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py               # Settings & environment configuration
│   │   └── rate_limiter.py         # Thread-safe sliding window rate limiter
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py           # Database connection pool manager
│   │   └── repository.py           # Data access repository (Postgres & test In-Memory)
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── cache.py                # Cache stats response schema
│   │   └── url.py                  # Pydantic request/response schemas and validators
│   └── services/
│       ├── __init__.py
│       └── url_service.py          # Business logic, short-code generator, cache manager
├── benchmarks/
│   ├── benchmark_resolution.py     # Comparative resolution benchmark
│   └── README.md                   # Benchmark methodology & measured results
├── supabase/
│   └── migrations/
│       └── 20260330000000_create_urls_table.sql
├── tests/
│   ├── __init__.py
│   ├── test_api.py                 # FastAPI endpoint integration tests
│   ├── test_cache_metrics.py       # Cache metrics & thread-safety unit tests
│   ├── test_database.py            # Database repository & fallback enforcement tests
│   ├── test_lru_cache.py           # LRU Cache unit & eviction order tests
│   ├── test_rate_limiter.py        # Sliding window rate limiter unit tests
│   ├── test_url_service.py         # URL service, cache-hit & collision logic tests
│   ├── test_url_stats.py           # URL Analytics endpoint tests
│   └── test_validation.py          # Input & URL format validation tests
├── .env.example                    # Sample environment variables template
├── .gitignore                      # Git ignore rules protecting secrets and caches
├── pytest.ini                      # Pytest configuration
├── README.md                       # Comprehensive documentation
├── render.yaml                     # Render Infrastructure-as-Code Blueprint
├── requirements.txt                # Pinned dependency definitions
└── runtime.txt                     # Target Python runtime version
```

---

## 6. Local Setup

### Prerequisites
- Python 3.12+
- Git

### Installation Steps

1. Clone or navigate to the project repository:
   ```bash
   cd d:/python_project
   ```

2. (Optional but recommended) Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   # Windows PowerShell:
   .venv\Scripts\Activate.ps1
   # Linux/macOS:
   source .venv/bin/activate
   ```

3. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

---

## 7. Environment Variables

Create a local `.env` file from the example template:
```bash
cp .env.example .env
```

### Variable Reference

| Variable | Type | Default | Required in Production | Description |
| :--- | :--- | :--- | :---: | :--- |
| `DATABASE_URL` | string | *None* | **Yes** | PostgreSQL connection string |
| `APP_ENV` | string | `development` | **Yes** (`production`) | Environment name (`development`, `test`, `production`) |
| `CACHE_CAPACITY` | integer | `1000` | No | Maximum items stored in LRU cache before eviction |
| `BASE_URL` | string | `http://localhost:8000` | **Yes** (Render URL) | Base domain for generated short URLs |
| `RATE_LIMIT_REQUESTS` | integer | `100` | No | Max requests allowed per client IP per window |
| `RATE_LIMIT_WINDOW_SECONDS`| integer | `60` | No | Sliding window duration in seconds |
| `RATE_LIMIT_ENABLED` | boolean | `true` | No | Enable or disable rate limiting |

> **Security Note:** Never commit `.env` or real credentials to version control. Production environment variables must be configured directly in the Render dashboard.

---

## 8. Supabase Database & Migration Setup

### Step 1: Obtain Connection String
1. Log in to [Supabase](https://supabase.com/) and open your project.
2. Navigate to **Project Settings** -> **Database**.
3. Under **Connection string**, select **Transaction Pooler** (Port `6543`) for Render deployment:
   ```text
   postgresql://postgres.[YOUR-PROJECT-REF]:[YOUR-PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres?sslmode=require
   ```

### Step 2: Apply Migration
Run the SQL migration in the Supabase SQL Editor from [supabase/migrations/20260330000000_create_urls_table.sql](file:///d:/python_project/supabase/migrations/20260330000000_create_urls_table.sql):

```sql
CREATE TABLE IF NOT EXISTS urls (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    short_code VARCHAR(16) NOT NULL UNIQUE,
    original_url TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_accessed_at TIMESTAMPTZ,
    access_count BIGINT NOT NULL DEFAULT 0
);
```

---

## 9. Production Deployment to Render

### Option A: Deploy via GitHub & Render Blueprint (`render.yaml`)

1. **Push your code to a new GitHub repository:**
   ```bash
   git init
   git add .
   git commit -m "feat: complete CacheShort URL shortener with custom LRU cache"
   git branch -M main
   git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/<YOUR_REPOSITORY_NAME>.git
   git push -u origin main
   ```

2. **Connect to Render:**
   - Log into [dashboard.render.com](https://dashboard.render.com/).
   - Click **New +** -> **Blueprint**.
   - Select your GitHub repository.
   - Render will detect [render.yaml](file:///d:/python_project/render.yaml).
   - Enter the required environment variable values (`DATABASE_URL`, `BASE_URL`).
   - Click **Apply**.

### Option B: Deploy Manually as a Render Web Service

1. On the Render dashboard, click **New +** -> **Web Service**.
2. Connect your GitHub repository.
3. Configure the following service settings:
   - **Name:** `cacheshort-api`
   - **Language:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`
   - **Plan:** `Free`
   - **Health Check Path:** `/health`
4. Add the **Environment Variables**:
   - `APP_ENV`: `production`
   - `DATABASE_URL`: `postgresql://postgres.[REF]:[PASSWORD]@[HOST]:6543/postgres?sslmode=require`
   - `BASE_URL`: `https://<YOUR-RENDER-SERVICE-NAME>.onrender.com`
   - `CACHE_CAPACITY`: `1000`
   - `RATE_LIMIT_REQUESTS`: `100`
   - `RATE_LIMIT_WINDOW_SECONDS`: `60`
5. Click **Create Web Service**.

---

## 10. Single-Process Deployment Model & Limitations

CacheShort is deliberately configured to run with a **single worker process** (`--workers 1`):
- **Process-Local LRU Cache:** Cache state is in-memory and synchronized across threads using `threading.RLock`.
- **Process-Local Rate Limiter:** The sliding-window rate limiter state is stored in-process memory.
- **Horizontal Scaling:** Multiple application instances would operate with independent in-memory caches and rate-limiting buckets. In future phases, distributed caching (Redis) will be introduced for multi-instance deployments.

---

## 11. API Endpoints

| Method | Endpoint | Description | Rate-Limited | Status Code |
| :--- | :--- | :--- | :---: | :--- |
| `GET` | `/health` | Service health, cache size, DB status | No | `200 OK` |
| `GET` | `/api/cache/stats` | Cache hits, misses, evictions, hit rate | No | `200 OK` |
| `POST` | `/api/urls` | Create a shortened URL | Yes | `201 Created` / `429` |
| `GET` | `/{short_code}` | Redirect to original target URL | Yes | `307 Redirect` / `404` / `429` |
| `GET` | `/api/urls/{short_code}` | Metadata for a short URL | Yes | `200 OK` / `404` / `429` |
| `GET` | `/api/urls/{short_code}/stats` | Analytics stats for a short URL | Yes | `200 OK` / `404` / `429` |

---

## 12. Post-Deployment Verification Checklist

Once deployed to Render (`https://<YOUR-APP>.onrender.com`), verify the live service:

1. **Health Check:**
   ```bash
   curl -i https://<YOUR-APP>.onrender.com/health
   ```
   *Expected:* HTTP 200 with `"status": "ok"` and `"database": "healthy"`.

2. **Create Short URL:**
   ```bash
   curl -i -X POST https://<YOUR-APP>.onrender.com/api/urls \
     -H "Content-Type: application/json" \
     -d '{"url": "https://fastapi.tiangolo.com/"}'
   ```
   *Expected:* HTTP 201 with `short_code`, `short_url`, and `original_url`.

3. **Follow Redirect:**
   ```bash
   curl -i https://<YOUR-APP>.onrender.com/<SHORT_CODE>
   ```
   *Expected:* HTTP 307 redirect with `Location: https://fastapi.tiangolo.com/`.

4. **Verify Cache Hit & Metrics:**
   ```bash
   curl -s https://<YOUR-APP>.onrender.com/api/cache/stats
   ```
   *Expected:* `hits` counter incremented.

5. **Verify URL Analytics:**
   ```bash
   curl -s https://<YOUR-APP>.onrender.com/api/urls/<SHORT_CODE>/stats
   ```
   *Expected:* Accurate `access_count` and timestamps.

---

## 13. Running Tests & Benchmarks

```bash
# Run complete test suite
pytest -v

# Run performance benchmark suite
python benchmarks/benchmark_resolution.py
```
