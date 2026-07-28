"""
Dependency Analyzer - Step 32
AI Codebase Assistant v2.0

Analyzes source code files to extract import/dependency relationships
and produces a graph structure for visualization in React Flow.

Supported languages:
    Python     - Uses ast module for 100% accurate import extraction
    JavaScript - Regex-based require() and import statement parsing
    TypeScript - Regex-based import/export parsing

Graph output format (React Flow compatible):
    {
        "nodes": [
            {
                "id": "src/auth/login.py",
                "data": {
                    "label": "login.py",
                    "file_path": "src/auth/login.py",
                    "language": "python",
                    "imports_count": 5,
                    "imported_by_count": 3,
                    "is_entry_point": false,
                    "is_orphan": false,
                    "node_type": "module"
                },
                "position": {"x": 0, "y": 0}
            }
        ],
        "edges": [
            {
                "id": "src/auth/login.py->src/utils/helpers.py",
                "source": "src/auth/login.py",
                "target": "src/utils/helpers.py",
                "data": {
                    "import_type": "internal",
                    "import_name": "helpers"
                }
            }
        ],
        "metadata": {
            "total_files": 42,
            "total_edges": 87,
            "circular_dependencies": [...],
            "orphan_nodes": [...],
            "most_imported": [...],
            "language_breakdown": {"python": 30, "javascript": 12}
        }
    }
"""

from __future__ import annotations

import ast
import logging
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

LANGUAGE_EXTENSIONS: dict[str, str] = {
    ".py":   "python",
    ".js":   "javascript",
    ".jsx":  "javascript",
    ".ts":   "typescript",
    ".tsx":  "typescript",
    ".mjs":  "javascript",
    ".cjs":  "javascript",
}

# External packages to exclude from dependency graph nodes
# (they show as external edges but not internal nodes)
KNOWN_STDLIB_PYTHON = frozenset([
    "os", "sys", "re", "json", "time", "datetime", "math", "random",
    "collections", "itertools", "functools", "typing", "pathlib",
    "logging", "hashlib", "hmac", "base64", "uuid", "enum", "abc",
    "dataclasses", "asyncio", "threading", "subprocess", "shutil",
    "copy", "io", "string", "struct", "socket", "http", "urllib",
    "email", "html", "xml", "csv", "sqlite3", "unittest", "traceback",
    "inspect", "importlib", "contextlib", "warnings", "weakref",
    "tempfile", "glob", "fnmatch", "stat", "platform", "signal",
])

KNOWN_STDLIB_JS = frozenset([
    "fs", "path", "os", "http", "https", "net", "url", "util",
    "events", "stream", "crypto", "buffer", "child_process",
    "cluster", "dns", "domain", "module", "process", "readline",
    "repl", "timers", "tty", "vm", "zlib",
])


# =============================================================================
# Import Extractors
# =============================================================================


def _strip_bom(text: str) -> str:
    """Remove UTF-8 BOM character from start of string."""
    return text.lstrip("\ufeff").lstrip("\u200b")


class PythonImportExtractor:
    """
    Extracts import statements from Python source using the ast module.

    Handles:
        import os                        -> stdlib
        import numpy as np               -> external package
        from pathlib import Path         -> stdlib
        from app.utils import helpers    -> internal (relative to project)
        from . import sibling            -> relative import
        from ..models import User        -> relative import
    """

    @staticmethod
    def extract(source: str, file_path: str) -> list[dict[str, Any]]:
        """
        Parse Python source and extract all import statements.

        Args:
            source:    Raw Python source code
            file_path: File path (used for resolving relative imports)

        Returns:
            List of import dicts with keys:
                module (str): Imported module name
                names (list[str]): Specific names imported
                is_relative (bool): True for from . import x
                level (int): Relative import level (0=absolute, 1=., 2=..)
                raw (str): Original import string
        """
        imports: list[dict[str, Any]] = []

        try:
            tree = ast.parse(_strip_bom(source.lstrip('\ufeff')).lstrip('\xef\xbb\xbf'))
        except SyntaxError as exc:
            logger.warning(
                "Python AST parse error in %s: %s", file_path, exc
            )
            return imports

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({
                        "module": alias.name,
                        "names": [alias.asname or alias.name],
                        "is_relative": False,
                        "level": 0,
                        "raw": f"import {alias.name}",
                        "line": node.lineno,
                    })

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                level = node.level or 0
                names = [a.name for a in node.names] if node.names else []
                is_relative = level > 0
                raw = (
                    f"from {'.' * level}{module} import "
                    + ", ".join(names)
                )
                imports.append({
                    "module": module,
                    "names": names,
                    "is_relative": is_relative,
                    "level": level,
                    "raw": raw,
                    "line": node.lineno,
                })

        return imports


