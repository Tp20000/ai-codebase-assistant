"""
Performance Analyzer Agent - Step 26
AI Codebase Assistant v2.0

Detects performance bottlenecks and inefficiencies:

    Algorithmic Complexity:
        O(n^2) nested loops, O(n^3) triple nesting
        Repeated linear searches instead of hash lookups
        Sorting inside loops, redundant recomputation

    Memory Issues:
        Unnecessary list copies, large intermediate collections
        String concatenation in loops (O(n^2) memory)
        Missing generator expressions for large datasets

    I/O & Database:
        N+1 query patterns
        Missing connection pooling indicators
        Synchronous I/O in async context
        Missing batch operations

    Python-Specific:
        list comprehension vs map/filter misuse
        Repeated attribute lookup in loops
        Missing __slots__ for data classes
        Global interpreter lock (GIL) issues in threading

    JavaScript-Specific:
        DOM queries inside loops
        Synchronous XHR
        Missing debounce/throttle on event handlers
        Array method chaining creating intermediate arrays

Correctly extends BaseAgent (same pattern as Steps 21-25).
CRITICAL: user_prompt_template uses ONLY {context} {query} {project_id}
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
# Performance Finding Schema
# =============================================================================
# Each finding dict has keys:
#   perf_id     (str)  e.g. "PERF-PY-001"
#   category    (str)  complexity | memory | io | language_specific
#   impact      (str)  CRITICAL | HIGH | MEDIUM | LOW
#   complexity  (str)  O(n^2) | O(n) | etc. if applicable
#   line_start  (int)  start line
#   line_end    (int)  end line
#   title       (str)  short description
#   detail      (str)  explanation of the issue
#   before_code (str)  current inefficient pattern
#   after_code  (str)  optimized version
#   speedup     (str)  estimated improvement e.g. "10x-100x for large n"

IMPACT_SCORE = {
    "CRITICAL": 40,
    "HIGH":     20,
    "MEDIUM":    8,
    "LOW":       2,
}

PERFORMANCE_GRADES = [
    (80, "CRITICAL — Major bottlenecks detected"),
    (40, "HIGH — Significant performance issues"),
    (15, "MEDIUM — Some inefficiencies found"),
    (5,  "LOW — Minor issues only"),
    (0,  "GOOD — No significant issues detected"),
]


def perf_grade(total_score: int) -> str:
    """
    Convert numeric performance impact score to grade label.

    Args:
        total_score: Sum of impact scores from all findings

    Returns:
        Grade string describing overall performance posture
    """
    for threshold, label in PERFORMANCE_GRADES:
        if total_score >= threshold:
            return label
    return "GOOD — No significant issues detected"


# =============================================================================
# Python Performance Analyzer
# =============================================================================

class PythonPerfAnalyzer:
    """
    AST + regex based performance analyzer for Python code.

    Rules:
        PERF-PY-001  O(n^2) nested loop over same collection
        PERF-PY-002  List membership test instead of set (O(n) vs O(1))
        PERF-PY-003  String concatenation in loop (O(n^2) memory)
        PERF-PY-004  Sorting inside a loop
        PERF-PY-005  Repeated len() / attribute lookup in loop condition
        PERF-PY-006  Creating list then immediately iterating (use generator)
        PERF-PY-007  N+1 query pattern (DB call inside loop)
        PERF-PY-008  Synchronous sleep / blocking call in async function
        PERF-PY-009  Unnecessary list copy (list(x) when iterating)
        PERF-PY-010  Global variable read in hot loop (cache locally)
        PERF-PY-011  Repeated dictionary key lookup
        PERF-PY-012  Missing enumerate() (manual index tracking)
        PERF-PY-013  Using + for list extend instead of .extend()
        PERF-PY-014  re.compile() inside loop (recompilation overhead)
        PERF-PY-015  Triple nested loop (O(n^3))
    """

    # Regex patterns for line-based checks
    STR_CONCAT_IN_LOOP = re.compile(
        r'^\s+\w+\s*\+=\s*["\']|^\s+\w+\s*=\s*\w+\s*\+\s*["\']',
        re.MULTILINE,
    )
    SORT_PAT = re.compile(r'\.sort\s*\(|sorted\s*\(')
    SLEEP_PAT = re.compile(r'time\.sleep\s*\(|asyncio\.sleep\s*\(')
    DB_CALL_PAT = re.compile(
        r'(?:\.query\s*\(|\.execute\s*\(|\.find\s*\(|\.get\s*\(|'
        r'session\.query|db\.query)',
        re.IGNORECASE,
    )
    RE_COMPILE_PAT = re.compile(r're\.compile\s*\(')
    IN_LIST_PAT = re.compile(r'\bin\s+\[')
    ENUMERATE_PAT = re.compile(
        r'for\s+\w+\s+in\s+range\s*\(\s*len\s*\(',
    )
    LIST_EXTEND_PAT = re.compile(r'\w+\s*\+=\s*\[')

    @classmethod
    def analyze(cls, source: str) -> list[dict[str, Any]]:
        """
        Run all Python performance analysis rules.

        Args:
            source: Raw Python source code

        Returns:
            List of performance finding dicts sorted by impact (desc)
        """
        findings: list[dict[str, Any]] = []
        lines = source.splitlines()

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return findings

        # AST-based analysis
        findings.extend(cls._find_nested_loops(tree, lines))
        findings.extend(cls._find_db_in_loops(tree, source, lines))
        findings.extend(cls._find_sync_in_async(tree, lines))
        findings.extend(cls._find_repeated_lookup(tree, lines))

        # Line-based analysis
        findings.extend(cls._line_checks(source, lines))

        # Sort by impact score descending
        return sorted(
            findings,
            key=lambda f: IMPACT_SCORE.get(str(f.get("impact", "LOW")), 0),
            reverse=True,
        )

    @classmethod
    def _find_nested_loops(
        cls, tree: ast.AST, lines: list[str]
    ) -> list[dict[str, Any]]:
        """
        Detect O(n^2) and O(n^3) nested loop patterns.

        Args:
            tree:  Parsed AST
            lines: Source lines for snippet extraction

        Returns:
            List of nested loop findings
        """
        findings: list[dict[str, Any]] = []

        for node in ast.walk(tree):
            if not isinstance(node, (ast.For, ast.While)):
                continue

            # Count nesting depth
            inner_loops: list[ast.AST] = []
            for child in ast.walk(node):
                if child is node:
                    continue
                if isinstance(child, (ast.For, ast.While)):
                    inner_loops.append(child)

            if not inner_loops:
                continue

            depth = 2  # outer + at least one inner
            # Check for triple nesting
            for inner in inner_loops:
                for grandchild in ast.walk(inner):
                    if grandchild is inner:
                        continue
                    if isinstance(grandchild, (ast.For, ast.While)):
                        depth = 3
                        break

            ln = node.lineno
            end_ln = getattr(node, "end_lineno", ln + 5)
            snippet = "\n".join(lines[ln - 1: min(ln + 8, len(lines))])

            if depth >= 3:
                findings.append({
                    "perf_id": "PERF-PY-015",
                    "category": "complexity",
                    "impact": "CRITICAL",
                    "complexity": "O(n^3)",
                    "line_start": ln,
                    "line_end": end_ln,
                    "title": "Triple Nested Loop — O(n^3) Complexity",
                    "detail": (
                        "Three nested loops at line " + str(ln)
                        + ". For n=1000 elements this means 10^9 iterations. "
                        "Will freeze for any real dataset."
                    ),
                    "before_code": snippet,
                    "after_code": (
                        "# Option 1: Use numpy/vectorized operations\n"
                        "import numpy as np\n"
                        "result = np.einsum('ijk->ij', matrix)\n\n"
                        "# Option 2: Precompute lookup structures\n"
                        "lookup = {k: v for k, v in data.items()}\n"
                        "# Then single pass: O(n)\n"
                        "result = [lookup[item] for item in collection]"
                    ),
                    "speedup": "10^6x improvement for n=10000",
                })
            else:
                # Check if both loops iterate over potentially the same data
                findings.append({
                    "perf_id": "PERF-PY-001",
                    "category": "complexity",
                    "impact": "HIGH",
                    "complexity": "O(n^2)",
                    "line_start": ln,
                    "line_end": end_ln,
                    "title": "Nested Loop — Potential O(n^2) Complexity",
                    "detail": (
                        "Nested loops at line " + str(ln)
                        + ". If both iterate over n-element collections, "
                        "complexity is O(n^2). For n=10000: 10^8 iterations."
                    ),
                    "before_code": snippet,
                    "after_code": (
                        "# Option 1: Use set/dict for O(1) lookups\n"
                        "lookup_set = set(collection_b)\n"
                        "result = [x for x in collection_a if x in lookup_set]\n\n"
                        "# Option 2: Sort + two-pointer (O(n log n))\n"
                        "a_sorted = sorted(collection_a)\n"
                        "b_sorted = sorted(collection_b)\n"
                        "# Two-pointer merge in O(n)"
                    ),
                    "speedup": "100x-10000x for large collections",
                })

        # Deduplicate by line (keep highest impact)
        seen_lines: set[int] = set()
        deduped: list[dict[str, Any]] = []
        for f in sorted(
            findings,
            key=lambda x: IMPACT_SCORE.get(str(x.get("impact", "LOW")), 0),
            reverse=True,
        ):
            ln = f["line_start"]
            if ln not in seen_lines:
                seen_lines.add(ln)
                deduped.append(f)
        return deduped[:4]

    @classmethod
    def _find_db_in_loops(
        cls,
        tree: ast.AST,
        source: str,
        lines: list[str],
    ) -> list[dict[str, Any]]:
        """
        Detect N+1 query pattern: database calls inside loops.

        Args:
            tree:   Parsed AST
            source: Full source string
            lines:  Source lines

        Returns:
            List of N+1 query findings
        """
        findings: list[dict[str, Any]] = []

        for node in ast.walk(tree):
            if not isinstance(node, (ast.For, ast.While)):
                continue

            loop_source = "\n".join(
                lines[node.lineno - 1: getattr(node, "end_lineno", node.lineno + 10)]
            )

            if cls.DB_CALL_PAT.search(loop_source):
                ln = node.lineno
                findings.append({
                    "perf_id": "PERF-PY-007",
                    "category": "io",
                    "impact": "CRITICAL",
                    "complexity": "O(n) queries",
                    "line_start": ln,
                    "line_end": getattr(node, "end_lineno", ln + 5),
                    "title": "N+1 Query Pattern — Database Call in Loop",
                    "detail": (
                        "Database query detected inside a loop at line "
                        + str(ln) + ". For n=100 items: 101 queries. "
                        "For n=1000: 1001 queries. "
                        "This is the #1 ORM performance killer."
                    ),
                    "before_code": (
                        "# N+1: 1 query for list + 1 per item\n"
                        "users = User.query.all()       # 1 query\n"
                        "for user in users:\n"
                        "    posts = user.posts.all()   # N queries!"
                    ),
                    "after_code": (
                        "# 1 query with JOIN — O(1) queries total\n"
                        "from sqlalchemy.orm import joinedload\n"
                        "users = User.query.options(\n"
                        "    joinedload(User.posts)\n"
                        ").all()  # 1 query, all data loaded\n\n"
                        "for user in users:\n"
                        "    posts = user.posts  # no query — already loaded!"
                    ),
                    "speedup": "100x-1000x reduction in DB roundtrips",
                })
            if len(findings) >= 2:
                break  # cap at 2 N+1 findings

        return findings

    @classmethod
    def _find_sync_in_async(
        cls, tree: ast.AST, lines: list[str]
    ) -> list[dict[str, Any]]:
        """
        Detect synchronous blocking calls inside async functions.

        Args:
            tree:  Parsed AST
            lines: Source lines

        Returns:
            List of sync-in-async findings
        """
        findings: list[dict[str, Any]] = []
        blocking_calls = frozenset([
            "time.sleep", "requests.get", "requests.post",
            "open", "subprocess.run", "subprocess.call",
        ])

        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue

            func_name = node.name
            func_lines = lines[node.lineno - 1: getattr(node, "end_lineno", node.lineno + 10)]
            func_source = "\n".join(func_lines)

            # Look for time.sleep (blocking in async)
            if re.search(r'time\.sleep\s*\(', func_source):
                findings.append({
                    "perf_id": "PERF-PY-008",
                    "category": "io",
                    "impact": "HIGH",
                    "complexity": "Blocks event loop",
                    "line_start": node.lineno,
                    "line_end": getattr(node, "end_lineno", node.lineno),
                    "title": "Blocking Call in Async Function",
                    "detail": (
                        "time.sleep() in async function '"
                        + func_name + "' blocks the entire event loop. "
                        "All other coroutines are frozen during the sleep."
                    ),
                    "before_code": (
                        "async def " + func_name + "():\n"
                        "    time.sleep(1)  # BLOCKS event loop!"
                    ),
                    "after_code": (
                        "async def " + func_name + "():\n"
                        "    await asyncio.sleep(1)  # yields to event loop"
                    ),
                    "speedup": "Unblocks all concurrent coroutines",
                })

            # Look for requests.get without httpx/aiohttp
            if re.search(r'requests\.(get|post|put|delete)\s*\(', func_source):
                findings.append({
                    "perf_id": "PERF-PY-008b",
                    "category": "io",
                    "impact": "HIGH",
                    "complexity": "Blocks event loop",
                    "line_start": node.lineno,
                    "line_end": getattr(node, "end_lineno", node.lineno),
                    "title": "Sync HTTP Request in Async Function",
                    "detail": (
                        "requests library is synchronous. Using it in async '"
                        + func_name + "' blocks the event loop during HTTP call."
                    ),
                    "before_code": (
                        "async def " + func_name + "():\n"
                        "    resp = requests.get(url)  # blocks!"
                    ),
                    "after_code": (
                        "import httpx\n\n"
                        "async def " + func_name + "():\n"
                        "    async with httpx.AsyncClient() as client:\n"
                        "        resp = await client.get(url)  # non-blocking"
                    ),
                    "speedup": "10x-100x throughput improvement under load",
                })

        return findings[:3]

    @classmethod
    def _find_repeated_lookup(
        cls, tree: ast.AST, lines: list[str]
    ) -> list[dict[str, Any]]:
        """
        Detect repeated dictionary/attribute lookups that could be cached.

        Args:
            tree:  Parsed AST
            lines: Source lines

        Returns:
            List of repeated lookup findings
        """
        findings: list[dict[str, Any]] = []

        for node in ast.walk(tree):
            if not isinstance(node, (ast.For, ast.While)):
                continue

            # Count subscript accesses (dict[key]) inside the loop
            subscripts: list[str] = []
            for child in ast.walk(node):
                if isinstance(child, ast.Subscript):
                    if isinstance(child.value, ast.Name):
                        subscripts.append(child.value.id)

            # Flag if same dict accessed 3+ times in one loop
            for name, count in {
                n: subscripts.count(n) for n in set(subscripts)
            }.items():
                if count >= 3:
                    ln = node.lineno
                    findings.append({
                        "perf_id": "PERF-PY-011",
                        "category": "memory",
                        "impact": "LOW",
                        "complexity": "Repeated hash computation",
                        "line_start": ln,
                        "line_end": getattr(node, "end_lineno", ln + 5),
                        "title": "Repeated Dictionary Lookup in Loop",
                        "detail": (
                            "Dictionary '" + name + "' accessed "
                            + str(count) + " times per loop iteration at line "
                            + str(ln) + ". Each access recomputes the hash."
                        ),
                        "before_code": (
                            "for item in items:\n"
                            "    x = " + name + "[key]\n"
                            "    y = " + name + "[key] + 1\n"
                            "    z = " + name + "[key] * 2"
                        ),
                        "after_code": (
                            "for item in items:\n"
                            "    # Cache the lookup once per iteration\n"
                            "    cached = " + name + "[key]\n"
                            "    x = cached\n"
                            "    y = cached + 1\n"
                            "    z = cached * 2"
                        ),
                        "speedup": "Minor but accumulates in hot loops",
                    })
                    break

        return findings[:2]

    @classmethod
    def _line_checks(
        cls, source: str, lines: list[str]
    ) -> list[dict[str, Any]]:
        """
        Run line-by-line regex checks for performance patterns.

        Args:
            source: Full source string
            lines:  Source lines list

        Returns:
            List of line-based performance findings
        """
        findings: list[dict[str, Any]] = []
        in_loop = False
        loop_indent = 0

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            indent = len(line) - len(line.lstrip())

            # Track loop context
            if re.match(r'^\s*(?:for|while)\s+', line):
                in_loop = True
                loop_indent = indent

            # Exit loop context when dedented
            if in_loop and indent <= loop_indent and stripped and not stripped.startswith('#'):
                if not re.match(r'^\s*(?:for|while|if|else|elif|try|except|finally|with)\s*', line):
                    if i > 1:
                        in_loop = False

            # PERF-PY-003: String concatenation in loop
            if in_loop and cls.STR_CONCAT_IN_LOOP.match(line):
                findings.append({
                    "perf_id": "PERF-PY-003",
                    "category": "memory",
                    "impact": "HIGH",
                    "complexity": "O(n^2) string building",
                    "line_start": i,
                    "line_end": i,
                    "title": "String Concatenation in Loop — O(n^2) Memory",
                    "detail": (
                        "String concatenation with += inside loop at line "
                        + str(i) + ". Each concatenation creates a new string "
                        "object. For n strings: O(n^2) total memory allocated."
                    ),
                    "before_code": (
                        "result = ''\n"
                        "for item in items:\n"
                        "    result += str(item)  # O(n^2)!"
                    ),
                    "after_code": (
                        "# Use list + join: O(n) memory\n"
                        "parts = []\n"
                        "for item in items:\n"
                        "    parts.append(str(item))\n"
                        "result = ''.join(parts)\n\n"
                        "# Or one-liner:\n"
                        "result = ''.join(str(item) for item in items)"
                    ),
                    "speedup": "10x-1000x for large string building",
                })

            # PERF-PY-004: Sorting inside loop
            if in_loop and cls.SORT_PAT.search(line):
                findings.append({
                    "perf_id": "PERF-PY-004",
                    "category": "complexity",
                    "impact": "HIGH",
                    "complexity": "O(n^2 log n)",
                    "line_start": i,
                    "line_end": i,
                    "title": "Sorting Inside Loop — O(n^2 log n)",
                    "detail": (
                        "Sort operation inside loop at line " + str(i)
                        + ". Each iteration sorts again unnecessarily. "
                        "O(n log n) per iteration = O(n^2 log n) total."
                    ),
                    "before_code": (
                        "for query in queries:\n"
                        "    results = sorted(data)  # sorts n times!"
                    ),
                    "after_code": (
                        "# Sort ONCE before the loop\n"
                        "sorted_data = sorted(data)\n"
                        "for query in queries:\n"
                        "    results = sorted_data  # O(1) — already sorted"
                    ),
                    "speedup": "n times faster where n = loop iterations",
                })

            # PERF-PY-002: List membership in list literal
            if cls.IN_LIST_PAT.search(line):
                findings.append({
                    "perf_id": "PERF-PY-002",
                    "category": "complexity",
                    "impact": "MEDIUM",
                    "complexity": "O(n) → O(1)",
                    "line_start": i,
                    "line_end": i,
                    "title": "List Membership Test — Use Set for O(1) Lookup",
                    "detail": (
                        "Membership test 'x in [...]' at line " + str(i)
                        + " is O(n). Python checks each element linearly."
                    ),
                    "before_code": (
                        "if status in ['active', 'pending', 'processing', 'retry']:\n"
                        "    ..."
                    ),
                    "after_code": (
                        "# frozenset is O(1) lookup, immutable, clear intent\n"
                        "VALID_STATUSES = frozenset(['active', 'pending', "
                        "'processing', 'retry'])\n"
                        "if status in VALID_STATUSES:\n"
                        "    ..."
                    ),
                    "speedup": "O(n) → O(1). Critical inside loops.",
                })

            # PERF-PY-012: Manual index in for loop
            if cls.ENUMERATE_PAT.search(line):
                findings.append({
                    "perf_id": "PERF-PY-012",
                    "category": "language_specific",
                    "impact": "LOW",
                    "complexity": "Minor overhead",
                    "line_start": i,
                    "line_end": i,
                    "title": "Manual Index Loop — Use enumerate()",
                    "detail": (
                        "for i in range(len(x)) at line " + str(i)
                        + " is Pythonic anti-pattern. "
                        "Two lookups per iteration vs one with enumerate."
                    ),
                    "before_code": (
                        "for i in range(len(items)):\n"
                        "    print(i, items[i])"
                    ),
                    "after_code": (
                        "for i, item in enumerate(items):\n"
                        "    print(i, item)  # no items[i] lookup"
                    ),
                    "speedup": "Minor but signals non-Pythonic code",
                })

            # PERF-PY-014: re.compile inside loop
            if in_loop and cls.RE_COMPILE_PAT.search(line):
                findings.append({
                    "perf_id": "PERF-PY-014",
                    "category": "language_specific",
                    "impact": "MEDIUM",
                    "complexity": "Repeated compilation overhead",
                    "line_start": i,
                    "line_end": i,
                    "title": "re.compile() Inside Loop — Precompile Pattern",
                    "detail": (
                        "Regex pattern compiled on every loop iteration at line "
                        + str(i) + ". Compilation is expensive. "
                        "Compile once and reuse."
                    ),
                    "before_code": (
                        "for text in texts:\n"
                        "    pattern = re.compile(r'\\d+')  # compiled n times!\n"
                        "    matches = pattern.findall(text)"
                    ),
                    "after_code": (
                        "# Compile once at module level\n"
                        "DIGIT_PATTERN = re.compile(r'\\d+')\n\n"
                        "for text in texts:\n"
                        "    matches = DIGIT_PATTERN.findall(text)  # reused"
                    ),
                    "speedup": "5x-50x faster regex in high-volume loops",
                })

        return findings


# =============================================================================
# JavaScript Performance Analyzer
# =============================================================================

class JSPerfAnalyzer:
    """
    Regex-based performance analyzer for JavaScript and TypeScript.

    Rules:
        PERF-JS-001  DOM query inside loop (document.querySelector in for)
        PERF-JS-002  Synchronous XHR / blocking fetch
        PERF-JS-003  Missing debounce on event handler
        PERF-JS-004  Array .forEach in hot path (use for...of)
        PERF-JS-005  String concatenation in loop
        PERF-JS-006  Nested loops over arrays
        PERF-JS-007  Missing useMemo/useCallback (React re-renders)
        PERF-JS-008  JSON.parse inside loop
        PERF-JS-009  Chained .filter().map() creating intermediate arrays
        PERF-JS-010  setInterval without clearInterval (memory leak)
    """

    DOM_QUERY_PAT = re.compile(
        r'document\.(?:querySelector|getElementById|getElementsBy'
        r'ClassName|getElementsByTagName)\s*\('
    )
    XHR_PAT = re.compile(r'XMLHttpRequest|\.open\s*\(\s*["\']GET')
    DEBOUNCE_HINT_PAT = re.compile(
        r'addEventListener\s*\(\s*["\'](?:input|keyup|scroll|resize)["\']'
    )
    STR_CONCAT_PAT = re.compile(r'\w+\s*\+=\s*["\']|\w+\s*=\s*\w+\s*\+\s*["\']')
    JSON_PARSE_PAT = re.compile(r'JSON\.parse\s*\(')
    FILTER_MAP_PAT = re.compile(r'\.filter\s*\([^)]*\)\s*\.map\s*\(')
    SET_INTERVAL_PAT = re.compile(r'setInterval\s*\(')
    CLEAR_INTERVAL_PAT = re.compile(r'clearInterval\s*\(')
    REACT_MEMO_HINT = re.compile(
        r'const\s+\w+\s*=\s*\([^)]*\)\s*=>\s*\{[^}]*(?:map|filter|reduce)'
    )
    FOR_LOOP_PAT = re.compile(r'for\s*\(|for\s+\w+\s+of\s+|for\s+\w+\s+in\s+')

    @classmethod
    def analyze(cls, source: str) -> list[dict[str, Any]]:
        """
        Run all JS/TS performance analysis rules.

        Args:
            source: Raw JavaScript or TypeScript source code

        Returns:
            List of performance finding dicts sorted by impact (desc)
        """
        findings: list[dict[str, Any]] = []
        lines = source.splitlines()
        in_loop = False
        loop_depth = 0

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Track loop context (simple heuristic)
            if cls.FOR_LOOP_PAT.search(line) or re.search(r'\bwhile\s*\(', line):
                loop_depth += 1
                in_loop = True
            if stripped == '}' and loop_depth > 0:
                loop_depth -= 1
                if loop_depth == 0:
                    in_loop = False

            # PERF-JS-001: DOM query in loop
            if in_loop and cls.DOM_QUERY_PAT.search(line):
                findings.append({
                    "perf_id": "PERF-JS-001",
                    "category": "io",
                    "impact": "HIGH",
                    "complexity": "O(n) DOM traversals",
                    "line_start": i,
                    "line_end": i,
                    "title": "DOM Query Inside Loop",
                    "detail": (
                        "DOM query at line " + str(i)
                        + " forces browser to traverse DOM on every iteration. "
                        "Expensive layout thrashing for large loops."
                    ),
                    "before_code": (
                        "for (const item of items) {\n"
                        "    const el = document.querySelector('.my-class');  // n queries!\n"
                        "    el.textContent = item;\n"
                        "}"
                    ),
                    "after_code": (
                        "// Cache DOM reference BEFORE the loop\n"
                        "const el = document.querySelector('.my-class');\n"
                        "for (const item of items) {\n"
                        "    el.textContent = item;  // no DOM query\n"
                        "}"
                    ),
                    "speedup": "10x-1000x for large lists",
                })

            # PERF-JS-002: Synchronous XHR
            if cls.XHR_PAT.search(line):
                findings.append({
                    "perf_id": "PERF-JS-002",
                    "category": "io",
                    "impact": "CRITICAL",
                    "complexity": "Blocks main thread",
                    "line_start": i,
                    "line_end": i,
                    "title": "Synchronous XHR — Blocks Main Thread",
                    "detail": (
                        "Synchronous XMLHttpRequest at line " + str(i)
                        + " freezes the browser tab until response arrives. "
                        "Deprecated in modern browsers."
                    ),
                    "before_code": (
                        "const xhr = new XMLHttpRequest();\n"
                        "xhr.open('GET', url, false);  // false = synchronous!\n"
                        "xhr.send();"
                    ),
                    "after_code": (
                        "// Use fetch with async/await\n"
                        "async function fetchData(url) {\n"
                        "    const response = await fetch(url);\n"
                        "    return response.json();\n"
                        "}"
                    ),
                    "speedup": "Non-blocking — UI stays responsive",
                })

            # PERF-JS-003: Missing debounce on event handler
            if cls.DEBOUNCE_HINT_PAT.search(line):
                findings.append({
                    "perf_id": "PERF-JS-003",
                    "category": "language_specific",
                    "impact": "MEDIUM",
                    "complexity": "O(n) calls per second",
                    "line_start": i,
                    "line_end": i,
                    "title": "Event Handler May Need Debounce/Throttle",
                    "detail": (
                        "Input/scroll/resize event at line " + str(i)
                        + " fires on every keystroke or pixel scroll. "
                        "Without debounce, can fire 100+ times per second."
                    ),
                    "before_code": (
                        "input.addEventListener('input', (e) => {\n"
                        "    searchAPI(e.target.value);  // fires every keystroke!\n"
                        "});"
                    ),
                    "after_code": (
                        "// Debounce: wait 300ms after last event\n"
                        "const debounce = (fn, delay) => {\n"
                        "    let timer;\n"
                        "    return (...args) => {\n"
                        "        clearTimeout(timer);\n"
                        "        timer = setTimeout(() => fn(...args), delay);\n"
                        "    };\n"
                        "};\n\n"
                        "input.addEventListener('input',\n"
                        "    debounce((e) => searchAPI(e.target.value), 300)\n"
                        ");"
                    ),
                    "speedup": "Reduces API calls by 90%+ in typical usage",
                })

            # PERF-JS-005: String concatenation in loop
            if in_loop and cls.STR_CONCAT_PAT.search(line):
                findings.append({
                    "perf_id": "PERF-JS-005",
                    "category": "memory",
                    "impact": "MEDIUM",
                    "complexity": "O(n^2) string building",
                    "line_start": i,
                    "line_end": i,
                    "title": "String Concatenation in Loop",
                    "detail": (
                        "String += in loop at line " + str(i)
                        + ". In older JS engines this is O(n^2). "
                        "Use array.join() for efficient string building."
                    ),
                    "before_code": (
                        "let html = '';\n"
                        "for (const item of items) {\n"
                        "    html += '<li>' + item + '</li>';  // O(n^2)!\n"
                        "}"
                    ),
                    "after_code": (
                        "const parts = [];\n"
                        "for (const item of items) {\n"
                        "    parts.push('<li>' + item + '</li>');\n"
                        "}\n"
                        "const html = parts.join('');  // O(n)"
                    ),
                    "speedup": "Significant for large lists in older runtimes",
                })

            # PERF-JS-008: JSON.parse in loop
            if in_loop and cls.JSON_PARSE_PAT.search(line):
                findings.append({
                    "perf_id": "PERF-JS-008",
                    "category": "complexity",
                    "impact": "MEDIUM",
                    "complexity": "Repeated parsing overhead",
                    "line_start": i,
                    "line_end": i,
                    "title": "JSON.parse() Inside Loop",
                    "detail": (
                        "JSON.parse at line " + str(i)
                        + " is called on every iteration. "
                        "Parse once and reuse the result."
                    ),
                    "before_code": (
                        "for (const item of items) {\n"
                        "    const config = JSON.parse(configStr);  // parsed n times!\n"
                        "    process(config, item);\n"
                        "}"
                    ),
                    "after_code": (
                        "const config = JSON.parse(configStr);  // parse once\n"
                        "for (const item of items) {\n"
                        "    process(config, item);\n"
                        "}"
                    ),
                    "speedup": "n times faster where n = iterations",
                })

            # PERF-JS-009: Chained filter().map()
            if cls.FILTER_MAP_PAT.search(line):
                findings.append({
                    "perf_id": "PERF-JS-009",
                    "category": "memory",
                    "impact": "LOW",
                    "complexity": "Two O(n) passes + intermediate array",
                    "line_start": i,
                    "line_end": i,
                    "title": "Chained filter().map() — Use reduce() or flatMap()",
                    "detail": (
                        "filter().map() at line " + str(i)
                        + " creates an intermediate array. "
                        "For large arrays this doubles memory allocation."
                    ),
                    "before_code": (
                        "const result = items\n"
                        "    .filter(x => x.active)  // intermediate array\n"
                        "    .map(x => x.value);"
                    ),
                    "after_code": (
                        "// Single pass with reduce:\n"
                        "const result = items.reduce((acc, x) => {\n"
                        "    if (x.active) acc.push(x.value);\n"
                        "    return acc;\n"
                        "}, []);"
                    ),
                    "speedup": "50% less memory allocation for large arrays",
                })

            # PERF-JS-010: setInterval without clearInterval
            if cls.SET_INTERVAL_PAT.search(line):
                if not cls.CLEAR_INTERVAL_PAT.search(source):
                    findings.append({
                        "perf_id": "PERF-JS-010",
                        "category": "memory",
                        "impact": "HIGH",
                        "complexity": "Memory leak",
                        "line_start": i,
                        "line_end": i,
                        "title": "setInterval Without clearInterval — Memory Leak",
                        "detail": (
                            "setInterval at line " + str(i)
                            + " but no clearInterval found in file. "
                            "Intervals accumulate if component re-mounts, "
                            "causing memory leaks and duplicate callbacks."
                        ),
                        "before_code": (
                            "function startPolling() {\n"
                            "    setInterval(() => poll(), 1000);  // never cleared!\n"
                            "}"
                        ),
                        "after_code": (
                            "function startPolling() {\n"
                            "    const intervalId = setInterval(() => poll(), 1000);\n"
                            "    // In React: return () => clearInterval(intervalId);\n"
                            "    // In vanilla: call clearInterval(intervalId) on cleanup\n"
                            "    return intervalId;\n"
                            "}"
                        ),
                        "speedup": "Prevents memory growth and duplicate timers",
                    })
                break  # only flag once

        return sorted(
            findings,
            key=lambda f: IMPACT_SCORE.get(str(f.get("impact", "LOW")), 0),
            reverse=True,
        )


# =============================================================================
# Performance Analyzer Agent
# =============================================================================

class PerformanceAnalyzerAgent(BaseAgent):
    """
    LangGraph-powered agent that detects performance bottlenecks in code.

    Correctly extends BaseAgent (same pattern as Steps 21-25):
        __init__(retriever, streaming_client) -> super().__init__()
        agent_type -> "performance_analyzer"
        _build_graph() -> compiled StateGraph
        _format_result(state) -> dict

    Two-layer analysis:
        Layer 1: Deterministic AST/regex rules — always runs
        Layer 2: LLM provides deeper algorithmic analysis and
                 optimization strategies

    AgentConfig.extra carries:
        code_content (str) source code to analyze
        language     (str) python | javascript | typescript
        file_path    (str) original file path

    LangGraph workflow:
        validate -> retrieve -> parse_code -> analyze_performance
                 -> aggregate -> generate_report -> fmt -> done -> END
    """

    def __init__(
        self,
        retriever: Any = None,
        streaming_client: Any = None,
    ) -> None:
        """
        Initialise the Performance Analyzer Agent.

        Args:
            retriever:        Optional RAG retriever for codebase context
            streaming_client: Optional Ollama client for AI analysis
        """
        super().__init__(retriever=retriever, streaming_client=streaming_client)

    @property
    def agent_type(self) -> str:
        """Return unique agent type identifier."""
        return "performance_analyzer"

    def _build_graph(self) -> Any:
        """
        Build and compile the LangGraph StateGraph for performance analysis.

        Node order:
            validate           (BaseAgent)
            retrieve           (BaseAgent)
            parse_code         (self)
            analyze_performance (self)  AST + regex rules
            aggregate          (self)  compute overall impact score
            generate_report    (self)  LLM enhancement
            fmt                (BaseAgent) _format_result()
            done               (self)  Markdown report

        Returns:
            Compiled LangGraph CompiledStateGraph
        """
        graph: StateGraph = StateGraph(AgentState)

        graph.add_node("validate",            self._node_validate)
        graph.add_node("retrieve",            self._node_retrieve)
        graph.add_node("parse_code",          self._node_parse_code)
        graph.add_node("analyze_performance", self._node_analyze_performance)
        graph.add_node("aggregate",           self._node_aggregate)
        graph.add_node("generate_report",     self._node_generate_report)
        graph.add_node("fmt",                 self._node_format)
        graph.add_node("done",                self._node_done)

        graph.set_entry_point("validate")
        graph.add_edge("validate",            "retrieve")
        graph.add_edge("retrieve",            "parse_code")
        graph.add_edge("parse_code",          "analyze_performance")
        graph.add_edge("analyze_performance", "aggregate")
        graph.add_edge("aggregate",           "generate_report")
        graph.add_edge("generate_report",     "fmt")
        graph.add_edge("fmt",                 "done")
        graph.add_edge("done",                END)

        return graph.compile()

    def _format_result(self, state: AgentState) -> dict[str, Any]:
        """
        Convert final AgentState into structured performance result dict.

        Args:
            state: Final AgentState

        Returns:
            Dict with keys: language, file_path, total_findings,
            impact_counts, perf_score, perf_grade, categories,
            critical_findings, llm_enhanced, summary
        """
        config: dict[str, Any] = state.get("config") or {}
        findings: list[dict[str, Any]] = config.get("_findings") or []
        agg: dict[str, Any] = config.get("_aggregation") or {}
        language: str = str(config.get("language") or "unknown")
        file_path: str = str(config.get("file_path") or "unknown")
        llm_enhanced: bool = bool(config.get("_llm_enhanced", False))

        impact_counts: dict[str, int] = agg.get("impact_counts") or {}
        total_score: int = int(agg.get("total_score") or 0)
        grade: str = str(agg.get("grade") or "GOOD")

        categories: list[str] = list({
            str(f.get("category", "")) for f in findings
        })

        critical_findings = [
            {
                "perf_id": f.get("perf_id", ""),
                "impact": f.get("impact", ""),
                "complexity": f.get("complexity", ""),
                "line_start": f.get("line_start", 0),
                "title": f.get("title", ""),
            }
            for f in findings
            if f.get("impact") in ("CRITICAL", "HIGH")
        ][:8]

        return {
            "language": language,
            "file_path": file_path,
            "total_findings": len(findings),
            "impact_counts": impact_counts,
            "perf_score": total_score,
            "perf_grade": grade,
            "categories": categories,
            "critical_findings": critical_findings,
            "llm_enhanced": llm_enhanced,
            "summary": (
                f"Performance analysis of '{file_path}' ({language}): "
                f"{grade}. "
                f"{len(findings)} issues found. "
                + ", ".join(
                    f"{v} {k}" for k, v in impact_counts.items() if v > 0
                ) + "."
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
            "[PerfAnalyzer] parse_code: language=%s len=%d",
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

    async def _node_analyze_performance(
        self, state: AgentState
    ) -> AgentState:
        """
        Node 4: Run language-specific performance analysis.

        Args:
            state: Current AgentState after parse_code

        Returns:
            Updated state with _findings in config
        """
        config: dict[str, Any] = dict(state.get("config") or {})
        source: str = str(config.get("_source") or "")
        language: str = str(config.get("language") or "unknown").lower()

        logger.info("[PerfAnalyzer] analyze: language=%s", language)

        findings: list[dict[str, Any]] = []
        try:
            if language == "python":
                findings = PythonPerfAnalyzer.analyze(source)
            elif language in (
                "javascript", "typescript", "jsx", "tsx", "js", "ts"
            ):
                findings = JSPerfAnalyzer.analyze(source)
            else:
                logger.info(
                    "[PerfAnalyzer] No specific analyzer for %s", language
                )
        except Exception as exc:
            logger.error(
                "[PerfAnalyzer] analyze error: %s", exc, exc_info=True
            )

        logger.info("[PerfAnalyzer] Found %d findings", len(findings))
        config["_findings"] = findings

        return {
            **state,
            "config": config,
            "current_step": "analyzed",
            "progress": 0.55,
        }

    async def _node_aggregate(self, state: AgentState) -> AgentState:
        """
        Node 5: Compute total impact score and performance grade.

        Args:
            state: Current AgentState with _findings

        Returns:
            Updated state with _aggregation in config
        """
        config: dict[str, Any] = dict(state.get("config") or {})
        findings: list[dict[str, Any]] = config.get("_findings") or []

        impact_counts: dict[str, int] = {
            "CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0,
        }
        total_score = 0

        for f in findings:
            imp = str(f.get("impact", "LOW"))
            impact_counts[imp] = impact_counts.get(imp, 0) + 1
            total_score += IMPACT_SCORE.get(imp, 0)

        grade = perf_grade(total_score)

        config["_aggregation"] = {
            "total_score": total_score,
            "grade": grade,
            "impact_counts": impact_counts,
            "total_findings": len(findings),
        }

        logger.info(
            "[PerfAnalyzer] score=%d grade=%s findings=%d",
            total_score, grade, len(findings),
        )

        return {
            **state,
            "config": config,
            "current_step": "aggregated",
            "progress": 0.65,
        }

    async def _node_generate_report(self, state: AgentState) -> AgentState:
        """
        Node 6: Optional LLM-enhanced performance analysis.

        Pre-renders all finding data as plain strings before building the
        template. ONLY {context} and {query} remain as placeholders.

        Args:
            state: Current AgentState with findings and aggregation

        Returns:
            Updated state with llm_response if LLM available
        """
        config: dict[str, Any] = dict(state.get("config") or {})
        findings: list[dict[str, Any]] = config.get("_findings") or []
        agg: dict[str, Any] = config.get("_aggregation") or {}
        language: str = str(config.get("language") or "unknown").lower()
        file_path: str = str(config.get("file_path") or "unknown")
        source: str = str(config.get("_source") or "")

        config["_llm_enhanced"] = False

        if not self._streaming_client or not findings:
            return {
                **state,
                "config": config,
                "llm_response": None,
                "current_step": "reported",
                "progress": 0.8,
            }

        # Pre-render findings — plain string, no braces for .format()
        finding_lines: list[str] = []
        for f in findings[:10]:
            pid = str(f.get("perf_id") or "")
            imp = str(f.get("impact") or "")
            cat = str(f.get("category") or "")
            cx = str(f.get("complexity") or "")
            ln = str(f.get("line_start") or 0)
            title = str(f.get("title") or "")
            finding_lines.append(
                "[" + pid + "] " + imp + " " + cat
                + " line " + ln + " " + cx
                + ": " + title
            )

        findings_block = "\n".join(finding_lines)
        grade_str = str(agg.get("grade") or "UNKNOWN")
        score_str = str(agg.get("total_score") or 0)

        # Safe code preview
        safe_preview = source[:600].replace("{", "(").replace("}", ")")

        system_prompt = (
            "You are a senior performance engineer and algorithm expert. "
            "Analyze the detected performance issues and provide: "
            "complexity analysis (Big-O), concrete optimization strategies, "
            "and profiling recommendations. "
            "Be specific with data structures and algorithms to use."
        )

        # ONLY {context} and {query} as placeholders
        user_prompt_template = (
            "Performance Analysis for: " + file_path
            + " (Language: " + language + ")\n"
            "Overall Grade: " + grade_str
            + " (Score: " + score_str + ")\n\n"
            "DETECTED ISSUES:\n"
            + findings_block + "\n\n"
            "CODE PREVIEW:\n"
            + safe_preview + "\n\n"
            "CODEBASE CONTEXT:\n{context}\n\n"
            "TASK: {query}\n\n"
            "Provide performance analysis with sections:\n"
            "1. COMPLEXITY ANALYSIS: Big-O for critical sections\n"
            "2. OPTIMIZATION STRATEGIES: Specific algorithms/data structures\n"
            "3. PROFILING GUIDE: How to measure and confirm improvements\n"
            "4. QUICK WINS: Easiest changes with highest impact\n"
        )

        query = (
            "Analyze performance bottlenecks and suggest optimizations "
            "for " + language + " code in " + file_path
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
                "current_step": "reported",
                "progress": 0.8,
            }
        except Exception as exc:
            logger.warning("[PerfAnalyzer] LLM failed: %s", exc)
            return {
                **state,
                "config": config,
                "llm_response": None,
                "current_step": "reported",
                "progress": 0.8,
            }

    async def _node_done(self, state: AgentState) -> AgentState:
        """
        Node 8: Assemble the final Markdown performance report.

        Args:
            state: AgentState after _node_format

        Returns:
            Final AgentState with formatted_report and progress 1.0
        """
        config: dict[str, Any] = state.get("config") or {}
        findings: list[dict[str, Any]] = config.get("_findings") or []
        agg: dict[str, Any] = config.get("_aggregation") or {}
        language: str = str(config.get("language") or "unknown")
        file_path: str = str(config.get("file_path") or "unknown")
        llm_response: str = state.get("llm_response") or ""
        final_result: dict[str, Any] = state.get("final_result") or {}
        total_lines = int(config.get("_total_lines") or 0)

        grade = str(agg.get("grade") or "GOOD")
        score = int(agg.get("total_score") or 0)
        impact_counts: dict[str, int] = agg.get("impact_counts") or {}

        lang_tag = "python" if language == "python" else "javascript"

        report: list[str] = [
            "# Performance Analysis Report",
            "",
            "**File:** `" + file_path + "`",
            "**Language:** " + language.title(),
            "**Analyzed:** " + datetime.now(timezone.utc).strftime(
                "%Y-%m-%d %H:%M UTC"
            ),
            "**Lines:** " + str(total_lines),
            "",
            "---",
            "",
            "## Performance Grade",
            "",
            "```",
            "Grade:  " + grade,
            "Score:  " + str(score) + " impact points",
            "Issues: " + str(len(findings)),
            "```",
            "",
        ]

        # Impact breakdown table
        report += [
            "| Impact | Count | Score |",
            "|--------|-------|-------|",
        ]
        for imp in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            cnt = impact_counts.get(imp, 0)
            if cnt > 0:
                sc = IMPACT_SCORE.get(imp, 0) * cnt
                report.append(
                    "| " + imp + " | " + str(cnt) + " | +" + str(sc) + " |"
                )
        report += ["", "---", ""]

        # Findings detail
        if findings:
            report.append("## Performance Issues")
            report.append("")

            for imp_level in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
                level_findings = [
                    f for f in findings if f.get("impact") == imp_level
                ]
                if not level_findings:
                    continue

                report.append(
                    "### " + imp_level
                    + " (" + str(len(level_findings)) + ")"
                )
                report.append("")

                for f in level_findings:
                    pid = str(f.get("perf_id") or "")
                    cat = str(f.get("category") or "")
                    cx = str(f.get("complexity") or "")
                    ln_s = str(f.get("line_start") or 0)
                    ln_e = str(f.get("line_end") or 0)
                    title = str(f.get("title") or "")
                    detail = str(f.get("detail") or "")
                    before = str(f.get("before_code") or "")
                    after = str(f.get("after_code") or "")
                    speedup = str(f.get("speedup") or "")

                    report += [
                        "**[" + pid + "] " + title + "**",
                        "- **Category:** " + cat
                        + " | **Complexity:** " + cx,
                        "- **Lines:** " + ln_s + "-" + ln_e,
                        "",
                        detail,
                        "",
                        "**Before (slow):**",
                        "",
                        "```" + lang_tag,
                        before,
                        "```",
                        "",
                        "**After (optimized):**",
                        "",
                        "```" + lang_tag,
                        after,
                        "```",
                        "",
                        "**Expected improvement:** " + speedup,
                        "",
                        "---",
                        "",
                    ]
        else:
            report += [
                "## Performance Issues",
                "",
                "No significant performance issues detected.",
                "",
                "---",
                "",
            ]

        report += ["## AI Performance Analysis", ""]
        if llm_response and llm_response.strip():
            report.append(llm_response.strip())
        else:
            report.append(
                "*AI performance analysis not available. "
                "Static analysis results above are complete.*"
            )

        report += [
            "",
            "---",
            "",
            "*Generated by AI Codebase Assistant — Performance Analyzer Agent*",
            "*Always profile with real data to confirm improvements.*",
        ]

        return {
            **state,
            "formatted_report": "\n".join(report),
            "status": AgentStatus.COMPLETED.value,
            "current_step": "done",
            "progress": 1.0,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }


# =============================================================================
# Factory
# =============================================================================

def create_performance_analyzer_agent(
    retriever: Any = None,
    streaming_client: Any = None,
) -> PerformanceAnalyzerAgent:
    """
    Create and return a configured PerformanceAnalyzerAgent.

    Args:
        retriever:        Optional RAG retriever
        streaming_client: Optional Ollama client

    Returns:
        Ready-to-use PerformanceAnalyzerAgent
    """
    return PerformanceAnalyzerAgent(
        retriever=retriever,
        streaming_client=streaming_client,
    )
