"""
Step 26 Test Suite - PerformanceAnalyzerAgent
Run from backend/ directory with venv activated:
    cd backend
    python test_performance_agent.py
"""

import asyncio
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
def test_nested_loop_detection() -> None:
    print("[1] PythonPerfAnalyzer - nested loops O(n^2)")
    from app.core.agents.performance_agent import PythonPerfAnalyzer

    code = (
        "def find_common(a, b):\n"
        "    result = []\n"
        "    for x in a:\n"
        "        for y in b:\n"
        "            if x == y:\n"
        "                result.append(x)\n"
        "    return result\n"
    )

    findings = PythonPerfAnalyzer.analyze(code)
    perf_ids = [f["perf_id"] for f in findings]
    print(f"  Findings: {len(findings)} | IDs: {perf_ids}")

    assert any(
        pid in ("PERF-PY-001", "PERF-PY-015") for pid in perf_ids
    ), f"Expected nested loop finding: {perf_ids}"

    nested = next(
        f for f in findings if f["perf_id"] in ("PERF-PY-001", "PERF-PY-015")
    )
    assert nested["impact"] in ("HIGH", "CRITICAL")
    assert "O(n" in nested["complexity"]

    ok("nested loop O(n^2) detection")


# ---------------------------------------------------------------------------
def test_string_concat_in_loop() -> None:
    print("[2] PythonPerfAnalyzer - string concat in loop")
    from app.core.agents.performance_agent import PythonPerfAnalyzer

    code = (
        "def build_html(items):\n"
        "    result = ''\n"
        "    for item in items:\n"
        "        result += '<li>' + str(item) + '</li>'\n"
        "    return result\n"
    )

    findings = PythonPerfAnalyzer.analyze(code)
    perf_ids = [f["perf_id"] for f in findings]
    print(f"  Findings: {len(findings)} | IDs: {perf_ids}")

    assert "PERF-PY-003" in perf_ids, \
        f"String concat PERF-PY-003 missing: {perf_ids}"

    ok("string concatenation in loop")


# ---------------------------------------------------------------------------
def test_list_membership() -> None:
    print("[3] PythonPerfAnalyzer - list membership O(n)")
    from app.core.agents.performance_agent import PythonPerfAnalyzer

    code = (
        "def is_valid(status):\n"
        "    return status in ['active', 'pending', 'processing', 'retry']\n"
    )

    findings = PythonPerfAnalyzer.analyze(code)
    perf_ids = [f["perf_id"] for f in findings]
    print(f"  Findings: {len(findings)} | IDs: {perf_ids}")

    assert "PERF-PY-002" in perf_ids, \
        f"List membership PERF-PY-002 missing: {perf_ids}"

    ok("list membership O(n) → O(1)")


# ---------------------------------------------------------------------------
def test_sort_in_loop() -> None:
    print("[4] PythonPerfAnalyzer - sort inside loop")
    from app.core.agents.performance_agent import PythonPerfAnalyzer

    code = (
        "def process_queries(queries, data):\n"
        "    results = []\n"
        "    for q in queries:\n"
        "        sorted_data = sorted(data)\n"
        "        results.append(sorted_data[0])\n"
        "    return results\n"
    )

    findings = PythonPerfAnalyzer.analyze(code)
    perf_ids = [f["perf_id"] for f in findings]
    print(f"  Findings: {len(findings)} | IDs: {perf_ids}")

    assert "PERF-PY-004" in perf_ids, \
        f"Sort in loop PERF-PY-004 missing: {perf_ids}"

    ok("sort inside loop")


# ---------------------------------------------------------------------------
def test_sync_in_async() -> None:
    print("[5] PythonPerfAnalyzer - blocking call in async")
    from app.core.agents.performance_agent import PythonPerfAnalyzer

    code = (
        "import time\n"
        "import requests\n\n"
        "async def fetch_data(url):\n"
        "    time.sleep(1)\n"
        "    return requests.get(url)\n"
    )

    findings = PythonPerfAnalyzer.analyze(code)
    perf_ids = [f["perf_id"] for f in findings]
    print(f"  Findings: {len(findings)} | IDs: {perf_ids}")

    assert any(
        pid in ("PERF-PY-008", "PERF-PY-008b") for pid in perf_ids
    ), f"Sync-in-async missing: {perf_ids}"

    ok("blocking call in async function")


# ---------------------------------------------------------------------------
def test_js_dom_in_loop() -> None:
    print("[6] JSPerfAnalyzer - DOM query in loop")
    from app.core.agents.performance_agent import JSPerfAnalyzer

    code = (
        "function updateItems(items) {\n"
        "    for (let i = 0; i < items.length; i++) {\n"
        "        const el = document.querySelector('.item');\n"
        "        el.textContent = items[i];\n"
        "    }\n"
        "}\n"
    )

    findings = JSPerfAnalyzer.analyze(code)
    perf_ids = [f["perf_id"] for f in findings]
    print(f"  Findings: {len(findings)} | IDs: {perf_ids}")

    assert "PERF-JS-001" in perf_ids, \
        f"DOM in loop PERF-JS-001 missing: {perf_ids}"

    ok("DOM query inside loop")


