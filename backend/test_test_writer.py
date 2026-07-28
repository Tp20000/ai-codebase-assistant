"""
Step 22 Test Suite - TestWriterAgent
Run from backend/ directory with venv activated:
    cd backend
    python test_test_writer.py
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
def test_python_testability_analyzer() -> None:
    print("[1] TestabilityAnalyzer - Python")
    from app.core.agents.test_writer import TestabilityAnalyzer

    code = (
        "def add(a: int, b: int) -> int:\n"
        "    return a + b\n\n"
        "def divide(x: float, y: float) -> float:\n"
        "    if y == 0:\n"
        "        raise ValueError('Division by zero')\n"
        "    return x / y\n\n"
        "async def fetch_user(user_id: str) -> dict:\n"
        "    pass\n\n"
        "class Calculator:\n"
        "    def __init__(self, precision: int = 2):\n"
        "        self.precision = precision\n\n"
        "    def multiply(self, x, y):\n"
        "        return x * y\n"
    )

    targets = TestabilityAnalyzer.analyze_python(code)
    names = [t["name"] for t in targets]
    print(f"  Found targets: {names}")

    assert "add" in names,        f"add missing: {names}"
    assert "divide" in names,     f"divide missing: {names}"
    assert "Calculator" in names, f"Calculator missing: {names}"

    divide_t = next(t for t in targets if t["name"] == "divide")
    assert divide_t["has_conditions"],    "divide should have conditions"
    assert divide_t["raises_exceptions"], "divide should raise exceptions"

    fetch_t = next(t for t in targets if t["name"] == "fetch_user")
    assert fetch_t["is_async"], "fetch_user should be async"

    ok("TestabilityAnalyzer Python")


# ---------------------------------------------------------------------------
def test_js_testability_analyzer() -> None:
    print("[2] TestabilityAnalyzer - JavaScript")
    from app.core.agents.test_writer import TestabilityAnalyzer

    code = (
        "function fetchData(url, options) {\n"
        "    if (!url) throw new Error('URL required');\n"
        "    return fetch(url, options);\n"
        "}\n\n"
        "const formatName = (first, last) => first + ' ' + last;\n\n"
        "class UserService {\n"
        "    constructor(apiClient) { this.api = apiClient; }\n"
        "    getUser(id) { return this.api.get(id); }\n"
        "}\n"
    )

    targets = TestabilityAnalyzer.analyze_js(code)
    names = [t["name"] for t in targets]
    print(f"  Found targets: {names}")

    assert "fetchData" in names,    f"fetchData missing: {names}"
    assert "UserService" in names,  f"UserService missing: {names}"
    assert len(targets) >= 2

    ok("TestabilityAnalyzer JS")


# ---------------------------------------------------------------------------
def test_python_template_generator() -> None:
    print("[3] TestTemplateGenerator - Python")
    from app.core.agents.test_writer import TestabilityAnalyzer, TestTemplateGenerator

    code = (
        "def add(a: int, b: int) -> int:\n"
        "    return a + b\n\n"
        "def divide(x: float, y: float) -> float:\n"
        "    if y == 0:\n"
        "        raise ValueError('zero')\n"
        "    return x / y\n\n"
        "class Calculator:\n"
        "    def __init__(self):\n"
        "        pass\n"
        "    def multiply(self, x, y):\n"
        "        return x * y\n"
    )

    targets = TestabilityAnalyzer.analyze_python(code)
    result = TestTemplateGenerator.python_tests(targets, "mymodule")

    print(f"  Generated {len(result)} chars of test code")
    print(f"  First 200 chars:\n  {result[:200]}")

    assert "import pytest" in result,      "Missing pytest import"
    assert "def test_" in result,          "Missing test functions"
    assert "def test_add" in result,       "Missing test_add"
    assert "def test_divide" in result,    "Missing test_divide"
    assert "TestCalculator" in result or "class Test" in result, \
        "Missing Calculator test class"

    ok("TestTemplateGenerator Python")


# ---------------------------------------------------------------------------
def test_jest_template_generator() -> None:
    print("[4] TestTemplateGenerator - Jest")
    from app.core.agents.test_writer import TestabilityAnalyzer, TestTemplateGenerator

    code = (
        "function fetchData(url, options) { return fetch(url, options); }\n\n"
        "class ApiClient {\n"
        "    constructor(base) { this.base = base; }\n"
        "    get(path) { return fetch(this.base + path); }\n"
        "}\n"
    )

    targets = TestabilityAnalyzer.analyze_js(code)
    result = TestTemplateGenerator.jest_tests(targets, "apiClient")

    print(f"  Generated {len(result)} chars of test code")
    print(f"  First 200 chars:\n  {result[:200]}")

    assert "describe(" in result,    "Missing describe blocks"
    assert "it(" in result,          "Missing it() tests"
    assert "expect(" in result,      "Missing expect assertions"
    assert "fetchData" in result,    "Missing fetchData test"

    ok("TestTemplateGenerator Jest")


# ---------------------------------------------------------------------------
def test_agent_instantiation() -> None:
    print("[5] TestWriterAgent instantiation")
    from app.core.agents.test_writer import TestWriterAgent

    agent = TestWriterAgent()
    print(f"  agent_type   = {agent.agent_type}")
    print(f"  display_name = {agent.display_name}")
    assert agent.agent_type == "test_writer"
    assert "Test Writer" in agent.display_name

    ok("instantiation")


# ---------------------------------------------------------------------------
def test_build_graph() -> None:
    print("[6] _build_graph")
    from app.core.agents.test_writer import TestWriterAgent

    agent = TestWriterAgent()
    graph = agent._get_graph()
    print(f"  graph type: {type(graph).__name__}")
    assert graph is not None
    assert "CompiledState" in type(graph).__name__ or "Compiled" in type(graph).__name__

    ok("_build_graph")


# ---------------------------------------------------------------------------
def test_format_result() -> None:
    print("[7] _format_result")
    from app.core.agents.test_writer import TestWriterAgent

    agent = TestWriterAgent()
    mock_state = {
        "config": {
            "language": "python",
            "file_path": "calculator.py",
            "test_framework": "pytest",
            "_resolved_framework": "pytest",
            "_test_targets": [
                {"name": "add",        "type": "function", "args": []},
                {"name": "divide",     "type": "function", "args": []},
                {"name": "Calculator", "type": "class",    "args": []},
            ],
            "_generated_tests": "def test_add(): pass\n",
            "_llm_enhanced": False,
        },
        "llm_response": None,
        "analysis_result": None,
    }

    result = agent._format_result(mock_state)
    print(f"  keys: {sorted(result.keys())}")
    print(f"  summary: {result['summary']}")

    assert result["targets_found"] == 3
    assert result["framework"] == "pytest"
    assert result["language"] == "python"
    assert result["test_file_name"] == "test_calculator.py"
    assert "add" in result["target_names"]

    ok("_format_result")


# ---------------------------------------------------------------------------
def test_factory() -> None:
    print("[8] factory function")
    from app.core.agents.test_writer import create_test_writer_agent

    agent = create_test_writer_agent()
    assert agent.agent_type == "test_writer"
    ok("factory")


# ---------------------------------------------------------------------------
def test_registry() -> None:
    print("[9] AGENT_REGISTRY contains test_writer")
    from app.core.agents import AGENT_REGISTRY

    assert "test_writer" in AGENT_REGISTRY, \
        f"test_writer not in registry: {list(AGENT_REGISTRY.keys())}"
    assert AGENT_REGISTRY["test_writer"]["class"] == "TestWriterAgent"
    print(f"  Registry: {list(AGENT_REGISTRY.keys())}")

    ok("AGENT_REGISTRY")


# ---------------------------------------------------------------------------
async def test_full_agent_run_python() -> None:
    print("[10] Full agent run - Python pytest (no LLM)")
    from app.core.agents.base_agent import AgentConfig, AgentStatus
    from app.core.agents.test_writer import TestWriterAgent

    agent = TestWriterAgent(retriever=None, streaming_client=None)

    config = AgentConfig(
        project_id="test-proj-step22",
        user_id="test-user-step22",
        query="Generate pytest tests for this Python module",
        model="tinyllama",
        extra={
            "code_content": (
                "def add(a: int, b: int) -> int:\n"
                "    return a + b\n\n"
                "def divide(x: float, y: float) -> float:\n"
                "    if y == 0:\n"
                "        raise ValueError('Division by zero')\n"
                "    return x / y\n\n"
                "class Calculator:\n"
                "    def __init__(self):\n"
                "        self.history = []\n\n"
                "    def multiply(self, x, y):\n"
                "        result = x * y\n"
                "        self.history.append(result)\n"
                "        return result\n"
            ),
            "language": "python",
            "file_path": "calculator.py",
            "test_framework": "pytest",
        },
    )

    result = await agent.run(config)

    print(f"  status:     {result.status}")
    print(f"  task_id:    {result.task_id}")
    print(f"  elapsed_ms: {result.elapsed_ms:.1f}")
    print(f"  error:      {result.error}")

    if result.result:
        print(f"  result summary: {result.result.get('summary', '')}")
        print(f"  test_file_name: {result.result.get('test_file_name', '')}")
        print(f"  targets_found:  {result.result.get('targets_found', 0)}")

    if result.report:
        print(f"  report ({len(result.report)} chars) preview:")
        for line in result.report[:600].splitlines():
            print("    " + line)

    assert result.status == AgentStatus.COMPLETED, \
        f"Expected COMPLETED, got {result.status}. Error: {result.error}"
    assert result.error is None
    assert result.result is not None
    assert result.report is not None
    assert "# Test Suite Report" in result.report
    assert result.result["framework"] == "pytest"
    assert result.result["targets_found"] >= 2
    assert "test_calculator.py" in result.report

    ok("full agent run Python pytest COMPLETED")


# ---------------------------------------------------------------------------
async def test_full_agent_run_js() -> None:
    print("[11] Full agent run - JavaScript Jest (no LLM)")
    from app.core.agents.base_agent import AgentConfig, AgentStatus
    from app.core.agents.test_writer import TestWriterAgent

    agent = TestWriterAgent(retriever=None, streaming_client=None)

    config = AgentConfig(
        project_id="test-proj-step22-js",
        user_id="test-user-step22-js",
        query="Generate Jest tests for this JavaScript module",
        model="tinyllama",
        extra={
            "code_content": (
                "function fetchUser(userId) {\n"
                "    if (!userId) throw new Error('userId required');\n"
                "    return fetch('/api/users/' + userId);\n"
                "}\n\n"
                "const formatFullName = (first, last) => first + ' ' + last;\n\n"
                "class UserService {\n"
                "    constructor(apiClient) { this.api = apiClient; }\n"
                "    getUser(id) { return this.api.get('/users/' + id); }\n"
                "}\n"
            ),
            "language": "javascript",
            "file_path": "userService.js",
            "test_framework": "jest",
        },
    )

    result = await agent.run(config)

    print(f"  status:     {result.status}")
    print(f"  error:      {result.error}")
    if result.result:
        print(f"  summary: {result.result.get('summary', '')}")

    assert result.status == AgentStatus.COMPLETED, \
        f"Expected COMPLETED, got {result.status}. Error: {result.error}"
    assert result.result["framework"] == "jest"
    assert "userService.test.ts" in result.report or "userService" in result.report

    ok("full agent run JavaScript Jest COMPLETED")


# ---------------------------------------------------------------------------
async def main() -> None:
    print("=" * 60)
    print("Step 22 - TestWriterAgent Test Suite")
    print("=" * 60)
    print()

    sync_fns = [
        test_python_testability_analyzer,
        test_js_testability_analyzer,
        test_python_template_generator,
        test_jest_template_generator,
        test_agent_instantiation,
        test_build_graph,
        test_format_result,
        test_factory,
        test_registry,
    ]
    async_fns = [
        test_full_agent_run_python,
        test_full_agent_run_js,
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
