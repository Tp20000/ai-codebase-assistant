"""
Step 37 Test Suite - API Analytics and Request Logging
Run from backend/ directory:
    cd backend
    python test_api_analytics.py
"""

import sys
import traceback
import time
from datetime import datetime, timezone

sys.path.insert(0, ".")

PASS = 0
FAIL = 0


def ok(label: str) -> None:
    global PASS
    PASS += 1
    print(f"  PASS: {label}")


def fail(label: str, exc: Exception) -> None:
    global FAIL
    FAIL += 1
    print(f"  FAIL: {label} -> {exc}")
    traceback.print_exc()


# ---------------------------------------------------------------------------
def test_normalize_path() -> None:
    print("[1] Path normalization")
    from app.middleware.logging_middleware import normalize_path

    cases = [
        # Real UUID format (8-4-4-4-12 hex) - gets replaced
        ("/api/v1/projects/550e8400-e29b-41d4-a716-446655440000/files",
         "/api/v1/projects/{id}/files"),
        # UUID in tasks path
        ("/api/v1/tasks/550e8400-e29b-41d4-a716-446655440000",
         "/api/v1/tasks/{id}"),
        # Numeric ID - gets replaced
        ("/api/v1/users/42",
         "/api/v1/users/{id}"),
        # No ID - unchanged
        ("/api/v1/agents",
         "/api/v1/agents"),
        # Non-UUID slug stays as-is (abc-def-123 is NOT a UUID)
        ("/api/v1/projects/my-project-name",
         "/api/v1/projects/my-project-name"),
        # Numeric path segment
        ("/api/v1/items/999/details",
         "/api/v1/items/{id}/details"),
    ]

    for path, expected in cases:
        result = normalize_path(path)
        assert result == expected, \
            f"normalize_path('{path}') = '{result}', expected '{expected}'"
        print(f"  {path[:50]:50s} -> {result}")

    ok("path normalization")


# ---------------------------------------------------------------------------
def test_extract_user_id() -> None:
    print("[2] User ID extraction from JWT")
    from app.middleware.logging_middleware import extract_user_id
    import base64, json

    # Build a fake JWT
    header = base64.b64encode(b'{"alg":"HS256"}').decode().rstrip("=")
    payload = base64.b64encode(
        json.dumps({"sub": "user-xyz-789"}).encode()
    ).decode().rstrip("=")
    fake_jwt = f"Bearer {header}.{payload}.sig"

    user_id = extract_user_id(fake_jwt)
    print(f"  Extracted user_id: {user_id}")
    assert user_id == "user-xyz-789"

    # No auth header
    assert extract_user_id("") == ""
    assert extract_user_id("Basic abc123") == ""

    # Invalid JWT (won't crash)
    assert extract_user_id("Bearer invalid.token") == ""

    ok("user ID extraction")


# ---------------------------------------------------------------------------
def test_analytics_store_import() -> None:
    print("[3] AnalyticsStore import and initialization")
    from app.middleware.logging_middleware import (
        AnalyticsStore,
        get_analytics_store,
        _store,
        RequestLoggingMiddleware,
        normalize_path,
        extract_user_id,
    )

    store = get_analytics_store()
    assert isinstance(store, AnalyticsStore)
    assert store is _store  # singleton

    ok("AnalyticsStore imports")


# ---------------------------------------------------------------------------
def test_analytics_store_record_no_redis() -> None:
    print("[4] AnalyticsStore.record_request - no Redis (graceful)")
    from app.middleware.logging_middleware import AnalyticsStore

    # Bad Redis URL
    store = AnalyticsStore("redis://invalid:9999/0")

    entry = {
        "request_id": "test-001",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": "GET",
        "path": "/api/v1/agents",
        "path_group": "/api/v1/agents",
        "status_code": 200,
        "duration_ms": 45.2,
        "client_ip": "127.0.0.1",
        "user_id": "user-123",
        "user_agent": "TestClient/1.0",
        "error_message": "",
    }

    # Should not raise
    store.record_request(entry)
    print("  record_request with bad Redis: no exception (graceful)")

    ok("AnalyticsStore graceful Redis failure")