# ---------------------------------------------------------------------------
def test_js_debounce_hint() -> None:
    print("[7] JSPerfAnalyzer - missing debounce")
    from app.core.agents.performance_agent import JSPerfAnalyzer

    code = (
        "const input = document.querySelector('input');\n"
        "input.addEventListener('input', (e) => {\n"
        "    fetchSuggestions(e.target.value);\n"
        "});\n"
    )

    findings = JSPerfAnalyzer.analyze(code)
    perf_ids = [f["perf_id"] for f in findings]
    print(f"  Findings: {len(findings)} | IDs: {perf_ids}")

    assert "PERF-JS-003" in perf_ids, \
        f"Debounce hint PERF-JS-003 missing: {perf_ids}"

    ok("missing debounce hint")


# ---------------------------------------------------------------------------
def test_perf_grade() -> None:
    print("[8] perf_grade function")
    from app.core.agents.performance_agent import perf_grade

    assert "GOOD" in perf_grade(0)
    assert "LOW" in perf_grade(5)
    assert "MEDIUM" in perf_grade(20)
    assert "HIGH" in perf_grade(45)
    assert "CRITICAL" in perf_grade(90)

    print(f"  0->GOOD, 5->LOW, 20->MEDIUM, 45->HIGH, 90->CRITICAL")
    ok("perf_grade")


# ---------------------------------------------------------------------------
def test_agent_instantiation() -> None:
    print("[9] PerformanceAnalyzerAgent instantiation")
    from app.core.agents.performance_agent import PerformanceAnalyzerAgent

    agent = PerformanceAnalyzerAgent()
    print(f"  agent_type   = {agent.agent_type}")
    print(f"  display_name = {agent.display_name}")
    assert agent.agent_type == "performance_analyzer"
    assert "Performance Analyzer" in agent.display_name

    ok("instantiation")


# ---------------------------------------------------------------------------
def test_build_graph() -> None:
    print("[10] _build_graph")
    from app.core.agents.performance_agent import PerformanceAnalyzerAgent

    agent = PerformanceAnalyzerAgent()
    graph = agent._get_graph()
    print(f"  type: {type(graph).__name__}")
    assert graph is not None

    ok("_build_graph")


# ---------------------------------------------------------------------------
def test_format_result() -> None:
    print("[11] _format_result")
    from app.core.agents.performance_agent import PerformanceAnalyzerAgent

    agent = PerformanceAnalyzerAgent()
    mock_state = {
        "config": {
            "language": "python",
            "file_path": "processor.py",
            "_findings": [
                {
                    "perf_id": "PERF-PY-001",
                    "category": "complexity",
                    "impact": "HIGH",
                    "complexity": "O(n^2)",
                    "line_start": 5,
                    "line_end": 10,
                    "title": "Nested Loop",
                    "detail": "Two nested loops",
                    "before_code": "for x in a:\n    for y in b:",
                    "after_code": "lookup = set(b)\nfor x in a:",
                    "speedup": "100x",
                },
                {
                    "perf_id": "PERF-PY-007",
                    "category": "io",
                    "impact": "CRITICAL",
                    "complexity": "O(n) queries",
                    "line_start": 20,
                    "line_end": 25,
                    "title": "N+1 Query",
                    "detail": "DB call in loop",
                    "before_code": "for u in users:\n    u.posts.all()",
                    "after_code": "joinedload(User.posts)",
                    "speedup": "1000x",
                },
            ],
            "_aggregation": {
                "total_score": 60,
                "grade": "HIGH — Significant performance issues",
                "impact_counts": {
                    "CRITICAL": 1, "HIGH": 1, "MEDIUM": 0, "LOW": 0
                },
            },
            "_llm_enhanced": False,
        },
        "llm_response": None,
    }

    result = agent._format_result(mock_state)
    print(f"  keys: {sorted(result.keys())}")
    print(f"  summary: {result['summary']}")

    assert result["total_findings"] == 2
    assert result["perf_score"] == 60
    assert "HIGH" in result["perf_grade"]
    assert len(result["critical_findings"]) == 2
    assert "complexity" in result["categories"]

    ok("_format_result")


# ---------------------------------------------------------------------------
def test_factory_registry() -> None:
    print("[12] factory + registry")
    from app.core.agents import AGENT_REGISTRY
    from app.core.agents.performance_agent import create_performance_analyzer_agent

    agent = create_performance_analyzer_agent()
    assert agent.agent_type == "performance_analyzer"

    assert "performance_analyzer" in AGENT_REGISTRY
    assert AGENT_REGISTRY["performance_analyzer"]["class"] == "PerformanceAnalyzerAgent"
    print(f"  Registry: {list(AGENT_REGISTRY.keys())}")

    ok("factory + registry")


