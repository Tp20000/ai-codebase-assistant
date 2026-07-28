"""
Parser API Router — Parsing and chunking endpoints.

Parsing endpoints:
  POST /api/v1/projects/{project_id}/parse
  POST /api/v1/projects/{project_id}/parse/{file_id}
  GET  /api/v1/projects/{project_id}/parse/status
  GET  /api/v1/projects/{project_id}/functions
  GET  /api/v1/projects/{project_id}/classes

Chunking endpoints:
  POST /api/v1/projects/{project_id}/chunk
  POST /api/v1/projects/{project_id}/chunk/{file_id}
  GET  /api/v1/projects/{project_id}/chunks
"""

import logging
from typing import Any, Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.cache_service import get_redis
from app.services.project_service import ProjectService, ProjectNotFoundError
from app.repositories.file_repo import FileRepository
from app.core.parsers.code_parser import CodeParser
from app.core.parsers.complexity import analyze_file_complexity
from app.core.parsers.chunker import CodeChunker, ChunkingConfig
from app.middleware.auth_middleware import get_current_user
from app.models.user import User
from app.models.file import ProjectFile

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Parser"])

_parser = CodeParser()
_chunker = CodeChunker()


class ParseResultSummary(BaseModel):
    project_id: str
    total_files: int
    parsed_files: int
    skipped_files: int
    total_functions: int
    total_classes: int
    total_imports: int
    parse_method: str
    errors: list[str]


class ParseStatusResponse(BaseModel):
    project_id: str
    total_files: int
    parsed_files: int
    unparsed_files: int
    parse_progress_pct: float


class ChunkConfigRequest(BaseModel):
    max_chars: int = Field(default=2200, ge=300, le=12000)
    max_lines: int = Field(default=120, ge=10, le=500)
    overlap_lines: int = Field(default=4, ge=0, le=50)
    include_imports: bool = True
    include_module_code: bool = True
    min_meaningful_lines: int = Field(default=2, ge=1, le=20)


class ChunkInfo(BaseModel):
    chunk_id: str
    file_id: str
    file_path: str
    language: str
    chunk_type: str
    name: str
    line_start: int
    line_end: int
    char_count: int
    token_estimate: int
    content: str
    content_preview: str
    metadata: dict[str, Any]


class ChunkListResponse(BaseModel):
    project_id: str
    file_id: Optional[str]
    total_chunks: int
    items: list[ChunkInfo]


class ChunkSummaryResponse(BaseModel):
    project_id: str
    total_files: int
    chunked_files: int
    total_chunks: int
    avg_chunks_per_file: float


