"""
Code Refactor Suggester Agent - Step 25
AI Codebase Assistant v2.0

Analyzes code and suggests concrete refactoring improvements:
    SOLID Principles:
        S - Single Responsibility (God classes/functions)
        O - Open/Closed (hardcoded switch/if chains)
        L - Liskov Substitution (improper inheritance)
        I - Interface Segregation (fat interfaces)
        D - Dependency Inversion (hardcoded dependencies)
    DRY - Duplicate code block detection
    KISS - Overly complex logic that can be simplified
    Design Patterns - Missing Strategy, Factory, Observer opportunities
    Naming - Poor variable/function names
    Magic Values - Inline constants that should be named

Each suggestion includes:
    - Issue category and severity
    - Affected lines
    - Before code (what it is now)
    - After code (what it should be)
    - Explanation of why this improves the code

Correctly extends BaseAgent (same pattern as Steps 21-24).
CRITICAL: user_prompt_template uses ONLY {context} {query} {project_id}
"""

from __future__ import annotations

import ast
import hashlib
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
# Refactor Suggestion Schema
# =============================================================================
# Each suggestion dict has keys:
#   refactor_id   (str)  unique ID e.g. "REF-001"
#   principle     (str)  SOLID-S | SOLID-O | DRY | KISS | NAMING | PATTERN
#   severity      (str)  HIGH | MEDIUM | LOW
#   line_start    (int)  start line of affected code
#   line_end      (int)  end line of affected code
#   title         (str)  short description
#   problem       (str)  what is wrong and why
#   before_code   (str)  current code snippet
#   after_code    (str)  suggested refactored code
#   benefit       (str)  what improves after refactoring


PRINCIPLE_PRIORITY = {
    "SOLID-S": 1,
    "SOLID-D": 2,
    "DRY":     3,
    "SOLID-O": 4,
    "KISS":    5,
    "PATTERN": 6,
    "NAMING":  7,
}


# =============================================================================
# Duplicate Code Detector
# =============================================================================

class DuplicateCodeDetector:
    """
    Detects duplicate or near-duplicate code blocks using line hashing.

    Strategy:
        1. Normalize each line (strip whitespace, remove comments)
        2. Create overlapping windows of N lines
        3. Hash each window
        4. Flag windows that appear more than once
    """

    MIN_BLOCK_LINES = 4   # minimum lines to consider as duplicate
    SIMILARITY_THRESHOLD = 0.85

    @classmethod
    def find_duplicates(
        cls, source: str
    ) -> list[dict[str, Any]]:
        """
        Find duplicate code blocks in source using sliding window hashing.

        Args:
            source: Raw source code string

        Returns:
            List of duplicate block dicts with line ranges and content
        """
        lines = source.splitlines()
        if len(lines) < cls.MIN_BLOCK_LINES * 2:
            return []

        normalized: list[str] = []
        for line in lines:
            # Strip whitespace and inline comments for comparison
            stripped = line.strip()
            stripped = re.sub(r'#.*$', '', stripped).strip()   # Python comments
            stripped = re.sub(r'//.*$', '', stripped).strip()  # JS comments
            stripped = re.sub(r'\s+', ' ', stripped)
            normalized.append(stripped)

        window = cls.MIN_BLOCK_LINES
        seen: dict[str, list[int]] = {}

        for i in range(len(normalized) - window + 1):
            block = normalized[i:i + window]
            # Skip blocks that are mostly empty
            non_empty = [l for l in block if len(l) > 3]
            if len(non_empty) < window // 2:
                continue
            block_hash = hashlib.md5("\n".join(block).encode()).hexdigest()
            if block_hash not in seen:
                seen[block_hash] = []
            seen[block_hash].append(i)

        duplicates: list[dict[str, Any]] = []
        reported: set[str] = set()

        for block_hash, positions in seen.items():
            if len(positions) < 2:
                continue
            # Take first two occurrences
            pos_a, pos_b = positions[0], positions[1]
            key = f"{pos_a}-{pos_b}"
            if key in reported:
                continue
            reported.add(key)

            block_lines = lines[pos_a:pos_a + window]
            before_snippet = "\n".join(block_lines)

            duplicates.append({
                "line_start_a": pos_a + 1,
                "line_end_a": pos_a + window,
                "line_start_b": pos_b + 1,
                "line_end_b": pos_b + window,
                "block_content": before_snippet,
                "occurrences": len(positions),
            })

        return duplicates[:5]  # cap at 5 duplicate groups


# =============================================================================
# Python Refactor Analyzer
# =============================================================================

