"""
LLM API Router — Ollama model management and generation endpoints.

Endpoints:
  GET  /api/v1/llm/health          — Ollama service health
  GET  /api/v1/llm/models          — List available models
  POST /api/v1/llm/pull            — Pull/download a model
  POST /api/v1/llm/generate        — Generate text (non-streaming)
  POST /api/v1/llm/chat            — Chat completion
"""

import logging
from typing import Optional, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.llm.ollama_service import OllamaService
from app.middleware.auth_middleware import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/llm", tags=["LLM"])

# Module-level service instance (shared, stateless)
_ollama = OllamaService()


class GenerateRequest(BaseModel):
    """Request body for text generation."""
    prompt: str = Field(..., min_length=1, max_length=32000)
    model: Optional[str] = Field(None, description="Model override")
    system: Optional[str] = Field(None, description="System prompt")
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=8192)
    stream: bool = Field(default=False)


class ChatMessage(BaseModel):
    """Single chat message."""
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str = Field(..., min_length=1)


class ChatRequest(BaseModel):
    """Request body for chat completion."""
    messages: list[ChatMessage] = Field(..., min_length=1)
    model: Optional[str] = None
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=8192)
    stream: bool = Field(default=False)


class PullRequest(BaseModel):
    """Request body for model pull."""
    model: str = Field(..., description="Model name to pull (e.g., llama3.2)")


@router.get(
    "/health",
    status_code=200,
    summary="Ollama health check",
    description="Check if Ollama is running and which models are available.",
)
async def llm_health(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Check Ollama service health and list loaded models."""
    return await _ollama.health_check()


@router.get(
    "/models",
    status_code=200,
    summary="List available models",
    description="List all locally available Ollama models.",
)
async def list_models(
    current_user: User = Depends(get_current_user),
) -> dict:
    """List all locally downloaded Ollama models."""
    models = await _ollama.list_models()
    return {
        "models": models,
        "total": len(models),
        "default_model": _ollama.default_model,
    }


@router.post(
    "/pull",
    status_code=200,
    summary="Pull a model",
    description="Download a model from Ollama registry. Returns progress as streaming text.",
)
async def pull_model(
    request: PullRequest,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    Pull (download) an Ollama model.
    Streams download progress to the client.
    Large models (llama3.2 ~2GB) take several minutes.
    """
    logger.info(f"Pulling model: {request.model} (user={current_user.email})")

    async def progress_generator() -> AsyncGenerator[bytes, None]:
        async for progress in _ollama.pull_model(request.model):
            yield f"{progress}\n".encode()
        yield b"Pull complete\n"

    return StreamingResponse(
        progress_generator(),
        media_type="text/plain",
    )


@router.post(
    "/generate",
    status_code=200,
    summary="Generate text",
    description="Generate text using Ollama. Set stream=true for streaming response.",
)
async def generate(
    request: GenerateRequest,
    current_user: User = Depends(get_current_user),
):
    """Generate text using specified model."""
    if request.stream:
        async def stream_generator() -> AsyncGenerator[bytes, None]:
            async for chunk in _ollama.generate_stream(
                prompt=request.prompt,
                model=request.model,
                system=request.system,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            ):
                yield chunk.encode()

        return StreamingResponse(stream_generator(), media_type="text/plain")

    try:
        text = await _ollama.generate(
            prompt=request.prompt,
            model=request.model,
            system=request.system,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        return {"response": text, "model": request.model or _ollama.default_model}
    except TimeoutError as exc:
        raise HTTPException(status_code=408, detail=str(exc))
    except Exception as exc:
        logger.error(f"Generate error: {exc}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"LLM unavailable: {exc}")


@router.post(
    "/chat",
    status_code=200,
    summary="Chat completion",
    description="Multi-turn chat completion. Set stream=true for streaming.",
)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    """Chat completion with message history."""
    messages = [m.model_dump() for m in request.messages]

    if request.stream:
        async def stream_generator() -> AsyncGenerator[bytes, None]:
            async for chunk in _ollama.chat_stream(
                messages=messages,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            ):
                yield chunk.encode()

        return StreamingResponse(stream_generator(), media_type="text/plain")

    try:
        text = await _ollama.chat(
            messages=messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        return {"response": text, "model": request.model or _ollama.default_model}
    except Exception as exc:
        logger.error(f"Chat error: {exc}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"LLM unavailable: {exc}")