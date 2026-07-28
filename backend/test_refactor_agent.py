"""
Step 25 Test Suite - RefactorSuggesterAgent
Run from backend/ directory with venv activated:
    cd backend
    python test_refactor_agent.py
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
def test_duplicate_detector() -> None:
    print("[1] DuplicateCodeDetector")
    from app.core.agents.refactor_agent import DuplicateCodeDetector

    # Code with a clear duplicate block
    code = (
        "def process_a(data):\n"
        "    result = []\n"
        "    for item in data:\n"
        "        if item > 0:\n"
        "            result.append(item * 2)\n"
        "    return result\n\n"
        "def process_b(data):\n"
        "    result = []\n"
        "    for item in data:\n"
        "        if item > 0:\n"
        "            result.append(item * 2)\n"
        "    return result\n"
    )

    dupes = DuplicateCodeDetector.find_duplicates(code)
    print(f"  Found {len(dupes)} duplicate groups")

    # Should find the duplicate block
    assert len(dupes) >= 1, f"Expected >= 1 duplicate, got {len(dupes)}"
    print(f"  First dupe: lines {dupes[0]['line_start_a']}-{dupes[0]['line_end_a']}"
          f" and {dupes[0]['line_start_b']}-{dupes[0]['line_end_b']}")

    ok("DuplicateCodeDetector")


# ---------------------------------------------------------------------------
def test_python_god_function() -> None:
    print("[2] PythonRefactorAnalyzer - God Function")
    from app.core.agents.refactor_agent import PythonRefactorAnalyzer

    # 50+ line function
    body_lines = "\n".join(
        "    x_" + str(i) + " = i * " + str(i) + "\n"
        "    if x_" + str(i) + " > 10:\n"
        "        pass"
        for i in range(20)
    )
    code = "def giant_function(a, b, c, d, e, f):\n" + body_lines + "\n    return a\n"

    suggestions = PythonRefactorAnalyzer.analyze(code)
    principles = [s["principle"] for s in suggestions]
    ref_ids = [s["refactor_id"] for s in suggestions]

    print(f"  Suggestions: {len(suggestions)}")
    print(f"  Principles: {set(principles)}")
    print(f"  IDs: {ref_ids}")

    # Should find god function AND long param list
    assert "SOLID-S" in principles, f"Expected SOLID-S: {principles}"
    assert "REF-PY-003" in ref_ids or "REF-PY-001" in ref_ids, \
        f"Expected god function or param list: {ref_ids}"

    ok("PythonRefactorAnalyzer God Function")


# ---------------------------------------------------------------------------
def test_python_god_class() -> None:
    print("[3] PythonRefactorAnalyzer - God Class")
    from app.core.agents.refactor_agent import PythonRefactorAnalyzer

    # Class with many methods
    methods = "\n".join(
        "    def method_" + str(i) + "(self):\n        return " + str(i)
        for i in range(12)
    )
    code = "class BigClass:\n" + methods + "\n"

    suggestions = PythonRefactorAnalyzer.analyze(code)
    ref_ids = [s["refactor_id"] for s in suggestions]
    print(f"  Suggestions: {len(suggestions)} | IDs: {ref_ids}")

    assert "REF-PY-002" in ref_ids, f"God class REF-PY-002 not found: {ref_ids}"

    ok("PythonRefactorAnalyzer God Class")


# ---------------------------------------------------------------------------
def test_python_dependency_injection() -> None:
    print("[4] PythonRefactorAnalyzer - Dependency Inversion")
    from app.core.agents.refactor_agent import PythonRefactorAnalyzer

    code = (
        "class UserService:\n"
        "    def __init__(self):\n"
        "        self.db = DatabaseClient()\n"
        "        self.cache = RedisCache()\n\n"
        "    def get_user(self, user_id):\n"
        "        return self.db.find(user_id)\n"
    )

    suggestions = PythonRefactorAnalyzer.analyze(code)
    ref_ids = [s["refactor_id"] for s in suggestions]
    principles = [s["principle"] for s in suggestions]
    print(f"  Suggestions: {len(suggestions)} | IDs: {ref_ids}")

    assert "SOLID-D" in principles, f"Expected SOLID-D: {principles}"
    assert "REF-PY-DI" in ref_ids, f"Expected REF-PY-DI: {ref_ids}"

    ok("PythonRefactorAnalyzer Dependency Injection")


# ---------------------------------------------------------------------------
def test_js_refactor_analyzer() -> None:
    print("[5] JSRefactorAnalyzer")
    from app.core.agents.refactor_agent import JSRefactorAnalyzer

    code = (
        "var count = 0;\n"
        "var total = 0;\n\n"
        "function process(type) {\n"
        "    if (type === 'A') { doA(); }\n"
        "    else if (type === 'B') { doB(); }\n"
        "    else if (type === 'C') { doC(); }\n"
        "    else if (type === 'D') { doD(); }\n"
        "}\n\n"
        "function nested(data) {\n"
        "    doWork(data, function(result) {\n"
        "        transform(result, function(final) {\n"
        "            console.log(final);\n"
        "        });\n"
        "    });\n"
        "}\n"
    )

    suggestions = JSRefactorAnalyzer.analyze(code)
    ref_ids = [s["refactor_id"] for s in suggestions]
    print(f"  Suggestions: {len(suggestions)} | IDs: {ref_ids}")

    assert "REF-JS-002" in ref_ids, f"var detection missing: {ref_ids}"
    assert "REF-JS-006" in ref_ids, f"if-else chain missing: {ref_ids}"
    assert "REF-JS-003" in ref_ids, f"callback hell missing: {ref_ids}"

    ok("JSRefactorAnalyzer")


# ---------------------------------------------------------------------------
def test_cyclomatic_complexity() -> None:
    print("[6] Cyclomatic complexity calculation")
    from app.core.agents.refactor_agent import PythonRefactorAnalyzer
    import ast

    simple_code = "def simple(x):\n    return x + 1\n"
    complex_code = (
        "def complex(x, y, z):\n"
        "    if x:\n"
        "        if y:\n"
        "            for i in range(10):\n"
        "                if z or x:\n"
        "                    pass\n"
        "    return x\n"
    )

    simple_tree = ast.parse(simple_code)
    complex_tree = ast.parse(complex_code)

    simple_func = next(n for n in ast.walk(simple_tree)
                       if isinstance(n, ast.FunctionDef))
    complex_func = next(n for n in ast.walk(complex_tree)
                        if isinstance(n, ast.FunctionDef))

    simple_cc = PythonRefactorAnalyzer._cyclomatic_complexity(simple_func)
    complex_cc = PythonRefactorAnalyzer._cyclomatic_complexity(complex_func)

    print(f"  simple CC={simple_cc}, complex CC={complex_cc}")
    assert simple_cc <= 2, f"Simple should be <= 2, got {simple_cc}"
    assert complex_cc > simple_cc, "Complex should have higher CC"

    ok("cyclomatic complexity")


# ---------------------------------------------------------------------------
def test_agent_instantiation() -> None:
    print("[7] RefactorSuggesterAgent instantiation")
    from app.core.agents.refactor_agent import RefactorSuggesterAgent

    agent = RefactorSuggesterAgent()
    print(f"  agent_type   = {agent.agent_type}")
    print(f"  display_name = {agent.display_name}")
    assert agent.agent_type == "refactor_suggester"
    assert "Refactor Suggester" in agent.display_name

    ok("instantiation")


# ---------------------------------------------------------------------------
def test_build_graph() -> None:
    print("[8] _build_graph")
    from app.core.agents.refactor_agent import RefactorSuggesterAgent

    agent = RefactorSuggesterAgent()
    graph = agent._get_graph()
    print(f"  type: {type(graph).__name__}")
    assert graph is not None

    ok("_build_graph")


# ---------------------------------------------------------------------------
def test_format_result() -> None:
    print("[9] _format_result")
    from app.core.agents.refactor_agent import RefactorSuggesterAgent

    agent = RefactorSuggesterAgent()
    mock_state = {
        "config": {
            "language": "python",
            "file_path": "service.py",
            "_suggestions": [
                {
                    "refactor_id": "REF-PY-001",
                    "principle": "SOLID-S",
                    "severity": "HIGH",
                    "line_start": 10,
                    "title": "God Function",
                    "problem": "Too long",
                    "before_code": "def big(): ...",
                    "after_code": "def small(): ...",
                    "benefit": "Easier to test",
                },
                {
                    "refactor_id": "REF-PY-006",
                    "principle": "DRY",
                    "severity": "HIGH",
                    "line_start": 50,
                    "title": "Duplicate Code",
                    "problem": "Appears twice",
                    "before_code": "# duplicated",
                    "after_code": "def extracted(): ...",
                    "benefit": "Single source of truth",
                },
                {
                    "refactor_id": "REF-PY-004",
                    "principle": "NAMING",
                    "severity": "LOW",
                    "line_start": 5,
                    "title": "Magic Number",
                    "problem": "42 unexplained",
                    "before_code": "x = 42",
                    "after_code": "MAX_SIZE = 42\nx = MAX_SIZE",
                    "benefit": "Self-documenting",
                },
            ],
            "_llm_enhanced": False,
        },
        "llm_response": None,
    }

    result = agent._format_result(mock_state)
    print(f"  keys: {sorted(result.keys())}")
    print(f"  summary: {result['summary']}")

    assert result["total_suggestions"] == 3
    assert result["by_principle"]["SOLID-S"] == 1
    assert result["by_principle"]["DRY"] == 1
    assert result["by_severity"]["HIGH"] == 2
    assert result["by_severity"]["LOW"] == 1

    ok("_format_result")


# ---------------------------------------------------------------------------
def test_factory_registry() -> None:
    print("[10] factory + registry")
    from app.core.agents import AGENT_REGISTRY
    from app.core.agents.refactor_agent import create_refactor_suggester_agent

    agent = create_refactor_suggester_agent()
    assert agent.agent_type == "refactor_suggester"

    assert "refactor_suggester" in AGENT_REGISTRY
    assert AGENT_REGISTRY["refactor_suggester"]["class"] == "RefactorSuggesterAgent"
    print(f"  Registry: {list(AGENT_REGISTRY.keys())}")

    ok("factory + registry")


# ---------------------------------------------------------------------------
async def test_full_run_python() -> None:
    print("[11] Full agent run - Python (no LLM)")
    from app.core.agents.base_agent import AgentConfig, AgentStatus
    from app.core.agents.refactor_agent import RefactorSuggesterAgent

    agent = RefactorSuggesterAgent(retriever=None, streaming_client=None)

    # Code with multiple refactor opportunities
    methods_body = "\n".join(
        "    def method_" + str(i) + "(self):\n"
        "        return self.value * " + str(i)
        for i in range(12)
    )

    code = (
        "class DataProcessor:\n"
        "    def __init__(self):\n"
        "        self.db = DatabaseClient()\n"
        "        self.value = 0\n\n"
        + methods_body + "\n\n"
        "def process_items(items, flag, mode, limit, offset, sort_key):\n"
        "    result = []\n"
        "    for i in items:\n"
        "        if flag:\n"
        "            if i > 0:\n"
        "                if i < limit:\n"
        "                    result.append(i)\n"
        "    return result\n"
    )

    config = AgentConfig(
        project_id="refactor-test-proj",
        user_id="refactor-test-user",
        query="Suggest refactoring improvements",
        model="tinyllama",
        extra={
            "code_content": code,
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
        print(f"  total_suggestions: {r.get('total_suggestions')}")
        print(f"  by_principle: {r.get('by_principle')}")
        print(f"  by_severity: {r.get('by_severity')}")
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
    assert "# Refactor Suggestions Report" in result.report
    assert result.result["total_suggestions"] >= 2, \
        f"Expected >= 2 suggestions, got {result.result['total_suggestions']}"

    ok("full agent run Python COMPLETED")


# ---------------------------------------------------------------------------
async def test_full_run_js() -> None:
    print("[12] Full agent run - JavaScript (no LLM)")
    from app.core.agents.base_agent import AgentConfig, AgentStatus
    from app.core.agents.refactor_agent import RefactorSuggesterAgent

    agent = RefactorSuggesterAgent(retriever=None, streaming_client=None)

    config = AgentConfig(
        project_id="refactor-js-proj",
        user_id="refactor-js-user",
        query="Suggest JavaScript refactoring",
        model="tinyllama",
        extra={
            "code_content": (
                "var userName = '';\n"
                "var userAge = 0;\n\n"
                "function getUser(type) {\n"
                "    if (type === 'admin') { return getAdmin(); }\n"
                "    else if (type === 'user') { return getRegular(); }\n"
                "    else if (type === 'guest') { return getGuest(); }\n"
                "    else if (type === 'mod') { return getMod(); }\n"
                "}\n\n"
                "function processData(data: any): any {\n"
                "    return data;\n"
                "}\n"
                "function transformData(data: any): any {\n"
                "    return data;\n"
                "}\n"
            ),
            "language": "javascript",
            "file_path": "userService.js",
        },
    )

    result = await agent.run(config)

    print(f"  status: {result.status}")
    print(f"  error:  {result.error}")
    if result.result:
        print(f"  suggestions: {result.result.get('total_suggestions')}")
        print(f"  principles:  {result.result.get('by_principle')}")

    assert result.status == AgentStatus.COMPLETED
    assert result.result["total_suggestions"] >= 2

    ok("full agent run JavaScript COMPLETED")


# ---------------------------------------------------------------------------
async def test_clean_code_few_suggestions() -> None:
    print("[13] Clean code has few suggestions")
    from app.core.agents.base_agent import AgentConfig, AgentStatus
    from app.core.agents.refactor_agent import RefactorSuggesterAgent

    agent = RefactorSuggesterAgent(retriever=None, streaming_client=None)

    config = AgentConfig(
        project_id="refactor-clean",
        user_id="test-user",
        query="Refactor analysis",
        model="tinyllama",
        extra={
            "code_content": (
                "from typing import Optional\n\n\n"
                "MAX_RETRIES = 3\n"
                "TIMEOUT_SECONDS = 30\n\n\n"
                "def calculate_average(numbers: list[float]) -> Optional[float]:\n"
                '    """Calculate mean of a number list."""\n'
                "    if not numbers:\n"
                "        return None\n"
                "    return sum(numbers) / len(numbers)\n\n\n"
                "def validate_email(email: str) -> bool:\n"
                '    """Return True if email format is valid."""\n'
                "    return '@' in email and '.' in email\n"
            ),
            "language": "python",
            "file_path": "utils.py",
        },
    )

    result = await agent.run(config)
    print(f"  status: {result.status}")
    if result.result:
        total = result.result.get("total_suggestions") or 0
        print(f"  total_suggestions: {total}")
        assert total <= 3, f"Clean code should have <= 3 suggestions, got {total}"

    assert result.status == AgentStatus.COMPLETED

    ok("clean code has few suggestions")


# ---------------------------------------------------------------------------
async def main() -> None:
    print("=" * 60)
    print("Step 25 - RefactorSuggesterAgent Test Suite")
    print("=" * 60)
    print()

    sync_fns = [
        test_duplicate_detector,
        test_python_god_function,
        test_python_god_class,
        test_python_dependency_injection,
        test_js_refactor_analyzer,
        test_cyclomatic_complexity,
        test_agent_instantiation,
        test_build_graph,
        test_format_result,
        test_factory_registry,
    ]
    async_fns = [
        test_full_run_python,
        test_full_run_js,
        test_clean_code_few_suggestions,
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