class JSImportExtractor:
    """
    Extracts import/require statements from JavaScript and TypeScript.

    Handles:
        import React from 'react'
        import { useState, useEffect } from 'react'
        import type { FC } from 'react'
        const x = require('./utils')
        export { default } from './Button'
        import('./LazyComponent')  (dynamic import)
    """

    # ES6 import: import X from 'module' or import { X } from 'module'
    IMPORT_PAT = re.compile(
        r"""import\s+(?:type\s+)?(?:
            [\w*{}\s,]+               # what is imported
        )\s+from\s+['"]([^'"]+)['"]   # from 'module'
        |
        import\s*\(\s*['"]([^'"]+)['"]\s*\)  # dynamic import('module')
        """,
        re.VERBOSE | re.MULTILINE,
    )

    # CommonJS require: const x = require('module')
    REQUIRE_PAT = re.compile(
        r"""(?:const|let|var)\s+[\w{}\s,]+\s*=\s*require\s*\(\s*['"]([^'"]+)['"]\s*\)""",
        re.MULTILINE,
    )

    # export { X } from 'module'
    EXPORT_FROM_PAT = re.compile(
        r"""export\s+(?:type\s+)?(?:\*|{[^}]*})\s+from\s+['"]([^'"]+)['"]""",
        re.MULTILINE,
    )

    @classmethod
    def extract(cls, source: str, file_path: str) -> list[dict[str, Any]]:
        """
        Parse JS/TS source and extract all import/require statements.

        Args:
            source:    Raw JavaScript or TypeScript source
            file_path: File path for logging

        Returns:
            List of import dicts with module, is_relative, raw keys
        """
        imports: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add_import(module: str, raw: str, line_num: int = 0) -> None:
            if module and module not in seen:
                seen.add(module)
                imports.append({
                    "module": module,
                    "names": [],
                    "is_relative": module.startswith("."),
                    "level": module.count("../"),
                    "raw": raw,
                    "line": line_num,
                })

        # ES6 imports
        for match in cls.IMPORT_PAT.finditer(source):
            module = match.group(1) or match.group(2) or ""
            if module:
                line = source[:match.start()].count("\n") + 1
                add_import(module.strip(), match.group(0).strip(), line)

        # CommonJS requires
        for match in cls.REQUIRE_PAT.finditer(source):
            module = match.group(1) or ""
            if module:
                line = source[:match.start()].count("\n") + 1
                add_import(module.strip(), match.group(0).strip(), line)

        # Re-exports
        for match in cls.EXPORT_FROM_PAT.finditer(source):
            module = match.group(1) or ""
            if module:
                line = source[:match.start()].count("\n") + 1
                add_import(module.strip(), match.group(0).strip(), line)

        return imports


# =============================================================================
# Module Resolver
# =============================================================================