class PythonRefactorAnalyzer:
    """
    AST-based refactor analyzer for Python source code.

    Detects:
        REF-PY-001  God function (> 40 lines, > 10 complexity)
        REF-PY-002  God class (> 10 methods, > 300 lines)
        REF-PY-003  Long parameter list (> 4 params)
        REF-PY-004  Magic values (inline literals)
        REF-PY-005  Nested conditionals (depth > 2)
        REF-PY-006  Duplicate code blocks
        REF-PY-007  Feature envy (method uses another class heavily)
        REF-PY-008  Dead code (unreachable after return)
        REF-PY-009  Boolean flag parameters (control coupling)
        REF-PY-010  Long chained method calls
    """

    MAGIC_EXEMPT = frozenset([0, 1, -1, 2, 10, 100, 1000])

    @classmethod
    def analyze(cls, source: str) -> list[dict[str, Any]]:
        """
        Run all Python refactor analysis rules.

        Args:
            source: Raw Python source code

        Returns:
            List of refactor suggestion dicts
        """
        suggestions: list[dict[str, Any]] = []
        lines = source.splitlines()

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return suggestions

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                suggestions.extend(
                    cls._check_function(node, lines)
                )
            elif isinstance(node, ast.ClassDef):
                suggestions.extend(
                    cls._check_class(node, lines)
                )

        # Duplicate code detection
        dupes = DuplicateCodeDetector.find_duplicates(source)
        for dupe in dupes:
            suggestions.append(
                cls._make_duplicate_suggestion(dupe)
            )

        # Magic values scan
        suggestions.extend(cls._check_magic_values(tree, lines))

        return suggestions

    @classmethod
    def _check_function(
        cls,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        lines: list[str],
    ) -> list[dict[str, Any]]:
        """
        Check a function node for refactoring opportunities.

        Args:
            node:  AST function definition node
            lines: All source lines for snippet extraction

        Returns:
            List of suggestions for this function
        """
        suggestions: list[dict[str, Any]] = []
        func_name = node.name
        start = node.lineno - 1
        end = (node.end_lineno or node.lineno) - 1
        func_lines = end - start + 1
        func_snippet = "\n".join(lines[start:min(start + 15, len(lines))])

        # REF-PY-001: God function
        if func_lines > 40:
            complexity = cls._cyclomatic_complexity(node)
            if complexity > 5 or func_lines > 60:
                suggestions.append({
                    "refactor_id": "REF-PY-001",
                    "principle": "SOLID-S",
                    "severity": "HIGH",
                    "line_start": node.lineno,
                    "line_end": node.end_lineno or node.lineno,
                    "title": "God Function — Single Responsibility Violation",
                    "problem": (
                        "Function '" + func_name + "' is " + str(func_lines)
                        + " lines with cyclomatic complexity " + str(complexity)
                        + ". Violates Single Responsibility Principle. "
                        "Hard to test, understand, and maintain."
                    ),
                    "before_code": func_snippet,
                    "after_code": (
                        "# Split into focused helper functions:\n"
                        "def " + func_name + "_validate(...):\n"
                        "    \"\"\"Validate inputs only.\"\"\"\n"
                        "    ...\n\n"
                        "def " + func_name + "_process(...):\n"
                        "    \"\"\"Process logic only.\"\"\"\n"
                        "    ...\n\n"
                        "def " + func_name + "(...):\n"
                        "    \"\"\"Orchestrate: validate then process.\"\"\"\n"
                        "    " + func_name + "_validate(...)\n"
                        "    return " + func_name + "_process(...)"
                    ),
                    "benefit": (
                        "Each function has one job. Easier to test, "
                        "debug, and reuse independently."
                    ),
                })

        # REF-PY-003: Long parameter list
        args = [a for a in node.args.args if a.arg != "self"]
        if len(args) > 4:
            arg_names = [a.arg for a in args]
            suggestions.append({
                "refactor_id": "REF-PY-003",
                "principle": "SOLID-S",
                "severity": "MEDIUM",
                "line_start": node.lineno,
                "line_end": node.lineno,
                "title": "Long Parameter List — Extract Config Object",
                "problem": (
                    "Function '" + func_name + "' has "
                    + str(len(args)) + " parameters: "
                    + str(arg_names) + ". Hard to call correctly and test."
                ),
                "before_code": (
                    "def " + func_name + "("
                    + ", ".join(arg_names) + "):\n    ..."
                ),
                "after_code": (
                    "from dataclasses import dataclass\n\n"
                    "@dataclass\n"
                    "class " + func_name.title().replace("_", "") + "Config:\n"
                    + "".join(
                        "    " + a + ": Any = None\n" for a in arg_names
                    )
                    + "\n\ndef " + func_name
                    + "(config: " + func_name.title().replace("_", "") + "Config"
                    + ") -> Any:\n    ..."
                ),
                "benefit": (
                    "Config object is self-documenting, extensible without "
                    "breaking callers, and easy to create test fixtures for."
                ),
            })

        # REF-PY-009: Boolean flag parameter (control coupling)
        for arg in node.args.args:
            if any(
                kw in arg.arg.lower()
                for kw in ["flag", "is_", "use_", "enable", "disable", "mode"]
            ):
                suggestions.append({
                    "refactor_id": "REF-PY-009",
                    "principle": "SOLID-S",
                    "severity": "LOW",
                    "line_start": node.lineno,
                    "line_end": node.lineno,
                    "title": "Boolean Flag Parameter — Split Into Two Functions",
                    "problem": (
                        "Parameter '" + arg.arg + "' in '" + func_name
                        + "' acts as a flag controlling function behavior. "
                        "This is control coupling — the caller must know internals."
                    ),
                    "before_code": (
                        "def " + func_name + "(..., " + arg.arg + "=False):\n"
                        "    if " + arg.arg + ":\n"
                        "        # path A\n"
                        "    else:\n"
                        "        # path B"
                    ),
                    "after_code": (
                        "def " + func_name + "_with_flag(...):\n"
                        "    # path A only\n\n"
                        "def " + func_name + "(...):\n"
                        "    # path B only"
                    ),
                    "benefit": (
                        "Each function does one thing. No hidden branching. "
                        "Caller intent is explicit."
                    ),
                })

        # REF-PY-005: Deeply nested conditionals
        max_depth = cls._max_nesting_depth(node)
        if max_depth > 3:
            suggestions.append({
                "refactor_id": "REF-PY-005",
                "principle": "KISS",
                "severity": "MEDIUM",
                "line_start": node.lineno,
                "line_end": node.end_lineno or node.lineno,
                "title": "Deeply Nested Code — Apply Early Return Pattern",
                "problem": (
                    "Function '" + func_name + "' has nesting depth "
                    + str(max_depth) + ". Hard to follow logic flow. "
                    "Arrow anti-pattern."
                ),
                "before_code": (
                    "def " + func_name + "(x):\n"
                    "    if x:\n"
                    "        if x.valid:\n"
                    "            if x.active:\n"
                    "                # real logic buried here\n"
                    "                return result"
                ),
                "after_code": (
                    "def " + func_name + "(x):\n"
                    "    # Guard clauses — early returns for invalid states\n"
                    "    if not x:\n"
                    "        return None\n"
                    "    if not x.valid:\n"
                    "        return None\n"
                    "    if not x.active:\n"
                    "        return None\n"
                    "    # Main logic at top level — easy to read\n"
                    "    return result"
                ),
                "benefit": (
                    "Early return pattern eliminates nesting. "
                    "Main logic is at the top indentation level. "
                    "Much easier to read and test."
                ),
            })

        # REF-PY-008: Dead code after return
        for i, child in enumerate(node.body[:-1]):
            if isinstance(child, ast.Return):
                remaining = node.body[i + 1:]
                non_trivial = [
                    n for n in remaining
                    if not isinstance(n, (ast.Pass, ast.Expr))
                ]
                if non_trivial:
                    suggestions.append({
                        "refactor_id": "REF-PY-008",
                        "principle": "KISS",
                        "severity": "LOW",
                        "line_start": child.lineno,
                        "line_end": node.end_lineno or node.lineno,
                        "title": "Dead Code After Return Statement",
                        "problem": (
                            "Code exists after a return statement in '"
                            + func_name + "'. This code is unreachable "
                            "and misleading."
                        ),
                        "before_code": "    return result\n    # unreachable code below",
                        "after_code": "    return result\n    # remove all code after this",
                        "benefit": "Removes confusion and dead weight from the codebase.",
                    })
                break

        return suggestions

    @classmethod
    def _check_class(
        cls,
        node: ast.ClassDef,
        lines: list[str],
    ) -> list[dict[str, Any]]:
        """
        Check a class node for refactoring opportunities.

        Args:
            node:  AST ClassDef node
            lines: All source lines

        Returns:
            List of suggestions for this class
        """
        suggestions: list[dict[str, Any]] = []
        class_name = node.name
        start = node.lineno - 1
        end = (node.end_lineno or node.lineno) - 1
        class_lines = end - start + 1

        methods = [
            item for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        public_methods = [m for m in methods if not m.name.startswith("_")]

        # REF-PY-002: God class
        if len(methods) > 10 or class_lines > 300:
            method_names = [m.name for m in methods[:10]]
            suggestions.append({
                "refactor_id": "REF-PY-002",
                "principle": "SOLID-S",
                "severity": "HIGH",
                "line_start": node.lineno,
                "line_end": node.end_lineno or node.lineno,
                "title": "God Class — Single Responsibility Violation",
                "problem": (
                    "Class '" + class_name + "' has " + str(len(methods))
                    + " methods and " + str(class_lines) + " lines. "
                    "Doing too many things. Hard to test and extend."
                ),
                "before_code": (
                    "class " + class_name + ":\n"
                    + "".join(
                        "    def " + m + "(self): ...\n"
                        for m in method_names[:6]
                    )
                    + "    # ... " + str(len(methods) - 6) + " more methods"
                ),
                "after_code": (
                    "# Group related methods into focused classes:\n\n"
                    "class " + class_name + "Reader:\n"
                    "    \"\"\"Handles only read operations.\"\"\"\n"
                    "    ...\n\n"
                    "class " + class_name + "Writer:\n"
                    "    \"\"\"Handles only write operations.\"\"\"\n"
                    "    ...\n\n"
                    "class " + class_name + "Validator:\n"
                    "    \"\"\"Handles only validation.\"\"\"\n"
                    "    ..."
                ),
                "benefit": (
                    "Each class has one responsibility. "
                    "Can be tested, extended, and replaced independently. "
                    "Follows Single Responsibility Principle."
                ),
            })

        # Detect hardcoded dependency (Dependency Inversion)
        # Look for direct instantiation of other classes inside __init__
        for method in methods:
            if method.name == "__init__":
                for child in ast.walk(method):
                    if isinstance(child, ast.Call):
                        if isinstance(child.func, ast.Name):
                            dep_name = child.func.id
                            if (
                                dep_name[0].isupper()
                                and dep_name != class_name
                                and dep_name not in ("Exception", "ValueError",
                                                     "TypeError", "list",
                                                     "dict", "set")
                            ):
                                suggestions.append({
                                    "refactor_id": "REF-PY-DI",
                                    "principle": "SOLID-D",
                                    "severity": "MEDIUM",
                                    "line_start": method.lineno,
                                    "line_end": method.lineno + 5,
                                    "title": "Hardcoded Dependency — Inject Instead",
                                    "problem": (
                                        "Class '" + class_name
                                        + "' directly instantiates '"
                                        + dep_name + "' in __init__. "
                                        "Violates Dependency Inversion Principle. "
                                        "Cannot swap implementation for testing."
                                    ),
                                    "before_code": (
                                        "class " + class_name + ":\n"
                                        "    def __init__(self):\n"
                                        "        self.dep = " + dep_name + "()"
                                    ),
                                    "after_code": (
                                        "class " + class_name + ":\n"
                                        "    def __init__(self, dep: "
                                        + dep_name + " | None = None):\n"
                                        "        # Inject dependency — testable!\n"
                                        "        self.dep = dep or " + dep_name + "()"
                                    ),
                                    "benefit": (
                                        "Allows injecting a mock/stub in tests. "
                                        "Can swap " + dep_name
                                        + " implementation without changing "
                                        + class_name + "."
                                    ),
                                })
                                break  # one suggestion per class

        return suggestions

    @classmethod
    def _check_magic_values(
        cls,
        tree: ast.AST,
        lines: list[str],
    ) -> list[dict[str, Any]]:
        """
        Detect magic numeric and string literals that should be named constants.

        Args:
            tree:  Parsed AST
            lines: All source lines

        Returns:
            List of magic value suggestions (capped at 3)
        """
        suggestions: list[dict[str, Any]] = []
        seen_values: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Constant):
                val = node.value
                if isinstance(val, (int, float)) and val not in cls.MAGIC_EXEMPT:
                    key = str(val)
                    if key not in seen_values:
                        seen_values.add(key)
                        ln = getattr(node, "lineno", 0)
                        line_content = lines[ln - 1].strip() if ln > 0 else ""
                        suggestions.append({
                            "refactor_id": "REF-PY-004",
                            "principle": "NAMING",
                            "severity": "LOW",
                            "line_start": ln,
                            "line_end": ln,
                            "title": "Magic Number — Extract to Named Constant",
                            "problem": (
                                "Literal value " + str(val)
                                + " at line " + str(ln)
                                + " has no semantic meaning. "
                                "Readers cannot understand why this value."
                            ),
                            "before_code": line_content[:80],
                            "after_code": (
                                "# At module top:\n"
                                "MY_CONSTANT = " + str(val) + "\n\n"
                                "# In code:\n"
                                + line_content[:80].replace(str(val), "MY_CONSTANT")
                            ),
                            "benefit": (
                                "Named constants are self-documenting. "
                                "Change in one place reflects everywhere."
                            ),
                        })

        return suggestions[:3]

    @staticmethod
    def _make_duplicate_suggestion(dupe: dict[str, Any]) -> dict[str, Any]:
        """
        Build a refactor suggestion dict for a detected duplicate block.

        Args:
            dupe: Duplicate block metadata from DuplicateCodeDetector

        Returns:
            Refactor suggestion dict
        """
        content_preview = "\n".join(
            dupe["block_content"].splitlines()[:6]
        )
        return {
            "refactor_id": "REF-PY-006",
            "principle": "DRY",
            "severity": "HIGH",
            "line_start": dupe["line_start_a"],
            "line_end": dupe["line_end_a"],
            "title": "Duplicate Code Block — Extract to Function",
            "problem": (
                "Code block appears at lines "
                + str(dupe["line_start_a"]) + "-" + str(dupe["line_end_a"])
                + " and " + str(dupe["line_start_b"]) + "-"
                + str(dupe["line_end_b"])
                + " (" + str(dupe["occurrences"]) + " occurrences). "
                "Violates DRY principle. Bug fixes must be applied in multiple places."
            ),
            "before_code": content_preview,
            "after_code": (
                "# Extract into a reusable function:\n"
                "def extracted_logic(...):\n"
                "    # The duplicated code goes here\n"
                "    ...\n\n"
                "# Call from both locations:\n"
                "extracted_logic(...)"
            ),
            "benefit": (
                "Single source of truth. Fix bugs once. "
                "Improves readability and reduces maintenance burden."
            ),
        }

    @staticmethod
    def _cyclomatic_complexity(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> int:
        """
        Calculate approximate cyclomatic complexity for a function.

        Counts: branches (if/elif/else), loops (for/while),
        exception handlers (except), boolean operators (and/or).

        Args:
            node: AST function node

        Returns:
            Integer complexity score (1 = no branches)
        """
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For,
                                  ast.ExceptHandler, ast.With,
                                  ast.Assert)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        return complexity

    @staticmethod
    def _max_nesting_depth(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> int:
        """
        Find the maximum nesting depth of conditionals/loops in a function.

        Args:
            node: AST function node

        Returns:
            Maximum depth integer (0 = no nesting)
        """
        def depth(n: ast.AST, current: int) -> int:
            if isinstance(n, (ast.If, ast.For, ast.While, ast.With,
                               ast.Try, ast.ExceptHandler)):
                current += 1
            max_d = current
            for child in ast.iter_child_nodes(n):
                max_d = max(max_d, depth(child, current))
            return max_d

        return depth(node, 0)


# =============================================================================
# JavaScript / TypeScript Refactor Analyzer
# =============================================================================

class JSRefactorAnalyzer:
    """
    Regex-based refactor analyzer for JavaScript and TypeScript code.

    Detects:
        REF-JS-001  Long function (> 40 lines)
        REF-JS-002  var declarations (use const/let)
        REF-JS-003  Callback nesting (callback hell)
        REF-JS-004  Magic numbers
        REF-JS-005  Duplicate code blocks
        REF-JS-006  Long if-else chains (use object map)
        REF-JS-007  any type usage (TypeScript)
        REF-JS-008  Missing error handling in async functions
    """

    FUNC_PAT = re.compile(
        r"(?:function\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|"
        r"\w+)\s*=>)\s*\{",
        re.MULTILINE,
    )
    MAGIC_PAT = re.compile(r'(?<!["\'])\b(\d{2,})\b(?!["\'])')
    CALLBACK_PAT = re.compile(r'function\s*\([^)]*\)\s*\{[^}]*function\s*\(')
    ELSE_IF_PAT = re.compile(r'else\s+if\s*\(', re.MULTILINE)
    ANY_PAT = re.compile(r':\s*any\b')
    VAR_PAT = re.compile(r'^\s*var\s+\w+', re.MULTILINE)

    @classmethod
    def analyze(cls, source: str) -> list[dict[str, Any]]:
        """
        Run all JS/TS refactor analysis rules.

        Args:
            source: Raw JavaScript or TypeScript source code

        Returns:
            List of refactor suggestion dicts
        """
        suggestions: list[dict[str, Any]] = []
        lines = source.splitlines()

        # REF-JS-002: var declarations
        for i, line in enumerate(lines, start=1):
            if re.match(r'^\s*var\s+\w+', line):
                var_match = re.search(r'var\s+(\w+)', line)
                var_name = var_match.group(1) if var_match else "x"
                suggestions.append({
                    "refactor_id": "REF-JS-002",
                    "principle": "KISS",
                    "severity": "LOW",
                    "line_start": i,
                    "line_end": i,
                    "title": "var Declaration — Use const or let",
                    "problem": (
                        "var has function scope and hoisting. "
                        "Leads to hard-to-debug bugs. "
                        "ES6 const/let are block-scoped and safer."
                    ),
                    "before_code": "var " + var_name + " = ...;",
                    "after_code": (
                        "const " + var_name + " = ...;  "
                        "// if value never reassigned\n"
                        "let " + var_name + " = ...;    "
                        "// if value is reassigned"
                    ),
                    "benefit": "Block scoping prevents accidental variable leakage.",
                })

        # REF-JS-006: Long if-else chain (3+ else-if)
        else_if_matches = list(cls.ELSE_IF_PAT.finditer(source))
        if len(else_if_matches) >= 3:
            first_line = source[:else_if_matches[0].start()].count("\n") + 1
            suggestions.append({
                "refactor_id": "REF-JS-006",
                "principle": "SOLID-O",
                "severity": "MEDIUM",
                "line_start": first_line,
                "line_end": first_line + len(else_if_matches) * 3,
                "title": "Long if-else Chain — Replace with Object Map",
                "problem": (
                    "Found " + str(len(else_if_matches))
                    + " else-if branches. Adding new cases requires "
                    "modifying existing code (Open/Closed violation)."
                ),
                "before_code": (
                    "if (type === 'A') { handleA(); }\n"
                    "else if (type === 'B') { handleB(); }\n"
                    "else if (type === 'C') { handleC(); }"
                ),
                "after_code": (
                    "const handlers = {\n"
                    "    A: handleA,\n"
                    "    B: handleB,\n"
                    "    C: handleC,\n"
                    "};\n"
                    "// New cases: just add to the object, no if-else needed\n"
                    "const handler = handlers[type];\n"
                    "if (handler) handler();"
                ),
                "benefit": (
                    "Adding new cases doesn't require changing existing code. "
                    "Open/Closed Principle: open for extension, closed for modification."
                ),
            })

        # REF-JS-003: Callback hell
        if cls.CALLBACK_PAT.search(source):
            suggestions.append({
                "refactor_id": "REF-JS-003",
                "principle": "KISS",
                "severity": "HIGH",
                "line_start": 1,
                "line_end": 10,
                "title": "Callback Hell — Convert to async/await",
                "problem": (
                    "Nested callback functions create deeply indented "
                    "code that is hard to read, debug, and handle errors in."
                ),
                "before_code": (
                    "fetchUser(id, function(user) {\n"
                    "    fetchPosts(user, function(posts) {\n"
                    "        fetchComments(posts, function(comments) {\n"
                    "            // actual work buried at depth 3\n"
                    "        });\n"
                    "    });\n"
                    "});"
                ),
                "after_code": (
                    "async function loadUserData(id) {\n"
                    "    const user = await fetchUser(id);\n"
                    "    const posts = await fetchPosts(user);\n"
                    "    const comments = await fetchComments(posts);\n"
                    "    // actual work at depth 1\n"
                    "    return comments;\n"
                    "}"
                ),
                "benefit": (
                    "Linear, readable code. Easy try/catch error handling. "
                    "No pyramid of doom indentation."
                ),
            })

        # REF-JS-007: any type (TypeScript)
        any_count = len(cls.ANY_PAT.findall(source))
        if any_count >= 2:
            suggestions.append({
                "refactor_id": "REF-JS-007",
                "principle": "NAMING",
                "severity": "MEDIUM",
                "line_start": 1,
                "line_end": len(lines),
                "title": "Excessive 'any' Type — Add Proper TypeScript Types",
                "problem": (
                    "Found " + str(any_count) + " 'any' type annotations. "
                    "any disables TypeScript's type checking, defeating its purpose."
                ),
                "before_code": (
                    "function process(data: any): any {\n"
                    "    return data.value;\n"
                    "}"
                ),
                "after_code": (
                    "interface ProcessData {\n"
                    "    value: string;\n"
                    "    id: number;\n"
                    "}\n\n"
                    "function process(data: ProcessData): string {\n"
                    "    return data.value;\n"
                    "}"
                ),
                "benefit": (
                    "Type safety catches bugs at compile time. "
                    "IDE autocomplete works correctly. "
                    "Code is self-documenting."
                ),
            })

        # Duplicate code blocks
        dupes = DuplicateCodeDetector.find_duplicates(source)
        for dupe in dupes:
            suggestions.append({
                "refactor_id": "REF-JS-005",
                "principle": "DRY",
                "severity": "HIGH",
                "line_start": dupe["line_start_a"],
                "line_end": dupe["line_end_a"],
                "title": "Duplicate Code — Extract to Shared Function",
                "problem": (
                    "Code block duplicated at lines "
                    + str(dupe["line_start_a"]) + " and "
                    + str(dupe["line_start_b"]) + "."
                ),
                "before_code": "\n".join(dupe["block_content"].splitlines()[:5]),
                "after_code": (
                    "// Extract to shared utility:\n"
                    "function sharedLogic(...args) {\n"
                    "    // extracted code\n"
                    "}\n\n"
                    "// Use in both places:\n"
                    "sharedLogic(...);"
                ),
                "benefit": "DRY: fix bugs once, change behavior in one place.",
            })

        return suggestions


# =============================================================================
# Refactor Suggester Agent
# =============================================================================

class RefactorSuggesterAgent(BaseAgent):
    """
    LangGraph-powered agent suggesting concrete code refactoring improvements.

    Correctly extends BaseAgent (same pattern as Steps 21-24):
        __init__(retriever, streaming_client) -> super().__init__()
        agent_type -> "refactor_suggester"
        _build_graph() -> compiled StateGraph
        _format_result(state) -> dict

    Two-layer strategy:
        Layer 1: Deterministic AST/regex analysis — always runs
        Layer 2: LLM provides before/after examples and deeper suggestions

    AgentConfig.extra carries:
        code_content (str) source code to analyze
        language     (str) python | javascript | typescript
        file_path    (str) original file path

    LangGraph workflow:
        validate -> retrieve -> parse_code -> analyze
                 -> prioritize -> generate_suggestions -> fmt -> done -> END
    """

    def __init__(
        self,
        retriever: Any = None,
        streaming_client: Any = None,
    ) -> None:
        """
        Initialise the Refactor Suggester Agent.

        Args:
            retriever:        Optional RAG retriever for codebase context
            streaming_client: Optional Ollama client for AI suggestions
        """
        super().__init__(retriever=retriever, streaming_client=streaming_client)

    @property
    def agent_type(self) -> str:
        """Return unique agent type identifier."""
        return "refactor_suggester"

    def _build_graph(self) -> Any:
        """
        Build and compile the LangGraph StateGraph.

        Node order:
            validate            (BaseAgent)
            retrieve            (BaseAgent)
            parse_code          (self)
            analyze             (self)  AST/regex analysis
            prioritize          (self)  sort and score suggestions
            generate_suggestions (self) LLM enhancement
            fmt                 (BaseAgent) _format_result()
            done                (self)  Markdown report

        Returns:
            Compiled LangGraph CompiledStateGraph
        """
        graph: StateGraph = StateGraph(AgentState)

        graph.add_node("validate",             self._node_validate)
        graph.add_node("retrieve",             self._node_retrieve)
        graph.add_node("parse_code",           self._node_parse_code)
        graph.add_node("analyze",              self._node_analyze_code)
        graph.add_node("prioritize",           self._node_prioritize)
        graph.add_node("generate_suggestions", self._node_generate_suggestions)
        graph.add_node("fmt",                  self._node_format)
        graph.add_node("done",                 self._node_done)

        graph.set_entry_point("validate")
        graph.add_edge("validate",             "retrieve")
        graph.add_edge("retrieve",             "parse_code")
        graph.add_edge("parse_code",           "analyze")
        graph.add_edge("analyze",              "prioritize")
        graph.add_edge("prioritize",           "generate_suggestions")
        graph.add_edge("generate_suggestions", "fmt")
        graph.add_edge("fmt",                  "done")
        graph.add_edge("done",                 END)

        return graph.compile()

    def _format_result(self, state: AgentState) -> dict[str, Any]:
        """
        Convert final AgentState into a structured refactor result dict.

        Args:
            state: Final AgentState

        Returns:
            Dict with keys: total_suggestions, by_principle, by_severity,
            language, file_path, top_suggestions, llm_enhanced, summary
        """
        config: dict[str, Any] = state.get("config") or {}
        suggestions: list[dict[str, Any]] = config.get("_suggestions") or []
        language: str = str(config.get("language") or "unknown")
        file_path: str = str(config.get("file_path") or "unknown")
        llm_enhanced: bool = bool(config.get("_llm_enhanced", False))

        # Group by principle
        by_principle: dict[str, int] = {}
        by_severity: dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}

        for s in suggestions:
            p = str(s.get("principle") or "OTHER")
            by_principle[p] = by_principle.get(p, 0) + 1
            sev = str(s.get("severity") or "LOW")
            by_severity[sev] = by_severity.get(sev, 0) + 1

        top = [
            {
                "refactor_id": s.get("refactor_id", ""),
                "principle": s.get("principle", ""),
                "severity": s.get("severity", ""),
                "line_start": s.get("line_start", 0),
                "title": s.get("title", ""),
            }
            for s in suggestions[:5]
        ]

        return {
            "total_suggestions": len(suggestions),
            "by_principle": by_principle,
            "by_severity": by_severity,
            "language": language,
            "file_path": file_path,
            "top_suggestions": top,
            "llm_enhanced": llm_enhanced,
            "summary": (
                f"Refactor analysis of '{file_path}' ({language}): "
                f"{len(suggestions)} suggestions. "
                + ", ".join(f"{v} {k}" for k, v in by_principle.items())
                + f". LLM enhanced: {llm_enhanced}."
            ),
        }

    # =========================================================================
    # Custom nodes
    # =========================================================================

    async def _node_parse_code(self, state: AgentState) -> AgentState:
        """
        Node 3: Read and validate source code from config.

        Args:
            state: Current AgentState

        Returns:
            Updated state with _source in config
        """
        config: dict[str, Any] = dict(state.get("config") or {})
        code_content: str = str(config.get("code_content") or "").strip()
        language: str = str(config.get("language") or "unknown").lower()

        logger.info(
            "[Refactor] parse_code: language=%s len=%d",
            language, len(code_content),
        )

        if not code_content:
            return {
                **state,
                "error": "No code_content provided",
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

    async def _node_analyze_code(self, state: AgentState) -> AgentState:
        """
        Node 4: Run language-specific refactor analysis.

        Args:
            state: Current AgentState after parse_code

        Returns:
            Updated state with _suggestions in config
        """
        config: dict[str, Any] = dict(state.get("config") or {})
        source: str = str(config.get("_source") or "")
        language: str = str(config.get("language") or "unknown").lower()

        logger.info("[Refactor] analyze: language=%s", language)

        suggestions: list[dict[str, Any]] = []
        try:
            if language == "python":
                suggestions = PythonRefactorAnalyzer.analyze(source)
            elif language in ("javascript", "typescript", "jsx", "tsx", "js", "ts"):
                suggestions = JSRefactorAnalyzer.analyze(source)
            else:
                # Generic: only duplicate detection
                dupes = DuplicateCodeDetector.find_duplicates(source)
                for d in dupes:
                    suggestions.append(
                        PythonRefactorAnalyzer._make_duplicate_suggestion(d)
                    )
        except Exception as exc:
            logger.error("[Refactor] analyze error: %s", exc, exc_info=True)

        logger.info("[Refactor] Found %d suggestions", len(suggestions))
        config["_suggestions"] = suggestions

        return {
            **state,
            "config": config,
            "current_step": "analyzed",
            "progress": 0.5,
        }

    async def _node_prioritize(self, state: AgentState) -> AgentState:
        """
        Node 5: Sort suggestions by principle priority and severity.

        Priority order: SOLID-S > SOLID-D > DRY > SOLID-O > KISS > PATTERN > NAMING
        Within same principle: HIGH > MEDIUM > LOW

        Args:
            state: Current AgentState with _suggestions

        Returns:
            Updated state with sorted _suggestions
        """
        config: dict[str, Any] = dict(state.get("config") or {})
        suggestions: list[dict[str, Any]] = config.get("_suggestions") or []

        sev_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

        suggestions.sort(key=lambda s: (
            PRINCIPLE_PRIORITY.get(str(s.get("principle") or ""), 99),
            sev_order.get(str(s.get("severity") or "LOW"), 2),
        ))

        config["_suggestions"] = suggestions

        return {
            **state,
            "config": config,
            "current_step": "prioritized",
            "progress": 0.6,
        }

    async def _node_generate_suggestions(
        self, state: AgentState
    ) -> AgentState:
        """
        Node 6: Optional LLM enhancement of refactor suggestions.

        Pre-renders all suggestion data as plain strings before building
        the template. ONLY {context} and {query} remain as placeholders.

        Args:
            state: Current AgentState with prioritized suggestions

        Returns:
            Updated state with llm_response if LLM available
        """
        config: dict[str, Any] = dict(state.get("config") or {})
        suggestions: list[dict[str, Any]] = config.get("_suggestions") or []
        language: str = str(config.get("language") or "unknown").lower()
        file_path: str = str(config.get("file_path") or "unknown")
        source: str = str(config.get("_source") or "")

        config["_llm_enhanced"] = False

        if not self._streaming_client or not suggestions:
            return {
                **state,
                "config": config,
                "llm_response": None,
                "current_step": "suggestions_generated",
                "progress": 0.8,
            }

        # Pre-render suggestions block — NO braces that .format() would hit
        suggestion_lines: list[str] = []
        for s in suggestions[:6]:
            rid = str(s.get("refactor_id") or "")
            principle = str(s.get("principle") or "")
            sev = str(s.get("severity") or "")
            title = str(s.get("title") or "")
            ln = str(s.get("line_start") or 0)
            problem = str(s.get("problem") or "")[:150]
            suggestion_lines.append(
                "[" + rid + "] " + principle + " " + sev
                + " line " + ln + ": " + title
                + " — " + problem
            )

        suggestions_block = "\n".join(suggestion_lines)

        # Safe code preview — escape braces
        safe_preview = source[:600].replace("{", "(").replace("}", ")")

        system_prompt = (
            "You are a senior software architect specializing in code refactoring. "
            "Review the detected issues and provide additional refactoring suggestions "
            "with concrete before/after code examples. "
            "Focus on the most impactful improvements first. "
            "Be specific with actual variable and function names from the code."
        )

        # ONLY {context} and {query} as placeholders
        user_prompt_template = (
            "Refactor Analysis for: " + file_path
            + " (Language: " + language + ")\n\n"
            "DETECTED ISSUES:\n"
            + suggestions_block + "\n\n"
            "CODE PREVIEW:\n"
            + safe_preview + "\n\n"
            "CODEBASE CONTEXT:\n{context}\n\n"
            "TASK: {query}\n\n"
            "Provide additional refactoring suggestions with:\n"
            "1. PRIORITY FIXES: Most impactful refactors (with before/after)\n"
            "2. DESIGN PATTERNS: Applicable patterns (Strategy, Factory, etc.)\n"
            "3. ARCHITECTURE NOTES: Higher-level structural improvements\n"
        )

        query = (
            "Identify refactoring opportunities applying SOLID, DRY, KISS "
            "principles for " + language + " code in " + file_path
        )
        state_for_llm = {**state, "config": config, "query": query}

        try:
            updated = await self._node_analyze(
                state_for_llm,
                system_prompt=system_prompt,
                user_prompt_template=user_prompt_template,
            )
            llm_out = updated.get("llm_response") or ""
            if llm_out and len(llm_out) > 50:
                config["_llm_enhanced"] = True
            return {
                **updated,
                "config": config,
                "current_step": "suggestions_generated",
                "progress": 0.8,
            }
        except Exception as exc:
            logger.warning("[Refactor] LLM failed: %s", exc)
            return {
                **state,
                "config": config,
                "llm_response": None,
                "current_step": "suggestions_generated",
                "progress": 0.8,
            }

    async def _node_done(self, state: AgentState) -> AgentState:
        """
        Node 8: Assemble the final Markdown refactor report.

        Includes: summary stats, suggestions grouped by principle,
        each with before/after code blocks, and LLM additions.

        Args:
            state: AgentState after _node_format

        Returns:
            Final AgentState with formatted_report and progress 1.0
        """
        config: dict[str, Any] = state.get("config") or {}
        suggestions: list[dict[str, Any]] = config.get("_suggestions") or []
        language: str = str(config.get("language") or "unknown")
        file_path: str = str(config.get("file_path") or "unknown")
        llm_response: str = state.get("llm_response") or ""
        final_result: dict[str, Any] = state.get("final_result") or {}
        total_lines = int(config.get("_total_lines") or 0)

        by_principle: dict[str, int] = final_result.get("by_principle") or {}
        by_severity: dict[str, int] = final_result.get("by_severity") or {}

        # Code fence language tag
        lang_tag = "python" if language == "python" else "javascript"

        report_lines: list[str] = [
            "# Refactor Suggestions Report",
            "",
            "**File:** `" + file_path + "`",
            "**Language:** " + language.title(),
            "**Analyzed:** " + datetime.now(timezone.utc).strftime(
                "%Y-%m-%d %H:%M UTC"
            ),
            "**Lines:** " + str(total_lines),
            "**Total Suggestions:** " + str(len(suggestions)),
            "",
            "---",
            "",
            "## Summary",
            "",
        ]

        # Severity breakdown
        report_lines += [
            "| Severity | Count |",
            "|----------|-------|",
        ]
        for sev in ["HIGH", "MEDIUM", "LOW"]:
            cnt = by_severity.get(sev, 0)
            if cnt > 0:
                report_lines.append("| " + sev + " | " + str(cnt) + " |")

        # Principle breakdown
        if by_principle:
            report_lines += ["", "**By Principle:**", ""]
            for principle, count in sorted(
                by_principle.items(),
                key=lambda x: PRINCIPLE_PRIORITY.get(x[0], 99),
            ):
                report_lines.append(
                    "- **" + principle + "**: " + str(count)
                    + " suggestion" + ("s" if count > 1 else "")
                )

        report_lines += ["", "---", "", "## Refactoring Suggestions", ""]

        if not suggestions:
            report_lines.append(
                "No significant refactoring opportunities detected. "
                "Code structure looks clean!"
            )
        else:
            for idx, s in enumerate(suggestions, start=1):
                rid = str(s.get("refactor_id") or "")
                principle = str(s.get("principle") or "")
                severity = str(s.get("severity") or "")
                line_start = str(s.get("line_start") or 0)
                line_end = str(s.get("line_end") or 0)
                title = str(s.get("title") or "")
                problem = str(s.get("problem") or "")
                before = str(s.get("before_code") or "")
                after = str(s.get("after_code") or "")
                benefit = str(s.get("benefit") or "")

                report_lines += [
                    "### " + str(idx) + ". [" + rid + "] " + title,
                    "",
                    "- **Principle:** " + principle,
                    "- **Severity:** " + severity,
                    "- **Lines:** " + line_start + "-" + line_end,
                    "",
                    "**Problem:**",
                    "",
                    problem,
                    "",
                    "**Before:**",
                    "",
                    "```" + lang_tag,
                    before,
                    "```",
                    "",
                    "**After:**",
                    "",
                    "```" + lang_tag,
                    after,
                    "```",
                    "",
                    "**Benefit:** " + benefit,
                    "",
                    "---",
                    "",
                ]

        # LLM additional suggestions
        report_lines += ["## AI Refactor Recommendations", ""]
        if llm_response and llm_response.strip():
            report_lines.append(llm_response.strip())
        else:
            report_lines.append(
                "*AI recommendations not available. "
                "Static analysis results above are complete.*"
            )

        report_lines += [
            "",
            "---",
            "",
            "*Generated by AI Codebase Assistant — Refactor Suggester Agent*",
            "*Apply suggestions incrementally. Run tests after each refactor.*",
        ]

        return {
            **state,
            "formatted_report": "\n".join(report_lines),
            "status": AgentStatus.COMPLETED.value,
            "current_step": "done",
            "progress": 1.0,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }


# =============================================================================
# Factory
# =============================================================================

def create_refactor_suggester_agent(
    retriever: Any = None,
    streaming_client: Any = None,
) -> RefactorSuggesterAgent:
    """
    Create and return a configured RefactorSuggesterAgent.

    Args:
        retriever:        Optional RAG retriever
        streaming_client: Optional Ollama client

    Returns:
        Ready-to-use RefactorSuggesterAgent
    """
    return RefactorSuggesterAgent(
        retriever=retriever,
        streaming_client=streaming_client,
    )
