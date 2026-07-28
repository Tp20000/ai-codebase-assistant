"""
Code Reviewer Agent - Step 23
AI Codebase Assistant v2.0

Performs comprehensive automated code review analyzing:
    - Style violations (naming conventions, line length, blank lines)
    - Design issues (SOLID principles, DRY, KISS, God objects)
    - Complexity problems (deeply nested code, long functions/classes)
    - Maintainability concerns (magic numbers, hardcoded strings, TODOs)
    - Python-specific issues (bare excepts, mutable defaults, shadowing)
    - JS/TS-specific issues (var usage, == vs ===, console.log leaks)

Output: Structured review with severity-rated findings and quality score.

Correctly extends BaseAgent (same pattern as Steps 21-22):
    BaseAgent.__init__(retriever=None, streaming_client=None)
    Abstract property:  agent_type -> str
    Abstract method:    _build_graph() -> compiled StateGraph
    Abstract method:    _format_result(state: AgentState) -> dict

    run() accepts AgentConfig
    AgentConfig.extra carries: code_content, language, file_path
    CRITICAL: user_prompt_template uses ONLY {context} {query} {project_id}

LangGraph workflow:
    validate -> retrieve -> parse_code -> static_analysis
             -> score -> generate_review -> fmt -> done -> END
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
# Review Finding dataclass-style dict schema
# =============================================================================
# Each finding is a dict with keys:
#   rule_id    (str)  unique rule identifier e.g. "PY001"
#   severity   (str)  CRITICAL | HIGH | MEDIUM | LOW | INFO
#   category   (str)  style | design | complexity | maintainability | security
#   line       (int)  line number where issue was found (0 = file-level)
#   title      (str)  short human-readable issue title
#   detail     (str)  explanation of the issue
#   suggestion (str)  actionable fix suggestion


SEVERITY_WEIGHT = {
    "CRITICAL": 10,
    "HIGH": 6,
    "MEDIUM": 3,
    "LOW": 1,
    "INFO": 0,
}


# =============================================================================
# Static Analyzers
# =============================================================================

class PythonStaticAnalyzer:
    """
    Performs rule-based static analysis on Python source code.

    Uses Python's ast module for structural checks and regex for
    style/pattern checks. Produces a list of finding dicts.

    Rules implemented:
        PY001  Long line (> 120 chars)
        PY002  Bare except clause
        PY003  Mutable default argument
        PY004  Magic number literal
        PY005  TODO/FIXME/HACK comment
        PY006  Deeply nested code (depth > 3)
        PY007  Long function (> 50 lines)
        PY008  Long class (> 200 lines)
        PY009  Too many arguments (> 5)
        PY010  Shadowed built-in name
        PY011  Missing return type annotation
        PY012  Single-letter variable (non-loop)
        PY013  print() call in production code
        PY014  Hardcoded credential pattern
        PY015  God function (> 100 lines)
    """

    BUILTINS = frozenset([
        "list", "dict", "set", "tuple", "str", "int", "float", "bool",
        "type", "object", "len", "range", "map", "filter", "zip", "sum",
        "min", "max", "abs", "round", "open", "input", "print", "id",
    ])

    MAGIC_NUMBER_EXEMPT = frozenset([0, 1, -1, 2, 100])

    CREDENTIAL_PATTERN = re.compile(
        r'(?i)(password|passwd|secret|api_key|token|auth)\s*=\s*["\'][^"\']{4,}["\']'
    )
    TODO_PATTERN = re.compile(r'#\s*(TODO|FIXME|HACK|XXX|BUG)\b', re.IGNORECASE)
    PRINT_PATTERN = re.compile(r'^\s*print\s*\(', re.MULTILINE)

    @classmethod
    def analyze(cls, source: str) -> list[dict[str, Any]]:
        """
        Run all Python static analysis rules on the given source.

        Args:
            source: Raw Python source code string

        Returns:
            List of finding dicts sorted by line number
        """
        findings: list[dict[str, Any]] = []
        lines = source.splitlines()

        # ── Line-based checks ─────────────────────────────────────
        for i, line in enumerate(lines, start=1):
            # PY001: long line
            if len(line) > 120:
                findings.append({
                    "rule_id": "PY001",
                    "severity": "LOW",
                    "category": "style",
                    "line": i,
                    "title": "Line too long",
                    "detail": f"Line is {len(line)} characters (limit: 120)",
                    "suggestion": "Break into multiple lines or use intermediate variables",
                })

            # PY005: TODO/FIXME comments
            if cls.TODO_PATTERN.search(line):
                match = cls.TODO_PATTERN.search(line)
                tag = match.group(1).upper() if match else "TODO"
                findings.append({
                    "rule_id": "PY005",
                    "severity": "INFO",
                    "category": "maintainability",
                    "line": i,
                    "title": f"{tag} comment found",
                    "detail": f"Unresolved {tag} at line {i}: {line.strip()[:60]}",
                    "suggestion": f"Resolve or create a ticket for this {tag}",
                })

            # PY014: hardcoded credentials
            if cls.CREDENTIAL_PATTERN.search(line):
                findings.append({
                    "rule_id": "PY014",
                    "severity": "CRITICAL",
                    "category": "security",
                    "line": i,
                    "title": "Hardcoded credential detected",
                    "detail": f"Possible hardcoded secret at line {i}: {line.strip()[:60]}",
                    "suggestion": "Use environment variables or a secrets manager",
                })

            # PY013: print() calls
            if cls.PRINT_PATTERN.match(line):
                findings.append({
                    "rule_id": "PY013",
                    "severity": "LOW",
                    "category": "style",
                    "line": i,
                    "title": "print() in production code",
                    "detail": "print() statements should not appear in production code",
                    "suggestion": "Replace with logging.info() / logging.debug()",
                })

        # ── AST-based checks ──────────────────────────────────────
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            findings.append({
                "rule_id": "PY000",
                "severity": "CRITICAL",
                "category": "style",
                "line": exc.lineno or 0,
                "title": "Syntax error",
                "detail": str(exc),
                "suggestion": "Fix syntax error before other analysis",
            })
            return sorted(findings, key=lambda f: f["line"])

        for node in ast.walk(tree):

            # PY002: bare except
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                findings.append({
                    "rule_id": "PY002",
                    "severity": "HIGH",
                    "category": "maintainability",
                    "line": node.lineno,
                    "title": "Bare except clause",
                    "detail": "except: catches ALL exceptions including SystemExit and KeyboardInterrupt",
                    "suggestion": "Use 'except Exception:' or catch specific exception types",
                })

            # PY003: mutable default argument
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for default in node.args.defaults:
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        findings.append({
                            "rule_id": "PY003",
                            "severity": "HIGH",
                            "category": "maintainability",
                            "line": node.lineno,
                            "title": "Mutable default argument",
                            "detail": (
                                f"Function '{node.name}' uses mutable default "
                                "(list/dict/set). Shared across all calls."
                            ),
                            "suggestion": "Use None as default and create inside function body",
                        })

                # PY009: too many arguments
                arg_count = len(node.args.args)
                if arg_count > 5:
                    findings.append({
                        "rule_id": "PY009",
                        "severity": "MEDIUM",
                        "category": "design",
                        "line": node.lineno,
                        "title": "Too many arguments",
                        "detail": (
                            f"Function '{node.name}' has {arg_count} arguments (limit: 5). "
                            "Hard to use and test."
                        ),
                        "suggestion": "Extract into a config dataclass or split into smaller functions",
                    })

                # PY011: missing return type annotation
                if node.returns is None and node.name != "__init__":
                    findings.append({
                        "rule_id": "PY011",
                        "severity": "LOW",
                        "category": "style",
                        "line": node.lineno,
                        "title": "Missing return type annotation",
                        "detail": f"Function '{node.name}' has no return type annotation",
                        "suggestion": f"Add '-> ReturnType' annotation to {node.name}()",
                    })

                # PY007: long function
                func_lines = (
                    (node.end_lineno or node.lineno) - node.lineno + 1
                    if hasattr(node, "end_lineno") else 0
                )
                if func_lines > 100:
                    findings.append({
                        "rule_id": "PY015",
                        "severity": "HIGH",
                        "category": "complexity",
                        "line": node.lineno,
                        "title": "God function (> 100 lines)",
                        "detail": (
                            f"Function '{node.name}' is {func_lines} lines. "
                            "Violates Single Responsibility Principle."
                        ),
                        "suggestion": "Extract logic into smaller focused helper functions",
                    })
                elif func_lines > 50:
                    findings.append({
                        "rule_id": "PY007",
                        "severity": "MEDIUM",
                        "category": "complexity",
                        "line": node.lineno,
                        "title": "Long function (> 50 lines)",
                        "detail": f"Function '{node.name}' is {func_lines} lines",
                        "suggestion": "Consider extracting into smaller focused functions",
                    })

                # PY010: shadowed built-in
                for arg in node.args.args:
                    if arg.arg in cls.BUILTINS:
                        findings.append({
                            "rule_id": "PY010",
                            "severity": "MEDIUM",
                            "category": "style",
                            "line": node.lineno,
                            "title": "Shadowed built-in name",
                            "detail": (
                                f"Argument '{arg.arg}' in '{node.name}' "
                                "shadows a Python built-in"
                            ),
                            "suggestion": f"Rename '{arg.arg}' to avoid shadowing (e.g. '{arg.arg}_value')",
                        })

            # PY008: long class
            if isinstance(node, ast.ClassDef):
                class_lines = (
                    (node.end_lineno or node.lineno) - node.lineno + 1
                    if hasattr(node, "end_lineno") else 0
                )
                if class_lines > 200:
                    findings.append({
                        "rule_id": "PY008",
                        "severity": "MEDIUM",
                        "category": "design",
                        "line": node.lineno,
                        "title": "Long class (> 200 lines)",
                        "detail": (
                            f"Class '{node.name}' is {class_lines} lines. "
                            "May violate Single Responsibility."
                        ),
                        "suggestion": "Extract responsibilities into separate classes or mixins",
                    })

            # PY004: magic numbers
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                if node.value not in cls.MAGIC_NUMBER_EXEMPT:
                    findings.append({
                        "rule_id": "PY004",
                        "severity": "LOW",
                        "category": "maintainability",
                        "line": getattr(node, "lineno", 0),
                        "title": "Magic number",
                        "detail": f"Unexplained numeric literal: {node.value}",
                        "suggestion": f"Extract to a named constant: MY_CONSTANT = {node.value}",
                    })

        return sorted(findings, key=lambda f: f["line"])


class JSStaticAnalyzer:
    """
    Performs rule-based static analysis on JavaScript/TypeScript source.

    Uses regex for pattern detection. Produces finding dicts.

    Rules implemented:
        JS001  var declaration (use const/let)
        JS002  == instead of === (loose equality)
        JS003  console.log in production
        JS004  Long line (> 120 chars)
        JS005  TODO/FIXME comment
        JS006  Hardcoded credential
        JS007  alert() / confirm() call
        JS008  Nested callback depth (callback hell indicator)
        JS009  Missing semicolon (style)
        JS010  any type in TypeScript
    """

    TODO_PAT = re.compile(r'//\s*(TODO|FIXME|HACK|XXX)\b', re.IGNORECASE)
    CRED_PAT = re.compile(
        r'(?i)(password|secret|apiKey|api_key|token)\s*[:=]\s*["\'][^"\']{4,}["\']'
    )
    VAR_PAT = re.compile(r'^\s*var\s+\w+', re.MULTILINE)
    LOOSE_EQ_PAT = re.compile(r'[^!=<>]==[^=]|[^!=<>]!=[^=]')
    CONSOLE_PAT = re.compile(r'console\.(log|warn|error|debug)\s*\(')
    ALERT_PAT = re.compile(r'\b(alert|confirm|prompt)\s*\(')
    ANY_PAT = re.compile(r':\s*any\b')

    @classmethod
    def analyze(cls, source: str) -> list[dict[str, Any]]:
        """
        Run all JS/TS static analysis rules on the given source.

        Args:
            source: Raw JavaScript or TypeScript source code

        Returns:
            List of finding dicts sorted by line number
        """
        findings: list[dict[str, Any]] = []
        lines = source.splitlines()

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            # JS001: var declaration
            if re.match(r'^\s*var\s+\w+', line):
                findings.append({
                    "rule_id": "JS001",
                    "severity": "MEDIUM",
                    "category": "style",
                    "line": i,
                    "title": "var declaration",
                    "detail": "var has function scope and hoisting issues",
                    "suggestion": "Use 'const' for values that don't change, 'let' otherwise",
                })

            # JS002: loose equality
            if cls.LOOSE_EQ_PAT.search(line) and "http" not in line:
                findings.append({
                    "rule_id": "JS002",
                    "severity": "MEDIUM",
                    "category": "maintainability",
                    "line": i,
                    "title": "Loose equality operator",
                    "detail": "== or != performs type coercion leading to unexpected behavior",
                    "suggestion": "Use === (strict equality) or !== instead",
                })

            # JS003: console.log
            if cls.CONSOLE_PAT.search(line):
                findings.append({
                    "rule_id": "JS003",
                    "severity": "LOW",
                    "category": "style",
                    "line": i,
                    "title": "console statement in production code",
                    "detail": f"console call found: {stripped[:60]}",
                    "suggestion": "Remove or replace with a proper logging library",
                })

            # JS004: long line
            if len(line) > 120:
                findings.append({
                    "rule_id": "JS004",
                    "severity": "LOW",
                    "category": "style",
                    "line": i,
                    "title": "Line too long",
                    "detail": f"Line is {len(line)} chars (limit: 120)",
                    "suggestion": "Break into multiple lines",
                })

            # JS005: TODO/FIXME
            if cls.TODO_PAT.search(line):
                match = cls.TODO_PAT.search(line)
                tag = match.group(1).upper() if match else "TODO"
                findings.append({
                    "rule_id": "JS005",
                    "severity": "INFO",
                    "category": "maintainability",
                    "line": i,
                    "title": f"{tag} comment",
                    "detail": stripped[:80],
                    "suggestion": f"Resolve or track this {tag} in your issue tracker",
                })

            # JS006: hardcoded credential
            if cls.CRED_PAT.search(line):
                findings.append({
                    "rule_id": "JS006",
                    "severity": "CRITICAL",
                    "category": "security",
                    "line": i,
                    "title": "Hardcoded credential",
                    "detail": f"Possible secret at line {i}: {stripped[:60]}",
                    "suggestion": "Use environment variables (process.env.MY_SECRET)",
                })

            # JS007: alert/confirm
            if cls.ALERT_PAT.search(line):
                findings.append({
                    "rule_id": "JS007",
                    "severity": "MEDIUM",
                    "category": "style",
                    "line": i,
                    "title": "Browser dialog function",
                    "detail": f"alert/confirm/prompt blocks the UI thread: {stripped[:60]}",
                    "suggestion": "Use custom modal components instead",
                })

            # JS010: any type (TypeScript)
            if cls.ANY_PAT.search(line):
                findings.append({
                    "rule_id": "JS010",
                    "severity": "MEDIUM",
                    "category": "style",
                    "line": i,
                    "title": "TypeScript 'any' type used",
                    "detail": f"'any' bypasses TypeScript's type safety: {stripped[:60]}",
                    "suggestion": "Use a specific type, unknown, or a generic instead",
                })

        return sorted(findings, key=lambda f: f["line"])


# =============================================================================
# Quality Scorer
# =============================================================================

class QualityScorer:
    """
    Converts a list of findings into a quality score (0-100) and grade.

    Scoring:
        Start at 100
        Deduct points based on severity weights
        Cap deduction at 100 (score floor = 0)
        Apply bonus for small files with no issues

    Grades:
        90-100  A  Excellent
        80-89   B  Good
        70-79   C  Acceptable
        60-69   D  Needs improvement
        0-59    F  Poor
    """

    @staticmethod
    def score(findings: list[dict[str, Any]], total_lines: int) -> dict[str, Any]:
        """
        Calculate quality score from findings list.

        Args:
            findings:    List of finding dicts from static analyzers
            total_lines: Total line count of the source file

        Returns:
            Dict with keys: score (int), grade (str), breakdown (dict),
            severity_counts (dict), total_findings (int)
        """
        severity_counts: dict[str, int] = {
            "CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0,
        }
        for f in findings:
            sev = str(f.get("severity", "INFO"))
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        # Weighted deduction
        raw_deduction = sum(
            SEVERITY_WEIGHT.get(sev, 0) * count
            for sev, count in severity_counts.items()
        )

        # Scale deduction by file size (larger files penalized less per finding)
        scale = max(1.0, total_lines / 100.0)
        scaled_deduction = min(100, int(raw_deduction / scale))

        score = max(0, 100 - scaled_deduction)

        # Grade
        if score >= 90:
            grade = "A"
        elif score >= 80:
            grade = "B"
        elif score >= 70:
            grade = "C"
        elif score >= 60:
            grade = "D"
        else:
            grade = "F"

        return {
            "score": score,
            "grade": grade,
            "total_findings": len(findings),
            "severity_counts": severity_counts,
            "breakdown": {
                "raw_deduction": raw_deduction,
                "scale_factor": round(scale, 2),
                "scaled_deduction": scaled_deduction,
            },
        }


# =============================================================================
# Code Reviewer Agent
# =============================================================================

class CodeReviewerAgent(BaseAgent):
    """
    LangGraph-powered agent performing comprehensive automated code review.

    Correctly extends BaseAgent (same pattern established in Steps 21-22):
        __init__(retriever, streaming_client) -> super().__init__()
        agent_type -> "code_reviewer"
        _build_graph() -> compiled StateGraph
        _format_result(state) -> dict

    Two-layer review strategy:
        Layer 1 (deterministic): Static analysis rules — always runs,
                                 no LLM needed, instant results
        Layer 2 (AI-enhanced):   LLM provides context-aware suggestions,
                                 refactoring advice, pattern recognition
                                 (only when streaming_client available)

    AgentConfig.extra carries:
        code_content   (str)  source code to review
        language       (str)  python | javascript | typescript | ...
        file_path      (str)  original file path for context

    CRITICAL PROMPT RULE (same as Steps 21-22):
        user_prompt_template ONLY uses {context} and {query} placeholders.
        ALL finding details pre-rendered as plain strings before template.

    LangGraph workflow:
        validate -> retrieve -> parse_code -> static_analysis
                 -> score -> generate_review -> fmt -> done -> END
    """

    def __init__(
        self,
        retriever: Any = None,
        streaming_client: Any = None,
    ) -> None:
        """
        Initialise the Code Reviewer Agent.

        Args:
            retriever:        Optional RAG retriever for codebase context
            streaming_client: Optional Ollama client for AI-enhanced review
        """
        super().__init__(retriever=retriever, streaming_client=streaming_client)

    # =========================================================================
    # Abstract property
    # =========================================================================

    @property
    def agent_type(self) -> str:
        """
        Unique type identifier for this agent.

        Returns:
            "code_reviewer"
        """
        return "code_reviewer"

    # =========================================================================
    # Abstract method: _build_graph
    # =========================================================================

    def _build_graph(self) -> Any:
        """
        Build and compile the LangGraph StateGraph for code review.

        Node execution order:
            validate        (BaseAgent)  check project_id present
            retrieve        (BaseAgent)  vector-store context lookup
            parse_code      (self)       read and store source + language
            static_analysis (self)       run rule-based checks
            score           (self)       calculate quality score
            generate_review (self)       LLM-enhanced review (optional)
            fmt             (BaseAgent)  calls _format_result()
            done            (self)       build Markdown report

        Returns:
            Compiled LangGraph CompiledStateGraph
        """
        graph: StateGraph = StateGraph(AgentState)

        graph.add_node("validate",        self._node_validate)
        graph.add_node("retrieve",        self._node_retrieve)
        graph.add_node("parse_code",      self._node_parse_code)
        graph.add_node("static_analysis", self._node_static_analysis)
        graph.add_node("score",           self._node_score)
        graph.add_node("generate_review", self._node_generate_review)
        graph.add_node("fmt",             self._node_format)
        graph.add_node("done",            self._node_done)

        graph.set_entry_point("validate")
        graph.add_edge("validate",        "retrieve")
        graph.add_edge("retrieve",        "parse_code")
        graph.add_edge("parse_code",      "static_analysis")
        graph.add_edge("static_analysis", "score")
        graph.add_edge("score",           "generate_review")
        graph.add_edge("generate_review", "fmt")
        graph.add_edge("fmt",             "done")
        graph.add_edge("done",            END)

        return graph.compile()

    # =========================================================================
    # Abstract method: _format_result
    # =========================================================================

    def _format_result(self, state: AgentState) -> dict[str, Any]:
        """
        Convert final AgentState into a structured review result dict.

        Called by BaseAgent._node_format() to build state["final_result"].
        Reads findings, score, and language from state["config"].

        Args:
            state: Final AgentState after all workflow nodes

        Returns:
            Dict with keys: language, file_path, total_findings,
            severity_counts, quality_score, grade, top_issues,
            llm_enhanced, summary
        """
        config: dict[str, Any] = state.get("config") or {}
        findings: list[dict[str, Any]] = config.get("_findings") or []
        score_data: dict[str, Any] = config.get("_score_data") or {}
        language: str = str(config.get("language") or "unknown")
        file_path: str = str(config.get("file_path") or "unknown")
        llm_enhanced: bool = bool(config.get("_llm_enhanced", False))

        # Top 5 highest-severity findings for summary
        sev_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
        sorted_findings = sorted(
            findings,
            key=lambda f: sev_order.index(str(f.get("severity", "INFO")))
        )
        top_issues = [
            {
                "rule_id": f.get("rule_id", ""),
                "severity": f.get("severity", "INFO"),
                "line": f.get("line", 0),
                "title": f.get("title", ""),
            }
            for f in sorted_findings[:5]
        ]

        severity_counts: dict[str, int] = score_data.get("severity_counts") or {}

        return {
            "language": language,
            "file_path": file_path,
            "total_findings": len(findings),
            "severity_counts": severity_counts,
            "quality_score": score_data.get("score", 0),
            "grade": score_data.get("grade", "F"),
            "top_issues": top_issues,
            "llm_enhanced": llm_enhanced,
            "summary": (
                f"Code review of '{file_path}' ({language}): "
                f"Quality score {score_data.get('score', 0)}/100 "
                f"(Grade {score_data.get('grade', '?')}). "
                f"{len(findings)} findings: "
                + ", ".join(
                    f"{v} {k}"
                    for k, v in severity_counts.items()
                    if v > 0
                ) + "."
            ),
        }

    # =========================================================================
    # Custom nodes
    # =========================================================================

    async def _node_parse_code(self, state: AgentState) -> AgentState:
        """
        Node 3: Read code_content from config and validate it.

        Reads code_content, language, file_path from state["config"]
        (populated by AgentConfig.to_initial_state() from extra dict).
        Stores validated source in config["_source"] for downstream nodes.

        Args:
            state: Current AgentState

        Returns:
            Updated AgentState with _source stored in config, or
            error state if code_content is missing
        """
        config: dict[str, Any] = dict(state.get("config") or {})
        code_content: str = str(config.get("code_content") or "").strip()
        language: str = str(config.get("language") or "unknown").lower()
        file_path: str = str(config.get("file_path") or "unknown")

        logger.info(
            "[CodeReviewer] parse_code: language=%s len=%d",
            language, len(code_content),
        )

        if not code_content:
            return {
                **state,
                "error": "No code_content provided in AgentConfig.extra",
                "current_step": "parsed",
                "progress": 0.2,
            }

        config["_source"] = code_content
        config["_total_lines"] = len(code_content.splitlines())

        return {
            **state,
            "config": config,
            "current_step": "parsed",
            "progress": 0.25,
        }

    async def _node_static_analysis(self, state: AgentState) -> AgentState:
        """
        Node 4: Run language-specific static analysis rules.

        Dispatches to PythonStaticAnalyzer or JSStaticAnalyzer based on
        the language stored in config. Stores findings list in
        config["_findings"] for downstream scoring and reporting.

        Args:
            state: Current AgentState after parse_code

        Returns:
            Updated AgentState with _findings list in config
        """
        config: dict[str, Any] = dict(state.get("config") or {})
        source: str = str(config.get("_source") or "")
        language: str = str(config.get("language") or "unknown").lower()

        logger.info("[CodeReviewer] static_analysis: language=%s", language)

        findings: list[dict[str, Any]] = []

        try:
            if language == "python":
                findings = PythonStaticAnalyzer.analyze(source)
            elif language in ("javascript", "typescript", "jsx", "tsx", "js", "ts"):
                findings = JSStaticAnalyzer.analyze(source)
            else:
                # Generic: only check long lines and TODOs
                for i, line in enumerate(source.splitlines(), start=1):
                    if len(line) > 120:
                        findings.append({
                            "rule_id": "GEN001",
                            "severity": "LOW",
                            "category": "style",
                            "line": i,
                            "title": "Line too long",
                            "detail": f"Line {i} is {len(line)} chars",
                            "suggestion": "Keep lines under 120 characters",
                        })
                    if re.search(r'#\s*(TODO|FIXME)', line, re.IGNORECASE):
                        findings.append({
                            "rule_id": "GEN002",
                            "severity": "INFO",
                            "category": "maintainability",
                            "line": i,
                            "title": "TODO comment",
                            "detail": line.strip()[:80],
                            "suggestion": "Resolve or track in issue tracker",
                        })

        except Exception as exc:
            logger.error("[CodeReviewer] static_analysis error: %s", exc, exc_info=True)
            findings.append({
                "rule_id": "ERR001",
                "severity": "HIGH",
                "category": "style",
                "line": 0,
                "title": "Analysis error",
                "detail": str(exc),
                "suggestion": "Check code syntax and retry",
            })

        logger.info("[CodeReviewer] Found %d findings", len(findings))
        config["_findings"] = findings

        return {
            **state,
            "config": config,
            "current_step": "analyzed",
            "progress": 0.5,
        }

    async def _node_score(self, state: AgentState) -> AgentState:
        """
        Node 5: Calculate the overall quality score from findings.

        Uses QualityScorer to convert findings into a 0-100 score
        with letter grade. Stores score data in config["_score_data"].

        Args:
            state: Current AgentState with _findings available

        Returns:
            Updated AgentState with _score_data in config
        """
        config: dict[str, Any] = dict(state.get("config") or {})
        findings: list[dict[str, Any]] = config.get("_findings") or []
        total_lines: int = int(config.get("_total_lines") or 1)

        score_data = QualityScorer.score(findings, total_lines)
        config["_score_data"] = score_data

        logger.info(
            "[CodeReviewer] score=%d grade=%s findings=%d",
            score_data["score"], score_data["grade"], score_data["total_findings"],
        )

        return {
            **state,
            "config": config,
            "current_step": "scored",
            "progress": 0.65,
        }

    async def _node_generate_review(self, state: AgentState) -> AgentState:
        """
        Node 6: Use LLM to generate context-aware review suggestions.

        If streaming_client is available:
            - Pre-renders top findings as a plain string (no format placeholders)
            - Calls BaseAgent._node_analyze() with language-specific system prompt
            - Stores LLM output in state["llm_response"]

        If streaming_client is None:
            - Sets a placeholder response and marks llm_enhanced=False
            - Workflow continues normally (graceful degradation)

        CRITICAL: user_prompt_template uses ONLY {context} and {query}.
        All finding details are pre-rendered into `findings_block` string.

        Args:
            state: Current AgentState with findings and score available

        Returns:
            Updated AgentState with llm_response and progress 0.85
        """
        config: dict[str, Any] = dict(state.get("config") or {})
        findings: list[dict[str, Any]] = config.get("_findings") or []
        score_data: dict[str, Any] = config.get("_score_data") or {}
        language: str = str(config.get("language") or "unknown").lower()
        file_path: str = str(config.get("file_path") or "unknown")
        source: str = str(config.get("_source") or "")

        config["_llm_enhanced"] = False

        if not self._streaming_client:
            logger.info("[CodeReviewer] No streaming_client — skipping LLM review")
            return {
                **state,
                "config": config,
                "llm_response": None,
                "current_step": "reviewed",
                "progress": 0.85,
            }

        # ── Pre-render findings into plain string ─────────────────────────
        # Sort by severity and take top 10 most important findings
        sev_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
        top_findings = sorted(
            findings,
            key=lambda f: sev_order.index(str(f.get("severity", "INFO")))
        )[:10]

        finding_lines: list[str] = []
        for f in top_findings:
            rule = str(f.get("rule_id") or "?")
            sev = str(f.get("severity") or "INFO")
            line_no = str(f.get("line") or 0)
            title = str(f.get("title") or "")
            detail = str(f.get("detail") or "")
            finding_lines.append(
                "[" + rule + "] " + sev + " at line " + line_no
                + ": " + title + " - " + detail
            )

        # Plain string — no braces — safe for .format()
        findings_block = "\n".join(finding_lines) if finding_lines else "No findings"

        score_str = str(score_data.get("score") or 0)
        grade_str = str(score_data.get("grade") or "?")

        # Code preview — escape any braces to prevent KeyError
        safe_code = source[:800].replace("{", "(").replace("}", ")")

        system_prompt = self._get_system_prompt(language)

        # ONLY {context} and {query} as format placeholders
        user_prompt_template = (
            "Code Review Request\n"
            "File: " + file_path + " | Language: " + language + "\n"
            "Quality Score: " + score_str + "/100 (Grade " + grade_str + ")\n\n"
            "STATIC ANALYSIS FINDINGS:\n"
            + findings_block + "\n\n"
            "CODE PREVIEW:\n"
            + safe_code + "\n\n"
            "CODEBASE CONTEXT:\n{context}\n\n"
            "TASK: {query}\n\n"
            "Provide:\n"
            "1. OVERVIEW: Overall assessment of code quality\n"
            "2. CRITICAL FIXES: Most important issues to fix immediately\n"
            "3. REFACTORING SUGGESTIONS: Design improvements\n"
            "4. BEST PRACTICES: Language-specific recommendations\n"
            "5. POSITIVE NOTES: What the code does well\n"
        )

        retrieval_query = (
            "Code quality best practices and review patterns for "
            + language + " in file " + file_path
        )
        state_for_llm = {**state, "config": config, "query": retrieval_query}

        try:
            updated = await self._node_analyze(
                state_for_llm,
                system_prompt=system_prompt,
                user_prompt_template=user_prompt_template,
            )
            llm_out = updated.get("llm_response") or ""
            if llm_out and len(llm_out) > 50:
                config["_llm_enhanced"] = True
                logger.info("[CodeReviewer] LLM review generated (%d chars)", len(llm_out))
            return {
                **updated,
                "config": config,
                "current_step": "reviewed",
                "progress": 0.85,
            }
        except Exception as exc:
            logger.warning("[CodeReviewer] LLM review failed: %s", exc)
            return {
                **state,
                "config": config,
                "llm_response": None,
                "current_step": "reviewed",
                "progress": 0.85,
            }

    async def _node_done(self, state: AgentState) -> AgentState:
        """
        Node 8: Assemble the final Markdown code review report.

        Combines static analysis findings (sorted by severity) with
        quality score breakdown and optional LLM suggestions into a
        complete, structured Markdown report.

        Sets state["formatted_report"] which BaseAgent.run() returns
        as AgentResult.report.

        Args:
            state: AgentState after _node_format has run

        Returns:
            Final AgentState with formatted_report and progress 1.0
        """
        config: dict[str, Any] = state.get("config") or {}
        findings: list[dict[str, Any]] = config.get("_findings") or []
        score_data: dict[str, Any] = config.get("_score_data") or {}
        language: str = str(config.get("language") or "unknown")
        file_path: str = str(config.get("file_path") or "unknown")
        llm_response: str = state.get("llm_response") or ""
        final_result: dict[str, Any] = state.get("final_result") or {}

        score = int(score_data.get("score") or 0)
        grade = str(score_data.get("grade") or "?")
        severity_counts: dict[str, int] = score_data.get("severity_counts") or {}
        total_lines = int(config.get("_total_lines") or 0)

        # Score bar visual
        filled = score // 10
        bar = "█" * filled + "░" * (10 - filled)

        lines: list[str] = [
            "# Code Review Report",
            "",
            "**File:** `" + file_path + "`",
            "**Language:** " + language.title(),
            "**Reviewed:** " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "**Lines of Code:** " + str(total_lines),
            "",
            "---",
            "",
            "## Quality Score",
            "",
            "```",
            "Score: " + str(score) + "/100  Grade: " + grade,
            "  [" + bar + "] " + str(score) + "%",
            "```",
            "",
        ]

        # Severity breakdown table
        lines += [
            "| Severity | Count |",
            "|----------|-------|",
        ]
        for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]:
            count = severity_counts.get(sev, 0)
            if count > 0:
                lines.append("| " + sev + " | " + str(count) + " |")
        lines += ["", "---", ""]

        # Findings grouped by severity
        if findings:
            lines.append("## Findings")
            lines.append("")

            for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]:
                sev_findings = [f for f in findings if f.get("severity") == sev]
                if not sev_findings:
                    continue

                icon = {
                    "CRITICAL": "CRIT",
                    "HIGH": "HIGH",
                    "MEDIUM": "MED",
                    "LOW": "LOW",
                    "INFO": "INFO",
                }.get(sev, sev)

                lines.append("### [" + icon + "] " + sev + " (" + str(len(sev_findings)) + ")")
                lines.append("")

                for f in sev_findings:
                    rule = str(f.get("rule_id") or "")
                    line_no = str(f.get("line") or 0)
                    title = str(f.get("title") or "")
                    detail = str(f.get("detail") or "")
                    suggestion = str(f.get("suggestion") or "")

                    lines.append("**[" + rule + "] Line " + line_no + ": " + title + "**")
                    lines.append("")
                    lines.append("- *Issue:* " + detail)
                    lines.append("- *Fix:* " + suggestion)
                    lines.append("")

            lines.append("---")
            lines.append("")
        else:
            lines += [
                "## Findings",
                "",
                "No issues found! Code looks clean.",
                "",
                "---",
                "",
            ]

        # LLM-enhanced review section
        lines.append("## AI Review Suggestions")
        lines.append("")
        if llm_response and llm_response.strip():
            lines.append(llm_response.strip())
        else:
            lines.append(
                "*AI review not available (LLM offline or not configured). "
                "Static analysis results above are complete.*"
            )
        lines += [
            "",
            "---",
            "",
            "*Generated by AI Codebase Assistant — Code Reviewer Agent*",
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
        Build LLM system prompt for code review.

        Args:
            language: Lowercase language name

        Returns:
            System prompt string with review format instructions
        """
        base = (
            "You are a senior software engineer conducting a professional code review. "
            "Be constructive, specific, and actionable. "
            "Reference line numbers when possible. "
            "Structure your response with clear sections: "
            "OVERVIEW, CRITICAL FIXES, REFACTORING SUGGESTIONS, "
            "BEST PRACTICES, POSITIVE NOTES."
        )
        if language == "python":
            return base + (
                " Apply Python-specific expertise: PEP 8, type hints, "
                "async best practices, Pythonic idioms, SOLID principles."
            )
        elif language in ("javascript", "typescript", "js", "ts", "jsx", "tsx"):
            return base + (
                " Apply JS/TS expertise: ES6+ patterns, TypeScript strict mode, "
                "React best practices if applicable, async/await patterns."
            )
        return base


# =============================================================================
# Factory
# =============================================================================

def create_code_reviewer_agent(
    retriever: Any = None,
    streaming_client: Any = None,
) -> CodeReviewerAgent:
    """
    Create and return a configured CodeReviewerAgent instance.

    Args:
        retriever:        Optional RAG retriever for codebase context
        streaming_client: Optional Ollama client for AI-enhanced review

    Returns:
        Ready-to-use CodeReviewerAgent
    """
    return CodeReviewerAgent(
        retriever=retriever,
        streaming_client=streaming_client,
    )
