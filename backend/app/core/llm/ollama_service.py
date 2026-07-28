"""
Ollama LLM Service — Local inference via Ollama HTTP API.

Ollama runs as a Docker container (ai-ollama on port 11434).
Supports streaming responses for real-time chat UI updates.

Models used:
  - llama3.2     — General purpose chat (default)
  - codellama    — Code-specific tasks
  - mistral      — Alternative general model

All models are FREE and run locally. No API keys required.
"""

import json
import logging
from typing import AsyncGenerator, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

OLLAMA_BASE = getattr(settings, "OLLAMA_BASE_URL", "http://ollama:11434")
DEFAULT_MODEL = getattr(settings, "OLLAMA_DEFAULT_MODEL", "llama3.2")
CODE_MODEL = getattr(settings, "OLLAMA_CODE_MODEL", "codellama")
TIMEOUT = int(getattr(settings, "OLLAMA_TIMEOUT", 120))


class OllamaService:
    """
    Async Ollama client for LLM inference.

    Provides:
    - Model availability checking
    - Model listing and pulling
    - Synchronous text generation
    - Async streaming generation (for WebSocket)
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
    ) -> None:
        self.base_url = (base_url or OLLAMA_BASE).rstrip("/")
        self.default_model = default_model or DEFAULT_MODEL

    # ─────────────────────────────────────────────
    # Model Management
    # ─────────────────────────────────────────────

    async def list_models(self) -> list[dict]:
        """
        List all locally available Ollama models.

        Returns:
            List of model dicts with name, size, modified_at
        """
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.get(f"{self.base_url}/api/tags")
                resp.raise_for_status()
                data = resp.json()
                return data.get("models", [])
            except Exception as exc:
                logger.error(f"Ollama list_models failed: {exc}")
                return []

    async def is_model_available(self, model_name: str) -> bool:
        """
        Check if a specific model is downloaded and available.

        Args:
            model_name: Model name (e.g., 'llama3.2', 'codellama')

        Returns:
            True if model is available locally
        """
        models = await self.list_models()
        available_names = {m.get("name", "").split(":")[0] for m in models}
        check_name = model_name.split(":")[0]
        return check_name in available_names

    async def pull_model(self, model_name: str) -> AsyncGenerator[str, None]:
        """
        Pull (download) a model from Ollama registry.
        Streams progress updates as the model downloads.

        Args:
            model_name: Model to download (e.g., 'llama3.2')

        Yields:
            Progress strings as model downloads
        """
        logger.info(f"Pulling model: {model_name}")
        async with httpx.AsyncClient(timeout=600) as client:
            try:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/pull",
                    json={"name": model_name, "stream": True},
                ) as resp:
                    async for line in resp.aiter_lines():
                        if line.strip():
                            try:
                                data = json.loads(line)
                                status = data.get("status", "")
                                if "total" in data and "completed" in data:
                                    total = data["total"]
                                    completed = data["completed"]
                                    if total > 0:
                                        pct = round(completed / total * 100, 1)
                                        yield f"{status} {pct}%"
                                else:
                                    yield status
                            except json.JSONDecodeError:
                                yield line
            except Exception as exc:
                logger.error(f"Pull model failed: {exc}")
                yield f"Error: {exc}"

    # ─────────────────────────────────────────────
    # Text Generation
    # ─────────────────────────────────────────────

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> str:
        """
        Generate a complete response (non-streaming).

        Args:
            prompt: User prompt text
            model: Model to use (defaults to self.default_model)
            system: System prompt for context
            temperature: Sampling temperature (0=deterministic, 1=creative)
            max_tokens: Maximum tokens to generate

        Returns:
            Complete generated text string
        """
        model = model or self.default_model
        payload: dict = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "stop": ["<|endoftext|>", "Human:", "User:"],
            },
        }
        if system:
            payload["system"] = system

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                response_text = data.get("response", "")
                logger.info(
                    f"Generated {len(response_text)} chars "
                    f"(model={model}, "
                    f"eval_count={data.get('eval_count', 0)})"
                )
                return response_text
            except httpx.TimeoutException:
                raise TimeoutError(
                    f"Ollama generation timed out after {TIMEOUT}s. "
                    "Try a shorter prompt or increase OLLAMA_TIMEOUT."
                )
            except Exception as exc:
                logger.error(f"Ollama generate failed: {exc}")
                raise

    async def generate_stream(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        """
        Generate response as a stream of text chunks.
        Used for real-time WebSocket streaming in the chat UI.

        Args:
            prompt: User prompt text
            model: Model to use
            system: System prompt
            temperature: Sampling temperature
            max_tokens: Max tokens to generate

        Yields:
            Text chunks as they are generated
        """
        model = model or self.default_model
        payload: dict = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "stop": ["<|endoftext|>", "Human:", "User:"],
            },
        }
        if system:
            payload["system"] = system

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            try:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/generate",
                    json=payload,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                            chunk = data.get("response", "")
                            if chunk:
                                yield chunk
                            if data.get("done", False):
                                logger.debug(
                                    f"Stream complete: "
                                    f"eval_count={data.get('eval_count', 0)}"
                                )
                                return
                        except json.JSONDecodeError:
                            continue
            except httpx.TimeoutException:
                yield "\n[Generation timed out]"
            except Exception as exc:
                logger.error(f"Stream generate failed: {exc}")
                yield f"\n[Error: {exc}]"

    async def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> str:
        """
        Chat completion using Ollama /api/chat endpoint.
        Supports multi-turn conversation with message history.

        Args:
            messages: List of {"role": "user"|"assistant"|"system", "content": str}
            model: Model to use
            temperature: Sampling temperature
            max_tokens: Max tokens

        Returns:
            Assistant response text
        """
        model = model or self.default_model
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("message", {}).get("content", "")
            except Exception as exc:
                logger.error(f"Ollama chat failed: {exc}")
                raise

    async def chat_stream(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        """
        Streaming chat completion — yields text chunks.
        Used for real-time WebSocket chat in the frontend.
        """
        model = model or self.default_model
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            try:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json=payload,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            data = json.loads(line)
                            chunk = data.get("message", {}).get("content", "")
                            if chunk:
                                yield chunk
                            if data.get("done", False):
                                return
                        except json.JSONDecodeError:
                            continue
            except httpx.TimeoutException:
                yield "\n[Timeout]"
            except Exception as exc:
                yield f"\n[Error: {exc}]"

    # ─────────────────────────────────────────────
    # Health Check
    # ─────────────────────────────────────────────

    async def health_check(self) -> dict:
        """
        Check Ollama service availability.

        Returns:
            Dict with status, models loaded, and base_url
        """
        async with httpx.AsyncClient(timeout=5) as client:
            try:
                resp = await client.get(f"{self.base_url}/api/tags")
                resp.raise_for_status()
                data = resp.json()
                models = data.get("models", [])
                return {
                    "status": "healthy",
                    "base_url": self.base_url,
                    "models_loaded": len(models),
                    "models": [m.get("name") for m in models[:10]],
                    "default_model": self.default_model,
                }
            except Exception as exc:
                return {
                    "status": "unavailable",
                    "base_url": self.base_url,
                    "error": str(exc),
                    "note": "Ollama is optional — pull a model to enable AI chat",
                }