class ModuleResolver:
    """
    Resolves import module strings to canonical file paths within the project.

    Given a set of known project files, maps import strings to the
    corresponding internal file path (or marks them as external).
    """

    def __init__(self, known_files: list[str]) -> None:
        """
        Initialise resolver with the set of project files.

        Args:
            known_files: List of relative file paths in the project
        """
        self._known_files = set(known_files)
        # Build lookup maps for fast resolution
        self._stem_map: dict[str, str] = {}   # stem -> full path
        self._module_map: dict[str, str] = {} # dotted module -> full path

        for fp in known_files:
            path = Path(fp)
            stem = path.stem
            # Map stem (filename without extension)
            if stem not in self._stem_map:
                self._stem_map[stem] = fp
            # Map dotted module path (e.g. app.utils.helpers)
            module_key = (
                str(path.with_suffix(""))
                .replace("\\", "/")
                .replace("/", ".")
            )
            self._module_map[module_key] = fp

    def resolve_python(
        self,
        import_info: dict[str, Any],
        importer_path: str,
    ) -> str | None:
        """
        Resolve a Python import to an internal file path.

        Args:
            import_info:   Import dict from PythonImportExtractor
            importer_path: File path of the importing file

        Returns:
            Internal file path if found, None if external/stdlib
        """
        module = str(import_info.get("module") or "")
        is_relative = bool(import_info.get("is_relative"))
        level = int(import_info.get("level") or 0)

        if not module:
            return None

        # Check if stdlib
        top_level = module.split(".")[0]
        if top_level in KNOWN_STDLIB_PYTHON:
            return None

        # Relative imports: resolve relative to importer
        if is_relative:
            importer_dir = Path(importer_path).parent
            # Go up 'level - 1' directories (level=1 means same dir)
            for _ in range(max(0, level - 1)):
                importer_dir = importer_dir.parent
            module_path = str(
                importer_dir / module.replace(".", "/")
            ).replace("\\", "/")
            # Try with .py extension
            candidate = module_path + ".py"
            if candidate in self._known_files:
                return candidate
            # Try as __init__.py
            init_candidate = module_path + "/__init__.py"
            if init_candidate in self._known_files:
                return init_candidate
            return None

        # Absolute imports: try dotted module path
        module_as_path = module.replace(".", "/")
        candidates = [
            module_as_path + ".py",
            module_as_path + "/__init__.py",
        ]
        for candidate in candidates:
            if candidate in self._known_files:
                return candidate

        # Try module map lookup
        if module in self._module_map:
            return self._module_map[module]

        # Partial match: last component as stem
        parts = module.split(".")
        for part in reversed(parts):
            if part in self._stem_map:
                return self._stem_map[part]

        return None  # external package

    def resolve_js(
        self,
        import_info: dict[str, Any],
        importer_path: str,
    ) -> str | None:
        """
        Resolve a JS/TS import to an internal file path.

        Args:
            import_info:   Import dict from JSImportExtractor
            importer_path: File path of the importing file

        Returns:
            Internal file path if found, None if external package
        """
        module = str(import_info.get("module") or "")

        if not module:
            return None

        # External package (no leading ./ or ../)
        if not module.startswith("."):
            top_level = module.split("/")[0]
            if top_level in KNOWN_STDLIB_JS:
                return None
            return None  # npm package

        # Relative import
        importer_dir = Path(importer_path).parent
        target_path = (importer_dir / module).resolve()

        # Try various extensions
        extensions = [".ts", ".tsx", ".js", ".jsx", ".mjs"]
        for ext in extensions:
            candidate = str(target_path.with_suffix(ext)).replace("\\", "/")
            # Normalize to relative path
            if candidate in self._known_files:
                return candidate
            # Try without leading ./
            candidate_rel = candidate.lstrip("./")
            for known in self._known_files:
                if known.endswith(candidate_rel):
                    return known

        # Try as index file
        for ext in extensions:
            index_candidate = str(target_path / f"index{ext}").replace("\\", "/")
            for known in self._known_files:
                if known.endswith(
                    index_candidate.split("/")[-2] + "/index" + ext
                ):
                    return known

        return None


# =============================================================================
# Circular Dependency Detector
# =============================================================================

def detect_circular_dependencies(
    adjacency: dict[str, set[str]]
) -> list[list[str]]:
    """
    Detect circular dependency chains using DFS with cycle detection.

    Uses iterative DFS with a path stack to find all simple cycles
    (not just whether cycles exist).

    Args:
        adjacency: Dict mapping file_path -> set of file_paths it imports

    Returns:
        List of cycles, each cycle is a list of file paths forming the loop
        e.g. [["a.py", "b.py", "a.py"]]
    """
    cycles: list[list[str]] = []
    visited: set[str] = set()
    rec_stack: set[str] = set()

    def dfs(node: str, path: list[str]) -> None:
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in adjacency.get(node, set()):
            if neighbor not in visited:
                dfs(neighbor, path)
            elif neighbor in rec_stack:
                # Found a cycle
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                # Avoid duplicate cycles
                cycle_key = "->".join(sorted(cycle[:-1]))
                if not any(
                    "->".join(sorted(c[:-1])) == cycle_key
                    for c in cycles
                ):
                    cycles.append(cycle)

        path.pop()
        rec_stack.discard(node)

    for node in adjacency:
        if node not in visited:
            dfs(node, [])

    return cycles[:10]  # cap at 10 cycles for readability


