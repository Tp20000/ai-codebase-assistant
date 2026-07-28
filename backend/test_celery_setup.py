"""
Step 28 Test Suite - Celery Setup
Run from backend/ directory with venv activated:
    cd backend
    python test_celery_setup.py

NOTE: Full task execution tests require Redis running.
      These tests verify imports, config, and task registration.
      Worker integration is tested via verify-phase4.ps1
"""

import sys
import traceback

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
def test_celery_app_import() -> None:
    print("[1] Celery app import")
    from app.tasks.celery_app import celery_app, REDIS_URL

    print(f"  app name: {celery_app.main}")
    print(f"  broker:   {REDIS_URL[:30]}...")
    assert celery_app.main == "ai_codebase_assistant"
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.task_soft_time_limit == 600

    ok("Celery app imports and configured")


# ---------------------------------------------------------------------------
def test_task_registration() -> None:
    print("[2] Task registration")
    from app.tasks.celery_app import celery_app

    # Force task discovery
    celery_app.autodiscover_tasks(
        ["app.tasks.agent_tasks", "app.tasks.indexing_tasks"]
    )

    registered = list(celery_app.tasks.keys())
    print(f"  Registered tasks: {[t for t in registered if 'app.tasks' in t]}")

    expected = [
        "app.tasks.agent_tasks.run_agent_task",
        "app.tasks.agent_tasks.run_orchestration_task",
        "app.tasks.indexing_tasks.index_project_files",
    ]

    for task_name in expected:
        assert task_name in registered, \
            f"Task not registered: {task_name}"
        print(f"  Found: {task_name}")

    ok("All tasks registered in Celery")


# ---------------------------------------------------------------------------
def test_agent_task_import() -> None:
    print("[3] agent_tasks module import")
    from app.tasks.agent_tasks import (
        run_agent_task,
        run_orchestration_task,
        get_task_progress,
        _store_progress,
    )

    print(f"  run_agent_task: {run_agent_task.name}")
    print(f"  run_orchestration_task: {run_orchestration_task.name}")
    assert run_agent_task.name == "app.tasks.agent_tasks.run_agent_task"
    assert run_orchestration_task.name == "app.tasks.agent_tasks.run_orchestration_task"
    assert callable(get_task_progress)

    ok("agent_tasks imports correctly")


# ---------------------------------------------------------------------------
def test_indexing_task_import() -> None:
    print("[4] indexing_tasks module import")
    from app.tasks.indexing_tasks import (
        index_project_files,
        get_indexing_progress,
    )

    print(f"  index_project_files: {index_project_files.name}")
    assert index_project_files.name == "app.tasks.indexing_tasks.index_project_files"
    assert callable(get_indexing_progress)

    ok("indexing_tasks imports correctly")


# ---------------------------------------------------------------------------
def test_tasks_package_init() -> None:
    print("[5] tasks package __init__ exports")
    from app.tasks import (
        celery_app,
        run_agent_task,
        run_orchestration_task,
        get_task_progress,
        index_project_files,
        get_indexing_progress,
    )

    assert celery_app is not None
    assert callable(run_agent_task)
    assert callable(run_orchestration_task)
    assert callable(get_task_progress)
    assert callable(index_project_files)
    assert callable(get_indexing_progress)

    ok("tasks package exports all symbols")


# ---------------------------------------------------------------------------
def test_celery_config_values() -> None:
    print("[6] Celery configuration values")
    from app.tasks.celery_app import celery_app

    conf = celery_app.conf
    print(f"  serializer:         {conf.task_serializer}")
    print(f"  soft_time_limit:    {conf.task_soft_time_limit}s")
    print(f"  time_limit:         {conf.task_time_limit}s")
    print(f"  result_expires:     {conf.result_expires}s")
    print(f"  prefetch_mult:      {conf.worker_prefetch_multiplier}")
    print(f"  acks_late:          {conf.task_acks_late}")

    assert conf.task_serializer == "json"
    assert conf.task_soft_time_limit == 600
    assert conf.task_time_limit == 720
    assert conf.result_expires == 86400
    assert conf.worker_prefetch_multiplier == 1
    assert conf.task_acks_late is True

    ok("Celery configuration correct")


# ---------------------------------------------------------------------------
def test_queue_configuration() -> None:
    print("[7] Queue configuration")
    from app.tasks.celery_app import TASK_QUEUES, TASK_ROUTES

    queue_names = [q.name for q in TASK_QUEUES]
    print(f"  Queues: {queue_names}")

    assert "high" in queue_names
    assert "default" in queue_names
    assert "low" in queue_names

    print(f"  Routes: {TASK_ROUTES}")
    assert "app.tasks.agent_tasks.*" in TASK_ROUTES
    assert "app.tasks.indexing_tasks.*" in TASK_ROUTES

    ok("Queue configuration correct")


# ---------------------------------------------------------------------------
def test_api_router_import() -> None:
    print("[8] tasks API router import")
    from app.api.v1.tasks import router, AgentTaskRequest, OrchestrationTaskRequest

    print(f"  router prefix: {router.prefix}")
    print(f"  router tags: {router.tags}")
    assert router.prefix == "/tasks"
    assert "tasks" in router.tags

    ok("tasks API router imports correctly")


# ---------------------------------------------------------------------------
def test_redis_progress_functions() -> None:
    print("[9] Redis progress functions (no Redis required)")
    from app.tasks.agent_tasks import get_task_progress, _store_progress

    # get_task_progress should return None gracefully when Redis unavailable
    result = get_task_progress("nonexistent-task-id")
    # Either None (Redis unavailable) or a dict (Redis available)
    assert result is None or isinstance(result, dict)
    print(f"  get_task_progress returned: {result}")

    ok("Redis progress functions handle missing Redis gracefully")


# ---------------------------------------------------------------------------
def test_store_progress_no_crash() -> None:
    print("[10] _store_progress handles Redis unavailable gracefully")
    from app.tasks.agent_tasks import _store_progress

    # Should not raise even if Redis is down
    try:
        _store_progress(
            task_id="test-task-123",
            status="RUNNING",
            progress=0.5,
            current_step="testing",
            agent_id="test_agent",
        )
        print("  _store_progress completed (Redis may or may not be available)")
        ok("_store_progress no crash")
    except Exception as exc:
        fail("_store_progress crashed", exc)


# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 60)
    print("Step 28 - Celery Setup Test Suite")
    print("=" * 60)
    print()

    tests = [
        test_celery_app_import,
        test_task_registration,
        test_agent_task_import,
        test_indexing_task_import,
        test_tasks_package_init,
        test_celery_config_values,
        test_queue_configuration,
        test_api_router_import,
        test_redis_progress_functions,
        test_store_progress_no_crash,
    ]

    for fn in tests:
        try:
            fn()
        except Exception as exc:
            fail(fn.__name__, exc)
        print()

    print("=" * 60)
    print(f"Results: {PASS} passed | {FAIL} failed")
    print("ALL TESTS PASSED" if FAIL == 0 else "SOME TESTS FAILED")
    print("=" * 60)

    if FAIL == 0:
        print()
        print("Next steps:")
        print("  1. Start Redis (already running via Docker)")
        print("  2. Start Celery worker:")
        print("     cd backend")
        print("     celery -A app.tasks.celery_app:celery_app worker --queues=high,default,low -l info")
        print("  3. Test task API:")
        print("     POST http://localhost:8000/api/v1/tasks/agent")

    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
