"""
Step 29 Test Suite - Background Indexing Tasks
Run from backend/ directory with venv activated:
    cd backend
    python test_indexing_tasks.py
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
def test_language_detection() -> None:
    print("[1] Language detection from file extensions")
    from app.tasks.indexing_tasks import _detect_language

    cases = [
        ("main.py",        "python"),
        ("app.js",         "javascript"),
        ("index.tsx",      "typescript"),
        ("Main.java",      "java"),
        ("main.go",        "go"),
        ("lib.rs",         "rust"),
        ("style.css",      "css"),
        ("query.sql",      "sql"),
        ("config.yaml",    "yaml"),
        ("README.md",      "markdown"),
        ("unknown.xyz",    "unknown"),
    ]

    for path, expected in cases:
        result = _detect_language(path)
        assert result == expected, \
            f"_detect_language('{path}') = '{result}', expected '{expected}'"
        print(f"  {path:20s} -> {result}")

    ok("language detection")


# ---------------------------------------------------------------------------
def test_should_skip_file() -> None:
    print("[2] File skip logic")
    from app.tasks.indexing_tasks import _should_skip_file

    # Should skip
    skip_cases = [
        ("image.jpg",         "content"),
        ("lib.pyc",           "content"),
        ("app.min.js",        "some js"),
        ("package-lock.json", "{}"),
        ("empty.py",          ""),
        ("empty.py",          "   \n  "),
    ]
    for path, content in skip_cases:
        should_skip, reason = _should_skip_file(path, content)
        assert should_skip, f"Should skip {path} but got should_skip=False"
        print(f"  SKIP: {path:25s} reason='{reason}'")

    # Should NOT skip
    keep_cases = [
        ("main.py",    "def hello(): pass"),
        ("app.js",     "const x = 1;"),
        ("README.md",  "# Hello World"),
    ]
    for path, content in keep_cases:
        should_skip, _ = _should_skip_file(path, content)
        assert not should_skip, f"Should NOT skip {path}"
        print(f"  KEEP: {path:25s}")

    ok("file skip logic")


# ---------------------------------------------------------------------------
def test_chunk_file_content() -> None:
    print("[3] File chunking (fallback chunker)")
    from app.tasks.indexing_tasks import _chunk_file_content

    # 50-line Python file
    code = "\n".join(
        f"def function_{i}(x: int) -> int:\n    return x + {i}"
        for i in range(25)
    )

    chunks = _chunk_file_content(
        content=code,
        language="python",
        file_path="test.py",
        chunk_size=200,
        chunk_overlap=50,
    )

    print(f"  Input: {len(code)} chars")
    print(f"  Output: {len(chunks)} chunks")
    assert len(chunks) >= 2, f"Expected >= 2 chunks, got {len(chunks)}"

    for i, chunk in enumerate(chunks):
        assert "content" in chunk, f"Chunk {i} missing 'content'"
        assert "metadata" in chunk, f"Chunk {i} missing 'metadata'"
        assert chunk["metadata"]["file_path"] == "test.py"
        assert chunk["metadata"]["language"] == "python"
        print(f"  Chunk {i}: {len(chunk['content'])} chars, "
              f"lines {chunk['metadata']['start_line']}-{chunk['metadata']['end_line']}")

    ok("file chunking")


# ---------------------------------------------------------------------------
def test_chunk_small_file() -> None:
    print("[4] Small file produces single chunk")
    from app.tasks.indexing_tasks import _chunk_file_content

    code = "def hello():\n    return 'world'\n"
    chunks = _chunk_file_content(
        content=code,
        language="python",
        file_path="small.py",
        chunk_size=1000,
        chunk_overlap=200,
    )

    print(f"  Chunks: {len(chunks)}")
    assert len(chunks) == 1, f"Expected 1 chunk for small file, got {len(chunks)}"
    assert "hello" in chunks[0]["content"]

    ok("small file single chunk")


# ---------------------------------------------------------------------------
def test_index_single_file_python() -> None:
    print("[5] _index_single_file - Python code")
    from app.tasks.indexing_tasks import _index_single_file

    code = (
        "def add(a: int, b: int) -> int:\n"
        "    return a + b\n\n"
        "class Calculator:\n"
        "    def multiply(self, x, y):\n"
        "        return x * y\n"
    )

    result = _index_single_file(
        file_path="calculator.py",
        content=code,
        project_id="test-project-001",
        chunk_size=500,
        chunk_overlap=100,
    )

    print(f"  status:        {result['status']}")
    print(f"  language:      {result['language']}")
    print(f"  chunks_created: {result['chunks_created']}")
    print(f"  elapsed_ms:    {result['elapsed_ms']}")

    assert result["status"] in ("indexed", "skipped"), \
        f"Unexpected status: {result['status']}"
    assert result["language"] == "python"
    assert result["error"] is None or result["status"] == "skipped"

    ok(f"_index_single_file Python ({result['chunks_created']} chunks)")


# ---------------------------------------------------------------------------
def test_index_single_file_js() -> None:
    print("[6] _index_single_file - JavaScript code")
    from app.tasks.indexing_tasks import _index_single_file

    code = (
        "function fetchData(url) {\n"
        "    return fetch(url).then(r => r.json());\n"
        "}\n\n"
        "class ApiClient {\n"
        "    constructor(base) { this.base = base; }\n"
        "    get(path) { return fetchData(this.base + path); }\n"
        "}\n"
    )

    result = _index_single_file(
        file_path="api.js",
        content=code,
        project_id="test-project-001",
    )

    print(f"  status: {result['status']} | language: {result['language']}")
    assert result["language"] == "javascript"
    assert result["status"] in ("indexed", "skipped")

    ok("_index_single_file JavaScript")


# ---------------------------------------------------------------------------
def test_index_single_file_skip_binary() -> None:
    print("[7] _index_single_file - binary extension skipped")
    from app.tasks.indexing_tasks import _index_single_file

    result = _index_single_file(
        file_path="image.jpg",
        content="fake binary content",
        project_id="test-project-001",
    )

    print(f"  status: {result['status']} | reason: {result.get('skip_reason')}")
    assert result["status"] == "skipped"
    assert result["chunks_created"] == 0

    ok("binary file skipped")


# ---------------------------------------------------------------------------
def test_index_single_file_empty_skipped() -> None:
    print("[8] _index_single_file - empty file skipped")
    from app.tasks.indexing_tasks import _index_single_file

    result = _index_single_file(
        file_path="empty.py",
        content="",
        project_id="test-project-001",
    )

    print(f"  status: {result['status']}")
    assert result["status"] == "skipped"

    ok("empty file skipped")


# ---------------------------------------------------------------------------
def test_get_indexing_progress_missing() -> None:
    print("[9] get_indexing_progress - missing project returns None gracefully")
    from app.tasks.indexing_tasks import get_indexing_progress

    result = get_indexing_progress("nonexistent-project-id-xyz")
    print(f"  result: {result}")
    assert result is None

    ok("missing progress returns None")


# ---------------------------------------------------------------------------
def test_indexing_task_registration() -> None:
    print("[10] Celery task registration")
    from app.tasks.celery_app import celery_app

    registered = list(celery_app.tasks.keys())
    expected = [
        "app.tasks.indexing_tasks.index_project_files",
        "app.tasks.indexing_tasks.reindex_single_file",
    ]
    for task_name in expected:
        assert task_name in registered, \
            f"Task not registered: {task_name}\nRegistered: {registered}"
        print(f"  Found: {task_name}")

    ok("indexing tasks registered in Celery")


# ---------------------------------------------------------------------------
def test_indexing_service_validation() -> None:
    print("[11] IndexingService input validation")
    from app.services.indexing_service import IndexingService

    # Empty files list
    try:
        IndexingService.queue_project_indexing(
            project_id="p1", user_id="u1", files=[]
        )
        raise AssertionError("Should have raised ValueError")
    except ValueError as exc:
        print(f"  Empty files -> ValueError: {exc}")

    # Missing path field
    try:
        IndexingService.queue_project_indexing(
            project_id="p1",
            user_id="u1",
            files=[{"content": "some code"}],  # missing path
        )
        raise AssertionError("Should have raised ValueError")
    except ValueError as exc:
        print(f"  Missing path -> ValueError: {exc}")

    ok("IndexingService validation")


# ---------------------------------------------------------------------------
def test_indexing_service_get_progress_not_started() -> None:
    print("[12] IndexingService.get_progress - not started")
    from app.services.indexing_service import IndexingService

    progress = IndexingService.get_progress("nonexistent-proj-xyz")
    print(f"  status: {progress.get('status')}")
    assert progress.get("status") == "NOT_STARTED"
    assert progress.get("progress") == 0.0

    ok("IndexingService get_progress not started")


# ---------------------------------------------------------------------------
def test_indexing_stats_calculation() -> None:
    print("[13] IndexingService.get_indexing_stats")
    from datetime import datetime, timezone
    from app.services.indexing_service import IndexingService

    # Mock progress dict
    progress = {
        "total_files": 100,
        "indexed_files": 50,
        "failed_files": 5,
        "indexed_chunks": 320,
        "started_at": (
            datetime.now(timezone.utc)
            .isoformat()
        ),
    }

    stats = IndexingService.get_indexing_stats(progress)
    print(f"  success_rate: {stats['success_rate_pct']}%")
    print(f"  files_per_second: {stats['files_per_second']}")
    print(f"  total_chunks: {stats['total_chunks']}")

    assert 0 <= stats["success_rate_pct"] <= 100
    assert stats["total_chunks"] == 320
    assert isinstance(stats["files_per_second"], float)

    ok("indexing stats calculation")


# ---------------------------------------------------------------------------
def test_api_router_import() -> None:
    print("[14] indexing API router import")
    from app.api.v1.indexing import (
        router,
        IndexingStartRequest,
        ReindexFileRequest,
        IndexingProgressResponse,
        FileEntry,
    )

    print(f"  router prefix: {router.prefix}")
    assert router.prefix == "/indexing"
    assert "indexing" in router.tags

    ok("indexing API router imports")


# ---------------------------------------------------------------------------
def test_update_progress_no_redis_crash() -> None:
    print("[15] _update_progress handles missing Redis gracefully")
    from app.tasks.indexing_tasks import _update_progress

    # Should not raise even if Redis is unavailable
    try:
        _update_progress(
            project_id="test-proj",
            task_id="test-task",
            status="RUNNING",
            total_files=10,
            indexed_files=3,
            failed_files=0,
            current_file="test.py",
            indexed_chunks=15,
            file_results=[],
        )
        print("  _update_progress completed (Redis may be unavailable)")
        ok("_update_progress no crash without Redis")
    except Exception as exc:
        fail("_update_progress crashed", exc)


# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 60)
    print("Step 29 - Background Indexing Tasks Test Suite")
    print("=" * 60)
    print()

    tests = [
        test_language_detection,
        test_should_skip_file,
        test_chunk_file_content,
        test_chunk_small_file,
        test_index_single_file_python,
        test_index_single_file_js,
        test_index_single_file_skip_binary,
        test_index_single_file_empty_skipped,
        test_get_indexing_progress_missing,
        test_indexing_task_registration,
        test_indexing_service_validation,
        test_indexing_service_get_progress_not_started,
        test_indexing_stats_calculation,
        test_api_router_import,
        test_update_progress_no_redis_crash,
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
        print("Step 29 complete! Indexing pipeline ready.")
        print()
        print("To test end-to-end with running worker:")
        print("  Terminal 1: celery -A app.tasks.celery_app:celery_app worker -l info")
        print("  Terminal 2: POST /api/v1/indexing/{project_id}/start")
        print("  Terminal 3: GET  /api/v1/indexing/{project_id}/progress  (poll)")

    import sys
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
