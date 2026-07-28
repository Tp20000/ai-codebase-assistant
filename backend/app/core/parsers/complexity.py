"""
Code Complexity Metrics Engine - Step 33
AI Codebase Assistant v2.0

Calculates comprehensive complexity metrics for Python and JS/TS:

    Cyclomatic Complexity (McCabe):
        Counts decision points (if/elif/else/for/while/except/and/or/
        ternary/assert/with). Score 1-5=simple, 6-10=moderate,
        11-20=complex, >20=very complex.

    Cognitive Complexity (SonarSource):
        Penalizes nesting more heavily than branching alone.
        Structural complexity (if/for/while) + nesting multiplier.
        Better predicts human difficulty in reading code.

    Halstead Metrics:
        - n1: unique operators (if, +, =, def, return, etc.)
        - n2: unique operands (variables, literals, function names)
        - N1: total operator occurrences
        - N2: total operand occurrences
        - Vocabulary: n1 + n2
        - Length: N1 + N2
        - Volume: Length * log2(Vocabulary)
        - Difficulty: (n1/2) * (N2/n2)
        - Effort: Difficulty * Volume (predicts implementation effort)
        - Time: Effort / 18 seconds (predicts time to implement)
        - Bugs: Volume / 3000 (predicts delivered defects)

    Maintainability Index (0-100):
        171 - 5.2*ln(Halstead_Volume)
            - 0.23*Cyclomatic_Complexity
            - 16.2*ln(Lines_Of_Code)
        >= 85: highly maintainable
        65-84: moderately maintainable
        < 65:  difficult to maintain

    Lines of Code (LoC):
        total_lines, code_lines, comment_lines, blank_lines,
        comment_ratio

Output per file:
    {
        "file_path": str,
        "language": str,
        "loc": {...},
        "functions": [{
            "name": str,
            "line_start": int,
            "line_end": int,
            "cyclomatic": int,
            "cognitive": int,
            "halstead": {...},
            "maintainability_index": float,
            "complexity_grade": str,    # A/B/C/D/F
            "parameters": int,
            "is_async": bool
        }],
        "classes": [{...}],
        "file_metrics": {
            "avg_cyclomatic": float,
            "max_cyclomatic": int,
            "avg_cognitive": float,
            "total_functions": int,
            "complex_functions": list,  # CC > 10
            "maintainability_index": float,
            "halstead": {...},
            "grade": str
        }
    }
"""

from __future__ import annotations

import ast
import logging
import math
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Complexity Grades
# =============================================================================

def cyclomatic_grade(cc: int) -> str:
    """
    Convert cyclomatic complexity score to letter grade.

    Args:
        cc: Cyclomatic complexity integer

    Returns:
        Grade string: A (1-5) | B (6-10) | C (11-15) | D (16-20) | F (>20)
    """
    if cc <= 5:
        return "A"
    if cc <= 10:
        return "B"
    if cc <= 15:
        return "C"
    if cc <= 20:
        return "D"
    return "F"


def maintainability_grade(mi: float) -> str:
    """
    Convert maintainability index to letter grade.

    Args:
        mi: Maintainability index float (0-100)

    Returns:
        Grade string: A (>=85) | B (75-84) | C (65-74) | D (50-64) | F (<50)
    """
    if mi >= 85:
        return "A"
    if mi >= 75:
        return "B"
    if mi >= 65:
        return "C"
    if mi >= 50:
        return "D"
    return "F"


# =============================================================================
# Lines of Code Counter
# =============================================================================

