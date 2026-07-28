"""
Test Writer Agent - Step 22
AI Codebase Assistant v2.0

Analyzes uploaded code and generates production-quality test suites:
    - Python  -> pytest unit tests with fixtures, parametrize, edge cases
    - JS/TS   -> Jest unit tests with describe/it blocks, mocks, edge cases
    - Generic -> Framework-agnostic test stubs

Correctly extends BaseAgent (same pattern as doc_generator.py - Step 21):
    BaseAgent.__init__(retriever=None, streaming_client=None)
    Abstract property:  agent_type -> str
    Abstract method:    _build_graph() -> compiled StateGraph
    Abstract method:    _format_result(state: AgentState) -> dict

    run() accepts AgentConfig
    AgentConfig.extra carries: code_content, language, file_path, test_framework
    CRITICAL: user_prompt_template uses ONLY {context} {query} {project_id}
              ALL other dynamic content pre-rendered as plain strings

LangGraph workflow:
    validate -> retrieve -> parse_code -> analyze_testability
             -> generate_tests -> fmt -> done -> END
"""

from __future__ import annotations

import ast
import logging
import re
from datetime import datetime, timezone
from typing import Any

from langgraph.graph import END, StateGraph

from app.core.agents.base_agent import (
    AgentConfig,
    AgentState,
    AgentStatus,
    BaseAgent,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Testability Analyzer - extracts what needs testing
# =============================================================================

class TestabilityAnalyzer:
    """
    Analyzes parsed code elements and determines what tests to generate.

    For each function/method/class produces a TestTarget describing:
    - function signature and arguments
    - return type for assertion planning
    - complexity hints (conditions, loops) for edge case generation
    - whether it is a pure function, method, or class
    """

    @staticmethod
    def analyze_python(source: str) -> list[dict[str, Any]]:
        """
        Parse Python source with ast and extract testable elements.

        Args:
            source: Raw Python source code

        Returns:
            List of test target dicts, each with keys:
                name, type, args, return_type, is_async,
                has_conditions, has_loops, raises_exceptions,
                existing_tests, class_name, complexity_score
        """
        targets: list[dict[str, Any]] = []

        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            logger.warning("[TestWriter] Python AST error: %s", exc)
            return targets

        # Track current class context
        class_map: dict[int, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for child in ast.walk(node):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        class_map[id(child)] = node.name

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                targets.append(TestabilityAnalyzer._class_target(node))

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Skip private/dunder methods from top-level scan
                # (they are captured inside class targets)
                if node.name.startswith("__") and node.name != "__init__":
                    continue
                targets.append(
                    TestabilityAnalyzer._function_target(node, class_map.get(id(node)))
                )

        return targets

    @staticmethod
    def _function_target(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        class_name: str | None,
    ) -> dict[str, Any]:
        """
        Build a test target dict from a function AST node.

        Args:
            node:       AST FunctionDef or AsyncFunctionDef
            class_name: Parent class name if method, else None

        Returns:
            Test target dict
        """
        args_info: list[dict[str, str]] = []
        for arg in node.args.args:
            if arg.arg == "self":
                continue
            arg_type = "Any"
            if arg.annotation:
                try:
                    arg_type = ast.unparse(arg.annotation)
                except Exception:
                    pass
            args_info.append({"name": arg.arg, "type": arg_type})

        return_type = "None"
        if node.returns:
            try:
                return_type = ast.unparse(node.returns)
            except Exception:
                return_type = "Any"

        # Scan body for complexity signals
        has_conditions = any(
            isinstance(n, (ast.If, ast.IfExp)) for n in ast.walk(node)
        )
        has_loops = any(
            isinstance(n, (ast.For, ast.While)) for n in ast.walk(node)
        )
        raises_exceptions = any(
            isinstance(n, ast.Raise) for n in ast.walk(node)
        )
        has_try = any(
            isinstance(n, ast.Try) for n in ast.walk(node)
        )

        complexity = sum([
            1,
            2 if has_conditions else 0,
            1 if has_loops else 0,
            1 if raises_exceptions else 0,
            1 if has_try else 0,
        ])

        return {
            "name": node.name,
            "type": "method" if class_name else "function",
            "class_name": class_name,
            "is_async": isinstance(node, ast.AsyncFunctionDef),
            "args": args_info,
            "return_type": return_type,
            "has_conditions": has_conditions,
            "has_loops": has_loops,
            "raises_exceptions": raises_exceptions,
            "has_try": has_try,
            "complexity_score": complexity,
            "line_number": node.lineno,
        }

    @staticmethod
    def _class_target(node: ast.ClassDef) -> dict[str, Any]:
        """
        Build a test target dict for a class (instantiation + method tests).

        Args:
            node: AST ClassDef node

        Returns:
            Class test target dict
        """
        bases: list[str] = []
        for base in node.bases:
            try:
                bases.append(ast.unparse(base))
            except Exception:
                bases.append("object")

        methods: list[str] = [
            item.name
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not item.name.startswith("__")
        ]

        has_init = any(
            isinstance(item, ast.FunctionDef) and item.name == "__init__"
            for item in node.body
        )

        init_args: list[dict[str, str]] = []
        if has_init:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    for arg in item.args.args:
                        if arg.arg == "self":
                            continue
                        arg_type = "Any"
                        if arg.annotation:
                            try:
                                arg_type = ast.unparse(arg.annotation)
                            except Exception:
                                pass
                        init_args.append({"name": arg.arg, "type": arg_type})

        return {
            "name": node.name,
            "type": "class",
            "class_name": None,
            "bases": bases,
            "methods": methods,
            "has_init": has_init,
            "init_args": init_args,
            "line_number": node.lineno,
            "complexity_score": len(methods) + 1,
        }

    @staticmethod
    def analyze_js(source: str) -> list[dict[str, Any]]:
        """
        Extract testable elements from JavaScript/TypeScript via regex.

        Args:
            source: Raw JS or TS source code

        Returns:
            List of test target dicts
        """
        targets: list[dict[str, Any]] = []

        func_pat = re.compile(
            r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)",
            re.MULTILINE,
        )
        arrow_pat = re.compile(
            r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*"
            r"(?:async\s+)?\(([^)]*)\)\s*(?::\s*[\w<>[\]|]+)?\s*=>",
            re.MULTILINE,
        )
        class_pat = re.compile(
            r"(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?",
            re.MULTILINE,
        )

        for match in func_pat.finditer(source):
            name = match.group(1)
            args_raw = match.group(2)
            args = [
                {"name": a.split(":")[0].strip(), "type": "any"}
                for a in args_raw.split(",")
                if a.strip()
            ]
            is_async = "async" in source[max(0, match.start()-10):match.start()]
            targets.append({
                "name": name,
                "type": "function",
                "class_name": None,
                "is_async": is_async,
                "args": args,
                "return_type": "any",
                "has_conditions": bool(re.search(r"\bif\b|\bswitch\b", source[match.start():match.start()+500])),
                "has_loops": bool(re.search(r"\bfor\b|\bwhile\b", source[match.start():match.start()+500])),
                "raises_exceptions": bool(re.search(r"\bthrow\b", source[match.start():match.start()+500])),
                "complexity_score": 2,
                "line_number": source[:match.start()].count("\n") + 1,
            })

        for match in arrow_pat.finditer(source):
            name = match.group(1)
            args_raw = match.group(2)
            args = [
                {"name": a.split(":")[0].strip(), "type": "any"}
                for a in args_raw.split(",")
                if a.strip()
            ]
            targets.append({
                "name": name,
                "type": "arrow_function",
                "class_name": None,
                "is_async": "async" in source[max(0, match.start()-10):match.start()+20],
                "args": args,
                "return_type": "any",
                "has_conditions": False,
                "has_loops": False,
                "raises_exceptions": False,
                "complexity_score": 1,
                "line_number": source[:match.start()].count("\n") + 1,
            })

        for match in class_pat.finditer(source):
            name = match.group(1)
            base = match.group(2) or ""
            targets.append({
                "name": name,
                "type": "class",
                "class_name": None,
                "bases": [base] if base else [],
                "methods": [],
                "has_init": True,
                "init_args": [],
                "complexity_score": 2,
                "line_number": source[:match.start()].count("\n") + 1,
            })

        return targets


# =============================================================================
# Test Template Generator - builds test stubs without LLM
# =============================================================================

class TestTemplateGenerator:
    """
    Generates deterministic test stubs as fallback when LLM is unavailable.

    Produces syntactically correct but semantically incomplete tests
    that serve as scaffolding for developers to complete.
    """

    @staticmethod
    def python_tests(targets: list[dict[str, Any]], module_name: str) -> str:
        """
        Generate pytest stubs for a list of Python test targets.

        Args:
            targets:     List of test target dicts from TestabilityAnalyzer
            module_name: Module name to import in the test file

        Returns:
            Complete pytest file content as a string
        """
        lines: list[str] = [
            '"""',
            "Auto-generated test suite by AI Codebase Assistant - Test Writer Agent",
            "Complete the TODO sections with actual assertions.",
            '"""',
            "",
            "import pytest",
            "from unittest.mock import MagicMock, patch, AsyncMock",
            f"# from {module_name} import ...",
            "",
            "",
        ]

        for target in targets:
            name = str(target.get("name", "unknown"))
            ttype = str(target.get("type", "function"))
            args: list[dict[str, str]] = target.get("args") or []
            is_async = bool(target.get("is_async", False))
            has_conditions = bool(target.get("has_conditions", False))
            raises_exceptions = bool(target.get("raises_exceptions", False))

            if ttype == "class":
                # Class fixture + instantiation test
                class_name = name
                init_args: list[dict[str, str]] = target.get("init_args") or []
                methods: list[str] = target.get("methods") or []

                lines.append("")
                lines.append(f"class Test{class_name}:")
                lines.append(f'    """Tests for {class_name} class."""')
                lines.append("")

                # Fixture
                fixture_args = ", ".join(
                    TestTemplateGenerator._py_default(a["type"])
                    for a in init_args
                ) or ""
                lines.append("    @pytest.fixture")
                lines.append(f"    def {class_name.lower()}_instance(self):")
                lines.append(f'        """Create {class_name} instance for testing."""')
                lines.append(f"        # TODO: provide real constructor arguments")
                lines.append(f"        return {class_name}({fixture_args})")
                lines.append("")

                # Instantiation test
                lines.append(f"    def test_{class_name.lower()}_instantiation(self, {class_name.lower()}_instance):")
                lines.append(f'        """Test that {class_name} can be instantiated."""')
                lines.append(f"        assert {class_name.lower()}_instance is not None")
                lines.append("")

                # Method stubs
                for method in methods[:6]:
                    lines.append(f"    def test_{class_name.lower()}_{method}(self, {class_name.lower()}_instance):")
                    lines.append(f'        """Test {class_name}.{method}() behavior."""')
                    lines.append(f"        # TODO: call {class_name.lower()}_instance.{method}(...)")
                    lines.append(f"        # TODO: assert expected result")
                    lines.append(f"        pass")
                    lines.append("")

            else:
                # Function tests
                arg_names = [a["name"] for a in args]
                arg_defaults = ", ".join(
                    TestTemplateGenerator._py_default(a["type"]) for a in args
                ) or ""
                call_args = ", ".join(arg_names) if arg_names else ""

                # Setup variables
                setup_lines: list[str] = []
                for arg in args:
                    default_val = TestTemplateGenerator._py_default(arg["type"])
                    setup_lines.append(f"    {arg['name']} = {default_val}  # TODO: use real value")

                async_marker = "@pytest.mark.asyncio\n" if is_async else ""
                async_prefix = "async " if is_async else ""
                await_prefix = "await " if is_async else ""

                # Happy path test
                lines.append("")
                if is_async:
                    lines.append("    @pytest.mark.asyncio")
                lines.append(f"def test_{name}_happy_path():")
                lines.append(f'    """Test {name}() with valid inputs returns expected result."""')
                for sl in setup_lines:
                    lines.append(sl)
                lines.append(f"    result = {await_prefix}{name}({call_args})")
                lines.append(f"    assert result is not None  # TODO: assert specific value")
                lines.append("")

                # Edge case: empty/None inputs
                if args:
                    lines.append(f"def test_{name}_with_none_input():")
                    lines.append(f'    """Test {name}() handles None input gracefully."""')
                    none_args = ", ".join("None" for _ in args)
                    lines.append(f"    # TODO: decide if None should raise or return default")
                    lines.append(f"    with pytest.raises((TypeError, ValueError)):")
                    lines.append(f"        {name}({none_args})")
                    lines.append("")

                # Conditional branches
                if has_conditions:
                    lines.append(f"def test_{name}_branch_true():")
                    lines.append(f'    """Test {name}() true-branch behavior."""')
                    for sl in setup_lines:
                        lines.append(sl)
                    lines.append(f"    # TODO: set up inputs that trigger true branch")
                    lines.append(f"    result = {await_prefix}{name}({call_args})")
                    lines.append(f"    assert result is not None")
                    lines.append("")

                    lines.append(f"def test_{name}_branch_false():")
                    lines.append(f'    """Test {name}() false-branch behavior."""')
                    for sl in setup_lines:
                        lines.append(sl)
                    lines.append(f"    # TODO: set up inputs that trigger false branch")
                    lines.append(f"    result = {await_prefix}{name}({call_args})")
                    lines.append(f"    assert result is not None")
                    lines.append("")

                # Exception tests
                if raises_exceptions:
                    lines.append(f"def test_{name}_raises_on_invalid_input():")
                    lines.append(f'    """Test {name}() raises expected exception."""')
                    lines.append(f"    with pytest.raises(Exception):  # TODO: specific exception")
                    lines.append(f"        {name}()")
                    lines.append("")

        return "\n".join(lines)

    @staticmethod
    def jest_tests(targets: list[dict[str, Any]], module_name: str) -> str:
        """
        Generate Jest test stubs for JS/TS test targets.

        Args:
            targets:     List of test target dicts from TestabilityAnalyzer
            module_name: Module file path for import statement

        Returns:
            Complete Jest test file content as a string
        """
        lines: list[str] = [
            "/**",
            " * Auto-generated test suite by AI Codebase Assistant",
            " * Complete the TODO sections with actual assertions.",
            " */",
            "",
            f"// import {{ ... }} from './{module_name}';",
            "",
        ]

        for target in targets:
            name = str(target.get("name", "unknown"))
            ttype = str(target.get("type", "function"))
            args: list[dict[str, str]] = target.get("args") or []
            is_async = bool(target.get("is_async", False))
            has_conditions = bool(target.get("has_conditions", False))

            if ttype == "class":
                lines.append(f"describe('{name}', () => {{")
                lines.append(f"  let instance;")
                lines.append("")
                lines.append(f"  beforeEach(() => {{")
                lines.append(f"    instance = new {name}();  // TODO: constructor args")
                lines.append(f"  }});")
                lines.append("")
                lines.append(f"  it('should instantiate without errors', () => {{")
                lines.append(f"    expect(instance).toBeDefined();")
                lines.append(f"  }});")
                lines.append("")
                methods: list[str] = target.get("methods") or []
                for method in methods[:4]:
                    lines.append(f"  it('should execute {method}() correctly', () => {{")
                    lines.append(f"    // TODO: call instance.{method}(...) and assert")
                    lines.append(f"    expect(instance.{method}).toBeDefined();")
                    lines.append(f"  }});")
                    lines.append("")
                lines.append(f"}});")
                lines.append("")

            else:
                await_kw = "await " if is_async else ""
                async_kw = "async " if is_async else ""
                arg_defaults = ", ".join(
                    TestTemplateGenerator._js_default(a.get("type", "any"))
                    for a in args
                ) or ""

                lines.append(f"describe('{name}', () => {{")
                lines.append("")

                lines.append(f"  it('should return expected result with valid inputs', {async_kw}() => {{")
                lines.append(f"    const result = {await_kw}{name}({arg_defaults});")
                lines.append(f"    expect(result).toBeDefined();  // TODO: specific assertion")
                lines.append(f"  }});")
                lines.append("")

                if args:
                    lines.append(f"  it('should handle edge case: empty inputs', {async_kw}() => {{")
                    lines.append(f"    // TODO: test boundary conditions")
                    lines.append(f"    expect(() => {name}()).toThrow();  // or not.toThrow()")
                    lines.append(f"  }});")
                    lines.append("")

                if has_conditions:
                    lines.append(f"  it('should handle true branch condition', {async_kw}() => {{")
                    lines.append(f"    // TODO: set inputs that hit true branch")
                    lines.append(f"    const result = {await_kw}{name}({arg_defaults});")
                    lines.append(f"    expect(result).toBeTruthy();")
                    lines.append(f"  }});")
                    lines.append("")

                lines.append(f"}});")
                lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _py_default(type_hint: str) -> str:
        """
        Return a sensible Python default value string for a type hint.

        Args:
            type_hint: Python type annotation string

        Returns:
            Python literal string suitable for use in test code
        """
        t = type_hint.lower().strip()
        if "str" in t:
            return '"test_value"'
        if "int" in t:
            return "42"
        if "float" in t:
            return "3.14"
        if "bool" in t:
            return "True"
        if "list" in t or "sequence" in t:
            return "[]"
        if "dict" in t or "mapping" in t:
            return "{}"
        if "optional" in t:
            return "None"
        if "bytes" in t:
            return 'b"test"'
        return "None  # TODO: provide value"

    @staticmethod
    def _js_default(type_hint: str) -> str:
        """
        Return a sensible JavaScript default value string for a type hint.

        Args:
            type_hint: TypeScript/JS type annotation string

        Returns:
            JS literal string suitable for use in test code
        """
        t = type_hint.lower().strip()
        if "string" in t or "str" in t:
            return '"testValue"'
        if "number" in t or "int" in t or "float" in t:
            return "42"
        if "boolean" in t or "bool" in t:
            return "true"
        if "array" in t or "[]" in t:
            return "[]"
        if "object" in t or "dict" in t:
            return "{}"
        if "null" in t or "undefined" in t or "none" in t:
            return "null"
        return "undefined  /* TODO */"


# =============================================================================
# Test Writer Agent
# =============================================================================

class TestWriterAgent(BaseAgent):
    """
    LangGraph-powered agent that generates comprehensive test suites.

    Correctly extends BaseAgent (same pattern as DocumentationGeneratorAgent):
        __init__(retriever, streaming_client) -> super().__init__()
        agent_type -> "test_writer"
        _build_graph() -> compiled StateGraph
        _format_result(state) -> dict

    Workflow:
        validate -> retrieve -> parse_code -> analyze_testability
                 -> generate_tests -> fmt -> done -> END

    Code stored in state["config"] via AgentConfig.extra:
        extra = dict(
            code_content="...",
            language="python",
            file_path="mymodule.py",
            test_framework="pytest",  # optional
        )

    PROMPT TEMPLATE RULE (same as Step 21):
        user_prompt_template must ONLY contain {context} {query} {project_id}.
        All dynamic element data pre-rendered as plain strings.
    """

    def __init__(
        self,
        retriever: Any = None,
        streaming_client: Any = None,
    ) -> None:
        """
        Initialise the Test Writer Agent.

        Args:
            retriever:        Optional RAG retriever for code context lookup
            streaming_client: Optional Ollama streaming client for LLM calls
        """
        super().__init__(retriever=retriever, streaming_client=streaming_client)

    # =========================================================================
    # Abstract property
    # =========================================================================

    @property
    def agent_type(self) -> str:
        """
        Unique identifier for this agent type.

        Returns:
            "test_writer"
        """
        return "test_writer"

    # =========================================================================
    # Abstract method: _build_graph
    # =========================================================================

    def _build_graph(self) -> Any:
        """
        Build and compile the LangGraph StateGraph for test generation.

        Nodes:
            validate          (BaseAgent) check project_id present
            retrieve          (BaseAgent) vector-store code context
            parse_code        (self)      AST/regex parse source
            analyze_testability (self)    determine what needs tests
            generate_tests    (self)      LLM + template test generation
            fmt               (BaseAgent) calls _format_result()
            done              (self)      build final Markdown report

        Returns:
            Compiled LangGraph CompiledStateGraph
        """
        graph: StateGraph = StateGraph(AgentState)

        graph.add_node("validate",            self._node_validate)
        graph.add_node("retrieve",            self._node_retrieve)
        graph.add_node("parse_code",          self._node_parse_code)
        graph.add_node("analyze_testability", self._node_analyze_testability)
        graph.add_node("generate_tests",      self._node_generate_tests)
        graph.add_node("fmt",                 self._node_format)
        graph.add_node("done",                self._node_done)

        graph.set_entry_point("validate")
        graph.add_edge("validate",            "retrieve")
        graph.add_edge("retrieve",            "parse_code")
        graph.add_edge("parse_code",          "analyze_testability")
        graph.add_edge("analyze_testability", "generate_tests")
        graph.add_edge("generate_tests",      "fmt")
        graph.add_edge("fmt",                 "done")
        graph.add_edge("done",                END)

        return graph.compile()

    # =========================================================================
    # Abstract method: _format_result
    # =========================================================================

    def _format_result(self, state: AgentState) -> dict[str, Any]:
        """
        Convert final AgentState into a structured result dict.

        Called by BaseAgent._node_format() after test generation completes.
        Reads test targets from state["config"]["_test_targets"] and
        the generated test code from state["config"]["_generated_tests"].

        Args:
            state: Final AgentState after all workflow nodes

        Returns:
            Dict with keys: targets_found, tests_generated, framework,
            language, file_path, test_file_name, target_names,
            llm_enhanced, summary
        """
        config: dict[str, Any] = state.get("config") or {}
        targets: list[dict[str, Any]] = config.get("_test_targets") or []
        language: str = str(config.get("language") or "unknown")
        file_path: str = str(config.get("file_path") or "unknown")
        framework: str = str(config.get("_resolved_framework") or "unknown")
        generated_tests: str = str(config.get("_generated_tests") or "")
        llm_used: bool = bool(config.get("_llm_enhanced", False))

        # Derive test file name
        base_name = file_path.split("/")[-1].rsplit(".", 1)[0]
        if language == "python":
            test_file_name = "test_" + base_name + ".py"
        elif language in ("javascript", "typescript", "js", "ts", "jsx", "tsx"):
            test_file_name = base_name + ".test.ts"
        else:
            test_file_name = "test_" + base_name + ".txt"

        return {
            "targets_found": len(targets),
            "tests_generated": len([t for t in targets if t.get("type") != "class"]),
            "classes_tested": len([t for t in targets if t.get("type") == "class"]),
            "framework": framework,
            "language": language,
            "file_path": file_path,
            "test_file_name": test_file_name,
            "target_names": [str(t.get("name", "")) for t in targets],
            "llm_enhanced": llm_used,
            "test_code_length": len(generated_tests),
            "summary": (
                f"Generated {framework} tests for {len(targets)} targets "
                f"in {language} file '{file_path}'. "
                f"Output file: {test_file_name}. "
                f"LLM enhanced: {llm_used}."
            ),
        }

    # =========================================================================
    # Custom nodes
    # =========================================================================

    async def _node_parse_code(self, state: AgentState) -> AgentState:
        """
        Node 3: Parse source code and detect language/framework.

        Reads code_content, language, file_path, test_framework from
        state["config"]. Performs light parsing to confirm language
        and stores raw source for downstream nodes.

        Args:
            state: Current AgentState

        Returns:
            Updated AgentState with language and file info confirmed
        """
        config: dict[str, Any] = dict(state.get("config") or {})
        code_content: str = str(config.get("code_content") or "").strip()
        language: str = str(config.get("language") or "unknown").lower()
        file_path: str = str(config.get("file_path") or "unknown")

        logger.info(
            "[TestWriter] parse_code: language=%s len=%d",
            language, len(code_content),
        )

        if not code_content:
            logger.warning("[TestWriter] No code_content — aborting")
            return {
                **state,
                "error": "No code_content provided in config",
                "current_step": "parsed",
                "progress": 0.3,
            }

        # Auto-detect framework if not provided
        requested_fw = str(config.get("test_framework") or "").lower()
        if requested_fw:
            framework = requested_fw
        elif language == "python":
            framework = "pytest"
        elif language in ("javascript", "typescript", "jsx", "tsx", "js", "ts"):
            framework = "jest"
        else:
            framework = "generic"

        config["_resolved_framework"] = framework
        config["_code_content"] = code_content

        return {
            **state,
            "config": config,
            "current_step": "parsed",
            "progress": 0.3,
        }

    async def _node_analyze_testability(self, state: AgentState) -> AgentState:
        """
        Node 4: Analyze code structure and extract testable targets.

        Uses TestabilityAnalyzer to parse the source into a list of
        test targets (functions, classes, methods) with complexity metadata.
        Stores targets in state["config"]["_test_targets"].

        Args:
            state: Current AgentState after parse_code

        Returns:
            Updated AgentState with _test_targets list in config
        """
        config: dict[str, Any] = dict(state.get("config") or {})
        code_content: str = str(config.get("_code_content") or "")
        language: str = str(config.get("language") or "unknown").lower()

        logger.info("[TestWriter] analyze_testability: language=%s", language)

        targets: list[dict[str, Any]] = []

        try:
            if language == "python":
                targets = TestabilityAnalyzer.analyze_python(code_content)
            elif language in ("javascript", "typescript", "jsx", "tsx", "js", "ts"):
                targets = TestabilityAnalyzer.analyze_js(code_content)
            else:
                # Generic: treat whole file as one target
                targets = [{
                    "name": str(config.get("file_path") or "module"),
                    "type": "module",
                    "args": [],
                    "is_async": False,
                    "has_conditions": False,
                    "raises_exceptions": False,
                    "complexity_score": 1,
                    "line_number": 1,
                }]
        except Exception as exc:
            logger.error("[TestWriter] analyze_testability error: %s", exc, exc_info=True)
            targets = []

        logger.info("[TestWriter] Found %d test targets", len(targets))
        config["_test_targets"] = targets

        return {
            **state,
            "config": config,
            "current_step": "analyzed",
            "progress": 0.5,
        }

    async def _node_generate_tests(self, state: AgentState) -> AgentState:
        """
        Node 5: Generate test code using templates + LLM enhancement.

        Strategy:
            1. Generate deterministic test stubs via TestTemplateGenerator
               (always works, no LLM needed)
            2. If streaming_client available, call LLM to enhance with:
               - Real assertions based on function logic
               - Edge cases based on complexity analysis
               - Mock setup for dependencies
            3. Store final test code in state["config"]["_generated_tests"]

        CRITICAL: user_prompt_template uses ONLY {context} and {query}
        as format placeholders. ALL other dynamic content (target summaries,
        file paths, framework names) pre-rendered as plain strings.

        Args:
            state: Current AgentState with test targets available

        Returns:
            Updated AgentState with generated test code and progress 0.8
        """
        config: dict[str, Any] = dict(state.get("config") or {})
        targets: list[dict[str, Any]] = config.get("_test_targets") or []
        language: str = str(config.get("language") or "unknown").lower()
        file_path: str = str(config.get("file_path") or "unknown")
        framework: str = str(config.get("_resolved_framework") or "generic")

        logger.info(
            "[TestWriter] generate_tests: %d targets, framework=%s",
            len(targets), framework,
        )

        # ── Step 1: deterministic template generation ─────────────────────
        module_name = file_path.rsplit(".", 1)[0].replace("/", ".").replace("\\", ".")

        if language == "python":
            template_tests = TestTemplateGenerator.python_tests(targets, module_name)
        elif language in ("javascript", "typescript", "jsx", "tsx", "js", "ts"):
            template_tests = TestTemplateGenerator.jest_tests(targets, module_name)
        else:
            template_tests = (
                "# Auto-generated test stubs\n"
                "# TODO: implement tests for this " + language + " module\n"
            )

        config["_generated_tests"] = template_tests
        config["_llm_enhanced"] = False

        # ── Step 2: LLM enhancement if streaming_client available ─────────
        if self._streaming_client and targets:
            # Pre-render target summary as plain string (NO format placeholders)
            target_lines: list[str] = []
            for t in targets[:8]:
                tname = str(t.get("name") or "unknown")
                ttype = str(t.get("type") or "function")
                args: list[dict[str, str]] = t.get("args") or []
                args_str = ", ".join(
                    a.get("name", "p") + ": " + a.get("type", "any")
                    for a in args
                ) or "none"
                ret = str(t.get("return_type") or "any")
                score = str(t.get("complexity_score") or 1)
                flags: list[str] = []
                if t.get("has_conditions"):
                    flags.append("has-conditions")
                if t.get("raises_exceptions"):
                    flags.append("raises-exceptions")
                if t.get("is_async"):
                    flags.append("async")
                flags_str = ", ".join(flags) or "simple"

                target_lines.append(
                    ttype.upper() + ": " + tname
                    + " | args: " + args_str
                    + " | returns: " + ret
                    + " | complexity: " + score
                    + " | flags: " + flags_str
                )

            # This is a fully-rendered plain string — no braces remaining
            targets_block = "\n".join(target_lines)

            # Escape any stray braces in template_tests before embedding
            safe_template = template_tests.replace("{", "(").replace("}", ")")

            system_prompt = self._get_system_prompt(language, framework)

            # ONLY {context} and {query} as placeholders — safe for .format()
            user_prompt_template = (
                "Language: " + language + " | Framework: " + framework + "\n"
                "File: " + file_path + "\n\n"
                "TEMPLATE TESTS (improve these):\n"
                + safe_template[:1500] + "\n\n"
                "TARGETS TO TEST:\n"
                + targets_block + "\n\n"
                "CODEBASE CONTEXT:\n{context}\n\n"
                "TASK: {query}\n\n"
                "Improve the template tests with:\n"
                "1. Real assertions based on function logic\n"
                "2. Edge cases for each complexity flag\n"
                "3. Proper mock setup for dependencies\n"
                "4. Parametrize tests where appropriate\n"
                "Return the COMPLETE improved test file only.\n"
            )

            retrieval_query = (
                "Test patterns and usage examples for "
                + language + " functions: "
                + ", ".join(str(t.get("name", "")) for t in targets[:5])
            )
            state_for_llm = {**state, "config": config, "query": retrieval_query}

            try:
                updated = await self._node_analyze(
                    state_for_llm,
                    system_prompt=system_prompt,
                    user_prompt_template=user_prompt_template,
                )
                llm_output = updated.get("llm_response") or ""
                if llm_output and len(llm_output) > 100:
                    config["_generated_tests"] = llm_output
                    config["_llm_enhanced"] = True
                    logger.info("[TestWriter] LLM enhanced tests (%d chars)", len(llm_output))
                    return {
                        **updated,
                        "config": config,
                        "current_step": "tests_generated",
                        "progress": 0.8,
                    }
            except Exception as exc:
                logger.warning("[TestWriter] LLM enhancement failed: %s — using template", exc)

        return {
            **state,
            "config": config,
            "current_step": "tests_generated",
            "progress": 0.8,
        }

    async def _node_done(self, state: AgentState) -> AgentState:
        """
        Node 7: Assemble the final Markdown report with embedded test code.

        Combines:
            - Test generation summary from state["final_result"]
            - Full test code from state["config"]["_generated_tests"]
            - Instructions for running the tests

        Sets state["formatted_report"] to the complete Markdown string.

        Args:
            state: AgentState after _node_format has run

        Returns:
            Final AgentState with formatted_report and progress 1.0
        """
        config: dict[str, Any] = state.get("config") or {}
        language: str = str(config.get("language") or "unknown")
        file_path: str = str(config.get("file_path") or "unknown")
        framework: str = str(config.get("_resolved_framework") or "generic")
        generated_tests: str = str(config.get("_generated_tests") or "")
        llm_enhanced: bool = bool(config.get("_llm_enhanced", False))
        final_result: dict[str, Any] = state.get("final_result") or {}

        test_file_name: str = str(final_result.get("test_file_name") or "test_output.py")
        targets_found: int = int(final_result.get("targets_found") or 0)
        target_names: list[str] = final_result.get("target_names") or []

        lines: list[str] = [
            "# Test Suite Report",
            "",
            "**Source File:** `" + file_path + "`",
            "**Language:** " + language.title(),
            "**Framework:** " + framework,
            "**Generated:** " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "**LLM Enhanced:** " + ("Yes" if llm_enhanced else "No (template mode)"),
            "",
            "---",
            "",
            "## Summary",
            "",
            "- **Test targets found:** " + str(targets_found),
            "- **Output file:** `" + test_file_name + "`",
        ]

        if target_names:
            lines.append("- **Targets:** " + ", ".join("`" + n + "`" for n in target_names[:10]))

        lines += ["", "---", "", "## How to Run", ""]

        if framework == "pytest":
            lines += [
                "```bash",
                "# Install pytest if needed",
                "pip install pytest pytest-asyncio",
                "",
                "# Run all tests",
                "pytest " + test_file_name + " -v",
                "",
                "# Run with coverage",
                "pytest " + test_file_name + " -v --cov=. --cov-report=term-missing",
                "```",
            ]
        elif framework == "jest":
            lines += [
                "```bash",
                "# Install Jest if needed",
                "npm install --save-dev jest @types/jest ts-jest",
                "",
                "# Run tests",
                "npx jest " + test_file_name + " --verbose",
                "",
                "# Run with coverage",
                "npx jest " + test_file_name + " --coverage",
                "```",
            ]
        else:
            lines += ["Run with your preferred test framework.", ""]

        lines += [
            "",
            "---",
            "",
            "## Generated Test Code",
            "",
            "Save the following as `" + test_file_name + "`:",
            "",
        ]

        if language == "python":
            lines.append("```python")
        elif language in ("javascript", "typescript", "jsx", "tsx", "js", "ts"):
            lines.append("```typescript")
        else:
            lines.append("```")

        lines.append(generated_tests if generated_tests else "# No tests generated")
        lines.append("```")
        lines += [
            "",
            "---",
            "",
            "*Generated by AI Codebase Assistant — Test Writer Agent*",
            "*Review and complete all TODO sections before running in CI/CD*",
        ]

        return {
            **state,
            "formatted_report": "\n".join(lines),
            "status": AgentStatus.COMPLETED.value,
            "current_step": "done",
            "progress": 1.0,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    # =========================================================================
    # Static helpers
    # =========================================================================

    @staticmethod
    def _get_system_prompt(language: str, framework: str) -> str:
        """
        Build an LLM system prompt for test generation.

        Args:
            language:  Target programming language
            framework: Test framework name (pytest, jest, etc.)

        Returns:
            System prompt string with test writing instructions
        """
        if framework == "pytest":
            return (
                "You are a senior Python engineer writing production pytest test suites. "
                "Generate complete, runnable pytest tests with: "
                "proper fixtures, parametrize for multiple inputs, "
                "mock/patch for external dependencies, "
                "edge cases (empty, None, boundary values), "
                "async test support with pytest.mark.asyncio. "
                "Return ONLY the complete Python test file, no explanation."
            )
        elif framework == "jest":
            return (
                "You are a senior JavaScript/TypeScript engineer writing Jest tests. "
                "Generate complete, runnable Jest tests with: "
                "describe/it blocks, beforeEach setup, "
                "jest.mock() for dependencies, "
                "edge cases and boundary values, "
                "async/await support. "
                "Return ONLY the complete test file, no explanation."
            )
        else:
            return (
                "You are a senior software engineer writing comprehensive tests. "
                "Generate complete test cases covering: "
                "happy path, edge cases, error conditions, boundary values. "
                "Return ONLY the complete test file."
            )


# =============================================================================
# Factory
# =============================================================================

def create_test_writer_agent(
    retriever: Any = None,
    streaming_client: Any = None,
) -> TestWriterAgent:
    """
    Create and return a configured TestWriterAgent instance.

    Args:
        retriever:        Optional RAG retriever for code context lookup
        streaming_client: Optional Ollama streaming client for LLM calls

    Returns:
        Ready-to-use TestWriterAgent
    """
    return TestWriterAgent(
        retriever=retriever,
        streaming_client=streaming_client,
    )
