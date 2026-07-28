"""
Step 32 Test Suite - Dependency Analyzer
Run from backend/ directory:
    cd backend
    python test_dependency_analyzer.py
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
def test_python_import_extractor() -> None:
    print("[1] PythonImportExtractor")
    from app.core.parsers.dependency_analyzer import PythonImportExtractor

    code = (
        "import os\n"
        "import numpy as np\n"
        "from pathlib import Path\n"
        "from app.utils import helpers\n"
        "from app.models.user import User, UserCreate\n"
        "from . import sibling\n"
        "from ..core import config\n"
    )
    imports = PythonImportExtractor.extract(code, "app/api/v1/routes.py")

    print(f"  Found {len(imports)} imports:")
    for imp in imports:
        print(f"    module={imp['module']!r} relative={imp['is_relative']} level={imp['level']}")

    modules = [i["module"] for i in imports]
    assert "os" in modules
    assert "numpy" in modules
    assert "pathlib" in modules
    assert "app.utils" in modules
    assert "app.models.user" in modules
    # from . import sibling -> module='' but names=['sibling']
    rel_names = [n for i in imports if i['is_relative'] for n in i['names']]
    assert 'sibling' in rel_names, f'sibling not in relative names: {rel_names}'

    # Relative imports
    rel_imports = [i for i in imports if i["is_relative"]]
    assert len(rel_imports) == 2

    ok("PythonImportExtractor")


# ---------------------------------------------------------------------------
def test_js_import_extractor() -> None:
    print("[2] JSImportExtractor")
    from app.core.parsers.dependency_analyzer import JSImportExtractor

    code = (
        "import React from 'react';\n"
        "import { useState, useEffect } from 'react';\n"
        "import type { FC } from 'react';\n"
        "import axios from 'axios';\n"
        "import { UserService } from './services/user';\n"
        "import Button from '../components/Button';\n"
        "const utils = require('./utils/helpers');\n"
        "export { default } from './Button';\n"
    )
    imports = JSImportExtractor.extract(code, "src/pages/Login.tsx")

    print(f"  Found {len(imports)} imports:")
    for imp in imports:
        print(f"    module={imp['module']!r} relative={imp['is_relative']}")

    modules = [i["module"] for i in imports]
    assert "react" in modules
    assert "axios" in modules
    assert "./services/user" in modules or any("services/user" in m for m in modules)
    assert "../components/Button" in modules or any("Button" in m for m in modules)

    rel_imports = [i for i in imports if i["is_relative"]]
    assert len(rel_imports) >= 2

    ok("JSImportExtractor")


# ---------------------------------------------------------------------------
def test_module_resolver_python() -> None:
    print("[3] ModuleResolver - Python")
    from app.core.parsers.dependency_analyzer import ModuleResolver

    known_files = [
        "app/__init__.py",
        "app/main.py",
        "app/utils/helpers.py",
        "app/models/user.py",
        "app/api/v1/routes.py",
    ]
    resolver = ModuleResolver(known_files)

    # Absolute import resolving to internal file
    result1 = resolver.resolve_python(
        {"module": "app.utils", "is_relative": False, "level": 0},
        "app/api/v1/routes.py",
    )
    print(f"  app.utils -> {result1}")

    # Relative import
    result2 = resolver.resolve_python(
        {"module": "helpers", "is_relative": True, "level": 1},
        "app/utils/main.py",
    )
    print(f"  . import helpers -> {result2}")

    # External package (should return None)
    result3 = resolver.resolve_python(
        {"module": "fastapi", "is_relative": False, "level": 0},
        "app/main.py",
    )
    print(f"  fastapi (external) -> {result3}")
    assert result3 is None

    # Stdlib (should return None)
    result4 = resolver.resolve_python(
        {"module": "os", "is_relative": False, "level": 0},
        "app/main.py",
    )
    assert result4 is None

    ok("ModuleResolver Python")


# ---------------------------------------------------------------------------
def test_circular_detection() -> None:
    print("[4] Circular dependency detection")
    from app.core.parsers.dependency_analyzer import detect_circular_dependencies

    # A -> B -> C -> A (cycle)
    adj = {
        "a.py": {"b.py"},
        "b.py": {"c.py"},
        "c.py": {"a.py"},
        "d.py": {"e.py"},  # no cycle
        "e.py": set(),
    }
    cycles = detect_circular_dependencies(adj)
    print(f"  Cycles found: {len(cycles)}")
    for c in cycles:
        print(f"    {' -> '.join(c)}")

    assert len(cycles) >= 1
    cycle_files = set()
    for cycle in cycles:
        cycle_files.update(cycle)
    assert "a.py" in cycle_files
    assert "b.py" in cycle_files
    assert "c.py" in cycle_files

    # No cycle case
    adj_clean = {
        "main.py": {"utils.py"},
        "utils.py": {"helpers.py"},
        "helpers.py": set(),
    }
    cycles_clean = detect_circular_dependencies(adj_clean)
    assert len(cycles_clean) == 0

    ok("circular dependency detection")


# ---------------------------------------------------------------------------
def test_layout_hierarchical() -> None:
    print("[5] calculate_layout - hierarchical")
    from app.core.parsers.dependency_analyzer import calculate_layout

    nodes = [{"id": f"file_{i}.py"} for i in range(5)]
    edges = [
        {"source": "file_0.py", "target": "file_1.py"},
        {"source": "file_0.py", "target": "file_2.py"},
        {"source": "file_1.py", "target": "file_3.py"},
        {"source": "file_2.py", "target": "file_4.py"},
    ]

    positions = calculate_layout(nodes, edges, layout="hierarchical")
    print(f"  Positions: {positions}")

    assert len(positions) == 5
    for node_id, pos in positions.items():
        assert "x" in pos and "y" in pos
        assert isinstance(pos["x"], float)
        assert isinstance(pos["y"], (int, float))

    ok("hierarchical layout")


# ---------------------------------------------------------------------------
def test_layout_circular() -> None:
    print("[6] calculate_layout - circular")
    from app.core.parsers.dependency_analyzer import calculate_layout

    nodes = [{"id": f"f{i}.py"} for i in range(6)]
    positions = calculate_layout(nodes, [], layout="circular")

    assert len(positions) == 6
    # All nodes should be equidistant from center
    import math
    distances = [
        math.sqrt(p["x"]**2 + p["y"]**2)
        for p in positions.values()
    ]
    print(f"  Distances from center: {[round(d, 1) for d in distances]}")
    # All distances should be approximately equal
    assert max(distances) - min(distances) < 1.0

    ok("circular layout")


# ---------------------------------------------------------------------------
def test_full_analysis_python() -> None:
    print("[7] DependencyAnalyzer - Python project")
    from app.core.parsers.dependency_analyzer import DependencyAnalyzer

    files = [
        {
            "path": "app/main.py",
            "content": (
                "from app.api.routes import router\n"
                "from app.core.config import settings\n"
                "from app.database import init_db\n"
            ),
        },
        {
            "path": "app/api/routes.py",
            "content": (
                "from app.services.user_service import UserService\n"
                "from app.models.user import User\n"
            ),
        },
        {
            "path": "app/services/user_service.py",
            "content": (
                "from app.models.user import User\n"
                "from app.database import get_db\n"
            ),
        },
        {
            "path": "app/models/user.py",
            "content": "from app.database import Base\n",
        },
        {
            "path": "app/database.py",
            "content": "import sqlalchemy\n",
        },
        {
            "path": "app/core/config.py",
            "content": "import os\n",
        },
    ]

    analyzer = DependencyAnalyzer()
    graph = analyzer.analyze(files, layout="hierarchical")

    print(f"  Nodes: {len(graph['nodes'])}")
    print(f"  Edges: {len(graph['edges'])}")
    print(f"  Circular deps: {graph['metadata']['circular_count']}")
    print(f"  Orphans: {graph['metadata']['orphan_count']}")
    print(f"  Language breakdown: {graph['metadata']['language_breakdown']}")

    assert len(graph["nodes"]) >= 4
    assert len(graph["edges"]) >= 2
    assert graph["metadata"]["circular_count"] == 0  # no cycles in this graph
    assert "python" in graph["metadata"]["language_breakdown"]

    # Check node structure
    for node in graph["nodes"]:
        assert "id" in node
        assert "data" in node
        assert "position" in node
        assert "x" in node["position"]
        assert "y" in node["position"]
        assert "label" in node["data"]
        assert "language" in node["data"]
        assert "node_type" in node["data"]

    ok("DependencyAnalyzer Python full analysis")


# ---------------------------------------------------------------------------
def test_circular_dep_in_graph() -> None:
    print("[8] DependencyAnalyzer - detects circular dependency")
    from app.core.parsers.dependency_analyzer import DependencyAnalyzer

    # A -> B -> C -> A (circular)
    files = [
        {
            "path": "module_a.py",
            "content": "from module_b import something\n",
        },
        {
            "path": "module_b.py",
            "content": "from module_c import something\n",
        },
        {
            "path": "module_c.py",
            "content": "from module_a import something\n",
        },
    ]

    analyzer = DependencyAnalyzer()
    graph = analyzer.analyze(files)

    print(f"  Circular deps found: {graph['metadata']['circular_count']}")
    print(f"  Cycles: {graph['metadata']['circular_dependencies']}")

    assert graph["metadata"]["circular_count"] >= 1

    # Cyclic edges should be animated
    cyclic_edges = [e for e in graph["edges"] if e["data"].get("in_cycle")]
    print(f"  Cyclic edges: {len(cyclic_edges)}")

    ok("circular dependency detected in graph")


# ---------------------------------------------------------------------------
def test_orphan_detection() -> None:
    print("[9] DependencyAnalyzer - orphan node detection")
    from app.core.parsers.dependency_analyzer import DependencyAnalyzer

    files = [
        {
            "path": "main.py",
            "content": "from utils import helper\n",
        },
        {
            "path": "utils.py",
            "content": "# utility functions\ndef helper(): pass\n",
        },
        {
            "path": "orphan.py",
            "content": "# standalone module, no imports, not imported\nx = 42\n",
        },
    ]

    analyzer = DependencyAnalyzer()
    graph = analyzer.analyze(files)

    print(f"  Orphan count: {graph['metadata']['orphan_count']}")
    print(f"  Orphan nodes: {graph['metadata']['orphan_nodes']}")

    assert graph["metadata"]["orphan_count"] >= 1
    assert any("orphan" in n for n in graph["metadata"]["orphan_nodes"])

    ok("orphan node detection")


# ---------------------------------------------------------------------------
def test_js_analysis() -> None:
    print("[10] DependencyAnalyzer - JavaScript/TypeScript")
    from app.core.parsers.dependency_analyzer import DependencyAnalyzer

    files = [
        {
            "path": "src/App.tsx",
            "content": (
                "import React from 'react';\n"
                "import { BrowserRouter } from 'react-router-dom';\n"
                "import { Layout } from './components/Layout';\n"
                "import { AuthProvider } from './context/AuthContext';\n"
            ),
        },
        {
            "path": "src/components/Layout.tsx",
            "content": (
                "import React from 'react';\n"
                "import { Sidebar } from './Sidebar';\n"
            ),
        },
        {
            "path": "src/components/Sidebar.tsx",
            "content": (
                "import React from 'react';\n"
                "import { NavLink } from 'react-router-dom';\n"
            ),
        },
        {
            "path": "src/context/AuthContext.tsx",
            "content": (
                "import React from 'react';\n"
                "import axios from 'axios';\n"
            ),
        },
    ]

    analyzer = DependencyAnalyzer()
    graph = analyzer.analyze(files, layout="hierarchical")

    print(f"  Nodes: {len(graph['nodes'])}")
    print(f"  Edges: {len(graph['edges'])}")
    print(f"  Language: {graph['metadata']['language_breakdown']}")

    assert len(graph["nodes"]) >= 2
    assert "typescript" in graph["metadata"]["language_breakdown"]

    ok("DependencyAnalyzer JavaScript/TypeScript")


# ---------------------------------------------------------------------------
def test_node_details() -> None:
    print("[11] get_node_details")
    from app.core.parsers.dependency_analyzer import DependencyAnalyzer

    files = [
        {"path": "main.py", "content": "from utils import helper\nfrom config import settings\n"},
        {"path": "utils.py", "content": "from helpers import parse\n"},
        {"path": "helpers.py", "content": "# no imports\n"},
        {"path": "config.py", "content": "import os\n"},
    ]

    analyzer = DependencyAnalyzer()
    details = analyzer.get_node_details(files, "main.py")

    print(f"  File: {details.get('file')}")
    print(f"  Direct imports: {details.get('direct_imports')}")
    print(f"  Imported by: {details.get('imported_by')}")
    print(f"  Transitive deps: {details.get('transitive_dependencies')}")

    assert details.get("file") == "main.py"
    assert "direct_imports_count" in details
    assert "imported_by_count" in details
    assert "in_cycle" in details

    ok("get_node_details")


# ---------------------------------------------------------------------------
def test_empty_files() -> None:
    print("[12] DependencyAnalyzer - empty input")
    from app.core.parsers.dependency_analyzer import DependencyAnalyzer

    analyzer = DependencyAnalyzer()
    graph = analyzer.analyze([])

    assert graph["nodes"] == []
    assert graph["edges"] == []
    assert graph["metadata"]["total_files"] == 0

    ok("empty files returns empty graph")


# ---------------------------------------------------------------------------
def test_api_router_import() -> None:
    print("[13] Analytics API router import")
    from app.api.v1.analytics import (
        router,
        DependencyGraphRequest,
        NodeDetailsRequest,
    )

    print(f"  prefix: {router.prefix}")
    assert router.prefix == "/analytics"
    assert "analytics" in router.tags

    ok("analytics router imports")


# ---------------------------------------------------------------------------
def test_layout_grid() -> None:
    print("[14] calculate_layout - grid")
    from app.core.parsers.dependency_analyzer import calculate_layout

    nodes = [{"id": f"f{i}.py"} for i in range(9)]
    positions = calculate_layout(nodes, [], layout="grid")

    print(f"  Positions for 9 nodes (3x3 grid):")
    for nid, pos in list(positions.items())[:4]:
        print(f"    {nid}: ({pos['x']}, {pos['y']})")

    assert len(positions) == 9
    # Grid should have multiple rows
    y_values = set(p["y"] for p in positions.values())
    assert len(y_values) >= 2

    ok("grid layout")


# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 60)
    print("Step 32 - Dependency Graph Test Suite")
    print("=" * 60)
    print()

    tests = [
        test_python_import_extractor,
        test_js_import_extractor,
        test_module_resolver_python,
        test_circular_detection,
        test_layout_hierarchical,
        test_layout_circular,
        test_full_analysis_python,
        test_circular_dep_in_graph,
        test_orphan_detection,
        test_js_analysis,
        test_node_details,
        test_empty_files,
        test_api_router_import,
        test_layout_grid,
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
        print("Dependency graph system ready!")
        print()
        print("Test with API:")
        print("  POST /api/v1/analytics/dependency-graph")
        print("  POST /api/v1/analytics/node-details")
        print("  POST /api/v1/analytics/summary")

    import sys
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
