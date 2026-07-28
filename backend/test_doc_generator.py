"""
Step 21 Test Suite - DocumentationGeneratorAgent
Run from backend/ directory with venv activated:
    cd backend
    python test_doc_generator.py
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
def test_python_parser() -> None:
    print("[1] PythonASTParser")
    from app.core.agents.doc_generator import PythonASTParser
    code = (
        "def add(a: int, b: int) -> int:\n"
        "    return a + b\n\n"
        "async def fetch(url: str) -> dict:\n"
        "    pass\n\n"
        "class Calculator:\n"
        '    """Already has a docstring."""\n\n'
        "    def multiply(self, x, y):\n"
        "        return x * y\n"
    )
    elems = PythonASTParser.parse(code)
    names = [e["name"] for e in elems]
    print(f"  Found: {names}")
    assert "add" in names
    assert "Calculator" in names
    calc = next(e for e in elems if e["name"] == "Calculator")
    assert not calc["needs_doc"], "Calculator should not need doc"
    ok("PythonASTParser")


# ---------------------------------------------------------------------------
def test_js_parser() -> None:
    print("[2] JSParser")
    from app.core.agents.doc_generator import JSParser
    code = (
        "function fetchData(url, options) { return fetch(url, options); }\n\n"
        "const handleClick = (event, target) => { console.log(event); };\n\n"
        "class ApiClient {\n"
        "    constructor(baseUrl) { this.baseUrl = baseUrl; }\n"
        "}\n"
    )
    elems = JSParser.parse(code)
    names = [e["name"] for e in elems]
    print(f"  Found: {names}")
    assert "fetchData" in names
    assert "ApiClient" in names
    assert len(elems) >= 2
    ok("JSParser")


# ---------------------------------------------------------------------------
def test_instantiation() -> None:
    print("[3] Instantiation")
    from app.core.agents.doc_generator import DocumentationGeneratorAgent
    agent = DocumentationGeneratorAgent()
    print(f"  agent_type   = {agent.agent_type}")
    print(f"  display_name = {agent.display_name}")
    assert agent.agent_type == "doc_generator"
    ok("instantiation")


# ---------------------------------------------------------------------------
def test_build_graph() -> None:
    print("[4] _build_graph")
    from app.core.agents.doc_generator import DocumentationGeneratorAgent
    agent = DocumentationGeneratorAgent()
    graph = agent._get_graph()
    print(f"  type: {type(graph).__name__}")
    assert graph is not None
    ok("_build_graph")


# ---------------------------------------------------------------------------
def test_format_result() -> None:
    print("[5] _format_result")
    from app.core.agents.doc_generator import DocumentationGeneratorAgent
    agent = DocumentationGeneratorAgent()
    mock_state = {
        "config": {
            "language": "python",
            "file_path": "calculator.py",
            "_parsed_elements": [
                {"type": "function", "name": "add",        "needs_doc": True,  "args": []},
                {"type": "function", "name": "subtract",   "needs_doc": True,  "args": []},
                {"type": "class",    "name": "Calculator", "needs_doc": False, "args": []},
            ],
        },
        "llm_response": "ELEMENT: add\nDOC:\nAdds two numbers.\n---",
        "analysis_result": None,
    }
    result = agent._format_result(mock_state)
    print(f"  keys: {sorted(result.keys())}")
    print(f"  summary: {result['summary']}")
    assert result["elements_documented"] == 3
    assert result["elements_needing_docs"] == 2
    assert result["coverage_pct"] == 33
    assert result["language"] == "python"
    ok("_format_result")


# ---------------------------------------------------------------------------
def test_fallback_doc() -> None:
    print("[6] _fallback_doc")
    from app.core.agents.doc_generator import DocumentationGeneratorAgent
    agent = DocumentationGeneratorAgent()
    py = agent._fallback_doc(
        {"name": "fn", "type": "function",
         "args": [{"name": "x", "type": "int"}, {"name": "y", "type": "str"}]},
        "python",
    )
    assert "TODO" in py
    print(f"  Python (80): {py[:80]}")
    js = agent._fallback_doc(
        {"name": "fn", "type": "function", "args": [{"name": "url", "type": "string"}]},
        "javascript",
    )
    assert "/**" in js
    print(f"  JS (80): {js[:80]}")
    ok("_fallback_doc")


# ---------------------------------------------------------------------------
def test_factory() -> None:
    print("[7] factory")
    from app.core.agents.doc_generator import create_doc_generator_agent
    agent = create_doc_generator_agent()
    assert agent.agent_type == "doc_generator"
    ok("factory")


# ---------------------------------------------------------------------------
async def test_agent_run() -> None:
    print("[8] Full agent run (no LLM — expects COMPLETED)")
    from app.core.agents.base_agent import AgentConfig, AgentStatus
    from app.core.agents.doc_generator import DocumentationGeneratorAgent

    agent = DocumentationGeneratorAgent(retriever=None, streaming_client=None)

    config = AgentConfig(
        project_id="test-proj-001",
        user_id="test-user-001",
        query="Generate Python documentation",
        model="tinyllama",
        extra={
            # No curly braces in code_content to avoid accidental format issues
            "code_content": (
                "def greet(name):\n"
                "    return 'Hello ' + name\n\n"
                "class Greeter:\n"
                "    def hello(self, name):\n"
                "        print(greet(name))\n"
            ),
            "language": "python",
            "file_path": "greeter.py",
        },
    )

    result = await agent.run(config)

    print(f"  status:     {result.status}")
    print(f"  task_id:    {result.task_id}")
    print(f"  elapsed_ms: {result.elapsed_ms:.1f}")
    print(f"  error:      {result.error}")

    if result.result:
        print(f"  result keys: {list(result.result.keys())}")
        print(f"  summary: {result.result.get('summary', '')}")

    if result.report:
        print(f"  report ({len(result.report)} chars) — first 400:")
        print("  ---")
        for line in result.report[:400].splitlines():
            print("  " + line)
        print("  ---")

    # With no streaming_client, BaseAgent._node_analyze returns a placeholder
    # string (not None) so the workflow completes successfully.
    assert result.status == AgentStatus.COMPLETED, (
        f"Expected COMPLETED, got {result.status}. Error: {result.error}"
    )
    assert result.error is None, f"Expected no error, got: {result.error}"
    assert result.result is not None, "result.result should not be None"
    assert result.report is not None, "result.report should not be None"
    assert "# Documentation Report" in result.report, "Markdown header missing"
    assert result.result["elements_documented"] >= 2, "Expected >= 2 elements"

    ok("full agent run COMPLETED")


# ---------------------------------------------------------------------------
async def main() -> None:
    print("=" * 60)
    print("Step 21 - DocumentationGeneratorAgent Test Suite v4")
    print("=" * 60)
    print()

    for fn in [
        test_python_parser,
        test_js_parser,
        test_instantiation,
        test_build_graph,
        test_format_result,
        test_fallback_doc,
        test_factory,
    ]:
        try:
            fn()
        except Exception as exc:
            fail(fn.__name__, exc)
        print()

    for fn in [test_agent_run]:
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
