"""
Analytics API - Step 32
AI Codebase Assistant v2.0

REST endpoints for codebase analytics:
    POST /api/v1/analytics/dependency-graph
        Generate dependency graph from uploaded files

    GET  /api/v1/analytics/dependency-graph/{project_id}
        Get cached dependency graph for a project

    POST /api/v1/analytics/node-details
        Get detailed dependency info for a specific file

    GET  /api/v1/analytics/summary
        Quick analytics summary (file counts, language breakdown)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.parsers.dependency_analyzer import DependencyAnalyzer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analytics", tags=["analytics"])

_analyzer = DependencyAnalyzer()


# =============================================================================
# Request / Response Models
# =============================================================================

class FileEntry(BaseModel):
    """A single file entry for analysis."""

    path: str = Field(..., description="Relative file path")
    content: str = Field(..., description="File content string")


class DependencyGraphRequest(BaseModel):
    """Request body for dependency graph generation."""

    files: list[FileEntry] = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Files to analyze (max 500)",
    )
    layout: str = Field(
        default="hierarchical",
        description="Layout algorithm: hierarchical | circular | grid",
    )
    include_external: bool = Field(
        default=False,
        description="Include external packages as nodes",
    )
    max_nodes: int = Field(
        default=200,
        ge=10,
        le=500,
        description="Maximum nodes in graph",
    )


class NodeDetailsRequest(BaseModel):
    """Request body for node detail lookup."""

    files: list[FileEntry] = Field(..., min_length=1)
    target_file: str = Field(..., description="File path to inspect")


# =============================================================================
# Endpoints
# =============================================================================

@router.post(
    "/dependency-graph",
    summary="Generate dependency graph from files",
    description=(
        "Analyzes file imports/requires and returns a React Flow-compatible "
        "graph with nodes, edges, and metadata. "
        "Detects circular dependencies, orphan modules, and hub nodes."
    ),
)
async def generate_dependency_graph(
    request: DependencyGraphRequest,
) -> dict[str, Any]:
    """
    Generate a dependency graph from a list of project files.

    Args:
        request: DependencyGraphRequest with files and layout options

    Returns:
        Dict with nodes, edges, and metadata for React Flow rendering
    """
    valid_layouts = {"hierarchical", "circular", "grid"}
    if request.layout not in valid_layouts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid layout '{request.layout}'. Valid: {valid_layouts}",
        )

    files = [{"path": f.path, "content": f.content} for f in request.files]

    logger.info(
        "Generating dependency graph: files=%d layout=%s",
        len(files), request.layout,
    )

    try:
        graph = _analyzer.analyze(
            files=files,
            layout=request.layout,
            include_external=request.include_external,
            max_nodes=request.max_nodes,
        )
        return graph
    except Exception as exc:
        logger.error("Dependency graph error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Graph generation failed: {exc}",
        )


@router.post(
    "/node-details",
    summary="Get detailed info for a specific file node",
)
async def get_node_details(
    request: NodeDetailsRequest,
) -> dict[str, Any]:
    """
    Get detailed dependency information for a specific file.

    Returns direct imports, what imports this file, transitive
    dependencies, and whether the file is in a circular dependency.

    Args:
        request: NodeDetailsRequest with files and target_file

    Returns:
        Detailed node dict with import chains
    """
    files = [{"path": f.path, "content": f.content} for f in request.files]

    try:
        details = _analyzer.get_node_details(
            files=files,
            target_file=request.target_file,
        )
        return details
    except Exception as exc:
        logger.error("Node details error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Node details failed: {exc}",
        )


@router.post(
    "/summary",
    summary="Get analytics summary for a file set",
)
async def get_analytics_summary(
    files: list[FileEntry],
) -> dict[str, Any]:
    """
    Return a quick analytics summary without full graph computation.

    Args:
        files: List of project files

    Returns:
        Summary dict with file counts, language breakdown, complexity hints
    """
    from pathlib import Path
    from collections import Counter

    file_list = [{"path": f.path, "content": f.content} for f in files]

    # Language breakdown
    ext_to_lang = {
        ".py": "python", ".js": "javascript", ".jsx": "javascript",
        ".ts": "typescript", ".tsx": "typescript",
        ".md": "markdown", ".json": "json", ".css": "css",
        ".html": "html", ".sql": "sql", ".yaml": "yaml",
    }
    language_counts: Counter = Counter()
    total_lines = 0
    total_chars = 0

    for f in file_list:
        ext = Path(f["path"]).suffix.lower()
        lang = ext_to_lang.get(ext, "other")
        language_counts[lang] += 1
        total_lines += f["content"].count("\n")
        total_chars += len(f["content"])

    # Quick graph for metadata only (no layout calculation)
    try:
        graph = _analyzer.analyze(files=file_list, max_nodes=500)
        meta = graph["metadata"]
    except Exception:
        meta = {}

    return {
        "total_files": len(file_list),
        "total_lines": total_lines,
        "total_characters": total_chars,
        "average_file_size_lines": round(total_lines / max(len(file_list), 1), 1),
        "language_breakdown": dict(language_counts.most_common()),
        "dependency_stats": {
            "total_edges": meta.get("total_edges", 0),
            "circular_count": meta.get("circular_count", 0),
            "orphan_count": meta.get("orphan_count", 0),
            "most_imported": meta.get("most_imported", [])[:5],
        },
    }


# =============================================================================
# Git History Endpoints (Step 34)
# =============================================================================

class CommitEntry(BaseModel):
    """A single git commit entry for analysis."""
    hash: str = Field(default="", description="Commit SHA")
    author_email: str = Field(default="", description="Author email")
    author_name: str = Field(default="", description="Author name")
    date: str = Field(default="", description="Commit date ISO string")
    message: str = Field(default="", description="Commit message")
    files_changed: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of file change dicts with path, additions, deletions",
    )


class GitAnalysisRequest(BaseModel):
    """Request for git history analysis."""
    commits: list[CommitEntry] = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="List of commit objects",
    )
    top_hotspots: int = Field(default=20, ge=1, le=100)


class GitRawLogRequest(BaseModel):
    """Request with raw git log string."""
    raw_log: str = Field(
        ...,
        min_length=1,
        description="Raw git log --numstat output",
    )
    top_hotspots: int = Field(default=20, ge=1, le=100)


class FileHistoryRequest(BaseModel):
    """Request for single-file git history."""
    commits: list[CommitEntry] = Field(..., min_length=1)
    file_path: str = Field(..., description="File path to inspect")


class BlameRequest(BaseModel):
    """Request for blame analysis."""
    blame_lines: list[dict[str, Any]] = Field(
        ...,
        min_length=1,
        description="List of blame line dicts with author, date, content",
    )


_git_analyzer_instance = None


def _get_git_analyzer():
    """Lazy singleton for GitAnalyzer."""
    global _git_analyzer_instance
    if _git_analyzer_instance is None:
        from app.core.parsers.git_analyzer import GitAnalyzer
        _git_analyzer_instance = GitAnalyzer()
    return _git_analyzer_instance


@router.post(
    "/git/analyze",
    summary="Analyze git commit history",
    description=(
        "Analyzes git commit history to find hotspot files, "
        "contributor stats, bug-prone files, and co-change patterns."
    ),
)
async def analyze_git_history(request: GitAnalysisRequest) -> dict[str, Any]:
    """
    Analyze git commit history from structured commit list.

    Args:
        request: GitAnalysisRequest with commits list

    Returns:
        Full git analysis with hotspots, contributors, bug files
    """
    try:
        commits = [c.model_dump() for c in request.commits]
        result = _get_git_analyzer().analyze_commits(
            commits=commits,
            top_hotspots=request.top_hotspots,
        )
        return result
    except Exception as exc:
        logger.error("Git analysis error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Git analysis failed: {exc}",
        )


@router.post(
    "/git/analyze-raw",
    summary="Analyze raw git log output",
)
async def analyze_raw_git_log(request: GitRawLogRequest) -> dict[str, Any]:
    """
    Analyze raw git log --numstat output.

    Args:
        request: GitRawLogRequest with raw_log string

    Returns:
        Full git analysis dict
    """
    try:
        result = _get_git_analyzer().analyze_raw_log(
            raw_log=request.raw_log,
            top_hotspots=request.top_hotspots,
        )
        return result
    except Exception as exc:
        logger.error("Raw git log error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Raw log analysis failed: {exc}",
        )


@router.post(
    "/git/file-history",
    summary="Get commit history for a specific file",
)
async def get_file_history(request: FileHistoryRequest) -> dict[str, Any]:
    """
    Get all commits that touched a specific file with churn trend.

    Args:
        request: FileHistoryRequest with commits and file_path

    Returns:
        File-specific history with author breakdown and weekly churn
    """
    try:
        commits = [c.model_dump() for c in request.commits]
        result = _get_git_analyzer().get_file_history(
            commits=commits,
            file_path=request.file_path,
        )
        return result
    except Exception as exc:
        logger.error("File history error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File history failed: {exc}",
        )


@router.post(
    "/git/blame",
    summary="Analyze git blame data for a file",
)
async def analyze_blame(request: BlameRequest) -> dict[str, Any]:
    """
    Analyze blame data to show line ownership and staleness.

    Args:
        request: BlameRequest with blame_lines list

    Returns:
        Ownership stats with author percentages and age metrics
    """
    try:
        result = _get_git_analyzer().analyze_blame(request.blame_lines)
        return result
    except Exception as exc:
        logger.error("Blame analysis error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Blame analysis failed: {exc}",
        )

# =============================================================================
# Language Detection Endpoints (Step 35)
# =============================================================================

class LanguageDetectRequest(BaseModel):
    """Request for single file language detection."""
    file_path: str = Field(..., description="File path")
    content: str = Field(default="", description="File content (optional)")


class BatchLanguageRequest(BaseModel):
    """Request for batch language detection."""
    files: list[FileEntry] = Field(..., min_length=1, max_length=1000)


@router.post(
    "/language/detect",
    summary="Detect programming language of a file",
)
async def detect_language(request: LanguageDetectRequest) -> dict[str, Any]:
    """
    Detect the programming language of a file using extension,
    shebang, and content heuristics.

    Args:
        request: File path and optional content

    Returns:
        Detection result with language_id, confidence, method, and info
    """
    from app.core.parsers.language_detector import LanguageDetector
    result = LanguageDetector.detect(
        file_path=request.file_path,
        content=request.content,
    )
    return result


@router.post(
    "/language/detect-batch",
    summary="Detect languages for multiple files",
)
async def detect_languages_batch(request: BatchLanguageRequest) -> dict[str, Any]:
    """
    Detect languages for a batch of files and return project stats.

    Args:
        request: List of files with path and content

    Returns:
        Per-file detections plus project language breakdown
    """
    from app.core.parsers.language_detector import LanguageDetector
    files = [{"path": f.path, "content": f.content} for f in request.files]
    detections = LanguageDetector.detect_batch(files)
    stats = LanguageDetector.get_project_language_stats(files)
    return {
        "detections": detections,
        "project_stats": stats,
    }


@router.get(
    "/language/supported",
    summary="List all supported languages with metadata",
)
async def list_supported_languages() -> dict[str, Any]:
    """
    Return all supported languages with their full metadata.

    Returns:
        Dict with languages list and routing information
    """
    from app.core.parsers.language_detector import (
        LANGUAGES, EXTENSION_MAP, LanguageRouter
    )
    return {
        "languages": [
            {**info.to_dict(), "routing": LanguageRouter.route(lang_id)}
            for lang_id, info in LANGUAGES.items()
        ],
        "total_supported": len(LANGUAGES),
        "extension_count": len(EXTENSION_MAP),
    }

# =============================================================================
# Similarity Endpoints (Step 38)
# =============================================================================

class SimilarityRequest(BaseModel):
    """Request for project-wide similarity analysis."""
    files: list[FileEntry] = Field(..., min_length=2, max_length=1000)
    threshold: float = Field(
        default=0.7, ge=0.0, le=1.0,
        description="Minimum similarity score to report"
    )
    algorithm: str = Field(
        default="auto",
        description="Algorithm: auto | exact | jaccard | minhash"
    )


class FileSimilarityRequest(BaseModel):
    """Request for intra-file duplicate detection."""
    content: str = Field(..., min_length=1)
    file_path: str = Field(default="unknown")
    window_lines: int = Field(default=8, ge=3, le=50)


class CompareFilesRequest(BaseModel):
    """Request to compare exactly two files."""
    file_a: FileEntry
    file_b: FileEntry


_similarity_engine = None


def _get_similarity_engine():
    """Lazy singleton for SimilarityEngine."""
    global _similarity_engine
    if _similarity_engine is None:
        from app.core.parsers.similarity import SimilarityEngine
        _similarity_engine = SimilarityEngine()
    return _similarity_engine


@router.post(
    "/similarity/project",
    summary="Find duplicate and near-duplicate files in a project",
    description=(
        "Analyzes all files for code similarity using exact hashing, "
        "Jaccard similarity, or MinHash LSH. Returns duplicate pairs "
        "with similarity scores and code snippets."
    ),
)
async def analyze_project_similarity(
    request: SimilarityRequest,
) -> dict[str, Any]:
    """
    Find similar and duplicate code files across a project.

    Args:
        request: SimilarityRequest with files, threshold, and algorithm

    Returns:
        Project similarity report with duplicate pairs and statistics
    """
    valid_algorithms = {"auto", "exact", "jaccard", "minhash"}
    if request.algorithm not in valid_algorithms:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid algorithm '{request.algorithm}'. Valid: {valid_algorithms}",
        )
    files = [{"path": f.path, "content": f.content} for f in request.files]
    try:
        return _get_similarity_engine().analyze_project(
            files=files,
            threshold=request.threshold,
            algorithm=request.algorithm,
        )
    except Exception as exc:
        logger.error("Similarity analysis error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Similarity analysis failed: {exc}",
        )


@router.post(
    "/similarity/file",
    summary="Find duplicate blocks within a single file",
)
async def analyze_file_similarity(
    request: FileSimilarityRequest,
) -> dict[str, Any]:
    """
    Find duplicate code blocks within a single file.

    Args:
        request: FileSimilarityRequest with content and window_lines

    Returns:
        Intra-file duplicate report
    """
    try:
        return _get_similarity_engine().analyze_file(
            content=request.content,
            file_path=request.file_path,
            window_lines=request.window_lines,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File similarity analysis failed: {exc}",
        )


@router.post(
    "/similarity/compare",
    summary="Compare two files for similarity",
)
async def compare_two_files(
    request: CompareFilesRequest,
) -> dict[str, Any]:
    """
    Compute similarity score between exactly two files.

    Args:
        request: CompareFilesRequest with file_a and file_b

    Returns:
        Similarity result with Jaccard score and token analysis
    """
    try:
        return _get_similarity_engine().compare_two_files(
            content_a=request.file_a.content,
            path_a=request.file_a.path,
            content_b=request.file_b.content,
            path_b=request.file_b.path,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File comparison failed: {exc}",
        )

# =============================================================================
# Architecture Diagram Endpoints (Step 39)
# =============================================================================

class ArchitectureRequest(BaseModel):
    """Request for full architecture diagram generation."""
    files: list[FileEntry] = Field(..., min_length=1, max_length=1000)
    title: str = Field(default="Project Architecture", max_length=100)


class LayerDiagramRequest(BaseModel):
    """Request for layered architecture diagram only."""
    files: list[FileEntry] = Field(..., min_length=1, max_length=1000)


class ClassDiagramRequest(BaseModel):
    """Request for class hierarchy diagram."""
    files: list[FileEntry] = Field(..., min_length=1, max_length=500)


_arch_generator = None


def _get_arch_generator():
    """Lazy singleton for ArchitectureGenerator."""
    global _arch_generator
    if _arch_generator is None:
        from app.core.parsers.architecture import ArchitectureGenerator
        _arch_generator = ArchitectureGenerator()
    return _arch_generator


@router.post(
    "/architecture/all",
    summary="Generate all architecture diagrams for a project",
    description=(
        "Generates layered architecture, class hierarchy, component, "
        "and API flow diagrams in both Mermaid.js and React Flow formats."
    ),
)
async def generate_all_diagrams(
    request: ArchitectureRequest,
) -> dict[str, Any]:
    """
    Generate all architecture diagram types for a project.

    Args:
        request: ArchitectureRequest with files and title

    Returns:
        Dict with mermaid, react_flow, raw_data, and summary
    """
    files = [{"path": f.path, "content": f.content} for f in request.files]
    try:
        return _get_arch_generator().generate_all(
            files=files,
            title=request.title,
        )
    except Exception as exc:
        logger.error("Architecture generation error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Architecture generation failed: {exc}",
        )


@router.post(
    "/architecture/layers",
    summary="Generate layered architecture diagram",
)
async def generate_layer_diagram(
    request: LayerDiagramRequest,
) -> dict[str, Any]:
    """
    Generate only the layered architecture diagram.

    Args:
        request: LayerDiagramRequest with files

    Returns:
        Dict with mermaid syntax, React Flow JSON, and layer stats
    """
    files = [{"path": f.path, "content": f.content} for f in request.files]
    try:
        return _get_arch_generator().generate_layer_diagram(files)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Layer diagram failed: {exc}",
        )


@router.post(
    "/architecture/classes",
    summary="Generate class hierarchy diagram",
)
async def generate_class_diagram(
    request: ClassDiagramRequest,
) -> dict[str, Any]:
    """
    Generate class inheritance hierarchy from Python files.

    Args:
        request: ClassDiagramRequest with Python files

    Returns:
        Dict with mermaid classDiagram, React Flow, and class list
    """
    files = [{"path": f.path, "content": f.content} for f in request.files]
    try:
        return _get_arch_generator().generate_class_diagram(files)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Class diagram failed: {exc}",
        )


@router.get(
    "/architecture/layer-definitions",
    summary="Get architectural layer definitions",
)
async def get_layer_definitions() -> dict[str, Any]:
    """
    Return the layer classification rules and color scheme.

    Returns:
        Dict with all layer definitions
    """
    from app.core.parsers.architecture import LayerClassifier
    return {"layers": LayerClassifier.get_all_layers()}