class LOCCounter:
    """
    Counts lines of code, comments, and blank lines.

    Language-aware: handles Python # comments and docstrings,
    JS/TS // and /* */ comments.
    """

    @staticmethod
    def count_python(source: str) -> dict[str, int]:
        """
        Count LoC metrics for Python source code.

        Args:
            source: Raw Python source string

        Returns:
            Dict with total_lines, code_lines, comment_lines,
            blank_lines, docstring_lines, comment_ratio
        """
        lines = source.splitlines()
        total = len(lines)
        blank = 0
        comment = 0
        docstring = 0
        code = 0
        in_docstring = False
        docstring_char = ""

        for line in lines:
            stripped = line.strip()

            # Blank line
            if not stripped:
                blank += 1
                continue

            # Inside a multi-line docstring
            if in_docstring:
                docstring += 1
                # Check if this line closes the docstring
                # (must contain the closing triple-quote)
                close_count = stripped.count(docstring_char)
                if close_count >= 1:
                    # If it opened with """: and this line has """
                    # but is NOT just the opener we saw already, close it
                    in_docstring = False
                continue

            # Check for triple-quote start
            found_triple = False
            for q in ('"""', "'''"):
                if q in stripped:
                    idx = stripped.find(q)
                    before = stripped[:idx].strip()
                    # It's a comment line containing a quote — skip
                    if before.startswith("#"):
                        comment += 1
                        found_triple = True
                        break
                    # Count occurrences of the triple quote
                    occ = stripped.count(q)
                    if occ == 1:
                        # Opens but does not close on same line
                        in_docstring = True
                        docstring_char = q
                        docstring += 1
                        found_triple = True
                        break
                    elif occ >= 2:
                        # Opens AND closes on same line (inline docstring)
                        docstring += 1
                        found_triple = True
                        break

            if found_triple:
                continue

            # Regular comment
            if stripped.startswith("#"):
                comment += 1
                continue

            # Must be code
            code += 1

        total_non_blank = total - blank
        comment_ratio = round(
            (comment + docstring) / max(total_non_blank, 1) * 100, 1
        )

        return {
            "total_lines": total,
            "code_lines": code,
            "comment_lines": comment,
            "docstring_lines": docstring,
            "blank_lines": blank,
            "comment_ratio": comment_ratio,
        }

    @staticmethod
    def count_js(source: str) -> dict[str, int]:
        """
        Count LoC metrics for JavaScript/TypeScript source.

        Args:
            source: Raw JS/TS source string

        Returns:
            Dict with total_lines, code_lines, comment_lines,
            blank_lines, comment_ratio
        """
        lines = source.splitlines()
        total = len(lines)
        blank = 0
        comment = 0
        code = 0
        in_block_comment = False

        for line in lines:
            stripped = line.strip()

            if not stripped:
                blank += 1
                continue

            if in_block_comment:
                comment += 1
                if "*/" in stripped:
                    in_block_comment = False
                continue

            if stripped.startswith("//"):
                comment += 1
            elif stripped.startswith("/*"):
                comment += 1
                if "*/" not in stripped[2:]:
                    in_block_comment = True
            else:
                code += 1

        total_non_blank = total - blank
        comment_ratio = round(
            comment / max(total_non_blank, 1) * 100, 1
        )

        return {
            "total_lines": total,
            "code_lines": code,
            "comment_lines": comment,
            "docstring_lines": 0,
            "blank_lines": blank,
            "comment_ratio": comment_ratio,
        }


# =============================================================================
# Cyclomatic Complexity Calculator
# =============================================================================

