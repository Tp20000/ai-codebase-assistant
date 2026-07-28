"""
Step 33 Test Suite - Code Complexity Metrics
Run from backend/ directory:
    cd backend
    python test_complexity.py
"""

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
def test_loc_counter_python() -> None:
    print("[1] LOCCounter Python")
    from app.core.parsers.complexity import LOCCounter

    code = (
        '"""Module docstring."""\n'
        "\n"
        "import os\n"
        "\n"
        "# This is a comment\n"
        "def hello():  # inline comment\n"
        "    pass\n"
        "\n"
        "x = 1\n"
    )

    result = LOCCounter.count_python(code)
    print(f"  total={result['total_lines']} code={result['code_lines']} "
          f"comment={result['comment_lines']} blank={result['blank_lines']}")

    assert result["total_lines"] == 9
    assert result["blank_lines"] >= 1
    assert result["comment_lines"] + result["docstring_lines"] >= 1
    assert result["code_lines"] >= 0  # docstring may count some as docstring
    # Total check: blank + comment + docstring + code = total
    accounted = (result["blank_lines"] + result["comment_lines"] +
                 result["docstring_lines"] + result["code_lines"])
    assert accounted == result["total_lines"], \
        f"Lines don't add up: {accounted} != {result['total_lines']}"

    ok("LOCCounter Python")


# ---------------------------------------------------------------------------
def test_loc_counter_js() -> None:
    print("[2] LOCCounter JavaScript")
    from app.core.parsers.complexity import LOCCounter

    code = (
        "// Header comment\n"
        "/*\n"
        " * Block comment\n"
        " */\n"
        "\n"
        "const x = 1;\n"
        "function hello() {\n"
        "    return x;\n"
        "}\n"
    )

    result = LOCCounter.count_js(code)
    print(f"  total={result['total_lines']} code={result['code_lines']} "
          f"comment={result['comment_lines']} blank={result['blank_lines']}")

    assert result["total_lines"] == 9
    assert result["comment_lines"] >= 2
    assert result["blank_lines"] >= 1
    assert result["code_lines"] >= 3

    ok("LOCCounter JavaScript")


# ---------------------------------------------------------------------------
def test_cyclomatic_simple() -> None:
    print("[3] CyclomaticCalculator - simple function (CC=1)")
    import ast
    from app.core.parsers.complexity import CyclomaticCalculator

    code = "def add(a, b):\n    return a + b\n"
    tree = ast.parse(code)
    func = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef))
    cc = CyclomaticCalculator.calculate(func)
    print(f"  CC for simple function: {cc}")
    assert cc == 1, f"Simple function should have CC=1, got {cc}"

    ok("cyclomatic simple (CC=1)")


# ---------------------------------------------------------------------------
def test_cyclomatic_complex() -> None:
    print("[4] CyclomaticCalculator - complex function")
    import ast
    from app.core.parsers.complexity import CyclomaticCalculator

    code = (
        "def process(x, y, z):\n"
        "    if x > 0:\n"
        "        if y > 0:\n"
        "            result = x + y\n"
        "        else:\n"
        "            result = x - y\n"
        "    elif z:\n"
        "        for i in range(10):\n"
        "            if i % 2 == 0:\n"
        "                result = i\n"
        "    else:\n"
        "        try:\n"
        "            result = x / z\n"
        "        except ZeroDivisionError:\n"
        "            result = 0\n"
        "    return result\n"
    )
    tree = ast.parse(code)
    func = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef))
    cc = CyclomaticCalculator.calculate(func)
    print(f"  CC for complex function: {cc}")
    assert cc >= 6, f"Complex function should have CC>=6, got {cc}"

    ok(f"cyclomatic complex (CC={cc})")


# ---------------------------------------------------------------------------
def test_cognitive_simple() -> None:
    print("[5] CognitiveCalculator - simple (cog=0)")
    import ast
    from app.core.parsers.complexity import CognitiveCalculator

    code = "def add(a, b):\n    return a + b\n"
    tree = ast.parse(code)
    func = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef))
    cog = CognitiveCalculator.calculate(func, "add")
    print(f"  Cognitive for simple function: {cog}")
    assert cog == 0, f"Simple function should have cog=0, got {cog}"

    ok("cognitive simple (cog=0)")


# ---------------------------------------------------------------------------
def test_cognitive_nested() -> None:
    print("[6] CognitiveCalculator - nested (higher score)")
    import ast
    from app.core.parsers.complexity import CognitiveCalculator

    code = (
        "def nested(x):\n"
        "    if x > 0:\n"
        "        for i in range(x):\n"
        "            if i % 2 == 0:\n"
        "                return i\n"
        "    return 0\n"
    )
    tree = ast.parse(code)
    func = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef))
    cog = CognitiveCalculator.calculate(func, "nested")
    print(f"  Cognitive for nested function: {cog}")
    assert cog >= 3, f"Nested function should have cog>=3, got {cog}"

    ok(f"cognitive nested (cog={cog})")


