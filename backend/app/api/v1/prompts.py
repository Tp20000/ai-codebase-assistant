"""
Prompts API — Prompt type listing and query analysis endpoint.

Provides:
- GET  /prompts/types    — List all available prompt types
- POST /prompts/analyze  — Auto-detect prompt type from query text
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.core.llm.prompt_templates import (
    PromptTemplateEngine,
    PromptType,
    QueryAnalysis,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/prompts", tags=["prompts"])

# Shared engine instance
_engine = PromptTemplateEngine()


# ─────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    """Request body for query analysis."""
    query: str = Field(..., min_length=1, max_length=4000, description="User query to analyze")


class AnalyzeResponse(BaseModel):
    """Response from query analysis."""
    detected_type: str
    confidence: float
    keywords_matched: list[str]
    suggested_model: Optional[str] = None
    language_hint: Optional[str] = None


class PromptTypeItem(BaseModel):
    """A single prompt type with metadata."""
    value: str
    label: str
    description: str


# ─────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────

@router.get(
    "/types",
    response_model=list[PromptTypeItem],
    summary="List all available prompt types",
    description="Returns all supported prompt types with labels and descriptions. Used by the frontend to populate the prompt type selector.",
)
async def list_prompt_types() -> list[PromptTypeItem]:
    """Return all available prompt types for the UI selector."""
    types = _engine.get_all_prompt_types()
    return [PromptTypeItem(**t) for t in types]


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    summary="Auto-detect prompt type from query",
    description="Analyzes a user query using keyword matching and pattern detection to suggest the optimal prompt type and model.",
)
async def analyze_query(body: AnalyzeRequest) -> AnalyzeResponse:
    """
    Analyze a query to determine the best prompt type.

    The frontend can call this endpoint as the user types to
    auto-suggest the appropriate analysis mode.
    """
    analysis = _engine.analyze_query(body.query)
    return AnalyzeResponse(
        detected_type=analysis.detected_type.value,
        confidence=analysis.confidence,
        keywords_matched=analysis.keywords_matched,
        suggested_model=analysis.suggested_model,
        language_hint=analysis.language_hint,
    )