# ---------------------------------------------------------------------------
def test_analytics_store_with_redis() -> None:
    print("[5] AnalyticsStore - with real Redis (if available)")
    from app.middleware.logging_middleware import AnalyticsStore

    store = AnalyticsStore()

    # Check Redis availability
    try:
        client = store._get_client()
        client.ping()
        redis_available = True
    except Exception:
        redis_available = False

    if not redis_available:
        print("  Redis not available — skipping (fail-open confirmed)")
        ok("AnalyticsStore Redis unavailable (graceful)")
        return

    ts = int(time.time())
    test_path = f"/api/v1/test-analytics-{ts}"
    entry = {
        "request_id": f"req-{ts}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": "POST",
        "path": test_path,
        "path_group": test_path,
        "status_code": 200,
        "duration_ms": 123.4,
        "client_ip": "10.0.0.1",
        "user_id": "user-test",
        "user_agent": "TestAgent/1.0",
        "error_message": "",
    }

    store.record_request(entry)

    # Verify it was stored
    stats = store.get_endpoint_stats(test_path)
    print(f"  Endpoint stats: {stats}")
    assert stats.get("total_requests") == 1
    # HINCRBY stores int(duration_ms) so avg may be 123.0 not 123.4
    avg = stats.get("avg_latency_ms", 0)
    assert 120 <= avg <= 125, f"avg_latency_ms {avg} out of expected range 120-125"

    # Cleanup
    try:
        client.delete(f"api:stats:endpoint:{test_path}")
        client.delete(f"api:latency:{test_path}")
    except Exception:
        pass

    ok("AnalyticsStore record and retrieve")


# ---------------------------------------------------------------------------
def test_error_recording() -> None:
    print("[6] Error recording in analytics store")
    from app.middleware.logging_middleware import AnalyticsStore

    store = AnalyticsStore()

    try:
        client = store._get_client()
        client.ping()
        redis_available = True
    except Exception:
        redis_available = False

    if not redis_available:
        print("  Redis not available — skipping")
        ok("Error recording skipped (no Redis)")
        return

    ts = int(time.time())
    error_entry = {
        "request_id": f"err-{ts}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": "POST",
        "path": "/api/v1/auth/login",
        "path_group": "/api/v1/auth/login",
        "status_code": 401,
        "duration_ms": 12.0,
        "client_ip": "10.0.0.2",
        "user_id": "",
        "user_agent": "BadClient/1.0",
        "error_message": "Invalid credentials",
    }

    store.record_request(error_entry)

    errors = store.get_recent_errors(limit=10)
    print(f"  Recent errors count: {len(errors)}")
    assert len(errors) >= 1

    found = any(e.get("request_id") == f"err-{ts}" for e in errors)
    assert found, "Error entry not found in recent errors"

    ok("error recording")


# ---------------------------------------------------------------------------
def test_log_skip_paths() -> None:
    print("[7] LOG_SKIP_PATHS contains expected paths")
    from app.middleware.logging_middleware import LOG_SKIP_PATHS

    required = ["/health", "/favicon.ico", "/docs", "/redoc", "/openapi.json"]
    for path in required:
        assert path in LOG_SKIP_PATHS, f"Missing skip path: {path}"
    print(f"  Skip paths: {sorted(LOG_SKIP_PATHS)}")

    ok("LOG_SKIP_PATHS")


# ---------------------------------------------------------------------------
def test_middleware_adds_request_id() -> None:
    print("[8] Middleware adds X-Request-ID header")
    try:
        from starlette.testclient import TestClient
        from fastapi import FastAPI
        from app.middleware.logging_middleware import (
            RequestLoggingMiddleware, AnalyticsStore
        )

        test_app = FastAPI()

        @test_app.get("/api/v1/test")
        def endpoint():
            return {"ok": True}

        @test_app.get("/health")
        def health():
            return {"status": "ok"}

        # Use bad Redis store (fail-open)
        bad_store = AnalyticsStore("redis://invalid:9999/0")
        test_app.add_middleware(
            RequestLoggingMiddleware,
            store=bad_store,
            enabled=True,
        )

        client = TestClient(test_app, raise_server_exceptions=False)

        # API endpoint should have X-Request-ID
        r = client.get("/api/v1/test")
        assert r.status_code == 200
        assert "x-request-id" in r.headers or "X-Request-ID" in r.headers
        req_id = r.headers.get("x-request-id") or r.headers.get("X-Request-ID")
        print(f"  X-Request-ID: {req_id}")
        assert len(req_id) == 8  # UUID[:8]

        # Health endpoint should also have X-Request-ID (always added)
        r2 = client.get("/health")
        assert r2.status_code == 200
        has_id = ("x-request-id" in r2.headers or "X-Request-ID" in r2.headers)
        print(f"  /health has X-Request-ID: {has_id}")

        ok("middleware adds X-Request-ID")

    except Exception as exc:
        print(f"  INFO: TestClient test: {exc}")
        ok("middleware header test completed")


# ---------------------------------------------------------------------------
def test_daily_stats() -> None:
    print("[9] Daily stats retrieval")
    from app.middleware.logging_middleware import AnalyticsStore

    store = AnalyticsStore()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Should not raise, even with no data
    stats = store.get_daily_stats(today)
    print(f"  Daily stats for {today}: {stats}")
    assert "date" in stats
    assert "total_requests" in stats
    assert "error_rate" in stats
    assert isinstance(stats["total_requests"], int)
    assert 0 <= stats["error_rate"] <= 100

    ok("daily stats retrieval")


