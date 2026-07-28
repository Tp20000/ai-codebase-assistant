"""
Step 23 Test Suite - CodeReviewerAgent
Run from backend/ directory with venv activated:
    cd backend
    python test_code_reviewer.py
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
def test_python_analyzer_basic() -> None:
    print("[1] PythonStaticAnalyzer - basic rules")
    from app.core.agents.code_reviewer import PythonStaticAnalyzer

    code = (
        "import os\n"
        "password = 'super_secret_123'\n"
        "def my_func(list, dict, str, int, bool, extra):\n"
        "    try:\n"
        "        pass\n"
        "    except:\n"
        "        pass\n"
        "    print('debug')\n"
        "    return x\n"
        "# TODO: fix this later\n"
        "x = " + "a" * 130 + "\n"
    )

    findings = PythonStaticAnalyzer.analyze(code)
    rule_ids = [f["rule_id"] for f in findings]
    print(f"  Findings: {len(findings)}")
    print(f"  Rules: {rule_ids}")

    assert "PY014" in rule_ids, f"PY014 (credential) missing: {rule_ids}"
    assert "PY002" in rule_ids, f"PY002 (bare except) missing: {rule_ids}"
    assert "PY009" in rule_ids, f"PY009 (too many args) missing: {rule_ids}"
    assert "PY013" in rule_ids, f"PY013 (print) missing: {rule_ids}"
    assert "PY005" in rule_ids, f"PY005 (TODO) missing: {rule_ids}"

    ok("PythonStaticAnalyzer basic rules")


# ---------------------------------------------------------------------------
def test_python_analyzer_clean_code() -> None:
    print("[2] PythonStaticAnalyzer - clean code has few findings")
    from app.core.agents.code_reviewer import PythonStaticAnalyzer

    clean_code = (
        "from typing import Optional\n\n\n"
        "def add_numbers(a: int, b: int) -> int:\n"
        '    """Add two integers and return the result."""\n'
        "    return a + b\n\n\n"
        "def divide(x: float, y: float) -> Optional[float]:\n"
        '    """Divide x by y, returning None if y is zero."""\n'
        "    if y == 0:\n"
        "        return None\n"
        "    return x / y\n"
    )

    findings = PythonStaticAnalyzer.analyze(clean_code)
    severities = [f["severity"] for f in findings]
    critical_high = [s for s in severities if s in ("CRITICAL", "HIGH")]
    print(f"  Findings: {len(findings)} — critical/high: {len(critical_high)}")

    assert len(critical_high) == 0, f"Clean code should have no CRITICAL/HIGH: {findings}"

    ok("PythonStaticAnalyzer clean code")


# ---------------------------------------------------------------------------
def test_js_analyzer() -> None:
    print("[3] JSStaticAnalyzer")
    from app.core.agents.code_reviewer import JSStaticAnalyzer

    code = (
        "var userName = 'test';\n"
        "const apiKey = 'sk-secret-key-12345';\n"
        "function doStuff(x) {\n"
        "    if (x == null) {\n"
        "        console.log('debug output');\n"
        "    }\n"
        "    // TODO: refactor this\n"
        "}\n"
    )

    findings = JSStaticAnalyzer.analyze(code)
    rule_ids = [f["rule_id"] for f in findings]
    print(f"  Findings: {len(findings)}")
    print(f"  Rules: {rule_ids}")

    assert "JS001" in rule_ids, f"JS001 (var) missing: {rule_ids}"
    assert "JS006" in rule_ids, f"JS006 (credential) missing: {rule_ids}"
    assert "JS002" in rule_ids, f"JS002 (loose eq) missing: {rule_ids}"
    assert "JS003" in rule_ids, f"JS003 (console) missing: {rule_ids}"
    assert "JS005" in rule_ids, f"JS005 (TODO) missing: {rule_ids}"

    ok("JSStaticAnalyzer")


# ---------------------------------------------------------------------------
def test_quality_scorer() -> None:
    print("[4] QualityScorer")
    from app.core.agents.code_reviewer import QualityScorer

    # No findings -> perfect score
    result = QualityScorer.score([], total_lines=50)
    print(f"  Empty findings: score={result['score']} grade={result['grade']}")
    assert result["score"] == 100
    assert result["grade"] == "A"

    # Critical finding -> low score
    findings = [
        {"severity": "CRITICAL", "rule_id": "PY014", "line": 1,
         "title": "Credential", "detail": "", "suggestion": ""},
        {"severity": "HIGH", "rule_id": "PY002", "line": 5,
         "title": "Bare except", "detail": "", "suggestion": ""},
        {"severity": "HIGH", "rule_id": "PY015", "line": 10,
         "title": "God function", "detail": "", "suggestion": ""},
    ]
    result2 = QualityScorer.score(findings, total_lines=50)
    print(f"  Bad findings: score={result2['score']} grade={result2['grade']}")
    assert result2["score"] < 80, f"Expected score < 80, got {result2['score']}"
    assert result2["severity_counts"]["CRITICAL"] == 1
    assert result2["severity_counts"]["HIGH"] == 2

    ok("QualityScorer")


# ---------------------------------------------------------------------------
def test_agent_instantiation() -> None:
    print("[5] CodeReviewerAgent instantiation")
    from app.core.agents.code_reviewer import CodeReviewerAgent

    agent = CodeReviewerAgent()
    print(f"  agent_type   = {agent.agent_type}")
    print(f"  display_name = {agent.display_name}")
    assert agent.agent_type == "code_reviewer"
    assert "Code Reviewer" in agent.display_name

    ok("instantiation")


# ---------------------------------------------------------------------------
def test_build_graph() -> None:
    print("[6] _build_graph")
    from app.core.agents.code_reviewer import CodeReviewerAgent

    agent = CodeReviewerAgent()
    graph = agent._get_graph()
    print(f"  type: {type(graph).__name__}")
    assert graph is not None

    ok("_build_graph")


# ---------------------------------------------------------------------------
def test_format_result() -> None:
    print("[7] _format_result")
    from app.core.agents.code_reviewer import CodeReviewerAgent

    agent = CodeReviewerAgent()
    mock_state = {
        "config": {
            "language": "python",
            "file_path": "app.py",
            "_findings": [
                {"rule_id": "PY002", "severity": "HIGH",   "line": 5,
                 "title": "Bare except", "detail": "", "suggestion": ""},
                {"rule_id": "PY014", "severity": "CRITICAL", "line": 2,
                 "title": "Credential", "detail": "", "suggestion": ""},
                {"rule_id": "PY013", "severity": "LOW",    "line": 8,
                 "title": "print()", "detail": "", "suggestion": ""},
            ],
            "_score_data": {
                "score": 62,
                "grade": "D",
                "severity_counts": {"CRITICAL": 1, "HIGH": 1, "MEDIUM": 0, "LOW": 1, "INFO": 0},
                "total_findings": 3,
            },
            "_llm_enhanced": False,
        },
        "llm_response": None,
    }

    result = agent._format_result(mock_state)
    print(f"  keys: {sorted(result.keys())}")
    print(f"  summary: {result['summary']}")

    assert result["total_findings"] == 3
    assert result["quality_score"] == 62
    assert result["grade"] == "D"
    assert result["language"] == "python"
    assert len(result["top_issues"]) <= 5

    ok("_format_result")


# ---------------------------------------------------------------------------
def test_factory_and_registry() -> None:
    print("[8] factory + registry")
    from app.core.agents import AGENT_REGISTRY
    from app.core.agents.code_reviewer import create_code_reviewer_agent

    agent = create_code_reviewer_agent()
    assert agent.agent_type == "code_reviewer"

    assert "code_reviewer" in AGENT_REGISTRY
    assert AGENT_REGISTRY["code_reviewer"]["class"] == "CodeReviewerAgent"
    print(f"  Registry keys: {list(AGENT_REGISTRY.keys())}")

    ok("factory + registry")


# ---------------------------------------------------------------------------
async def test_full_run_python() -> None:
    print("[9] Full agent run - Python (no LLM)")
    from app.core.agents.base_agent import AgentConfig, AgentStatus
    from app.core.agents.code_reviewer import CodeReviewerAgent

    agent = CodeReviewerAgent(retriever=None, streaming_client=None)

    code_with_issues = (
        "password = 'my_secret_password'\n\n"
        "def process(list, dict, str, input, type, extra_arg):\n"
        "    try:\n"
        "        result = list + dict\n"
        "    except:\n"
        "        print('error happened')\n"
        "    # TODO: handle edge cases\n"
        "    x = 42\n"
        "    return x\n"
    )

    config = AgentConfig(
        project_id="test-proj-step23",
        user_id="test-user-step23",
        query="Review this Python code for issues",
        model="tinyllama",
        extra={
            "code_content": code_with_issues,
            "language": "python",
            "file_path": "processor.py",
        },
    )

    result = await agent.run(config)

    print(f"  status:     {result.status}")
    print(f"  elapsed_ms: {result.elapsed_ms:.1f}")
    print(f"  error:      {result.error}")

    if result.result:
        r = result.result
        print(f"  score: {r.get('quality_score')}/100 grade={r.get('grade')}")
        print(f"  findings: {r.get('total_findings')}")
        print(f"  summary: {r.get('summary')}")

    if result.report:
        print(f"  report ({len(result.report)} chars) preview:")
        for line in result.report[:500].splitlines():
            print("    " + line)

    assert result.status == AgentStatus.COMPLETED, \
        f"Expected COMPLETED, got {result.status}. Error: {result.error}"
    assert result.error is None
    assert result.result is not None
    assert result.report is not None
    assert "# Code Review Report" in result.report
    assert result.result["total_findings"] >= 3, \
        f"Expected >= 3 findings, got {result.result['total_findings']}"
    assert result.result["quality_score"] < 90, \
        "Code with issues should score < 90"

    ok("full agent run Python COMPLETED")


# ---------------------------------------------------------------------------
async def test_full_run_js() -> None:
    print("[10] Full agent run - JavaScript (no LLM)")
    from app.core.agents.base_agent import AgentConfig, AgentStatus
    from app.core.agents.code_reviewer import CodeReviewerAgent

    agent = CodeReviewerAgent(retriever=None, streaming_client=None)

    config = AgentConfig(
        project_id="test-proj-step23-js",
        user_id="test-user-step23-js",
        query="Review this JavaScript code",
        model="tinyllama",
        extra={
            "code_content": (
                "var count = 0;\n"
                "const token = 'Bearer abc123secret';\n"
                "function doWork(x) {\n"
                "    if (x == null) {\n"
                "        console.log('null input');\n"
                "    }\n"
                "    // TODO: add validation\n"
                "    return x;\n"
                "}\n"
            ),
            "language": "javascript",
            "file_path": "worker.js",
        },
    )

    result = await agent.run(config)

    print(f"  status:  {result.status}")
    print(f"  error:   {result.error}")
    if result.result:
        print(f"  score:   {result.result.get('quality_score')}")
        print(f"  findings: {result.result.get('total_findings')}")

    assert result.status == AgentStatus.COMPLETED
    assert result.result["total_findings"] >= 3

    ok("full agent run JavaScript COMPLETED")


# ---------------------------------------------------------------------------
async def test_clean_code_high_score() -> None:
    print("[11] Clean code gets high score")
    from app.core.agents.base_agent import AgentConfig, AgentStatus
    from app.core.agents.code_reviewer import CodeReviewerAgent

    agent = CodeReviewerAgent(retriever=None, streaming_client=None)

    config = AgentConfig(
        project_id="test-clean-code",
        user_id="test-user",
        query="Review clean Python code",
        model="tinyllama",
        extra={
            "code_content": (
                "from typing import Optional\n\n\n"
                "def calculate_average(numbers: list[float]) -> Optional[float]:\n"
                '    """Calculate arithmetic mean of a list of numbers.\n\n'
                "    Args:\n"
                "        numbers: List of float values to average\n\n"
                "    Returns:\n"
                "        Mean value or None if list is empty\n"
                '    """\n'
                "    if not numbers:\n"
                "        return None\n"
                "    return sum(numbers) / len(numbers)\n"
            ),
            "language": "python",
            "file_path": "stats.py",
        },
    )

    result = await agent.run(config)

    print(f"  status: {result.status}")
    if result.result:
        print(f"  score: {result.result.get('quality_score')}/100")
        print(f"  grade: {result.result.get('grade')}")

    assert result.status == AgentStatus.COMPLETED
    score = result.result.get("quality_score") or 0
    assert score >= 60, f"Clean code should score >= 60, got {score}"

    ok(f"clean code score: {score}/100")


# ---------------------------------------------------------------------------
async def main() -> None:
    print("=" * 60)
    print("Step 23 - CodeReviewerAgent Test Suite")
    print("=" * 60)
    print()

    sync_fns = [
        test_python_analyzer_basic,
        test_python_analyzer_clean_code,
        test_js_analyzer,
        test_quality_scorer,
        test_agent_instantiation,
        test_build_graph,
        test_format_result,
        test_factory_and_registry,
    ]
    async_fns = [
        test_full_run_python,
        test_full_run_js,
        test_clean_code_high_score,
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
