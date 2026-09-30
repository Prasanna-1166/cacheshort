# CacheShort — LRU-Cache-Backed URL Shortener

An educational, high-performance URL-shortening backend built with FastAPI, PostgreSQL (hosted on Supabase), and a custom in-memory Least Recently Used (LRU) Cache implemented from scratch using a HashMap + Doubly Linked List with full observability metrics, sliding-window rate limiting, and database-backed hashed API-key authentication.

---

## 1. Project Overview

**CacheShort** is designed to demonstrate clean backend architecture, data structure fundamentals, and caching mechanics. In high-throughput URL shortening services, lookups follow the Pareto distribution (80-90% of redirects hit a small subset of hot/viral URLs). Querying the database for every redirect creates unnecessary disk I/O and connection overhead. CacheShort solves this by placing an $O(1)$ LRU cache in front of the database.

In Phase 4, CacheShort incorporates **API-Key Authentication and Security Hardening**:
- **Public High-Speed Redirects:** `GET /{short_code}` and `GET /health` remain open, ultra-fast, and unauthenticated.
- **Protected Management Endpoints:** `POST /api/urls`, `GET /api/urls/{short_code}`, `GET /api/urls/{short_code}/stats`, and `GET /api/cache/stats` require valid database-backed API keys via the `X-API-Key` header.
- **Cryptographic Security:** API keys are formatted as `cs_live_<token>`, hashed using SHA-256 before storage in PostgreSQL, verified in constant time (`secrets.compare_digest`), and supported by active/revocation lifecycle controls.

---

## 2. Architecture & Security Model

```
Client Request
      │
      ▼
Process-Local Sliding Window Rate Limiter ──[Exceed Limit]──> HTTP 429 + Retry-After
      │
      ▼
Route Security Gateway
      │
      ├── Public Routes (GET /{short_code}, GET /health, /docs, /openapi.json)
      │     └── Directly proceeds to Service Layer
      │
      └── Protected Routes (POST /api/urls, GET /api/urls/{code}, /stats, /cache/stats)
            │
            ├── Missing / Malformed X-API-Key ───> HTTP 401 Unauthorized
            │
            ├── SHA-256 Lookup in Supabase `api_keys`
            │     │
            │     ├── Inactive / Revoked / Not Found ──> HTTP 401 Unauthorized
            │     │
            │     └── Valid Active Key (Constant-time check)
            │           │
            │           └── Update `last_used_at` ──> Proceed to Service Layer
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
                         ├── [Found] ───> Populate LRU Cache + Return original URL
                         └── [Not Found] > Return 404
```

---

## 3. API Authentication & Security Rules

### Header Format
All protected management requests must supply the API key in the custom header:
```http
X-API-Key: cs_live_<cryptographically-random-token>
```
*(Note: `Authorization: Bearer` is intentionally not accepted in this phase).*

### Security & Lifecycle Principles
1. **Never Stored in Plaintext:** Only a 64-character SHA-256 hexadecimal hash is stored in the `api_keys` table.
2. **Displayed Only Once:** Plaintext keys are shown only when generated via the bootstrap CLI and can never be retrieved again.
3. **No Credential Leaks:** Authentication failures return a uniform `401 Unauthorized` with `{"detail": "Invalid or missing API key"}` to prevent attackers from enumerating valid or revoked keys.
4. **Timing Attack Protection:** Hash comparisons use Python's `secrets.compare_digest`.
5. **Key Revocation:** Keys can be deactivated instantly by setting `is_active = FALSE` and `revoked_at = CURRENT_TIMESTAMP`.

---

## 4. Technology Stack