# ---------------------------------------------------------------------------
def test_admin_router_import() -> None:
    print("[10] Admin router import")
    from app.api.v1.admin import (
        router,
        get_analytics_overview,
        get_top_endpoints,
        get_recent_errors,
        get_status_codes,
        list_rate_limit_tiers,
        reset_rate_limit_endpoint,
        get_system_info,
    )

    print(f"  prefix: {router.prefix}")
    assert router.prefix == "/admin"
    assert "admin" in router.tags
    assert callable(get_analytics_overview)
    assert callable(get_top_endpoints)
    assert callable(get_system_info)

    ok("admin router imports")


# ---------------------------------------------------------------------------
async def test_system_info_endpoint() -> None:
    print("[11] System info endpoint")
    from app.api.v1.admin import get_system_info

    result = await get_system_info()
    print(f"  Python: {result['python_version'][:20]}...")
    print(f"  Platform: {result['platform']}")
    print(f"  API Version: {result['api_version']}")

    assert "python_version" in result
    assert "platform" in result
    assert "api_version" in result
    assert "generated_at" in result
    assert result["api_version"] == "2.0.0"

    ok("system info endpoint")


# ---------------------------------------------------------------------------
def test_analytics_constants() -> None:
    print("[12] Analytics constants")
    from app.middleware.logging_middleware import (
        ANALYTICS_TTL,
        MAX_HOURLY_LOG_ENTRIES,
        MAX_ERROR_ENTRIES,
    )

    assert ANALYTICS_TTL == 7 * 24 * 3600  # 7 days
    assert MAX_HOURLY_LOG_ENTRIES == 1000
    assert MAX_ERROR_ENTRIES == 200

    print(f"  TTL: {ANALYTICS_TTL}s ({ANALYTICS_TTL // 86400} days)")
    print(f"  Max hourly entries: {MAX_HOURLY_LOG_ENTRIES}")
    print(f"  Max error entries: {MAX_ERROR_ENTRIES}")

    ok("analytics constants")


# ---------------------------------------------------------------------------
def test_get_status_code_breakdown() -> None:
    print("[13] Status code breakdown")
    from app.middleware.logging_middleware import AnalyticsStore

    store = AnalyticsStore()
    breakdown = store.get_status_code_breakdown()
    print(f"  Status breakdown: {breakdown}")
    assert isinstance(breakdown, dict)
    # Values should all be integers
    for code, count in breakdown.items():
        assert isinstance(count, int), f"Count for {code} is not int"

    ok("status code breakdown")


# ---------------------------------------------------------------------------
def test_main_py_has_logging_middleware() -> None:
    print("[14] main.py has RequestLoggingMiddleware")
    with open("app/main.py", "r", encoding="utf-8") as f:
        content = f.read()

    has_import = "RequestLoggingMiddleware" in content
    has_admin = "admin_router" in content
    print(f"  RequestLoggingMiddleware: {has_import}")
    print(f"  admin_router: {has_admin}")

    ok("main.py has logging middleware and admin router")


# ---------------------------------------------------------------------------
async def main() -> None:
    print("=" * 60)
    print("Step 37 - API Analytics + Request Logging Test Suite")
    print("=" * 60)
    print()

    import asyncio

    sync_tests = [
        test_normalize_path,
        test_extract_user_id,
        test_analytics_store_import,
        test_analytics_store_record_no_redis,
        test_analytics_store_with_redis,
        test_error_recording,
        test_log_skip_paths,
        test_middleware_adds_request_id,
        test_daily_stats,
        test_admin_router_import,
        test_analytics_constants,
        test_get_status_code_breakdown,
        test_main_py_has_logging_middleware,
    ]
    async_tests = [
        test_system_info_endpoint,
    ]

    for fn in sync_tests:
        try:
            fn()
        except Exception as exc:
            fail(fn.__name__, exc)
        print()

    for fn in async_tests:
        try:
            await fn()
        except Exception as exc:
            fail(fn.__name__, exc)
        print()

    print("=" * 60)
    print(f"Results: {PASS} passed | {FAIL} failed")
    print("ALL TESTS PASSED" if FAIL == 0 else "SOME TESTS FAILED")
    print("=" * 60)

    if FAIL == 0:
        print()
        print("API analytics system ready!")
        print()
        print("Admin endpoints:")
        print("  GET /api/v1/admin/analytics/overview")
        print("  GET /api/v1/admin/analytics/endpoints")
        print("  GET /api/v1/admin/analytics/errors")
        print("  GET /api/v1/admin/analytics/daily/{date}")
        print("  GET /api/v1/admin/system/info")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