# =============================================================================
# Graph Layout Calculator
# =============================================================================

def calculate_layout(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    layout: str = "hierarchical",
) -> dict[str, dict[str, float]]:
    """
    Calculate 2D positions for graph nodes.

    Uses a simple hierarchical layout (topological sort layers)
    for DAGs, and a circular layout for cyclic graphs.

    Args:
        nodes: List of node dicts with 'id' field
        edges: List of edge dicts with 'source' and 'target' fields
        layout: Layout algorithm: "hierarchical" | "circular" | "grid"

    Returns:
        Dict mapping node_id -> {"x": float, "y": float}
    """
    positions: dict[str, dict[str, float]] = {}
    node_ids = [n["id"] for n in nodes]

    if not node_ids:
        return positions

    if layout == "circular":
        import math
        n = len(node_ids)
        radius = max(300, n * 60)
        for i, node_id in enumerate(node_ids):
            angle = (2 * math.pi * i) / max(n, 1)
            positions[node_id] = {
                "x": round(radius * math.cos(angle), 2),
                "y": round(radius * math.sin(angle), 2),
            }
        return positions

    if layout == "grid":
        cols = max(1, int(len(node_ids) ** 0.5))
        for i, node_id in enumerate(node_ids):
            positions[node_id] = {
                "x": float((i % cols) * 250),
                "y": float((i // cols) * 150),
            }
        return positions

    # Hierarchical layout: topological sort then assign layers
    # Build adjacency for in-degree calculation
    in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
    adj: dict[str, list[str]] = {nid: [] for nid in node_ids}

    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src in in_degree and tgt in in_degree:
            adj[src].append(tgt)
            in_degree[tgt] += 1

    # BFS-based topological layering (Kahn's algorithm)
    layers: list[list[str]] = []
    queue: deque[str] = deque(
        nid for nid in node_ids if in_degree[nid] == 0
    )
    remaining = set(node_ids)

    while queue or remaining:
        if not queue:
            # Cycle detected — put remaining in own layer
            queue.extend(list(remaining)[:5])
        layer: list[str] = []
        next_queue: deque[str] = deque()
        while queue:
            node = queue.popleft()
            if node in remaining:
                remaining.discard(node)
                layer.append(node)
                for neighbor in adj.get(node, []):
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_queue.append(neighbor)
        if layer:
            layers.append(layer)
        queue = next_queue

    # Assign x/y based on layer
    x_spacing = 300
    y_spacing = 150

    for layer_idx, layer in enumerate(layers):
        layer_width = len(layer)
        x_start = -(layer_width - 1) * x_spacing / 2
        for item_idx, node_id in enumerate(layer):
            positions[node_id] = {
                "x": round(x_start + item_idx * x_spacing, 2),
                "y": round(layer_idx * y_spacing, 2),
            }

    # Assign any remaining nodes (shouldn't happen but safety net)
    for node_id in node_ids:
        if node_id not in positions:
            positions[node_id] = {"x": 0.0, "y": float(len(positions) * 50)}

    return positions


# =============================================================================
# Main Dependency Analyzer
# =============================================================================

class DependencyAnalyzer:
    """
    Analyzes a project's files to build a dependency graph.

    Accepts a list of file dicts (path + content) and returns
    a React Flow-compatible graph with nodes, edges, and metadata.

    Usage:
        analyzer = DependencyAnalyzer()
        graph = analyzer.analyze(files=[
            {"path": "src/main.py", "content": "import utils\\n..."},
            {"path": "src/utils.py", "content": "..."},
        ])
        # graph["nodes"], graph["edges"], graph["metadata"]
    """

    def __init__(self) -> None:
        """Initialise the analyzer (stateless — reusable across calls)."""
        pass

    def analyze(
        self,
        files: list[dict[str, str]],
        layout: str = "hierarchical",
        include_external: bool = False,
        max_nodes: int = 200,
    ) -> dict[str, Any]:
        """
        Analyze files and return a complete dependency graph.

        Args:
            files:            List of {"path": str, "content": str} dicts
            layout:           Node layout algorithm: hierarchical|circular|grid
            include_external: If True, include external packages as nodes
            max_nodes:        Maximum nodes in graph (truncated if exceeded)

        Returns:
            Dict with "nodes", "edges", and "metadata" keys
        """
        if not files:
            return self._empty_graph()

        # Step 1: Detect language for each file
        file_meta: dict[str, dict[str, Any]] = {}
        for f in files:
            path = str(f.get("path") or "")
            content = str(f.get("content") or "")
            language = LANGUAGE_EXTENSIONS.get(
                Path(path).suffix.lower(), "unknown"
            )
            if language != "unknown":
                file_meta[path] = {
                    "path": path,
                    "content": content,
                    "language": language,
                }

        if not file_meta:
            return self._empty_graph()

        known_files = list(file_meta.keys())
        resolver = ModuleResolver(known_files)

        # Step 2: Extract imports from each file
        # adjacency[A] = {B, C} means A imports B and C
        adjacency: dict[str, set[str]] = defaultdict(set)
        # external_imports[A] = {"numpy", "react", ...}
        external_imports: dict[str, set[str]] = defaultdict(set)

        for path, meta in file_meta.items():
            language = meta["language"]
            content = meta["content"]

            if language == "python":
                raw_imports = PythonImportExtractor.extract(content, path)
                for imp in raw_imports:
                    resolved = resolver.resolve_python(imp, path)
                    if resolved and resolved != path:
                        adjacency[path].add(resolved)
                    elif not resolved:
                        module = str(imp.get("module") or "")
                        top = module.split(".")[0]
                        if top and top not in KNOWN_STDLIB_PYTHON:
                            external_imports[path].add(top)

            elif language in ("javascript", "typescript"):
                raw_imports = JSImportExtractor.extract(content, path)
                for imp in raw_imports:
                    resolved = resolver.resolve_js(imp, path)
                    if resolved and resolved != path:
                        adjacency[path].add(resolved)
                    elif not resolved:
                        module = str(imp.get("module") or "")
                        if module and not module.startswith("."):
                            pkg = module.split("/")[0].lstrip("@")
                            external_imports[path].add(pkg)

        # Step 3: Compute node metrics
        # imported_by[B] = {A, C} means A and C import B
        imported_by: dict[str, set[str]] = defaultdict(set)
        for src, targets in adjacency.items():
            for tgt in targets:
                imported_by[tgt].add(src)

        # Identify entry points (not imported by anyone)
        entry_points = {
            path for path in file_meta
            if not imported_by.get(path) and adjacency.get(path)
        }
        # Identify orphans (no imports and not imported)
        orphans = {
            path for path in file_meta
            if not adjacency.get(path) and not imported_by.get(path)
        }

        # Step 4: Detect circular dependencies
        circular_deps = detect_circular_dependencies(dict(adjacency))

        # Step 5: Build node list (limit to max_nodes)
        sorted_files = sorted(
            file_meta.keys(),
            key=lambda p: len(imported_by.get(p, set())),
            reverse=True,
        )[:max_nodes]

        nodes: list[dict[str, Any]] = []
        for path in sorted_files:
            meta = file_meta[path]
            filename = Path(path).name
            import_count = len(adjacency.get(path, set()))
            imported_by_count = len(imported_by.get(path, set()))

            # Node type classification
            if path in entry_points:
                node_type = "entry_point"
            elif path in orphans:
                node_type = "orphan"
            elif imported_by_count > 5:
                node_type = "hub"
            else:
                node_type = "module"

            nodes.append({
                "id": path,
                "type": "moduleNode",  # React Flow custom node type
                "data": {
                    "label": filename,
                    "file_path": path,
                    "language": meta["language"],
                    "imports_count": import_count,
                    "imported_by_count": imported_by_count,
                    "is_entry_point": path in entry_points,
                    "is_orphan": path in orphans,
                    "is_hub": imported_by_count > 5,
                    "node_type": node_type,
                    "external_deps": list(
                        external_imports.get(path, set())
                    )[:5],
                },
                "position": {"x": 0, "y": 0},  # updated by layout step
            })

        # Step 6: Build edge list
        node_id_set = {n["id"] for n in nodes}
        edges: list[dict[str, Any]] = []
        edge_ids: set[str] = set()

        for src, targets in adjacency.items():
            if src not in node_id_set:
                continue
            for tgt in targets:
                if tgt not in node_id_set:
                    continue
                edge_id = f"{src}->{tgt}"
                if edge_id in edge_ids:
                    continue
                edge_ids.add(edge_id)

                # Check if this edge is part of a cycle
                in_cycle = any(
                    src in cycle and tgt in cycle
                    for cycle in circular_deps
                )

                edges.append({
                    "id": edge_id,
                    "source": src,
                    "target": tgt,
                    "type": "smoothstep",  # React Flow edge type
                    "animated": in_cycle,   # animate cyclic edges
                    "data": {
                        "import_type": "internal",
                        "in_cycle": in_cycle,
                    },
                    "style": {
                        "stroke": "#f87171" if in_cycle else "#3b82f6",
                        "strokeWidth": 2,
                    },
                })

        # Step 7: Calculate layout positions
        positions = calculate_layout(nodes, edges, layout=layout)
        for node in nodes:
            if node["id"] in positions:
                node["position"] = positions[node["id"]]

        # Step 8: Build metadata
        language_breakdown: dict[str, int] = defaultdict(int)
        for meta in file_meta.values():
            language_breakdown[meta["language"]] += 1

        most_imported = sorted(
            [
                {
                    "file": path,
                    "imported_by_count": len(imported_by.get(path, set())),
                    "imports_count": len(adjacency.get(path, set())),
                }
                for path in file_meta
            ],
            key=lambda x: x["imported_by_count"],
            reverse=True,
        )[:10]

        metadata = {
            "total_files": len(file_meta),
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "circular_dependencies": [
                {"cycle": c, "length": len(c) - 1}
                for c in circular_deps
            ],
            "circular_count": len(circular_deps),
            "orphan_nodes": list(orphans)[:10],
            "orphan_count": len(orphans),
            "entry_points": list(entry_points)[:10],
            "most_imported": most_imported,
            "language_breakdown": dict(language_breakdown),
            "layout": layout,
            "truncated": len(file_meta) > max_nodes,
        }

        return {
            "nodes": nodes,
            "edges": edges,
            "metadata": metadata,
        }

    @staticmethod
    def _empty_graph() -> dict[str, Any]:
        """Return an empty graph structure."""
        return {
            "nodes": [],
            "edges": [],
            "metadata": {
                "total_files": 0,
                "total_nodes": 0,
                "total_edges": 0,
                "circular_dependencies": [],
                "circular_count": 0,
                "orphan_nodes": [],
                "orphan_count": 0,
                "entry_points": [],
                "most_imported": [],
                "language_breakdown": {},
                "layout": "hierarchical",
                "truncated": False,
            },
        }

    def get_node_details(
        self,
        files: list[dict[str, str]],
        target_file: str,
    ) -> dict[str, Any]:
        """
        Get detailed dependency information for a specific file.

        Args:
            files:       Full project file list
            target_file: File path to inspect

        Returns:
            Dict with direct_imports, imported_by, transitive_deps,
            depth_from_root, and import_tree
        """
        graph = self.analyze(files, max_nodes=500)
        nodes = {n["id"]: n for n in graph["nodes"]}
        edges = graph["edges"]

        if target_file not in nodes:
            return {
                "error": f"File '{target_file}' not found in graph",
                "available_files": list(nodes.keys())[:20],
            }

        # Direct imports (what this file imports)
        direct_imports = [
            e["target"]
            for e in edges
            if e["source"] == target_file
        ]

        # Imported by (what files import this)
        imported_by = [
            e["source"]
            for e in edges
            if e["target"] == target_file
        ]

        # Transitive dependencies (BFS from this node)
        transitive: set[str] = set()
        queue: deque[str] = deque(direct_imports)
        visited_bfs: set[str] = {target_file}
        depth = 0

        while queue and depth < 10:
            level_size = len(queue)
            for _ in range(level_size):
                node = queue.popleft()
                if node not in visited_bfs:
                    visited_bfs.add(node)
                    transitive.add(node)
                    children = [
                        e["target"]
                        for e in edges
                        if e["source"] == node
                        and e["target"] not in visited_bfs
                    ]
                    queue.extend(children)
            depth += 1

        return {
            "file": target_file,
            "node_type": nodes[target_file]["data"]["node_type"],
            "direct_imports": direct_imports,
            "direct_imports_count": len(direct_imports),
            "imported_by": imported_by,
            "imported_by_count": len(imported_by),
            "transitive_dependencies": list(transitive)[:20],
            "transitive_count": len(transitive),
            "in_cycle": any(
                target_file in c["cycle"]
                for c in graph["metadata"]["circular_dependencies"]
            ),
        }