- **Language:** Python 3.12+
- **API Framework:** [FastAPI](https://fastapi.tiangolo.com/)
- **ASGI Server:** [Uvicorn](https://www.uvicorn.org/)
- **Data Validation & Settings:** [Pydantic v2](https://docs.pydantic.dev/) / `pydantic-settings`
- **Database:** PostgreSQL (hosted on [Supabase](https://supabase.com/))
- **Database Driver & Pool:** `psycopg` (v3) with `psycopg_pool.ConnectionPool` (`prepare_threshold=None`)
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
│   │       ├── cache.py            # Cache metrics endpoint (Protected)
│   │       ├── health.py           # Health check endpoint (Public)
│   │       └── urls.py             # URL creation, redirect & analytics endpoints
│   ├── cache/
│   │   ├── __init__.py
│   │   ├── node.py                 # Doubly Linked List Node
│   │   └── lru_cache.py            # Custom HashMap + Doubly Linked List LRU Cache
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py               # Settings & environment configuration
│   │   ├── rate_limiter.py         # Thread-safe sliding window rate limiter
│   │   └── security.py             # Key generation, SHA-256 hashing, and verification dependency
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py           # Database connection pool manager
│   │   ├── repository.py           # URL data access repository (Postgres & InMemory)
│   │   └── api_key_repository.py   # API key data access repository (Postgres & InMemory)
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── api_key.py              # Safe API key metadata schemas
│   │   ├── cache.py                # Cache stats response schema
│   │   └── url.py                  # Pydantic request/response schemas
│   └── services/
│       ├── __init__.py
│       └── url_service.py          # Business logic, short-code generator, cache manager
├── benchmarks/
│   ├── benchmark_resolution.py     # Comparative resolution benchmark
│   └── README.md                   # Benchmark methodology & measured results
├── scripts/
│   └── create_api_key.py           # Safe CLI tool to generate and store hashed API keys
├── supabase/
│   └── migrations/
│       ├── 20260330000000_create_urls_table.sql
│       └── 20260330000001_create_api_keys_table.sql
├── tests/
│   ├── __init__.py
│   ├── test_api.py                 # FastAPI endpoint integration tests
│   ├── test_cache_metrics.py       # Cache metrics & thread-safety unit tests
│   ├── test_database.py            # Database repository & fallback enforcement tests
│   ├── test_lru_cache.py           # LRU Cache unit & eviction order tests
│   ├── test_rate_limiter.py        # Sliding window rate limiter unit tests
│   ├── test_security.py            # API key generation, hashing & authentication tests
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

## 6. Local Setup & API Key Generation

### 1. Installation
```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Or on Windows: .venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Local `.env`
```bash
cp .env.example .env
```

### 3. Generate a Developer / Admin API Key
Run the developer CLI script to create an initial API key in PostgreSQL:
```bash
python scripts/create_api_key.py --name "local-dev-key"
```
Output:
```text
============================================================
SUCCESS: NEW CACHESHORT API KEY GENERATED
============================================================
Key ID:     1
Key Name:   local-dev-key
Key Prefix: cs_live_abc12
Created At: 2026-09-30T16:00:00+00:00
------------------------------------------------------------
RAW API KEY (Save this now!):

    cs_live_vY8z9k...<random-token>

------------------------------------------------------------
WARNING: This raw key is shown ONLY ONCE and cannot be recovered.
Only its cryptographic SHA-256 hash has been stored in PostgreSQL.
Include this header in API requests:
    X-API-Key: cs_live_vY8z9k...<random-token>
============================================================
```

---

## 7. Supabase Database Migrations

Apply both migrations in the Supabase SQL Editor:

### Migration 1: URLs Table
File: [supabase/migrations/20260330000000_create_urls_table.sql](file:///d:/python_project/supabase/migrations/20260330000000_create_urls_table.sql)
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

### Migration 2: API Keys Table
File: [supabase/migrations/20260330000001_create_api_keys_table.sql](file:///d:/python_project/supabase/migrations/20260330000001_create_api_keys_table.sql)
```sql
CREATE TABLE IF NOT EXISTS api_keys (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    key_prefix VARCHAR(16) NOT NULL,
    key_hash VARCHAR(64) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ
);
```

---

## 8. API Endpoints Reference

| Method | Endpoint | Authentication | Rate Limited | Description |
| :--- | :--- | :---: | :---: | :--- |
| `GET` | `/health` | **Public** | No | Service health, cache size, DB status |
| `GET` | `/{short_code}` | **Public** | Yes | $O(1)$ LRU Cache redirect to original URL |
| `GET` | `/docs` | **Public** | No | Interactive OpenAPI Swagger UI |
| `GET` | `/openapi.json` | **Public** | No | OpenAPI 3.0 schema |
| `POST` | `/api/urls` | **Protected** (`X-API-Key`) | Yes | Create and shorten a new URL |
| `GET` | `/api/urls/{short_code}` | **Protected** (`X-API-Key`) | Yes | Retrieve URL metadata |
| `GET` | `/api/urls/{short_code}/stats` | **Protected** (`X-API-Key`) | Yes | Access analytics & timestamps |
| `GET` | `/api/cache/stats` | **Protected** (`X-API-Key`) | Yes | Observability stats of LRU cache |

---

## 9. Usage & Curl Examples

### 1. Health Probe (Public)
```bash
curl -i https://cacheshort-api.onrender.com/health
```

### 2. Create Short URL (Protected)
```bash
curl -i -X POST https://cacheshort-api.onrender.com/api/urls \
  -H "X-API-Key: cs_live_your_actual_key_here" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://fastapi.tiangolo.com/"}'
```
Response (`201 Created`):
```json
{
  "short_code": "k9ZaB1x",
  "short_url": "https://cacheshort-api.onrender.com/k9ZaB1x",
  "original_url": "https://fastapi.tiangolo.com/"
}
```

### 3. Public Redirect (No Key Required)
```bash
curl -i https://cacheshort-api.onrender.com/k9ZaB1x
```
Response (`307 Temporary Redirect`):
```http
HTTP/1.1 307 Temporary Redirect
Location: https://fastapi.tiangolo.com/
```

### 4. Fetch Analytics (Protected)
```bash
curl -i https://cacheshort-api.onrender.com/api/urls/k9ZaB1x/stats \
  -H "X-API-Key: cs_live_your_actual_key_here"
```

### 5. Fetch LRU Cache Observability Stats (Protected)
```bash
curl -i https://cacheshort-api.onrender.com/api/cache/stats \
  -H "X-API-Key: cs_live_your_actual_key_here"
```

### 6. Key Revocation (Database SQL)
To revoke an API key, update the record in Supabase:
```sql
UPDATE api_keys
SET is_active = FALSE,
    revoked_at = CURRENT_TIMESTAMP
WHERE key_prefix = 'cs_live_abc12';
```

---

## 10. Running Test Suite

```bash
pytest -v
```
All 70+ automated tests validate cache mechanics, rate limiting, collision resolution, security rules, hashing, invalid key rejection, and endpoints.
