"""
Architecture Diagram Generator - Step 39
AI Codebase Assistant v2.0

Analyzes a codebase and generates multiple diagram representations:

1. Layered Architecture Diagram
   Groups files into architectural layers based on path patterns:
   - Presentation (api/, routes/, views/, controllers/, pages/)
   - Business Logic (services/, core/, domain/, use_cases/)
   - Data Access (models/, repositories/, db/, database/)
   - Infrastructure (middleware/, tasks/, workers/, config/)
   - Utilities (utils/, helpers/, common/, shared/)

2. Component Diagram
   Shows which modules depend on which, grouped by package/directory.
   Nodes = packages, Edges = cross-package imports.

3. Class Hierarchy Diagram
   Extracts class inheritance relationships for Python files.
   Shows base → derived class relationships as a tree.

4. API Flow Diagram (Sequence)
   Maps HTTP endpoints to their service and model dependencies.
   Shows request flow: Client → Router → Service → Repository → DB.

Output formats:
   React Flow JSON  - Interactive graph for the frontend
   Mermaid.js       - Text syntax for Markdown embedding
   PlantUML         - Enterprise diagram format
   Summary          - Statistics about the architecture
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


# =============================================================================
# Layer Classifier
# =============================================================================

class LayerClassifier:
    """
    Classifies files into architectural layers based on path patterns.

    Layer priority (highest to lowest):
        presentation  - User-facing HTTP handlers
        business      - Business logic and orchestration
        data          - Data access and persistence
        infrastructure - Cross-cutting concerns
        utility       - Shared helpers
        unknown       - Unclassified
    """

    LAYER_PATTERNS: list[tuple[str, list[str], str]] = [
        # (layer_id, path_keywords, display_name)
        ("presentation", [
            "api", "routes", "views", "controllers", "handlers",
            "endpoints", "pages", "graphql", "rest", "grpc",
            "routers", "router",
        ], "Presentation Layer"),
        ("business", [
            "services", "service", "core", "domain", "use_cases",
            "usecases", "interactors", "commands", "queries",
            "managers", "orchestrators", "agents",
        ], "Business Logic Layer"),
        ("data", [
            "models", "model", "repositories", "repository",
            "repos", "db", "database", "storage", "dao",
            "entities", "schemas", "migrations",
        ], "Data Access Layer"),
        ("infrastructure", [
            "middleware", "tasks", "workers", "celery", "jobs",
            "config", "settings", "di", "container", "cache",
            "messaging", "events", "notifications",
        ], "Infrastructure Layer"),
        ("utility", [
            "utils", "util", "helpers", "helper", "common",
            "shared", "lib", "libs", "tools", "support",
        ], "Utility Layer"),
    ]

    LAYER_COLORS: dict[str, str] = {
        "presentation":   "#3B82F6",   # Blue
        "business":       "#8B5CF6",   # Purple
        "data":           "#10B981",   # Green
        "infrastructure": "#F59E0B",   # Amber
        "utility":        "#6B7280",   # Gray
        "unknown":        "#374151",   # Dark gray
    }

    @classmethod
    def classify(cls, file_path: str) -> dict[str, str]:
        """
        Classify a file path into an architectural layer.

        Args:
            file_path: Relative file path string

        Returns:
            Dict with layer_id, display_name, color
        """
        path_lower = file_path.lower().replace("\\", "/")
        parts = path_lower.split("/")

        for layer_id, keywords, display_name in cls.LAYER_PATTERNS:
            for part in parts:
                if any(kw in part for kw in keywords):
                    return {
                        "layer_id": layer_id,
                        "display_name": display_name,
                        "color": cls.LAYER_COLORS[layer_id],
                    }

        return {
            "layer_id": "unknown",
            "display_name": "Unknown",
            "color": cls.LAYER_COLORS["unknown"],
        }

    @classmethod
    def get_all_layers(cls) -> list[dict[str, str]]:
        """Return all layer definitions."""
        layers = [
            {
                "layer_id": lid,
                "display_name": dn,
                "color": cls.LAYER_COLORS[lid],
            }
            for lid, _, dn in cls.LAYER_PATTERNS
        ]
        layers.append({
            "layer_id": "unknown",
            "display_name": "Unknown",
            "color": cls.LAYER_COLORS["unknown"],
        })
        return layers


# =============================================================================
# Python Class Extractor
# =============================================================================

class ClassHierarchyExtractor:
    """
    Extracts class inheritance relationships from Python source.

    Produces a list of (class_name, base_class_name, file_path) triples
    for building class hierarchy diagrams.
    """

    @staticmethod
    def extract(source: str, file_path: str) -> list[dict[str, Any]]:
        """
        Extract class definitions and their base classes from Python source.

        Args:
            source:    Raw Python source code
            file_path: File path for attribution

        Returns:
            List of class info dicts with name, bases, methods, file_path
        """
        classes: list[dict[str, Any]] = []

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return classes

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            bases: list[str] = []
            for base in node.bases:
                try:
                    bases.append(ast.unparse(base))
                except Exception:
                    if isinstance(base, ast.Name):
                        bases.append(base.id)
                    elif isinstance(base, ast.Attribute):
                        bases.append(f"{base.attr}")

            # Filter out object (implicit base)
            bases = [b for b in bases if b not in ("object", "ABC")]

            methods: list[str] = [
                item.name
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not item.name.startswith("_")
            ]

            classes.append({
                "name": node.name,
                "bases": bases,
                "methods": methods[:8],  # cap at 8
                "line": node.lineno,
                "file_path": file_path,
                "is_abstract": any(
                    isinstance(b, ast.Name) and b.id in ("ABC", "ABCMeta")
                    for b in node.bases
                ),
            })

        return classes


# =============================================================================
# API Endpoint Extractor
# =============================================================================

class APIEndpointExtractor:
    """
    Extracts HTTP API endpoint definitions from Python route files.

    Supports FastAPI (@router.get, @app.post) and Flask (@app.route).
    """

    FASTAPI_PAT = re.compile(
        r'@(?:router|app)\.(get|post|put|delete|patch|head|options)\s*\(\s*["\']([^"\']+)["\']',
        re.MULTILINE,
    )
    FLASK_PAT = re.compile(
        r'@(?:app|blueprint)\.route\s*\(\s*["\']([^"\']+)["\'](?:[^)]*methods\s*=\s*\[([^\]]+)\])?',
        re.MULTILINE,
    )
    FUNC_PAT = re.compile(
        r'(?:async\s+)?def\s+(\w+)\s*\(',
        re.MULTILINE,
    )

    @classmethod
    def extract(cls, source: str, file_path: str) -> list[dict[str, Any]]:
        """
        Extract API endpoint definitions from a route file.

        Args:
            source:    Route file source code
            file_path: File path for attribution

        Returns:
            List of endpoint dicts with method, path, handler_name
        """
        endpoints: list[dict[str, Any]] = []

        # FastAPI style
        for match in cls.FASTAPI_PAT.finditer(source):
            http_method = match.group(1).upper()
            route_path = match.group(2)

            # Find the function name after the decorator
            after_decorator = source[match.end():]
            func_match = cls.FUNC_PAT.search(after_decorator[:200])
            handler_name = func_match.group(1) if func_match else "unknown"

            endpoints.append({
                "method": http_method,
                "path": route_path,
                "handler": handler_name,
                "file_path": file_path,
                "framework": "fastapi",
            })

        # Flask style
        for match in cls.FLASK_PAT.finditer(source):
            route_path = match.group(1)
            methods_str = match.group(2) or "GET"
            methods = [m.strip().strip("'\"") for m in methods_str.split(",")]

            after_decorator = source[match.end():]
            func_match = cls.FUNC_PAT.search(after_decorator[:200])
            handler_name = func_match.group(1) if func_match else "unknown"

            for http_method in methods:
                endpoints.append({
                    "method": http_method.upper(),
                    "path": route_path,
                    "handler": handler_name,
                    "file_path": file_path,
                    "framework": "flask",
                })

        return endpoints


# =============================================================================
# Package Analyzer
# =============================================================================

class PackageAnalyzer:
    """
    Groups files into packages (directories) and identifies
    cross-package dependencies for component diagrams.
    """

    @staticmethod
    def group_by_package(
        files: list[dict[str, str]],
    ) -> dict[str, list[str]]:
        """
        Group file paths by their top-level package directory.

        Args:
            files: List of file dicts with "path" keys

        Returns:
            Dict mapping package_name -> list of file_paths
        """
        packages: dict[str, list[str]] = defaultdict(list)
        for f in files:
            path = str(f.get("path") or "")
            parts = path.replace("\\", "/").split("/")
            if len(parts) >= 2:
                package = parts[0]
                if package in (".", ""):
                    package = parts[1] if len(parts) > 1 else "root"
            else:
                package = "root"
            packages[package].append(path)
        return dict(packages)

    @staticmethod
    def detect_cross_package_deps(
        import_edges: list[tuple[str, str]],
        package_map: dict[str, list[str]],
    ) -> list[dict[str, Any]]:
        """
        Find import relationships that cross package boundaries.

        Args:
            import_edges: List of (importer_path, imported_path) tuples
            package_map:  Package name -> file list mapping

        Returns:
            List of cross-package dependency dicts
        """
        # Build reverse map: file_path -> package
        file_to_package: dict[str, str] = {}
        for pkg, files in package_map.items():
            for fp in files:
                file_to_package[fp] = pkg

        # Find cross-package edges
        cross_deps: dict[tuple[str, str], int] = defaultdict(int)
        for importer, imported in import_edges:
            pkg_a = file_to_package.get(importer, "unknown")
            pkg_b = file_to_package.get(imported, "unknown")
            if pkg_a != pkg_b:
                key = (pkg_a, pkg_b)
                cross_deps[key] += 1

        return [
            {
                "from_package": a,
                "to_package": b,
                "dependency_count": count,
            }
            for (a, b), count in cross_deps.items()
        ]


# =============================================================================
# Diagram Formatters
# =============================================================================

class MermaidFormatter:
    """
    Generates Mermaid.js diagram syntax from architecture data.

    Mermaid diagrams can be embedded directly in Markdown and
    rendered by GitHub, GitLab, Notion, and many other tools.
    """

    @staticmethod
    def layered_diagram(
        layers: dict[str, list[str]],
        title: str = "Architecture Layers",
    ) -> str:
        """
        Generate a Mermaid flowchart showing architectural layers.

        Args:
            layers:  Dict mapping layer_id -> list of file_paths
            title:   Diagram title

        Returns:
            Mermaid diagram string
        """
        lines = [
            f"---",
            f"title: {title}",
            f"---",
            "flowchart TD",
        ]

        # Define layer subgraphs
        layer_order = [
            "presentation", "business", "data",
            "infrastructure", "utility", "unknown"
        ]

        layer_display = {
            "presentation": "Presentation Layer",
            "business": "Business Logic",
            "data": "Data Access",
            "infrastructure": "Infrastructure",
            "utility": "Utilities",
            "unknown": "Other",
        }

        for layer_id in layer_order:
            files = layers.get(layer_id, [])
            if not files:
                continue

            display = layer_display.get(layer_id, layer_id)
            lines.append(f"    subgraph {layer_id}[\"{display}\"]")
            for fp in files[:8]:  # cap at 8 per layer
                node_id = fp.replace("/", "_").replace(".", "_").replace("-", "_")
                label = Path(fp).name
                lines.append(f"        {node_id}[\"{label}\"]")
            lines.append("    end")

        # Add layer arrows (presentation depends on business, etc.)
        layer_deps = [
            ("presentation", "business"),
            ("business", "data"),
            ("business", "infrastructure"),
            ("infrastructure", "utility"),
        ]
        for src, tgt in layer_deps:
            if layers.get(src) and layers.get(tgt):
                lines.append(f"    {src} --> {tgt}")

        return "\n".join(lines)

    @staticmethod
    def class_hierarchy_diagram(
        classes: list[dict[str, Any]],
        title: str = "Class Hierarchy",
    ) -> str:
        """
        Generate a Mermaid classDiagram from class definitions.

        Args:
            classes: List of class info dicts
            title:   Diagram title

        Returns:
            Mermaid classDiagram string
        """
        lines = [
            "classDiagram",
            f"    note \"{title}\"",
        ]

        # Define classes
        for cls_info in classes[:20]:  # cap at 20
            name = cls_info["name"]
            methods = cls_info.get("methods", [])
            lines.append(f"    class {name} {{")
            for method in methods[:5]:
                lines.append(f"        +{method}()")
            lines.append("    }")

        # Add inheritance arrows
        for cls_info in classes[:20]:
            name = cls_info["name"]
            for base in cls_info.get("bases", []):
                # Only add arrow if base is in our class list
                known_names = {c["name"] for c in classes}
                if base in known_names:
                    lines.append(f"    {base} <|-- {name}")

        return "\n".join(lines)

    @staticmethod
    def component_diagram(
        packages: dict[str, list[str]],
        cross_deps: list[dict[str, Any]],
        title: str = "Component Dependencies",
    ) -> str:
        """
        Generate a Mermaid graph showing package-level dependencies.

        Args:
            packages:   Package name -> files mapping
            cross_deps: Cross-package dependency list
            title:      Diagram title

        Returns:
            Mermaid graph string
        """
        lines = [
            "graph LR",
            f"    %% {title}",
        ]

        # Define package nodes
        for pkg, files in packages.items():
            if pkg in (".", "", "root"):
                continue
            node_id = pkg.replace("-", "_").replace(".", "_")
            file_count = len(files)
            lines.append(
                f"    {node_id}[\"{pkg}\\n{file_count} files\"]"
            )

        # Add dependency arrows
        for dep in cross_deps[:30]:
            src = dep["from_package"].replace("-", "_").replace(".", "_")
            tgt = dep["to_package"].replace("-", "_").replace(".", "_")
            count = dep["dependency_count"]
            lines.append(f"    {src} -->|{count}| {tgt}")

        return "\n".join(lines)

    @staticmethod
    def api_flow_diagram(
        endpoints: list[dict[str, Any]],
        title: str = "API Request Flow",
    ) -> str:
        """
        Generate a Mermaid sequence diagram for API flows.

        Args:
            endpoints: List of endpoint dicts
            title:     Diagram title

        Returns:
            Mermaid sequenceDiagram string
        """
        lines = [
            "sequenceDiagram",
            f"    title {title}",
            "    participant Client",
            "    participant API",
            "    participant Service",
            "    participant Database",
        ]

        for endpoint in endpoints[:8]:  # cap at 8
            method = endpoint.get("method", "GET")
            path = endpoint.get("path", "/")
            handler = endpoint.get("handler", "handler")
            lines.append(f"    Client->>API: {method} {path}")
            lines.append(f"    API->>Service: {handler}()")
            lines.append(f"    Service->>Database: query()")
            lines.append(f"    Database-->>Service: result")
            lines.append(f"    Service-->>API: response")
            lines.append(f"    API-->>Client: 200 OK")

        return "\n".join(lines)


# =============================================================================
# React Flow Formatter
# =============================================================================

class ReactFlowFormatter:
    """
    Generates React Flow compatible node/edge JSON for interactive diagrams.
    """

    @staticmethod
    def layered_diagram(
        layers: dict[str, list[str]],
    ) -> dict[str, Any]:
        """
        Generate React Flow nodes and edges for layered architecture.

        Args:
            layers: Dict mapping layer_id -> list of file_paths

        Returns:
            Dict with nodes, edges for React Flow
        """
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []

        layer_y: dict[str, int] = {
            "presentation": 0,
            "business": 200,
            "data": 400,
            "infrastructure": 200,
            "utility": 600,
            "unknown": 800,
        }
        layer_colors = LayerClassifier.LAYER_COLORS

        # Layer group nodes
        for layer_id, files in layers.items():
            if not files:
                continue

            y = layer_y.get(layer_id, 600)
            color = layer_colors.get(layer_id, "#374151")

            # Add a group node for the layer
            nodes.append({
                "id": f"layer:{layer_id}",
                "type": "group",
                "position": {"x": 0, "y": y},
                "data": {
                    "label": LayerClassifier.LAYER_PATTERNS[
                        next(
                            (i for i, (lid, _, _)
                             in enumerate(LayerClassifier.LAYER_PATTERNS)
                             if lid == layer_id),
                            -1
                        )
                    ][2] if layer_id != "unknown" else "Other",
                    "layer_id": layer_id,
                    "color": color,
                    "file_count": len(files),
                },
                "style": {
                    "backgroundColor": color + "20",
                    "borderColor": color,
                    "width": 800,
                    "height": 150,
                },
            })

            # File nodes within each layer
            for i, fp in enumerate(files[:10]):
                node_id = f"file:{fp}"
                nodes.append({
                    "id": node_id,
                    "type": "fileNode",
                    "position": {
                        "x": 20 + (i % 5) * 155,
                        "y": y + 40 + (i // 5) * 60,
                    },
                    "data": {
                        "label": Path(fp).name,
                        "file_path": fp,
                        "layer": layer_id,
                        "color": color,
                    },
                    "parentNode": f"layer:{layer_id}",
                })

        # Layer dependency edges
        layer_dep_pairs = [
            ("presentation", "business"),
            ("business", "data"),
            ("business", "infrastructure"),
        ]
        for src_layer, tgt_layer in layer_dep_pairs:
            if src_layer in layers and tgt_layer in layers:
                edges.append({
                    "id": f"layer-dep:{src_layer}->{tgt_layer}",
                    "source": f"layer:{src_layer}",
                    "target": f"layer:{tgt_layer}",
                    "type": "smoothstep",
                    "animated": False,
                    "style": {"stroke": "#6B7280", "strokeWidth": 2},
                })

        return {"nodes": nodes, "edges": edges}

    @staticmethod
    def class_hierarchy(
        classes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Generate React Flow nodes and edges for class hierarchy.

        Args:
            classes: Class info dicts

        Returns:
            React Flow graph dict
        """
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        class_names = {c["name"] for c in classes}

        for i, cls_info in enumerate(classes[:25]):
            name = cls_info["name"]
            nodes.append({
                "id": f"class:{name}",
                "type": "classNode",
                "position": {
                    "x": (i % 4) * 250,
                    "y": (i // 4) * 200,
                },
                "data": {
                    "label": name,
                    "methods": cls_info.get("methods", [])[:5],
                    "file_path": cls_info.get("file_path", ""),
                    "is_abstract": cls_info.get("is_abstract", False),
                },
            })

            for base in cls_info.get("bases", []):
                if base in class_names:
                    edges.append({
                        "id": f"inherit:{base}->{name}",
                        "source": f"class:{base}",
                        "target": f"class:{name}",
                        "type": "smoothstep",
                        "markerEnd": {"type": "ArrowClosed"},
                        "label": "extends",
                        "style": {
                            "stroke": "#8B5CF6",
                            "strokeWidth": 2,
                        },
                    })

        return {"nodes": nodes, "edges": edges}


# =============================================================================
# Main Architecture Generator
# =============================================================================

class ArchitectureGenerator:
    """
    Main entry point for architecture diagram generation.

    Orchestrates all analyzers and formatters to produce
    complete diagram data in multiple formats.
    """

    def __init__(self) -> None:
        """Initialize sub-analyzers."""
        self._layer_classifier = LayerClassifier()

    def generate_all(
        self,
        files: list[dict[str, str]],
        title: str = "Project Architecture",
    ) -> dict[str, Any]:
        """
        Generate all diagram types for a project.

        Args:
            files: List of {"path": str, "content": str} dicts
            title: Project title for diagram headers

        Returns:
            Dict with all diagram formats and metadata
        """
        if not files:
            return self._empty_result()

        # Classify files into layers
        layers: dict[str, list[str]] = defaultdict(list)
        for f in files:
            path = str(f.get("path") or "")
            if not path:
                continue
            layer_info = LayerClassifier.classify(path)
            layers[layer_info["layer_id"]].append(path)

        # Extract classes from Python files
        all_classes: list[dict[str, Any]] = []
        all_endpoints: list[dict[str, Any]] = []

        for f in files:
            path = str(f.get("path") or "")
            content = str(f.get("content") or "")
            if not content.strip():
                continue

            ext = Path(path).suffix.lower()
            if ext == ".py":
                classes = ClassHierarchyExtractor.extract(content, path)
                all_classes.extend(classes)
                endpoints = APIEndpointExtractor.extract(content, path)
                all_endpoints.extend(endpoints)

        # Package-level analysis
        package_map = PackageAnalyzer.group_by_package(files)

        # Build import edges from dependency analyzer
        import_edges: list[tuple[str, str]] = []
        try:
            from app.core.parsers.dependency_analyzer import (
                PythonImportExtractor,
                ModuleResolver,
            )
            known_files = [str(f.get("path", "")) for f in files]
            resolver = ModuleResolver(known_files)
            for f in files:
                path = str(f.get("path") or "")
                content = str(f.get("content") or "")
                ext = Path(path).suffix.lower()
                if ext == ".py" and content.strip():
                    raw_imports = PythonImportExtractor.extract(content, path)
                    for imp in raw_imports:
                        resolved = resolver.resolve_python(imp, path)
                        if resolved and resolved != path:
                            import_edges.append((path, resolved))
        except Exception:
            pass  # Dependency analysis is optional

        cross_pkg_deps = PackageAnalyzer.detect_cross_package_deps(
            import_edges, package_map
        )

        # Generate all formats
        mermaid_layered = MermaidFormatter.layered_diagram(
            dict(layers), title=f"{title} — Layers"
        )
        mermaid_classes = MermaidFormatter.class_hierarchy_diagram(
            all_classes, title=f"{title} — Classes"
        )
        mermaid_components = MermaidFormatter.component_diagram(
            package_map, cross_pkg_deps,
            title=f"{title} — Components"
        )
        mermaid_api = MermaidFormatter.api_flow_diagram(
            all_endpoints[:8], title=f"{title} — API Flow"
        )

        react_flow_layers = ReactFlowFormatter.layered_diagram(dict(layers))
        react_flow_classes = ReactFlowFormatter.class_hierarchy(all_classes)

        # Summary statistics
        summary = {
            "total_files": len(files),
            "total_classes": len(all_classes),
            "total_endpoints": len(all_endpoints),
            "total_packages": len(package_map),
            "layers": {
                layer_id: len(file_list)
                for layer_id, file_list in layers.items()
                if file_list
            },
            "cross_package_dependencies": len(cross_pkg_deps),
            "inheritance_relationships": sum(
                len(c.get("bases", [])) for c in all_classes
            ),
            "title": title,
        }

        return {
            "summary": summary,
            "mermaid": {
                "layered": mermaid_layered,
                "classes": mermaid_classes,
                "components": mermaid_components,
                "api_flow": mermaid_api,
            },
            "react_flow": {
                "layered": react_flow_layers,
                "classes": react_flow_classes,
            },
            "raw_data": {
                "layers": dict(layers),
                "classes": all_classes[:30],
                "endpoints": all_endpoints[:20],
                "packages": {
                    pkg: len(fls)
                    for pkg, fls in package_map.items()
                },
                "cross_package_deps": cross_pkg_deps[:20],
            },
        }

    def generate_layer_diagram(
        self,
        files: list[dict[str, str]],
    ) -> dict[str, Any]:
        """
        Generate only the layered architecture diagram.

        Args:
            files: Project file list

        Returns:
            Dict with mermaid, react_flow, and layer stats
        """
        layers: dict[str, list[str]] = defaultdict(list)
        for f in files:
            path = str(f.get("path") or "")
            if path:
                info = LayerClassifier.classify(path)
                layers[info["layer_id"]].append(path)

        return {
            "mermaid": MermaidFormatter.layered_diagram(dict(layers)),
            "react_flow": ReactFlowFormatter.layered_diagram(dict(layers)),
            "layer_counts": {
                lid: len(fls) for lid, fls in layers.items() if fls
            },
        }

    def generate_class_diagram(
        self,
        files: list[dict[str, str]],
    ) -> dict[str, Any]:
        """
        Generate class hierarchy diagram from Python files.

        Args:
            files: Project file list (Python files only processed)

        Returns:
            Dict with mermaid, react_flow, and class list
        """
        classes: list[dict[str, Any]] = []
        for f in files:
            path = str(f.get("path") or "")
            content = str(f.get("content") or "")
            if Path(path).suffix.lower() == ".py" and content.strip():
                classes.extend(
                    ClassHierarchyExtractor.extract(content, path)
                )

        return {
            "mermaid": MermaidFormatter.class_hierarchy_diagram(classes),
            "react_flow": ReactFlowFormatter.class_hierarchy(classes),
            "classes": classes[:30],
            "total_classes": len(classes),
            "inheritance_count": sum(
                len(c.get("bases", [])) for c in classes
            ),
        }

    @staticmethod
    def _empty_result() -> dict[str, Any]:
        """Return empty result structure."""
        return {
            "summary": {
                "total_files": 0,
                "total_classes": 0,
                "total_endpoints": 0,
                "total_packages": 0,
                "layers": {},
            },
            "mermaid": {
                "layered": "",
                "classes": "",
                "components": "",
                "api_flow": "",
            },
            "react_flow": {
                "layered": {"nodes": [], "edges": []},
                "classes": {"nodes": [], "edges": []},
            },
            "raw_data": {
                "layers": {},
                "classes": [],
                "endpoints": [],
                "packages": {},
                "cross_package_deps": [],
            },
        }
