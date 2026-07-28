"""
Step 39 Test Suite - Architecture Diagram Generator
Run from backend/ directory:
    cd backend
    python test_architecture.py
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
def test_layer_classifier() -> None:
    print("[1] LayerClassifier")
    from app.core.parsers.architecture import LayerClassifier

    cases = [
        ("app/api/v1/auth.py",              "presentation"),
        ("app/api/routes/users.py",         "presentation"),
        ("src/controllers/HomeController.py","presentation"),
        ("app/services/auth_service.py",    "business"),
        ("app/core/agents/orchestrator.py", "business"),
        ("domain/use_cases/login.py",       "business"),
        ("app/models/user.py",              "data"),
        ("app/repositories/user_repo.py",   "data"),
        ("app/database.py",                 "data"),
        ("app/middleware/rate_limiter.py",  "infrastructure"),
        ("app/tasks/celery_app.py",         "infrastructure"),
        ("app/utils/helpers.py",            "utility"),
        ("shared/common/validators.py",     "utility"),
        ("main.py",                         "unknown"),
        ("setup.py",                        "unknown"),
    ]

    for path, expected_layer in cases:
        result = LayerClassifier.classify(path)
        assert result["layer_id"] == expected_layer, \
            f"classify('{path}') = '{result['layer_id']}', expected '{expected_layer}'"
        print(f"  {path:45s} -> {result['layer_id']}")

    # Test color is valid hex
    for path, _ in cases[:3]:
        info = LayerClassifier.classify(path)
        assert info["color"].startswith("#")
        assert len(info["color"]) == 7

    ok("LayerClassifier")


# ---------------------------------------------------------------------------
def test_class_extractor() -> None:
    print("[2] ClassHierarchyExtractor")
    from app.core.parsers.architecture import ClassHierarchyExtractor

    code = (
        "from abc import ABC, abstractmethod\n\n"
        "class BaseAgent(ABC):\n"
        '    """Abstract agent base."""\n'
        "    def run(self): pass\n"
        "    def validate(self): pass\n\n"
        "class SecurityAgent(BaseAgent):\n"
        "    def scan(self): pass\n"
        "    def report(self): pass\n\n"
        "class PerformanceAgent(BaseAgent):\n"
        "    def analyze(self): pass\n\n"
        "class Orchestrator:\n"
        "    def run_all(self): pass\n"
    )

    classes = ClassHierarchyExtractor.extract(code, "agents/base.py")
    names = [c["name"] for c in classes]
    print(f"  Classes found: {names}")

    assert "BaseAgent" in names
    assert "SecurityAgent" in names
    assert "PerformanceAgent" in names
    assert "Orchestrator" in names

    security = next(c for c in classes if c["name"] == "SecurityAgent")
    assert "BaseAgent" in security["bases"]
    assert "scan" in security["methods"]
    assert security["file_path"] == "agents/base.py"

    ok("ClassHierarchyExtractor")


# ---------------------------------------------------------------------------
def test_api_endpoint_extractor() -> None:
    print("[3] APIEndpointExtractor")
    from app.core.parsers.architecture import APIEndpointExtractor

    fastapi_code = (
        "from fastapi import APIRouter\n\n"
        "router = APIRouter()\n\n"
        "@router.get('/users')\n"
        "async def list_users():\n"
        "    return []\n\n"
        "@router.post('/users')\n"
        "async def create_user():\n"
        "    return {}\n\n"
        "@router.delete('/users/{id}')\n"
        "async def delete_user():\n"
        "    pass\n"
    )

    endpoints = APIEndpointExtractor.extract(fastapi_code, "api/users.py")
    print(f"  Endpoints found: {len(endpoints)}")
    for e in endpoints:
        print(f"  {e['method']:7s} {e['path']:20s} -> {e['handler']}")

    assert len(endpoints) == 3
    methods = {e["method"] for e in endpoints}
    assert "GET" in methods
    assert "POST" in methods
    assert "DELETE" in methods
    assert all(e["framework"] == "fastapi" for e in endpoints)

    ok("APIEndpointExtractor")


# ---------------------------------------------------------------------------
def test_package_analyzer() -> None:
    print("[4] PackageAnalyzer")
    from app.core.parsers.architecture import PackageAnalyzer

    files = [
        {"path": "app/api/users.py"},
        {"path": "app/api/auth.py"},
        {"path": "app/services/user_service.py"},
        {"path": "app/models/user.py"},
        {"path": "tests/test_users.py"},
        {"path": "main.py"},
    ]

    packages = PackageAnalyzer.group_by_package(files)
    print(f"  Packages: {dict(packages)}")

    assert "app" in packages
    assert "tests" in packages
    assert len(packages["app"]) == 4  # api×2 + services + models

    ok("PackageAnalyzer")


# ---------------------------------------------------------------------------
def test_mermaid_layered_diagram() -> None:
    print("[5] MermaidFormatter.layered_diagram")
    from app.core.parsers.architecture import MermaidFormatter

    layers = {
        "presentation": ["api/routes.py", "api/auth.py"],
        "business": ["services/user.py"],
        "data": ["models/user.py", "repositories/user.py"],
    }

    mermaid = MermaidFormatter.layered_diagram(layers, title="Test App")
    print(f"  Mermaid length: {len(mermaid)} chars")
    print(f"  First 200 chars:\n{mermaid[:200]}")

    assert "flowchart TD" in mermaid
    assert "presentation" in mermaid
    assert "business" in mermaid
    assert "data" in mermaid
    assert "routes" in mermaid or "api" in mermaid

    ok("Mermaid layered diagram")


# ---------------------------------------------------------------------------
def test_mermaid_class_diagram() -> None:
    print("[6] MermaidFormatter.class_hierarchy_diagram")
    from app.core.parsers.architecture import MermaidFormatter

    classes = [
        {
            "name": "BaseModel",
            "bases": [],
            "methods": ["save", "delete", "update"],
            "file_path": "models/base.py",
            "is_abstract": False,
        },
        {
            "name": "User",
            "bases": ["BaseModel"],
            "methods": ["authenticate", "get_profile"],
            "file_path": "models/user.py",
            "is_abstract": False,
        },
        {
            "name": "AdminUser",
            "bases": ["User"],
            "methods": ["get_all_users", "delete_user"],
            "file_path": "models/admin.py",
            "is_abstract": False,
        },
    ]

    mermaid = MermaidFormatter.class_hierarchy_diagram(classes)
    print(f"  Mermaid length: {len(mermaid)} chars")

    assert "classDiagram" in mermaid
    assert "BaseModel" in mermaid
    assert "User" in mermaid
    assert "AdminUser" in mermaid
    # Inheritance arrows
    assert "BaseModel <|-- User" in mermaid
    assert "User <|-- AdminUser" in mermaid

    ok("Mermaid class hierarchy diagram")


# ---------------------------------------------------------------------------
def test_mermaid_api_flow() -> None:
    print("[7] MermaidFormatter.api_flow_diagram")
    from app.core.parsers.architecture import MermaidFormatter

    endpoints = [
        {"method": "GET", "path": "/api/users", "handler": "list_users"},
        {"method": "POST", "path": "/api/users", "handler": "create_user"},
    ]

    mermaid = MermaidFormatter.api_flow_diagram(endpoints)
    print(f"  Mermaid length: {len(mermaid)} chars")

    assert "sequenceDiagram" in mermaid
    assert "Client" in mermaid
    assert "API" in mermaid
    assert "Service" in mermaid
    assert "Database" in mermaid
    assert "GET /api/users" in mermaid

    ok("Mermaid API flow diagram")


# ---------------------------------------------------------------------------
def test_react_flow_layered() -> None:
    print("[8] ReactFlowFormatter.layered_diagram")
    from app.core.parsers.architecture import ReactFlowFormatter

    layers = {
        "presentation": ["api/users.py", "api/auth.py"],
        "business": ["services/user_service.py"],
        "data": ["models/user.py"],
    }

    result = ReactFlowFormatter.layered_diagram(layers)
    print(f"  Nodes: {len(result['nodes'])}")
    print(f"  Edges: {len(result['edges'])}")

    assert "nodes" in result
    assert "edges" in result
    assert len(result["nodes"]) >= 4  # 3 layer groups + files

    # Check node structure
    for node in result["nodes"]:
        assert "id" in node
        assert "position" in node
        assert "data" in node
        assert "x" in node["position"]
        assert "y" in node["position"]

    ok("React Flow layered diagram")


# ---------------------------------------------------------------------------
def test_react_flow_class_hierarchy() -> None:
    print("[9] ReactFlowFormatter.class_hierarchy")
    from app.core.parsers.architecture import ReactFlowFormatter

    classes = [
        {
            "name": "Animal",
            "bases": [],
            "methods": ["speak", "move"],
            "file_path": "animals/base.py",
            "is_abstract": True,
        },
        {
            "name": "Dog",
            "bases": ["Animal"],
            "methods": ["fetch", "bark"],
            "file_path": "animals/dog.py",
            "is_abstract": False,
        },
    ]

    result = ReactFlowFormatter.class_hierarchy(classes)
    print(f"  Nodes: {len(result['nodes'])}")
    print(f"  Edges: {len(result['edges'])}")

    assert len(result["nodes"]) == 2
    assert len(result["edges"]) == 1  # Dog extends Animal

    edge = result["edges"][0]
    assert "Animal" in edge["source"]
    assert "Dog" in edge["target"]
    assert edge["label"] == "extends"

    ok("React Flow class hierarchy")


# ---------------------------------------------------------------------------
def test_architecture_generator_full() -> None:
    print("[10] ArchitectureGenerator.generate_all")
    from app.core.parsers.architecture import ArchitectureGenerator

    generator = ArchitectureGenerator()

    files = [
        {
            "path": "app/api/v1/users.py",
            "content": (
                "from fastapi import APIRouter\n"
                "router = APIRouter()\n\n"
                "@router.get('/users')\n"
                "async def list_users(): return []\n\n"
                "@router.post('/users')\n"
                "async def create_user(): return {}\n"
            ),
        },
        {
            "path": "app/services/user_service.py",
            "content": (
                "class UserService:\n"
                "    def get_user(self, id): pass\n"
                "    def create(self, data): pass\n"
            ),
        },
        {
            "path": "app/models/user.py",
            "content": (
                "from sqlalchemy import Column, String\n\n"
                "class User:\n"
                "    id = Column(String)\n"
                "    email = Column(String)\n"
                "    def __repr__(self): return self.email\n"
            ),
        },
        {
            "path": "app/repositories/user_repo.py",
            "content": (
                "class UserRepository:\n"
                "    def find_by_id(self, id): pass\n"
                "    def save(self, user): pass\n"
            ),
        },
        {
            "path": "app/utils/helpers.py",
            "content": "def format_date(d): return str(d)\n",
        },
    ]

    result = generator.generate_all(files, title="Test App")

    print(f"  Summary: {result['summary']}")
    print(f"  Layers: {list(result['raw_data']['layers'].keys())}")
    print(f"  Classes: {result['summary']['total_classes']}")
    print(f"  Endpoints: {result['summary']['total_endpoints']}")
    print(f"  Mermaid layered length: {len(result['mermaid']['layered'])}")

    assert result["summary"]["total_files"] == 5
    assert result["summary"]["total_classes"] >= 3
    assert result["summary"]["total_endpoints"] == 2
    assert "flowchart TD" in result["mermaid"]["layered"]
    assert "classDiagram" in result["mermaid"]["classes"]
    assert "sequenceDiagram" in result["mermaid"]["api_flow"]
    assert len(result["react_flow"]["layered"]["nodes"]) >= 3
    assert "presentation" in result["raw_data"]["layers"]
    assert "business" in result["raw_data"]["layers"]
    assert "data" in result["raw_data"]["layers"]

    ok("ArchitectureGenerator full generation")


# ---------------------------------------------------------------------------
def test_empty_input() -> None:
    print("[11] Empty input handling")
    from app.core.parsers.architecture import ArchitectureGenerator

    gen = ArchitectureGenerator()
    result = gen.generate_all([])

    assert result["summary"]["total_files"] == 0
    assert result["react_flow"]["layered"]["nodes"] == []
    assert result["mermaid"]["layered"] == ""

    ok("empty input handling")


# ---------------------------------------------------------------------------
def test_layer_definitions_api() -> None:
    print("[12] LayerClassifier.get_all_layers")
    from app.core.parsers.architecture import LayerClassifier

    layers = LayerClassifier.get_all_layers()
    print(f"  Layers defined: {len(layers)}")

    layer_ids = [l["layer_id"] for l in layers]
    assert "presentation" in layer_ids
    assert "business" in layer_ids
    assert "data" in layer_ids
    assert "infrastructure" in layer_ids
    assert "utility" in layer_ids
    assert "unknown" in layer_ids

    for layer in layers:
        assert "layer_id" in layer
        assert "display_name" in layer
        assert "color" in layer
        assert layer["color"].startswith("#")

    ok("layer definitions")


# ---------------------------------------------------------------------------
def test_analytics_api_has_architecture() -> None:
    print("[13] analytics.py has architecture endpoints")
    with open("app/api/v1/analytics.py", "r", encoding="utf-8") as f:
        content = f.read()

    assert "/architecture/all" in content
    assert "/architecture/layers" in content
    assert "/architecture/classes" in content
    assert "/architecture/layer-definitions" in content
    print(f"  Architecture endpoints: {content.count('/architecture/')}")

    ok("analytics.py has architecture endpoints")


# ---------------------------------------------------------------------------
def test_mermaid_component_diagram() -> None:
    print("[14] MermaidFormatter.component_diagram")
    from app.core.parsers.architecture import MermaidFormatter

    packages = {
        "api": ["api/users.py", "api/auth.py"],
        "services": ["services/user.py"],
        "models": ["models/user.py"],
    }
    cross_deps = [
        {"from_package": "api", "to_package": "services", "dependency_count": 3},
        {"from_package": "services", "to_package": "models", "dependency_count": 5},
    ]

    mermaid = MermaidFormatter.component_diagram(packages, cross_deps)
    print(f"  Mermaid length: {len(mermaid)} chars")
    print(f"  Content:\n{mermaid}")

    assert "graph LR" in mermaid
    assert "api" in mermaid
    assert "services" in mermaid
    assert "models" in mermaid
    assert "-->|3|" in mermaid or "-->|5|" in mermaid

    ok("Mermaid component diagram")


# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 60)
    print("Step 39 - Architecture Diagram Generator Test Suite")
    print("=" * 60)
    print()

    tests = [
        test_layer_classifier,
        test_class_extractor,
        test_api_endpoint_extractor,
        test_package_analyzer,
        test_mermaid_layered_diagram,
        test_mermaid_class_diagram,
        test_mermaid_api_flow,
        test_react_flow_layered,
        test_react_flow_class_hierarchy,
        test_architecture_generator_full,
        test_empty_input,
        test_layer_definitions_api,
        test_analytics_api_has_architecture,
        test_mermaid_component_diagram,
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
        print("Architecture diagram generator ready!")
        print()
        print("Phase 6 (Analytics Features) COMPLETE!")
        print()
        print("New API endpoints:")
        print("  POST /api/v1/analytics/architecture/all")
        print("  POST /api/v1/analytics/architecture/layers")
        print("  POST /api/v1/analytics/architecture/classes")
        print("  GET  /api/v1/analytics/architecture/layer-definitions")

    import sys
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
