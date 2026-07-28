"""
Documentation Generator Agent - Step 21
AI Codebase Assistant v2.0

Correctly extends BaseAgent from base_agent.py:
    BaseAgent.__init__(retriever=None, streaming_client=None)
    Abstract property:  agent_type -> str
    Abstract method:    _build_graph() -> compiled StateGraph
    Abstract method:    _format_result(state: AgentState) -> dict

    run() accepts AgentConfig (not dict)
    AgentConfig.extra dict carries: code_content, language, file_path
    These get merged into state["config"] via to_initial_state()

LangGraph workflow nodes:
    validate -> retrieve -> parse_code -> generate -> fmt -> done -> END

KEY FIX (v3):
    _node_generate builds element_summaries as a plain pre-rendered string.
    The user_prompt_template then contains ONLY {context}, {query}, {project_id}
    placeholders so BaseAgent._node_analyze().format() never hits a KeyError.
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
# Python AST Parser
# =============================================================================

class PythonASTParser:
    """
    Extracts structural elements from Python source using the built-in ast module.

    Provides accurate parsing of function signatures, class hierarchies,
    argument types, return types, and existing docstrings.
    """

    @staticmethod
    def parse(source: str) -> list[dict[str, Any]]:
        """
        Parse Python source code and extract all documentable elements.

        Args:
            source: Raw Python source code string

        Returns:
            List of element dicts with keys: type, name, args, return_type,
            existing_doc, body_preview, line_number, needs_doc
        """
        elements: list[dict[str, Any]] = []
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            logger.warning("[DocGen] Python AST SyntaxError: %s", exc)
            return elements

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                elements.append(PythonASTParser._extract_function(node, source))
            elif isinstance(node, ast.ClassDef):
                elements.append(PythonASTParser._extract_class(node, source))

        return elements

    @staticmethod
    def _extract_function(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        source: str,
    ) -> dict[str, Any]:
        """
        Extract function metadata from an AST FunctionDef node.

        Args:
            node:   AST function definition node (sync or async)
            source: Full source code for line-range extraction

        Returns:
            Dict with name, is_async, args, return_type, existing_doc,
            body_preview, line_number, needs_doc
        """
        args_info: list[dict[str, str]] = []
        for arg in node.args.args:
            arg_type = "Any"
            if arg.annotation:
                try:
                    arg_type = ast.unparse(arg.annotation)
                except Exception:
                    arg_type = "Any"
            args_info.append({"name": arg.arg, "type": arg_type})

        return_type = "None"
        if node.returns:
            try:
                return_type = ast.unparse(node.returns)
            except Exception:
                return_type = "Any"

        existing_doc = ""
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            existing_doc = node.body[0].value.value.strip()

        source_lines = source.splitlines()
        start = node.lineno - 1
        end = min(start + 12, len(source_lines))
        body_preview = "\n".join(source_lines[start:end])

        return {
            "type": "function",
            "name": node.name,
            "is_async": isinstance(node, ast.AsyncFunctionDef),
            "args": args_info,
            "return_type": return_type,
            "existing_doc": existing_doc,
            "body_preview": body_preview,
            "line_number": node.lineno,
            "needs_doc": len(existing_doc) < 20,
        }

    @staticmethod
    def _extract_class(node: ast.ClassDef, source: str) -> dict[str, Any]:
        """
        Extract class metadata including base classes and method names.

        Args:
            node:   AST ClassDef node
            source: Full source code string

        Returns:
            Dict with name, bases, methods, existing_doc,
            body_preview, line_number, needs_doc
        """
        bases: list[str] = []
        for base in node.bases:
            try:
                bases.append(ast.unparse(base))
            except Exception:
                bases.append("object")

        existing_doc = ""
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            existing_doc = node.body[0].value.value.strip()

        methods: list[str] = [
            item.name
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]

        source_lines = source.splitlines()
        start = node.lineno - 1
        end = min(start + 6, len(source_lines))
        body_preview = "\n".join(source_lines[start:end])

        return {
            "type": "class",
            "name": node.name,
            "bases": bases,
            "methods": methods,
            "existing_doc": existing_doc,
            "body_preview": body_preview,
            "line_number": node.lineno,
            "needs_doc": len(existing_doc) < 20,
        }


# =============================================================================
# JavaScript / TypeScript Regex Parser
# =============================================================================

class JSParser:
    """
    Regex-based extractor for JavaScript and TypeScript code elements.

    Handles named functions, arrow functions, classes, and TS interfaces.
    """

    FUNC_PATTERN = re.compile(
        r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)",
        re.MULTILINE,
    )
    ARROW_PATTERN = re.compile(
        r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*"
        r"(?:async\s+)?\(([^)]*)\)\s*(?::\s*\w+)?\s*=>",
        re.MULTILINE,
    )
    CLASS_PATTERN = re.compile(
        r"(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?",
        re.MULTILINE,
    )
    INTERFACE_PATTERN = re.compile(
        r"(?:export\s+)?interface\s+(\w+)",
        re.MULTILINE,
    )

    @classmethod
    def parse(cls, source: str) -> list[dict[str, Any]]:
        """
        Parse JS/TS source and extract all documentable elements.

        Args:
            source: Raw JavaScript or TypeScript source code string

        Returns:
            List of element dicts with type, name, args, existing_doc,
            body_preview, line_number, needs_doc
        """
        elements: list[dict[str, Any]] = []

        for match in cls.FUNC_PATTERN.finditer(source):
            name = match.group(1)
            args_raw = match.group(2)
            args = [
                {"name": a.split(":")[0].strip(), "type": "any"}
                for a in args_raw.split(",")
                if a.strip()
            ]
            pos = match.start()
            has_doc = "/**" in source[max(0, pos - 200):pos]
            elements.append({
                "type": "function",
                "name": name,
                "args": args,
                "existing_doc": "JSDoc present" if has_doc else "",
                "body_preview": source[pos:pos + 200],
                "line_number": source[:pos].count("\n") + 1,
                "needs_doc": not has_doc,
            })

        for match in cls.ARROW_PATTERN.finditer(source):
            name = match.group(1)
            args_raw = match.group(2)
            args = [
                {"name": a.split(":")[0].strip(), "type": "any"}
                for a in args_raw.split(",")
                if a.strip()
            ]
            pos = match.start()
            has_doc = "/**" in source[max(0, pos - 200):pos]
            elements.append({
                "type": "arrow_function",
                "name": name,
                "args": args,
                "existing_doc": "JSDoc present" if has_doc else "",
                "body_preview": source[pos:pos + 200],
                "line_number": source[:pos].count("\n") + 1,
                "needs_doc": not has_doc,
            })

        for match in cls.CLASS_PATTERN.finditer(source):
            name = match.group(1)
            base = match.group(2) or ""
            pos = match.start()
            has_doc = "/**" in source[max(0, pos - 200):pos]
            elements.append({
                "type": "class",
                "name": name,
                "bases": [base] if base else [],
                "existing_doc": "JSDoc present" if has_doc else "",
                "body_preview": source[pos:pos + 200],
                "line_number": source[:pos].count("\n") + 1,
                "needs_doc": not has_doc,
            })

        for match in cls.INTERFACE_PATTERN.finditer(source):
            name = match.group(1)
            pos = match.start()
            has_doc = "/**" in source[max(0, pos - 200):pos]
            elements.append({
                "type": "interface",
                "name": name,
                "existing_doc": "JSDoc present" if has_doc else "",
                "body_preview": source[pos:pos + 200],
                "line_number": source[:pos].count("\n") + 1,
                "needs_doc": not has_doc,
            })

        return elements


# =============================================================================
# Documentation Generator Agent
# =============================================================================

class DocumentationGeneratorAgent(BaseAgent):
    """
    LangGraph-powered agent that generates comprehensive code documentation.

    Correctly extends BaseAgent:
        __init__(retriever, streaming_client) -> super().__init__()
        agent_type property  -> "doc_generator"
        _build_graph()       -> compiled StateGraph
        _format_result(state) -> structured dict

    IMPORTANT - prompt template rule:
        BaseAgent._node_analyze() calls user_prompt_template.format(
            context=..., query=..., project_id=...
        )
        Therefore the template string must ONLY contain {context}, {query},
        {project_id} as format placeholders. All other curly braces (e.g.
        from code snippets or element names) must be pre-rendered into the
        string BEFORE it is used as the template.
    """

    def __init__(
        self,
        retriever: Any = None,
        streaming_client: Any = None,
    ) -> None:
        """
        Initialise the Documentation Generator Agent.

        Args:
            retriever:        Optional RAG retriever for vector-store code lookup.
            streaming_client: Optional Ollama streaming client for LLM calls.
        """
        super().__init__(retriever=retriever, streaming_client=streaming_client)

    # =========================================================================
    # Abstract property
    # =========================================================================

    @property
    def agent_type(self) -> str:
        """
        Unique identifier for this agent used by BaseAgent.run() and task tracking.

        Returns:
            "doc_generator"
        """
        return "doc_generator"

    # =========================================================================
    # Abstract method: _build_graph
    # =========================================================================

    def _build_graph(self) -> Any:
        """
        Build and compile the LangGraph StateGraph for documentation generation.

        Node execution order:
            validate    (BaseAgent._node_validate)   check project_id present
            retrieve    (BaseAgent._node_retrieve)   vector-store code lookup
            parse_code  (self._node_parse_code)      AST / regex parsing
            generate    (self._node_generate)        LLM docstring generation
            fmt         (BaseAgent._node_format)     calls _format_result()
            done        (self._node_done)            build Markdown report

        Returns:
            Compiled LangGraph CompiledStateGraph supporting ainvoke()
        """
        graph: StateGraph = StateGraph(AgentState)

        graph.add_node("validate",   self._node_validate)
        graph.add_node("retrieve",   self._node_retrieve)
        graph.add_node("parse_code", self._node_parse_code)
        graph.add_node("generate",   self._node_generate)
        graph.add_node("fmt",        self._node_format)
        graph.add_node("done",       self._node_done)

        graph.set_entry_point("validate")
        graph.add_edge("validate",   "retrieve")
        graph.add_edge("retrieve",   "parse_code")
        graph.add_edge("parse_code", "generate")
        graph.add_edge("generate",   "fmt")
        graph.add_edge("fmt",        "done")
        graph.add_edge("done",       END)

        return graph.compile()

    # =========================================================================
    # Abstract method: _format_result
    # =========================================================================

    def _format_result(self, state: AgentState) -> dict[str, Any]:
        """
        Convert final AgentState into a structured result dict.

        Called by BaseAgent._node_format() after LLM generation completes.
        Result is stored in state["final_result"] and returned as
        AgentResult.result by BaseAgent.run().

        Args:
            state: Final AgentState after all workflow nodes have executed

        Returns:
            Dict with keys: elements_documented, elements_needing_docs,
            coverage_pct, language, file_path, type_counts,
            element_names, llm_output_length, summary
        """
        config: dict[str, Any] = state.get("config") or {}
        parsed_elements: list[dict[str, Any]] = config.get("_parsed_elements") or []
        language: str = str(config.get("language") or "unknown")
        file_path: str = str(config.get("file_path") or "unknown")
        llm_response: str = (
            state.get("llm_response") or state.get("analysis_result") or ""
        )

        type_counts: dict[str, int] = {}
        for elem in parsed_elements:
            t = str(elem.get("type", "unknown"))
            type_counts[t] = type_counts.get(t, 0) + 1

        needs_doc_count = sum(1 for e in parsed_elements if e.get("needs_doc", True))
        total = len(parsed_elements)
        already_documented = total - needs_doc_count
        coverage_pct = round((already_documented / max(total, 1)) * 100)

        return {
            "elements_documented": total,
            "elements_needing_docs": needs_doc_count,
            "coverage_pct": coverage_pct,
            "language": language,
            "file_path": file_path,
            "type_counts": type_counts,
            "element_names": [str(e.get("name", "")) for e in parsed_elements],
            "llm_output_length": len(llm_response),
            "summary": (
                f"Found {total} elements in {language} file '{file_path}'. "
                f"Generated docs for {needs_doc_count} undocumented elements. "
                f"Pre-existing coverage: {coverage_pct}%."
            ),
        }

    # =========================================================================
    # Custom node: parse_code
    # =========================================================================

    async def _node_parse_code(self, state: AgentState) -> AgentState:
        """
        Node 3: Parse uploaded source code into a list of structural elements.

        Reads code_content and language from state["config"] (populated by
        AgentConfig.to_initial_state() merging AgentConfig.extra).
        Writes parsed element list to state["config"]["_parsed_elements"].

        Args:
            state: Current LangGraph AgentState

        Returns:
            Updated AgentState with _parsed_elements stored in config
            and progress advanced to 0.45
        """
        config: dict[str, Any] = dict(state.get("config") or {})
        code_content: str = str(config.get("code_content") or "").strip()
        language: str = str(config.get("language") or "unknown").lower()

        logger.info(
            "[DocGen] parse_code: language=%s code_len=%d",
            language, len(code_content),
        )

        parsed_elements: list[dict[str, Any]] = []

        if not code_content:
            logger.warning("[DocGen] No code_content in state config — skipping parse")
            config["_parsed_elements"] = []
            return {
                **state,
                "config": config,
                "current_step": "parsed",
                "progress": 0.45,
            }

        try:
            if language == "python":
                parsed_elements = PythonASTParser.parse(code_content)
                logger.info("[DocGen] Python AST found %d elements", len(parsed_elements))

            elif language in ("javascript", "typescript", "jsx", "tsx", "js", "ts"):
                parsed_elements = JSParser.parse(code_content)
                logger.info("[DocGen] JS/TS regex found %d elements", len(parsed_elements))

            else:
                file_path = str(config.get("file_path") or "unknown")
                parsed_elements = [{
                    "type": "module",
                    "name": file_path,
                    "existing_doc": "",
                    "body_preview": code_content[:400],
                    "line_number": 1,
                    "needs_doc": True,
                }]
                logger.info("[DocGen] Generic fallback: 1 module element")

        except Exception as exc:
            logger.error("[DocGen] parse_code error: %s", exc, exc_info=True)
            parsed_elements = []

        config["_parsed_elements"] = parsed_elements
        return {
            **state,
            "config": config,
            "current_step": "parsed",
            "progress": 0.45,
        }

    # =========================================================================
    # Custom node: generate
    # =========================================================================

    async def _node_generate(self, state: AgentState) -> AgentState:
        """
        Node 4: Generate docstrings for parsed elements using the LLM.

        CRITICAL DESIGN NOTE — avoiding KeyError in .format():
            BaseAgent._node_analyze() calls:
                user_prompt_template.format(context=..., query=..., project_id=...)
            This means ANY {xyz} in the template string that is not one of those
            three keys will raise a KeyError.

            Solution: Pre-render ALL dynamic content (element names, args, code
            previews) into a plain string called `elements_block` BEFORE building
            the template. The template then only contains the three safe placeholders.

        Args:
            state: Current AgentState with parse_code results available

        Returns:
            Updated AgentState with llm_response set and progress at 0.75
        """
        config: dict[str, Any] = state.get("config") or {}
        parsed_elements: list[dict[str, Any]] = config.get("_parsed_elements") or []
        language: str = str(config.get("language") or "unknown").lower()
        file_path: str = str(config.get("file_path") or "unknown")

        elements_needing_doc = [e for e in parsed_elements if e.get("needs_doc", True)]

        logger.info(
            "[DocGen] generate: %d/%d elements need docs",
            len(elements_needing_doc), len(parsed_elements),
        )

        # ── Fast path: nothing to document ───────────────────────────────────
        if not elements_needing_doc:
            return {
                **state,
                "llm_response": (
                    "All elements in this file already have documentation. "
                    "No generation needed."
                ),
                "analysis_result": "All elements already documented.",
                "llm_time_ms": 0.0,
                "tokens_used": 0,
                "current_step": "generated",
                "progress": 0.75,
            }

        # ── Pre-render element summaries into a plain string ──────────────────
        # IMPORTANT: Do NOT leave any {word} patterns in this string.
        # They would be treated as .format() placeholders and raise KeyError.
        summary_parts: list[str] = []
        for elem in elements_needing_doc[:8]:
            elem_name: str = str(elem.get("name") or "unknown")
            elem_type: str = str(elem.get("type") or "function")
            args: list[dict[str, str]] = elem.get("args") or []
            return_type: str = str(elem.get("return_type") or "")
            # Strip all curly braces from preview to avoid KeyError
            raw_preview: str = str(elem.get("body_preview") or "")[:250]
            safe_preview: str = raw_preview.replace("{", "(").replace("}", ")")

            if language == "python":
                args_str = ", ".join(
                    a.get("name", "p") + ": " + a.get("type", "Any")
                    for a in args
                ) or "none"
                part = (
                    "### " + elem_type.upper() + ": " + elem_name + "\n"
                    + "Args: " + args_str + "\n"
                    + "Returns: " + (return_type or "None") + "\n"
                    + "```python\n" + safe_preview + "\n```"
                )
            else:
                args_str = ", ".join(
                    str(a.get("name", "p")) for a in args
                ) or "none"
                part = (
                    "### " + elem_type.upper() + ": " + elem_name + "\n"
                    + "Params: " + args_str + "\n"
                    + "```javascript\n" + safe_preview + "\n```"
                )
            summary_parts.append(part)

        # This is now a fully-rendered plain string with NO format placeholders
        elements_block: str = "\n\n".join(summary_parts)

        total_to_doc = len(elements_needing_doc)
        if total_to_doc > 8:
            elements_block += (
                "\n\n(Showing 8 of "
                + str(total_to_doc)
                + " elements needing documentation)"
            )

        system_prompt = self._get_system_prompt(language)

        # ── Build template — ONLY {context}, {query}, {project_id} allowed ───
        # elements_block is already rendered — no braces remain inside it.
        user_prompt_template = (
            "File: `" + file_path + "` | Language: " + language + "\n\n"
            "Generate " + language + " documentation for "
            + str(total_to_doc) + " undocumented code elements.\n\n"
            "ELEMENTS TO DOCUMENT:\n"
            + elements_block + "\n\n"
            "CODEBASE CONTEXT:\n{context}\n\n"
            "TASK: {query}\n\n"
            "For EACH element above output exactly:\n"
            "ELEMENT: <name>\n"
            "DOC:\n"
            "<docstring or comment text here>\n"
            "---\n"
        )

        # Targeted retrieval query
        elem_names_preview = ", ".join(
            str(e.get("name", "")) for e in elements_needing_doc[:5]
        )
        retrieval_query = (
            "Documentation and usage examples for "
            + language + " functions: "
            + elem_names_preview
            + " in file " + file_path
        )
        state_for_analyze = {**state, "query": retrieval_query}

        # Delegate to BaseAgent._node_analyze() — safe: only {context}/{query} remain
        updated = await self._node_analyze(
            state_for_analyze,
            system_prompt=system_prompt,
            user_prompt_template=user_prompt_template,
        )

        return {**updated, "current_step": "generated", "progress": 0.75}

    # =========================================================================
    # Custom node: done
    # =========================================================================

    async def _node_done(self, state: AgentState) -> AgentState:
        """
        Node 6: Assemble the final Markdown documentation report.

        Combines parsed element metadata with the LLM-generated docstrings
        and structured summary from state["final_result"] into a complete
        Markdown string stored as state["formatted_report"].

        Args:
            state: AgentState after _node_format has run

        Returns:
            Final AgentState with formatted_report set and progress at 1.0
        """
        config: dict[str, Any] = state.get("config") or {}
        parsed_elements: list[dict[str, Any]] = config.get("_parsed_elements") or []
        language: str = str(config.get("language") or "unknown")
        file_path: str = str(config.get("file_path") or "unknown")
        llm_response: str = (
            state.get("llm_response") or state.get("analysis_result") or ""
        )
        final_result: dict[str, Any] = state.get("final_result") or {}

        lines: list[str] = [
            "# Documentation Report",
            "",
            "**File:** `" + file_path + "`",
            "**Language:** " + language.title(),
            "**Generated:** " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "",
            "---",
            "",
            "## Summary",
            "",
        ]

        total = final_result.get("elements_documented", len(parsed_elements))
        needs = final_result.get("elements_needing_docs", 0)
        coverage = final_result.get("coverage_pct", 0)
        type_counts: dict[str, int] = final_result.get("type_counts") or {}

        lines += [
            "- **Total elements found:** " + str(total),
            "- **Needed documentation:** " + str(needs),
            "- **Pre-existing coverage:** " + str(coverage) + "%",
        ]
        if type_counts:
            tc_str = " | ".join(k + ": " + str(v) for k, v in type_counts.items())
            lines.append("- **Breakdown:** " + tc_str)

        lines += ["", "---", "", "## Elements Found", ""]

        type_icon: dict[str, str] = {
            "function": "fn", "class": "cls",
            "arrow_function": "=>", "interface": "iface", "module": "mod",
        }
        for elem in parsed_elements:
            icon = type_icon.get(str(elem.get("type", "")), "-")
            status = "needs doc" if elem.get("needs_doc", True) else "documented"
            lines.append(
                "- `[" + icon + "]` **" + str(elem.get("name", "?")) + "**"
                " (line " + str(elem.get("line_number", "?")) + ") — " + status
            )

        lines += ["", "---", "", "## Generated Documentation", ""]

        if llm_response and llm_response.strip():
            lines.append(llm_response.strip())
        else:
            lines.append(
                "*No documentation generated. "
                "LLM may be unavailable or all elements were already documented.*"
            )

        lines += [
            "",
            "---",
            "",
            "*Generated by AI Codebase Assistant — Documentation Generator Agent*",
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
    def _get_system_prompt(language: str) -> str:
        """
        Return the LLM system prompt for the given programming language.

        Args:
            language: Lowercase language name (python, javascript, etc.)

        Returns:
            System prompt string with docstring format instructions
        """
        if language == "python":
            return (
                "You are a senior Python engineer writing production-quality documentation. "
                "Generate Google-style docstrings for each function and class listed. "
                "Each docstring: one-line summary, blank line, Args: section "
                "(one line per arg with type and description), Returns: section. "
                "Respond for each element as:\n"
                "ELEMENT: <name>\n"
                "DOC:\n"
                "<docstring text only — no triple quotes>\n"
                "---"
            )
        elif language in ("javascript", "typescript", "jsx", "tsx", "js", "ts"):
            return (
                "You are a senior JavaScript/TypeScript engineer writing JSDoc. "
                "Generate complete JSDoc blocks with @description, "
                "@param (type) name - description for each param, "
                "and @returns (type) description. "
                "Respond for each element as:\n"
                "ELEMENT: <name>\n"
                "DOC:\n"
                "/** ... */\n"
                "---"
            )
        else:
            return (
                "You are a senior software engineer writing clear code documentation. "
                "Generate professional comment blocks describing each element's "
                "purpose, parameters, and return value. "
                "Respond for each element as:\n"
                "ELEMENT: <name>\n"
                "DOC:\n"
                "<comment text>\n"
                "---"
            )

    @staticmethod
    def _fallback_doc(element: dict[str, Any], language: str) -> str:
        """
        Generate a minimal template docstring when the LLM is unavailable.

        Args:
            element:  Parsed element dict with name, type, args
            language: Programming language string

        Returns:
            Minimal docstring template as a plain string
        """
        name = str(element.get("name") or "unknown")
        elem_type = str(element.get("type") or "function")
        args: list[dict[str, str]] = element.get("args") or []

        if language == "python":
            args_section = ""
            if args:
                args_section = "\n\n    Args:"
                for arg in args:
                    args_section += (
                        "\n        " + arg.get("name", "p")
                        + " (" + arg.get("type", "Any") + ")"
                        + ": TODO — describe parameter"
                    )
            return (
                "TODO: Document this " + elem_type + "."
                + args_section
                + "\n\n    Returns:\n        TODO — describe return value"
            )
        else:
            param_lines = "\n".join(
                " * @param ("
                + a.get("type", "any") + ") "
                + a.get("name", "param")
                + " - TODO description"
                for a in args
            )
            return (
                "/**\n * TODO: Document " + name + ".\n *\n"
                + param_lines + "\n"
                + " * @returns (any) TODO\n */"
            )


# =============================================================================
# Factory
# =============================================================================

def create_doc_generator_agent(
    retriever: Any = None,
    streaming_client: Any = None,
) -> DocumentationGeneratorAgent:
    """
    Create and return a configured DocumentationGeneratorAgent.

    Args:
        retriever:        Optional RAG retriever for vector-store code lookup
        streaming_client: Optional Ollama streaming client for LLM calls

    Returns:
        Ready-to-use DocumentationGeneratorAgent instance
    """
    return DocumentationGeneratorAgent(
        retriever=retriever,
        streaming_client=streaming_client,
    )