async def get_project_dep(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Verify project ownership and return project."""
    svc = ProjectService(db=db, redis=redis)
    try:
        return await svc.get_project(project_id, current_user)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found.")


def _to_chunk_config(request: Optional[ChunkConfigRequest]) -> ChunkingConfig:
    """Convert API chunk config schema to core config dataclass."""
    if request is None:
        return ChunkingConfig()
    return ChunkingConfig(
        max_chars=request.max_chars,
        max_lines=request.max_lines,
        overlap_lines=request.overlap_lines,
        include_imports=request.include_imports,
        include_module_code=request.include_module_code,
        min_meaningful_lines=request.min_meaningful_lines,
    )


async def _parse_single_file(
    project_file: ProjectFile,
    db: AsyncSession,
) -> dict[str, Any]:
    """Parse and persist metadata for a single file."""
    if not project_file.content or project_file.is_binary:
        return {"skipped": True, "reason": "binary or no content"}

    language = project_file.language or "unknown"

    try:
        parse_result = _parser.parse(
            source=project_file.content,
            language=language,
            file_path=project_file.file_path,
        )
        complexity = analyze_file_complexity(project_file.content, language)

        await db.execute(
            update(ProjectFile)
            .where(ProjectFile.id == project_file.id)
            .values(
                functions=parse_result["functions"],
                classes=parse_result["classes"],
                imports=parse_result["imports"],
                complexity_score=float(complexity["cyclomatic"]),
                ast_metadata={
                    "parse_method": parse_result.get("parse_method", "unknown"),
                    "cognitive_complexity": complexity["cognitive"],
                    "cyclomatic_complexity": complexity["cyclomatic"],
                    "rating": complexity["rating"],
                    "code_lines": complexity["code_lines"],
                    "comment_lines": complexity["comment_lines"],
                },
                is_parsed=True,
                parse_error=parse_result.get("error"),
            )
        )
        await db.commit()

        return {
            "skipped": False,
            "functions": len(parse_result["functions"]),
            "classes": len(parse_result["classes"]),
            "imports": len(parse_result["imports"]),
            "parse_method": parse_result.get("parse_method", "unknown"),
        }
    except Exception as exc:
        logger.error(f"Parse error for {project_file.file_path}: {exc}", exc_info=True)
        await db.execute(
            update(ProjectFile)
            .where(ProjectFile.id == project_file.id)
            .values(parse_error=str(exc), is_parsed=False)
        )
        await db.commit()
        return {"skipped": True, "reason": str(exc)}


async def _chunk_single_file(
    project_file: ProjectFile,
    db: AsyncSession,
    config: ChunkingConfig,
) -> list[dict[str, Any]]:
    """Chunk a single file, parsing first if needed."""
    if not project_file.content or project_file.is_binary:
        return []

    # Ensure parsed metadata exists
    if not project_file.is_parsed or project_file.functions is None:
        await _parse_single_file(project_file, db)
        file_repo = FileRepository(db)
        refreshed = await file_repo.get_by_id(project_file.id)
        if refreshed is not None:
            project_file = refreshed

    parse_result = {
        "functions": project_file.functions or [],
        "classes": project_file.classes or [],
        "imports": project_file.imports or [],
    }

    chunks = _chunker.chunk_file(
        source=project_file.content,
        language=project_file.language or "unknown",
        file_path=project_file.file_path,
        file_id=str(project_file.id),
        parse_result=parse_result,
        config=config,
    )

    metadata = dict(project_file.ast_metadata or {})
    metadata["chunking"] = {
        "chunk_count": len(chunks),
        "chunk_method": "semantic",
        "max_chars": config.max_chars,
        "max_lines": config.max_lines,
    }

    await db.execute(
        update(ProjectFile)
        .where(ProjectFile.id == project_file.id)
        .values(
            chunk_count=len(chunks),
            ast_metadata=metadata,
        )
    )
    await db.commit()

    return chunks


@router.post(
    "/projects/{project_id}/parse",
    response_model=ParseResultSummary,
    status_code=200,
    summary="Parse all project files",
)
async def parse_project(
    project_id: str,
    force: bool = Query(default=False, description="Re-parse already parsed files"),
    current_user: User = Depends(get_current_user),
    project=Depends(get_project_dep),
    db: AsyncSession = Depends(get_db),
) -> ParseResultSummary:
    """Parse all project files and persist function/class/import metadata."""
    file_repo = FileRepository(db)
    all_files = await file_repo.get_by_project(project_id, limit=1000)
    files_to_parse = [
        f for f in all_files
        if (not f.is_parsed or force) and not f.is_binary and f.content
    ]

    total_functions = 0
    total_classes = 0
    total_imports = 0
    parsed_count = 0
    skipped_count = 0
    errors: list[str] = []
    methods: list[str] = []

    for project_file in files_to_parse:
        result = await _parse_single_file(project_file, db)
        if result.get("skipped"):
            skipped_count += 1
            reason = result.get("reason")
            if reason and reason not in ("binary or no content",):
                errors.append(f"{project_file.file_path}: {reason}")
        else:
            parsed_count += 1
            total_functions += result.get("functions", 0)
            total_classes += result.get("classes", 0)
            total_imports += result.get("imports", 0)
            methods.append(result.get("parse_method", "unknown"))

    parse_method = max(set(methods), key=methods.count) if methods else "none"

    return ParseResultSummary(
        project_id=project_id,
        total_files=len(all_files),
        parsed_files=parsed_count,
        skipped_files=skipped_count,
        total_functions=total_functions,
        total_classes=total_classes,
        total_imports=total_imports,
        parse_method=parse_method,
        errors=errors[:10],
    )


@router.post(
    "/projects/{project_id}/parse/{file_id}",
    status_code=200,
    summary="Parse a single file",
)
async def parse_single_file(
    project_id: str,
    file_id: str,
    current_user: User = Depends(get_current_user),
    project=Depends(get_project_dep),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Parse one file and return extracted metadata."""
    file_repo = FileRepository(db)
    project_file = await file_repo.get_by_id(file_id)

    if not project_file or str(project_file.project_id) != project_id:
        raise HTTPException(status_code=404, detail="File not found.")
    if project_file.is_binary:
        raise HTTPException(status_code=400, detail="Cannot parse binary files.")
    if not project_file.content:
        raise HTTPException(status_code=400, detail="File content not stored.")

    result = await _parse_single_file(project_file, db)
    updated = await file_repo.get_by_id(file_id)

    return {
        "file_id": file_id,
        "file_path": project_file.file_path,
        "language": project_file.language,
        "parse_method": result.get("parse_method", "unknown"),
        "functions": updated.functions or [],
        "classes": updated.classes or [],
        "imports": updated.imports or [],
        "complexity": updated.complexity_score,
        "ast_metadata": updated.ast_metadata or {},
    }


@router.get(
    "/projects/{project_id}/parse/status",
    response_model=ParseStatusResponse,
    status_code=200,
    summary="Get parsing status",
)
async def get_parse_status(
    project_id: str,
    current_user: User = Depends(get_current_user),
    project=Depends(get_project_dep),
    db: AsyncSession = Depends(get_db),
) -> ParseStatusResponse:
    """Check parse progress for all non-binary files in the project."""
    file_repo = FileRepository(db)
    files = await file_repo.get_by_project(project_id, limit=1000)
    parseable = [f for f in files if not f.is_binary and f.content]
    total = len(parseable)
    parsed = len([f for f in parseable if f.is_parsed])
    unparsed = total - parsed
    pct = round((parsed / total * 100.0) if total else 0.0, 1)

    return ParseStatusResponse(
        project_id=project_id,
        total_files=total,
        parsed_files=parsed,
        unparsed_files=unparsed,
        parse_progress_pct=pct,
    )


@router.post(
    "/projects/{project_id}/chunk",
    response_model=ChunkSummaryResponse,
    status_code=200,
    summary="Chunk all project files",
)
async def chunk_project(
    project_id: str,
    request: Optional[ChunkConfigRequest] = None,
    current_user: User = Depends(get_current_user),
    project=Depends(get_project_dep),
    db: AsyncSession = Depends(get_db),
) -> ChunkSummaryResponse:
    """Chunk all parseable files in a project."""
    cfg = _to_chunk_config(request)
    file_repo = FileRepository(db)
    files = await file_repo.get_by_project(project_id, limit=1000)
    parseable = [f for f in files if not f.is_binary and f.content]

    total_chunks = 0
    chunked_files = 0

    for project_file in parseable:
        chunks = await _chunk_single_file(project_file, db, cfg)
        if chunks:
            chunked_files += 1
            total_chunks += len(chunks)

    avg = round((total_chunks / chunked_files) if chunked_files else 0.0, 2)
    return ChunkSummaryResponse(
        project_id=project_id,
        total_files=len(parseable),
        chunked_files=chunked_files,
        total_chunks=total_chunks,
        avg_chunks_per_file=avg,
    )


@router.post(
    "/projects/{project_id}/chunk/{file_id}",
    response_model=ChunkListResponse,
    status_code=200,
    summary="Chunk a single file",
)
async def chunk_single_file(
    project_id: str,
    file_id: str,
    request: Optional[ChunkConfigRequest] = None,
    current_user: User = Depends(get_current_user),
    project=Depends(get_project_dep),
    db: AsyncSession = Depends(get_db),
) -> ChunkListResponse:
    """Chunk one file and return the generated chunks."""
    cfg = _to_chunk_config(request)
    file_repo = FileRepository(db)
    project_file = await file_repo.get_by_id(file_id)

    if not project_file or str(project_file.project_id) != project_id:
        raise HTTPException(status_code=404, detail="File not found.")

    chunks = await _chunk_single_file(project_file, db, cfg)
    return ChunkListResponse(
        project_id=project_id,
        file_id=file_id,
        total_chunks=len(chunks),
        items=[ChunkInfo(**c) for c in chunks],
    )


@router.get(
    "/projects/{project_id}/chunks",
    response_model=ChunkListResponse,
    status_code=200,
    summary="List chunks for a project or file",
)
async def list_chunks(
    project_id: str,
    file_id: Optional[str] = Query(default=None),
    max_chars: int = Query(default=2200, ge=300, le=12000),
    max_lines: int = Query(default=120, ge=10, le=500),
    current_user: User = Depends(get_current_user),
    project=Depends(get_project_dep),
    db: AsyncSession = Depends(get_db),
) -> ChunkListResponse:
    """Compute and return chunks on demand."""
    cfg = ChunkingConfig(max_chars=max_chars, max_lines=max_lines)
    file_repo = FileRepository(db)

    if file_id:
        project_file = await file_repo.get_by_id(file_id)
        if not project_file or str(project_file.project_id) != project_id:
            raise HTTPException(status_code=404, detail="File not found.")
        chunks = await _chunk_single_file(project_file, db, cfg)
        return ChunkListResponse(
            project_id=project_id,
            file_id=file_id,
            total_chunks=len(chunks),
            items=[ChunkInfo(**c) for c in chunks],
        )

    files = await file_repo.get_by_project(project_id, limit=1000)
    items: list[ChunkInfo] = []
    for f in files:
        if f.is_binary or not f.content:
            continue
        chunks = await _chunk_single_file(f, db, cfg)
        items.extend([ChunkInfo(**c) for c in chunks])

    return ChunkListResponse(
        project_id=project_id,
        file_id=None,
        total_chunks=len(items),
        items=items,
    )


@router.get(
    "/projects/{project_id}/functions",
    status_code=200,
    summary="List all extracted functions",
)
async def list_functions(
    project_id: str,
    language: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    project=Depends(get_project_dep),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return all extracted functions from parsed files."""
    file_repo = FileRepository(db)
    files = await file_repo.get_by_project(project_id, limit=1000)

    items: list[dict[str, Any]] = []
    for f in files:
        if not f.is_parsed or not f.functions:
            continue
        if language and f.language != language:
            continue
        for func in f.functions:
            items.append({
                **func,
                "file_id": str(f.id),
                "file_path": f.file_path,
                "language": f.language,
            })

    return {"project_id": project_id, "total": len(items), "items": items}


@router.get(
    "/projects/{project_id}/classes",
    status_code=200,
    summary="List all extracted classes",
)
async def list_classes(
    project_id: str,
    language: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    project=Depends(get_project_dep),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return all extracted classes from parsed files."""
    file_repo = FileRepository(db)
    files = await file_repo.get_by_project(project_id, limit=1000)

    items: list[dict[str, Any]] = []
    for f in files:
        if not f.is_parsed or not f.classes:
            continue
        if language and f.language != language:
            continue
        for cls in f.classes:
            items.append({
                **cls,
                "file_id": str(f.id),
                "file_path": f.file_path,
                "language": f.language,
            })

    return {"project_id": project_id, "total": len(items), "items": items}