# ---------------------------------------------------------------------------
async def test_full_run_python() -> None:
    print("[13] Full agent run - Python with perf issues (no LLM)")
    from app.core.agents.base_agent import AgentConfig, AgentStatus
    from app.core.agents.performance_agent import PerformanceAnalyzerAgent

    agent = PerformanceAnalyzerAgent(retriever=None, streaming_client=None)

    code = (
        "import time\n"
        "import requests\n\n"
        "def find_duplicates(list_a, list_b):\n"
        "    result = []\n"
        "    for item_a in list_a:\n"
        "        for item_b in list_b:\n"
        "            if item_a == item_b:\n"
        "                result.append(item_a)\n"
        "    return result\n\n"
        "def build_report(items):\n"
        "    report = ''\n"
        "    for item in items:\n"
        "        sorted_items = sorted(items)\n"
        "        report += str(item) + ', '\n"
        "    return report\n\n"
        "def check_status(status):\n"
        "    return status in ['active', 'pending', 'done', 'failed']\n\n"
        "async def fetch(url):\n"
        "    time.sleep(1)\n"
        "    return requests.get(url)\n"
    )

    config = AgentConfig(
        project_id="perf-test-proj",
        user_id="perf-test-user",
        query="Analyze performance bottlenecks",
        model="tinyllama",
        extra={
            "code_content": code,
            "language": "python",
            "file_path": "slow_module.py",
        },
    )

    result = await agent.run(config)

    print(f"  status:     {result.status}")
    print(f"  elapsed_ms: {result.elapsed_ms:.1f}")
    print(f"  error:      {result.error}")

    if result.result:
        r = result.result
        print(f"  total_findings: {r.get('total_findings')}")
        print(f"  perf_grade:     {r.get('perf_grade')}")
        print(f"  impact_counts:  {r.get('impact_counts')}")
        print(f"  summary:        {r.get('summary')}")

    if result.report:
        print(f"  report ({len(result.report)} chars) preview:")
        for line in result.report[:600].splitlines():
            print("    " + line)

    assert result.status == AgentStatus.COMPLETED, \
        f"Expected COMPLETED, got {result.status}. Error: {result.error}"
    assert result.error is None
    assert result.result is not None
    assert result.report is not None
    assert "# Performance Analysis Report" in result.report
    assert result.result["total_findings"] >= 3, \
        f"Expected >= 3 findings, got {result.result['total_findings']}"

    ok("full agent run Python COMPLETED")


# ---------------------------------------------------------------------------
async def test_full_run_clean_code() -> None:
    print("[14] Full agent run - clean efficient Python")
    from app.core.agents.base_agent import AgentConfig, AgentStatus
    from app.core.agents.performance_agent import PerformanceAnalyzerAgent

    agent = PerformanceAnalyzerAgent(retriever=None, streaming_client=None)

    config = AgentConfig(
        project_id="perf-clean-proj",
        user_id="perf-clean-user",
        query="Analyze performance",
        model="tinyllama",
        extra={
            "code_content": (
                "from typing import Optional\n\n"
                "VALID_STATUSES = frozenset(['active', 'pending', 'done'])\n\n"
                "def find_common(set_a: set, set_b: set) -> set:\n"
                '    """O(min(|a|,|b|)) intersection."""\n'
                "    return set_a & set_b\n\n"
                "def build_report(items: list) -> str:\n"
                '    """O(n) string building."""\n'
                "    return ', '.join(str(i) for i in items)\n\n"
                "def is_valid(status: str) -> bool:\n"
                "    return status in VALID_STATUSES\n"
            ),
            "language": "python",
            "file_path": "efficient_module.py",
        },
    )

    result = await agent.run(config)

    print(f"  status: {result.status}")
    if result.result:
        total = result.result.get("total_findings") or 0
        print(f"  findings: {total}")
        print(f"  grade: {result.result.get('perf_grade')}")

    assert result.status == AgentStatus.COMPLETED
    total = (result.result or {}).get("total_findings") or 0
    assert total <= 2, f"Efficient code should have <= 2 findings, got {total}"

    ok(f"clean code: {total} findings")


# ---------------------------------------------------------------------------
async def main() -> None:
    print("=" * 60)
    print("Step 26 - PerformanceAnalyzerAgent Test Suite")
    print("=" * 60)
    print()

    sync_fns = [
        test_nested_loop_detection,
        test_string_concat_in_loop,
        test_list_membership,
        test_sort_in_loop,
        test_sync_in_async,
        test_js_dom_in_loop,
        test_js_debounce_hint,
        test_perf_grade,
        test_agent_instantiation,
        test_build_graph,
        test_format_result,
        test_factory_registry,
    ]
    async_fns = [
        test_full_run_python,
        test_full_run_clean_code,
    ]

    for fn in sync_fns:
        try:
            fn()
        except Exception as exc:
            fail(fn.__name__, exc)
        print()

    for fn in async_fns:
        try:
            await fn()
        except Exception as exc:
            fail(fn.__name__, exc)
        print()

    print("=" * 60)
    print(f"Results: {PASS} passed | {FAIL} failed")
    print("ALL TESTS PASSED" if FAIL == 0 else "SOME TESTS FAILED")
    print("=" * 60)
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