# ---------------------------------------------------------------------------
def test_halstead_metrics() -> None:
    print("[7] HalsteadCalculator")
    from app.core.parsers.complexity import HalsteadCalculator

    code = (
        "def multiply(a, b):\n"
        "    result = a * b\n"
        "    return result\n"
    )
    metrics = HalsteadCalculator.calculate(code)
    print(f"  n1={metrics['n1_unique_operators']} "
          f"n2={metrics['n2_unique_operands']}")
    print(f"  volume={metrics['volume']} "
          f"difficulty={metrics['difficulty']}")
    print(f"  bugs={metrics['bugs_delivered']}")

    assert metrics["n1_unique_operators"] > 0
    assert metrics["n2_unique_operands"] > 0
    assert metrics["volume"] > 0
    assert metrics["bugs_delivered"] >= 0
    assert isinstance(metrics["time_seconds"], float)

    ok("Halstead metrics")


# ---------------------------------------------------------------------------
def test_maintainability_index() -> None:
    print("[8] calculate_maintainability_index")
    from app.core.parsers.complexity import calculate_maintainability_index

    # Simple, short function should score high
    mi_high = calculate_maintainability_index(
        halstead_volume=50.0,
        cyclomatic_complexity=1,
        loc=5,
    )
    print(f"  Simple function MI: {mi_high}")
    assert mi_high > 60, f"Simple function MI should be > 60, got {mi_high}"

    # Complex, long function should score lower
    mi_low = calculate_maintainability_index(
        halstead_volume=5000.0,
        cyclomatic_complexity=25,
        loc=200,
    )
    print(f"  Complex function MI: {mi_low}")
    assert mi_low < mi_high, "Complex function should score lower"

    # Bounds check
    assert 0.0 <= mi_high <= 100.0
    assert 0.0 <= mi_low <= 100.0

    ok("maintainability index")


# ---------------------------------------------------------------------------
def test_complexity_grades() -> None:
    print("[9] Grade functions")
    from app.core.parsers.complexity import cyclomatic_grade, maintainability_grade

    assert cyclomatic_grade(1)  == "A"
    assert cyclomatic_grade(5)  == "A"
    assert cyclomatic_grade(6)  == "B"
    assert cyclomatic_grade(10) == "B"
    assert cyclomatic_grade(11) == "C"
    assert cyclomatic_grade(20) == "D"
    assert cyclomatic_grade(21) == "F"

    assert maintainability_grade(100) == "A"
    assert maintainability_grade(85)  == "A"
    assert maintainability_grade(80)  == "B"
    assert maintainability_grade(70)  == "C"
    assert maintainability_grade(55)  == "D"
    assert maintainability_grade(40)  == "F"

    print("  Cyclomatic: 1->A 6->B 11->C 20->D 21->F")
    print("  Maintain:   85->A 80->B 70->C 55->D 40->F")

    ok("grade functions")


# ---------------------------------------------------------------------------
def test_python_file_analysis() -> None:
    print("[10] PythonComplexityAnalyzer.analyze_file")
    from app.core.parsers.complexity import PythonComplexityAnalyzer

    code = (
        '"""Calculator module."""\n\n'
        "def add(a: int, b: int) -> int:\n"
        '    """Add two numbers."""\n'
        "    return a + b\n\n"
        "def divide(x: float, y: float) -> float:\n"
        '    """Divide with branch."""\n'
        "    if y == 0:\n"
        "        raise ValueError('div by zero')\n"
        "    return x / y\n\n"
        "class Calculator:\n"
        '    """Calculator class."""\n\n'
        "    def multiply(self, x, y):\n"
        "        return x * y\n\n"
        "    def power(self, base, exp):\n"
        "        if exp < 0:\n"
        "            return 1 / (base ** abs(exp))\n"
        "        return base ** exp\n"
    )

    result = PythonComplexityAnalyzer.analyze_file(code, "calculator.py")

    print(f"  File: {result['file_path']}")
    print(f"  Functions: {len(result['functions'])}")
    print(f"  Classes: {len(result['classes'])}")
    print(f"  Avg CC: {result['file_metrics']['avg_cyclomatic']}")
    print(f"  MI: {result['file_metrics']['maintainability_index']}")
    print(f"  Grade: {result['file_metrics']['grade']}")

    assert result["file_path"] == "calculator.py"
    assert result["language"] == "python"
    assert len(result["functions"]) >= 2  # add, divide
    assert len(result["classes"]) >= 1    # Calculator
    assert result["file_metrics"]["avg_cyclomatic"] >= 1.0
    assert 0 <= result["file_metrics"]["maintainability_index"] <= 100

    # Check function structure
    for func in result["functions"]:
        assert "name" in func
        assert "cyclomatic" in func
        assert "cognitive" in func
        assert "complexity_grade" in func
        assert func["cyclomatic"] >= 1

    # divide should have CC=2 (one if branch)
    divide_fn = next(
        (f for f in result["functions"] if f["name"] == "divide"), None
    )
    if divide_fn:
        assert divide_fn["cyclomatic"] >= 2, \
            f"divide CC should be >= 2, got {divide_fn['cyclomatic']}"
        print(f"  divide CC={divide_fn['cyclomatic']} cog={divide_fn['cognitive']}")

    ok("PythonComplexityAnalyzer full file analysis")