class CyclomaticCalculator:
    """
    Calculates McCabe Cyclomatic Complexity using AST analysis.

    Formula: CC = 1 + (number of binary decision points)
    Decision points: if, elif, for, while, except, with, assert,
                     and, or, ternary (IfExp), comprehension conditions
    """

    @staticmethod
    def calculate(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
        """
        Calculate cyclomatic complexity for a function AST node.

        Args:
            node: AST FunctionDef or AsyncFunctionDef node

        Returns:
            Cyclomatic complexity integer (minimum 1)
        """
        complexity = 1  # Base complexity

        for child in ast.walk(node):
            if child is node:
                continue
            # Each of these adds a branch
            if isinstance(child, (ast.If, ast.While, ast.For,
                                   ast.ExceptHandler, ast.With,
                                   ast.Assert, ast.Try)):
                complexity += 1
            # Boolean operators (and/or): each operand after first adds branch
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
            # Ternary expressions (x if condition else y)
            elif isinstance(child, ast.IfExp):
                complexity += 1
            # Comprehension conditions [x for x in y if condition]
            elif isinstance(child, (ast.ListComp, ast.SetComp,
                                     ast.DictComp, ast.GeneratorExp)):
                for generator in child.generators:
                    complexity += len(generator.ifs)

        return complexity


# =============================================================================
# Cognitive Complexity Calculator
# =============================================================================

class CognitiveCalculator:
    """
    Calculates Cognitive Complexity (SonarSource methodology).

    Unlike Cyclomatic, Cognitive penalizes nesting:
    - Each structural element (if/for/while/try) adds 1 + nesting_level
    - Each logical operator sequence adds 1
    - Recursion adds 1

    This better predicts how hard code is to read and understand.
    """

    @staticmethod
    def calculate(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        func_name: str = "",
    ) -> int:
        """
        Calculate cognitive complexity for a function node.

        Args:
            node:      AST function node
            func_name: Function name for recursion detection

        Returns:
            Cognitive complexity integer
        """
        return CognitiveCalculator._compute(node, func_name)

    @staticmethod
    def _compute(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        func_name: str,
    ) -> int:
        """
        Compute cognitive complexity via recursive walk with nesting tracking.

        Args:
            node:      Function AST node
            func_name: Function name for recursion detection

        Returns:
            Total cognitive complexity
        """
        def walk(
            n: ast.AST,
            nesting: int,
            last_bool_op: str | None = None,
        ) -> int:
            score = 0

            # Structural increments (add 1 + nesting)
            if isinstance(n, ast.If):
                score += 1 + nesting
                for child in n.body:
                    score += walk(child, nesting + 1)
                # else/elif each add 1 (no nesting penalty)
                for child in n.orelse:
                    if isinstance(child, ast.If):
                        score += 1  # elif
                        score += walk(child, nesting + 1) - (1 + nesting + 1)
                    else:
                        score += 1  # else
                        score += walk(child, nesting + 1)
                return score

            elif isinstance(n, (ast.For, ast.AsyncFor, ast.While)):
                score += 1 + nesting
                for child in ast.iter_child_nodes(n):
                    score += walk(child, nesting + 1)
                return score

            elif isinstance(n, ast.Try):
                score += 1 + nesting
                for child in ast.iter_child_nodes(n):
                    score += walk(child, nesting + 1)
                return score

            elif isinstance(n, (ast.With, ast.AsyncWith)):
                score += 1 + nesting
                for child in n.body:
                    score += walk(child, nesting + 1)
                return score

            elif isinstance(n, (ast.ListComp, ast.SetComp,
                                  ast.DictComp, ast.GeneratorExp)):
                score += 1
                return score

            elif isinstance(n, ast.Lambda):
                score += 1
                return score

            # Boolean operator sequences
            elif isinstance(n, ast.BoolOp):
                op_name = "and" if isinstance(n.op, ast.And) else "or"
                if op_name != last_bool_op:
                    score += 1
                for value in n.values:
                    if isinstance(value, ast.BoolOp):
                        score += walk(value, nesting,
                                      last_bool_op=op_name)
                return score

            # Recursion detection
            elif isinstance(n, ast.Call):
                if (isinstance(n.func, ast.Name)
                        and n.func.id == func_name
                        and func_name):
                    score += 1

            # Walk children for other node types
            for child in ast.iter_child_nodes(n):
                score += walk(child, nesting, last_bool_op)
            return score

        total = 0
        for child in node.body:
            total += walk(child, nesting=0)
        return total


# =============================================================================
# Halstead Metrics Calculator
# =============================================================================

class HalsteadCalculator:
    """
    Calculates Halstead software metrics for Python code.

    Operators: keywords and punctuation (if, for, +, =, def, return, ...)
    Operands:  identifiers and literals (variable names, numbers, strings)
    """

    # Python operator keywords and symbols
    OPERATORS = frozenset([
        "if", "else", "elif", "for", "while", "in", "not", "and", "or",
        "is", "is not", "not in", "return", "yield", "raise", "del",
        "assert", "pass", "break", "continue", "import", "from", "as",
        "with", "try", "except", "finally", "lambda", "class", "def",
        "async", "await", "global", "nonlocal",
        "+", "-", "*", "/", "//", "%", "**", "@",
        "=", "+=", "-=", "*=", "/=", "//=", "%=", "**=",
        "==", "!=", "<", ">", "<=", ">=",
        "&", "|", "^", "~", "<<", ">>",
        "->", ":", ",", ".", "(", ")", "[", "]", "{", "}",
    ])

    @staticmethod
    def calculate(source: str) -> dict[str, Any]:
        """
        Calculate Halstead metrics for Python source code.

        Uses a simplified token-based approach (without full lexer)
        that gives good approximations for real code.

        Args:
            source: Raw Python source string

        Returns:
            Dict with n1, n2, N1, N2, vocabulary, length,
            volume, difficulty, effort, time_seconds, bugs
        """
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return HalsteadCalculator._empty()

        operators: list[str] = []
        operands: list[str] = []

        for node in ast.walk(tree):
            # Operators: keywords and operators
            if isinstance(node, ast.BinOp):
                operators.append(type(node.op).__name__)
            elif isinstance(node, ast.UnaryOp):
                operators.append(type(node.op).__name__)
            elif isinstance(node, ast.BoolOp):
                operators.append(type(node.op).__name__)
            elif isinstance(node, ast.Compare):
                for op in node.ops:
                    operators.append(type(op).__name__)
            elif isinstance(node, ast.AugAssign):
                operators.append(type(node.op).__name__)
            elif isinstance(node, (
                ast.If, ast.For, ast.While, ast.With,
                ast.Try, ast.Return, ast.Yield, ast.Raise,
                ast.Import, ast.ImportFrom, ast.FunctionDef,
                ast.AsyncFunctionDef, ast.ClassDef,
            )):
                operators.append(type(node).__name__)
            elif isinstance(node, ast.Assign):
                operators.append("Assign")
            # Operands: names and literals
            elif isinstance(node, ast.Name):
                operands.append(node.id)
            elif isinstance(node, ast.Constant):
                operands.append(str(node.value))
            elif isinstance(node, ast.Attribute):
                operands.append(node.attr)

        return HalsteadCalculator._compute(operators, operands)

    @staticmethod
    def _compute(
        operators: list[str],
        operands: list[str],
    ) -> dict[str, Any]:
        """
        Compute Halstead metrics from operator and operand lists.

        Args:
            operators: List of all operator occurrences
            operands:  List of all operand occurrences

        Returns:
            Dict with all Halstead metrics
        """
        unique_ops = set(operators)
        unique_opds = set(operands)

        n1 = len(unique_ops)     # unique operators
        n2 = len(unique_opds)    # unique operands
        N1 = len(operators)       # total operators
        N2 = len(operands)        # total operands

        vocab = n1 + n2
        length = N1 + N2

        if vocab <= 1 or length == 0:
            return HalsteadCalculator._empty()

        volume = round(length * math.log2(max(vocab, 2)), 2)
        difficulty = round((n1 / max(2, 1)) * (N2 / max(n2, 1)), 2)
        effort = round(difficulty * volume, 2)
        time_sec = round(effort / 18, 2)
        bugs = round(volume / 3000, 4)

        return {
            "n1_unique_operators": n1,
            "n2_unique_operands": n2,
            "N1_total_operators": N1,
            "N2_total_operands": N2,
            "vocabulary": vocab,
            "length": length,
            "volume": volume,
            "difficulty": difficulty,
            "effort": effort,
            "time_seconds": time_sec,
            "bugs_delivered": bugs,
        }

    @staticmethod
    def _empty() -> dict[str, Any]:
        """Return empty Halstead metrics dict."""
        return {
            "n1_unique_operators": 0,
            "n2_unique_operands": 0,
            "N1_total_operators": 0,
            "N2_total_operands": 0,
            "vocabulary": 0,
            "length": 0,
            "volume": 0.0,
            "difficulty": 0.0,
            "effort": 0.0,
            "time_seconds": 0.0,
            "bugs_delivered": 0.0,
        }


# =============================================================================
# Maintainability Index Calculator
# =============================================================================

def calculate_maintainability_index(
    halstead_volume: float,
    cyclomatic_complexity: int,
    loc: int,
) -> float:
    """
    Calculate the Maintainability Index (0-100 scale).

    Formula (Microsoft Visual Studio variant):
        MI = max(0, (171
                     - 5.2 * ln(HV)
                     - 0.23 * CC
                     - 16.2 * ln(LoC)) * 100 / 171)

    Args:
        halstead_volume:       Halstead volume metric
        cyclomatic_complexity: McCabe cyclomatic complexity
        loc:                   Lines of code (code lines only)

    Returns:
        Maintainability index float in range [0.0, 100.0]
    """
    if halstead_volume <= 0 or loc <= 0:
        return 100.0

    try:
        raw = (
            171.0
            - 5.2 * math.log(max(halstead_volume, 1))
            - 0.23 * cyclomatic_complexity
            - 16.2 * math.log(max(loc, 1))
        )
        mi = max(0.0, min(100.0, raw * 100.0 / 171.0))
        return round(mi, 2)
    except (ValueError, ZeroDivisionError):
        return 100.0


# =============================================================================
# JavaScript Complexity Analyzer (regex-based)
# =============================================================================

class JSComplexityAnalyzer:
    """
    Approximates complexity metrics for JavaScript/TypeScript.

    Uses regex-based heuristics (no full JS AST available in Python).
    Less accurate than the Python AST-based approach but useful for
    high-level analysis and hotspot identification.
    """

    # Patterns that increase cyclomatic complexity
    BRANCH_PAT = re.compile(
        r'\b(if|else\s+if|for|while|do\s*\{|switch|case|catch|'
        r'\?\s*:|&&|\|\|)\b',
        re.MULTILINE,
    )
    # Function pattern
    FUNC_PAT = re.compile(
        r'(?:function\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s+)?'
        r'(?:\([^)]*\)|[\w]+)\s*=>)',
        re.MULTILINE,
    )
    # Line-level patterns
    COMMENT_LINE_PAT = re.compile(r'^\s*//', re.MULTILINE)
    BLOCK_COMMENT_PAT = re.compile(r'/\*.*?\*/', re.DOTALL)

    @classmethod
    def analyze_file(cls, source: str, file_path: str) -> dict[str, Any]:
        """
        Analyze a JS/TS file and return complexity metrics.

        Args:
            source:    Raw JS/TS source code
            file_path: File path for identification

        Returns:
            File metrics dict matching Python analyzer output format
        """
        loc = LOCCounter.count_js(source)
        functions: list[dict[str, Any]] = []

        # Find function boundaries (simplified)
        for match in cls.FUNC_PAT.finditer(source):
            name = match.group(1) or match.group(2) or "anonymous"
            start_pos = match.start()
            start_line = source[:start_pos].count("\n") + 1

            # Extract function body (find matching braces)
            body_start = source.find("{", start_pos)
            if body_start == -1:
                continue
            body = cls._extract_body(source, body_start)
            end_line = start_line + body.count("\n")

            # Count branches in function body
            branch_count = len(cls.BRANCH_PAT.findall(body))
            cc = max(1, branch_count)

            # Approximate cognitive complexity
            cog = cls._cognitive_approx(body)

            # Parameter count
            param_match = re.search(r'\(([^)]*)\)', source[start_pos:body_start])
            param_count = 0
            if param_match:
                params_str = param_match.group(1).strip()
                param_count = len(params_str.split(",")) if params_str else 0

            is_async = "async" in source[max(0, start_pos - 10):start_pos + 20]

            # Halstead approximation for JS
            halstead = cls._halstead_approx(body)
            mi = calculate_maintainability_index(
                halstead["volume"],
                cc,
                max(1, end_line - start_line),
            )

            functions.append({
                "name": name,
                "line_start": start_line,
                "line_end": end_line,
                "cyclomatic": cc,
                "cognitive": cog,
                "halstead": halstead,
                "maintainability_index": mi,
                "complexity_grade": cyclomatic_grade(cc),
                "parameters": param_count,
                "is_async": is_async,
            })

        # File-level metrics
        file_halstead = cls._halstead_approx(source)
        all_cc = [f["cyclomatic"] for f in functions]
        avg_cc = round(sum(all_cc) / max(len(all_cc), 1), 2)
        max_cc = max(all_cc) if all_cc else 0
        total_lines = loc["total_lines"]
        file_mi = calculate_maintainability_index(
            file_halstead["volume"],
            max_cc or 1,
            max(1, loc["code_lines"]),
        )

        complex_funcs = [
            {"name": f["name"], "cyclomatic": f["cyclomatic"],
             "line": f["line_start"]}
            for f in functions if f["cyclomatic"] > 10
        ]

        return {
            "file_path": file_path,
            "language": "javascript",
            "loc": loc,
            "functions": functions[:50],  # cap at 50
            "classes": [],
            "file_metrics": {
                "avg_cyclomatic": avg_cc,
                "max_cyclomatic": max_cc,
                "avg_cognitive": round(
                    sum(f["cognitive"] for f in functions)
                    / max(len(functions), 1), 2
                ),
                "total_functions": len(functions),
                "complex_functions": complex_funcs,
                "maintainability_index": file_mi,
                "maintainability_grade": maintainability_grade(file_mi),
                "halstead": file_halstead,
                "grade": cyclomatic_grade(max_cc or 1),
            },
        }

    @staticmethod
    def _extract_body(source: str, brace_start: int) -> str:
        """
        Extract function body by matching braces.

        Args:
            source:      Full source string
            brace_start: Position of opening brace

        Returns:
            Function body string (between matching braces)
        """
        depth = 0
        for i, ch in enumerate(source[brace_start:], start=brace_start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return source[brace_start:i + 1]
        return source[brace_start:brace_start + 500]

    @classmethod
    def _cognitive_approx(cls, body: str) -> int:
        """
        Approximate cognitive complexity for a JS function body.

        Args:
            body: Function body string

        Returns:
            Approximate cognitive complexity integer
        """
        score = 0
        nesting = 0
        for line in body.splitlines():
            stripped = line.strip()
            if re.search(r'\b(if|for|while|switch)\b', stripped):
                score += 1 + nesting
                nesting += 1
            elif re.match(r'\}', stripped) and nesting > 0:
                nesting -= 1
            if "&&" in stripped or "||" in stripped:
                score += 1
        return max(0, score)

    @staticmethod
    def _halstead_approx(source: str) -> dict[str, Any]:
        """
        Approximate Halstead metrics for JS/TS.

        Args:
            source: JS/TS source string

        Returns:
            Approximate Halstead metrics dict
        """
        # Count operator-like tokens
        op_pat = re.compile(
            r'\b(if|else|for|while|return|function|const|let|var|'
            r'class|new|this|typeof|instanceof|in|of|async|await|'
            r'try|catch|throw|import|export)\b|'
            r'[+\-*/%=<>!&|^~?:]+'
        )
        # Count operand-like tokens (identifiers and literals)
        opd_pat = re.compile(r'\b[a-zA-Z_$]\w*\b|\b\d+\.?\d*\b|"[^"]*"|\'[^\']*\'')

        operators = op_pat.findall(source)
        operands = opd_pat.findall(source)

        # Flatten tuples from findall with groups
        flat_ops: list[str] = []
        for op in operators:
            if isinstance(op, tuple):
                flat_ops.extend(o for o in op if o)
            else:
                flat_ops.append(op)

        n1 = len(set(flat_ops))
        n2 = len(set(operands))
        N1 = len(flat_ops)
        N2 = len(operands)

        vocab = n1 + n2
        length = N1 + N2

        if vocab <= 1 or length == 0:
            return HalsteadCalculator._empty()

        volume = round(length * math.log2(max(vocab, 2)), 2)
        difficulty = round((n1 / max(2, 1)) * (N2 / max(n2, 1)), 2)
        effort = round(difficulty * volume, 2)

        return {
            "n1_unique_operators": n1,
            "n2_unique_operands": n2,
            "N1_total_operators": N1,
            "N2_total_operands": N2,
            "vocabulary": vocab,
            "length": length,
            "volume": volume,
            "difficulty": difficulty,
            "effort": effort,
            "time_seconds": round(effort / 18, 2),
            "bugs_delivered": round(volume / 3000, 4),
        }


# =============================================================================
# Python Complexity Analyzer (AST-based, production quality)
# =============================================================================

class PythonComplexityAnalyzer:
    """
    AST-based complexity analyzer for Python source code.

    Produces accurate Cyclomatic, Cognitive, Halstead, and MI metrics
    for every function and class method in the file.
    """

    @classmethod
    def analyze_file(cls, source: str, file_path: str) -> dict[str, Any]:
        """
        Analyze a Python file and compute all complexity metrics.

        Args:
            source:    Raw Python source code
            file_path: File path for identification

        Returns:
            Complete file metrics dict with per-function breakdown
        """
        loc = LOCCounter.count_python(source)

        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            logger.warning("AST parse failed for %s: %s", file_path, exc)
            return {
                "file_path": file_path,
                "language": "python",
                "loc": loc,
                "functions": [],
                "classes": [],
                "file_metrics": {
                    "avg_cyclomatic": 0.0,
                    "max_cyclomatic": 0,
                    "avg_cognitive": 0.0,
                    "total_functions": 0,
                    "complex_functions": [],
                    "maintainability_index": 0.0,
                    "maintainability_grade": "F",
                    "halstead": HalsteadCalculator._empty(),
                    "grade": "F",
                    "parse_error": str(exc),
                },
            }

        functions: list[dict[str, Any]] = []
        classes: list[dict[str, Any]] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_info = cls._analyze_class(node, source)
                classes.append(class_info)

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Skip methods (they're handled inside class analysis)
                if not cls._is_method(node, tree):
                    func_info = cls._analyze_function(node, source)
                    functions.append(func_info)

        # File-level Halstead (whole file)
        file_halstead = HalsteadCalculator.calculate(source)

        # Aggregate metrics
        all_functions = functions + [
            m for cls_info in classes for m in cls_info.get("methods", [])
        ]
        all_cc = [f["cyclomatic"] for f in all_functions]
        all_cog = [f["cognitive"] for f in all_functions]

        avg_cc = round(sum(all_cc) / max(len(all_cc), 1), 2)
        max_cc = max(all_cc) if all_cc else 0
        avg_cog = round(sum(all_cog) / max(len(all_cog), 1), 2)

        file_mi = calculate_maintainability_index(
            file_halstead["volume"],
            max_cc or 1,
            max(1, loc["code_lines"]),
        )

        complex_funcs = [
            {
                "name": f["name"],
                "cyclomatic": f["cyclomatic"],
                "cognitive": f["cognitive"],
                "line": f["line_start"],
                "grade": f["complexity_grade"],
            }
            for f in all_functions
            if f["cyclomatic"] > 10
        ]

        return {
            "file_path": file_path,
            "language": "python",
            "loc": loc,
            "functions": functions[:50],
            "classes": classes[:20],
            "file_metrics": {
                "avg_cyclomatic": avg_cc,
                "max_cyclomatic": max_cc,
                "avg_cognitive": avg_cog,
                "total_functions": len(all_functions),
                "total_classes": len(classes),
                "complex_functions": complex_funcs,
                "maintainability_index": file_mi,
                "maintainability_grade": maintainability_grade(file_mi),
                "halstead": file_halstead,
                "grade": cyclomatic_grade(max_cc or 1),
            },
        }

    @staticmethod
    def _is_method(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        tree: ast.AST,
    ) -> bool:
        """
        Check whether a function node is a class method.

        Args:
            node: Function node to check
            tree: Full AST tree

        Returns:
            True if node is a method of a class
        """
        for parent in ast.walk(tree):
            if isinstance(parent, ast.ClassDef):
                for item in parent.body:
                    if item is node:
                        return True
        return False

    @classmethod
    def _analyze_function(
        cls,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        source: str,
    ) -> dict[str, Any]:
        """
        Compute all metrics for a single function node.

        Args:
            node:   Function AST node
            source: Full source (for Halstead over function body)

        Returns:
            Function metrics dict
        """
        source_lines = source.splitlines()
        start = node.lineno - 1
        end = (node.end_lineno or node.lineno) - 1
        func_source = "\n".join(source_lines[start:end + 1])

        cc = CyclomaticCalculator.calculate(node)
        cog = CognitiveCalculator.calculate(node, node.name)
        halstead = HalsteadCalculator.calculate(func_source)
        loc_count = end - start + 1
        mi = calculate_maintainability_index(
            halstead["volume"], cc, max(1, loc_count)
        )

        # Parameter count (exclude self/cls)
        args = node.args.args
        param_count = len([
            a for a in args
            if a.arg not in ("self", "cls")
        ])

        # Return type annotation
        return_type = ""
        if node.returns:
            try:
                return_type = ast.unparse(node.returns)
            except Exception:
                return_type = "Any"

        return {
            "name": node.name,
            "line_start": node.lineno,
            "line_end": node.end_lineno or node.lineno,
            "lines": loc_count,
            "cyclomatic": cc,
            "cognitive": cog,
            "halstead": halstead,
            "maintainability_index": mi,
            "complexity_grade": cyclomatic_grade(cc),
            "maintainability_grade": maintainability_grade(mi),
            "parameters": param_count,
            "is_async": isinstance(node, ast.AsyncFunctionDef),
            "return_type": return_type,
            "has_docstring": (
                bool(node.body)
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ),
        }

    @classmethod
    def _analyze_class(
        cls,
        node: ast.ClassDef,
        source: str,
    ) -> dict[str, Any]:
        """
        Compute metrics for a class including all its methods.

        Args:
            node:   ClassDef AST node
            source: Full source string

        Returns:
            Class metrics dict with per-method breakdown
        """
        start = node.lineno
        end = node.end_lineno or node.lineno
        class_lines = end - start + 1

        methods: list[dict[str, Any]] = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_info = cls._analyze_function(item, source)
                methods.append(method_info)

        method_cc = [m["cyclomatic"] for m in methods]
        avg_cc = round(sum(method_cc) / max(len(method_cc), 1), 2)
        max_cc = max(method_cc) if method_cc else 0

        bases = []
        for base in node.bases:
            try:
                bases.append(ast.unparse(base))
            except Exception:
                bases.append("object")

        return {
            "name": node.name,
            "line_start": start,
            "line_end": end,
            "lines": class_lines,
            "bases": bases,
            "method_count": len(methods),
            "methods": methods,
            "avg_cyclomatic": avg_cc,
            "max_cyclomatic": max_cc,
            "complexity_grade": cyclomatic_grade(max_cc or 1),
            "has_docstring": (
                bool(node.body)
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ),
        }


# =============================================================================
# Main Complexity Engine (dispatcher)
# =============================================================================

class ComplexityEngine:
    """
    Main entry point for complexity analysis.

    Dispatches to PythonComplexityAnalyzer or JSComplexityAnalyzer
    based on the file extension. Returns a unified metrics format.
    """

    LANGUAGE_MAP: dict[str, str] = {
        ".py":   "python",
        ".js":   "javascript",
        ".jsx":  "javascript",
        ".ts":   "typescript",
        ".tsx":  "typescript",
        ".mjs":  "javascript",
    }

    @classmethod
    def analyze(
        cls,
        source: str,
        file_path: str,
    ) -> dict[str, Any]:
        """
        Analyze a single file and return all complexity metrics.

        Args:
            source:    Raw file content string
            file_path: File path (used for language detection)

        Returns:
            Complete metrics dict for the file
        """
        ext = Path(file_path).suffix.lower()
        language = cls.LANGUAGE_MAP.get(ext, "unknown")

        if language == "python":
            return PythonComplexityAnalyzer.analyze_file(source, file_path)
        elif language in ("javascript", "typescript"):
            result = JSComplexityAnalyzer.analyze_file(source, file_path)
            result["language"] = language
            return result
        else:
            # Generic: just LoC
            lines = source.splitlines()
            return {
                "file_path": file_path,
                "language": language or "unknown",
                "loc": {
                    "total_lines": len(lines),
                    "code_lines": len([l for l in lines if l.strip()]),
                    "blank_lines": len([l for l in lines if not l.strip()]),
                    "comment_lines": 0,
                    "docstring_lines": 0,
                    "comment_ratio": 0.0,
                },
                "functions": [],
                "classes": [],
                "file_metrics": {
                    "avg_cyclomatic": 0.0,
                    "max_cyclomatic": 0,
                    "avg_cognitive": 0.0,
                    "total_functions": 0,
                    "complex_functions": [],
                    "maintainability_index": 100.0,
                    "maintainability_grade": "A",
                    "halstead": HalsteadCalculator._empty(),
                    "grade": "A",
                },
            }

    @classmethod
    def analyze_project(
        cls,
        files: list[dict[str, str]],
        top_n_complex: int = 10,
    ) -> dict[str, Any]:
        """
        Analyze all files in a project and return aggregated metrics.

        Args:
            files:         List of {"path": str, "content": str} dicts
            top_n_complex: How many most-complex functions to return

        Returns:
            Project-level aggregated metrics dict
        """
        file_results: list[dict[str, Any]] = []
        all_functions: list[dict[str, Any]] = []

        for f in files:
            path = str(f.get("path") or "")
            content = str(f.get("content") or "")
            if not path or not content.strip():
                continue
            result = cls.analyze(content, path)
            file_results.append(result)

            # Collect all functions with file reference
            for func in result.get("functions") or []:
                all_functions.append({**func, "file": path})
            for cls_info in result.get("classes") or []:
                for method in cls_info.get("methods") or []:
                    all_functions.append({
                        **method,
                        "file": path,
                        "class": cls_info["name"],
                    })

        if not file_results:
            return {
                "total_files": 0,
                "total_functions": 0,
                "project_avg_cyclomatic": 0.0,
                "project_avg_cognitive": 0.0,
                "project_avg_mi": 0.0,
                "most_complex_functions": [],
                "files_by_complexity": [],
                "language_breakdown": {},
                "total_loc": 0,
                "total_code_loc": 0,
            }

        # Project-wide averages
        all_cc = [
            f["file_metrics"]["avg_cyclomatic"]
            for f in file_results
        ]
        all_cog = [
            f["file_metrics"].get("avg_cognitive", 0.0)
            for f in file_results
        ]
        all_mi = [
            f["file_metrics"]["maintainability_index"]
            for f in file_results
        ]

        # Top N most complex functions
        most_complex = sorted(
            all_functions,
            key=lambda x: x.get("cyclomatic", 0),
            reverse=True,
        )[:top_n_complex]

        # Files sorted by complexity (worst first)
        files_by_complexity = sorted(
            [
                {
                    "file": r["file_path"],
                    "avg_cyclomatic": r["file_metrics"]["avg_cyclomatic"],
                    "max_cyclomatic": r["file_metrics"]["max_cyclomatic"],
                    "maintainability_index": r["file_metrics"]["maintainability_index"],
                    "grade": r["file_metrics"]["grade"],
                    "total_lines": r["loc"]["total_lines"],
                }
                for r in file_results
            ],
            key=lambda x: x["max_cyclomatic"],
            reverse=True,
        )

        # Language breakdown
        lang_count: dict[str, int] = {}
        for r in file_results:
            lang = r.get("language") or "unknown"
            lang_count[lang] = lang_count.get(lang, 0) + 1

        total_loc = sum(
            r["loc"]["total_lines"] for r in file_results
        )
        total_code_loc = sum(
            r["loc"]["code_lines"] for r in file_results
        )

        return {
            "total_files": len(file_results),
            "total_functions": len(all_functions),
            "project_avg_cyclomatic": round(
                sum(all_cc) / max(len(all_cc), 1), 2
            ),
            "project_avg_cognitive": round(
                sum(all_cog) / max(len(all_cog), 1), 2
            ),
            "project_avg_mi": round(
                sum(all_mi) / max(len(all_mi), 1), 2
            ),
            "most_complex_functions": most_complex,
            "files_by_complexity": files_by_complexity[:20],
            "language_breakdown": lang_count,
            "total_loc": total_loc,
            "total_code_loc": total_code_loc,
            "file_results": file_results,
        }


# =============================================================================
# Compatibility aliases for parser.py (Step 33 integration)
# parser.py expects keys: cyclomatic, cognitive, rating, code_lines, comment_lines
# =============================================================================

def analyze_file_complexity(source: str, file_path: str) -> dict:
    """
    Compatibility wrapper that returns a flat dict matching parser.py expectations.

    parser.py uses: complexity["cyclomatic"], complexity["cognitive"],
                    complexity["rating"], complexity["code_lines"],
                    complexity["comment_lines"]

    Args:
        source:    Raw file content string
        file_path: File path for language detection

    Returns:
        Flat complexity dict with all keys parser.py expects
    """
    result = ComplexityEngine.analyze(source=source, file_path=file_path)
    metrics = result.get("file_metrics", {})
    loc = result.get("loc", {})

    # Map ComplexityEngine output to the flat keys parser.py expects
    cyclomatic = int(metrics.get("max_cyclomatic") or metrics.get("avg_cyclomatic") or 1)
    cognitive  = float(metrics.get("avg_cognitive") or 0.0)
    grade      = str(metrics.get("grade") or metrics.get("maintainability_grade") or "A")

    return {
        # Keys parser.py reads directly
        "cyclomatic":    cyclomatic,
        "cognitive":     cognitive,
        "rating":        grade,
        "code_lines":    int(loc.get("code_lines") or 0),
        "comment_lines": int(loc.get("comment_lines") or 0),
        # Bonus: full data for any future use
        "maintainability_index": float(metrics.get("maintainability_index") or 100.0),
        "total_lines":   int(loc.get("total_lines") or 0),
        "blank_lines":   int(loc.get("blank_lines") or 0),
        "language":      str(result.get("language") or "unknown"),
    }


def analyze_project_complexity(files: list, top_n_complex: int = 10) -> dict:
    """
    Compatibility wrapper around ComplexityEngine.analyze_project().

    Args:
        files:         List of file dicts with path and content
        top_n_complex: Most-complex functions to return

    Returns:
        Project-level aggregated metrics dict
    """
    return ComplexityEngine.analyze_project(files=files, top_n_complex=top_n_complex)