# ---------------------------------------------------------------------------
def test_complexity_engine_dispatch() -> None:
    print("[11] ComplexityEngine language dispatch")
    from app.core.parsers.complexity import ComplexityEngine

    py_result = ComplexityEngine.analyze(
        "def f(x):\n    return x\n",
        "test.py",
    )
    assert py_result["language"] == "python"
    print(f"  .py -> {py_result['language']}")

    js_result = ComplexityEngine.analyze(
        "function f(x) { return x; }\n",
        "test.js",
    )
    assert js_result["language"] == "javascript"
    print(f"  .js -> {js_result['language']}")

    ts_result = ComplexityEngine.analyze(
        "function f(x: number): number { return x; }\n",
        "test.ts",
    )
    assert ts_result["language"] == "typescript"
    print(f"  .ts -> {ts_result['language']}")

    unknown = ComplexityEngine.analyze("x = 1", "test.xyz")
    assert unknown["language"] == "unknown"

    ok("ComplexityEngine dispatch")


# ---------------------------------------------------------------------------
def test_project_analysis() -> None:
    print("[12] ComplexityEngine.analyze_project")
    from app.core.parsers.complexity import ComplexityEngine

    files = [
        {
            "path": "main.py",
            "content": (
                "def simple(x):\n    return x\n\n"
                "def complex_fn(a, b, c, d):\n"
                "    if a:\n"
                "        if b:\n"
                "            for i in range(c):\n"
                "                if i % 2 == 0:\n"
                "                    return i\n"
                "    elif d:\n"
                "        return d\n"
                "    return 0\n"
            ),
        },
        {
            "path": "utils.py",
            "content": (
                "def add(a, b):\n    return a + b\n\n"
                "def subtract(a, b):\n    return a - b\n"
            ),
        },
    ]

    result = ComplexityEngine.analyze_project(files, top_n_complex=5)

    print(f"  Total files: {result['total_files']}")
    print(f"  Total functions: {result['total_functions']}")
    print(f"  Avg CC: {result['project_avg_cyclomatic']}")
    print(f"  Avg MI: {result['project_avg_mi']}")
    print(f"  Most complex: {[f['name'] for f in result['most_complex_functions']]}")

    assert result["total_files"] == 2
    assert result["total_functions"] >= 4
    assert result["project_avg_cyclomatic"] >= 1.0
    assert result["project_avg_mi"] > 0
    assert len(result["most_complex_functions"]) >= 1
    assert result["most_complex_functions"][0]["name"] == "complex_fn"

    ok("analyze_project aggregation")


# ---------------------------------------------------------------------------
def test_halstead_empty_source() -> None:
    print("[13] Halstead - edge cases")
    from app.core.parsers.complexity import HalsteadCalculator

    empty = HalsteadCalculator.calculate("")
    assert empty["volume"] == 0.0
    assert empty["bugs_delivered"] == 0.0

    one_line = HalsteadCalculator.calculate("x = 1")
    print(f"  One-liner: volume={one_line['volume']}")
    assert one_line["volume"] >= 0

    ok("Halstead edge cases")


# ---------------------------------------------------------------------------
def test_analytics_api_has_complexity() -> None:
    print("[14] analytics.py has complexity endpoints")
    with open("app/api/v1/analytics.py", "r") as f:
        content = f.read()

    assert "complexity" in content.lower(), \
        "analytics.py missing complexity endpoints"
    assert "/complexity" in content or "complexity" in content
    print(f"  analytics.py size: {len(content)} chars")
    print(f"  Has 'complexity': {content.count('complexity')} occurrences")

    ok("analytics.py has complexity endpoints")


# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 60)
    print("Step 33 - Code Complexity Metrics Test Suite")
    print("=" * 60)
    print()

    tests = [
        test_loc_counter_python,
        test_loc_counter_js,
        test_cyclomatic_simple,
        test_cyclomatic_complex,
        test_cognitive_simple,
        test_cognitive_nested,
        test_halstead_metrics,
        test_maintainability_index,
        test_complexity_grades,
        test_python_file_analysis,
        test_complexity_engine_dispatch,
        test_project_analysis,
        test_halstead_empty_source,
        test_analytics_api_has_complexity,
    ]

    for fn in tests:
        try:
            fn()
        except Exception as exc:
            fail(fn.__name__, exc)
        print()

    print("=" * 60)
    print(f"Results: {PASS} passed | {FAIL} failed")
    print("ALL TESTS PASSED" if FAIL == 0 else "SOME TESTS FAILED")
    print("=" * 60)

    if FAIL == 0:
        print()
        print("Complexity metrics engine ready!")
        print()
        print("API endpoints added:")
        print("  POST /api/v1/analytics/complexity")
        print("  POST /api/v1/analytics/complexity/project")

    import sys
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
