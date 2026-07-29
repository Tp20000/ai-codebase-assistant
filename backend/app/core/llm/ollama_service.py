"""
LLM Service - Supports Ollama (local) and Groq API (production fallback)
AI Codebase Assistant v2.0
"""

from __future__ import annotations

import logging
import os
from typing import AsyncGenerator, Optional

import httpx

logger = logging.getLogger(__name__)


class LLMService:
    """
    LLM service with automatic fallback:
    1. Try Ollama (local dev)
    2. Fall back to Groq API (production)
    3. Return helpful error if neither available
    """

    def __init__(self) -> None:
        self.ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        self.groq_url = "https://api.groq.com/openai/v1"
        self.default_model = os.getenv("DEFAULT_MODEL", "llama3.2")
        self.groq_model = os.getenv("GROQ_MODEL", "llama3-8b-8192")
        self._ollama_available: Optional[bool] = None

    async def _check_ollama(self) -> bool:
        """Check if Ollama is reachable."""
        if self._ollama_available is not None:
            return self._ollama_available
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{self.ollama_url}/api/tags")
                self._ollama_available = r.status_code == 200
        except Exception:
            self._ollama_available = False
        return self._ollama_available

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """Generate a response using available LLM backend."""

        # Try Ollama first (local dev)
        if await self._check_ollama():
            return await self._ollama_generate(prompt, model, temperature, max_tokens)

        # Fallback to Groq (production)
        if self.groq_api_key:
            return await self._groq_generate(prompt, temperature, max_tokens)

        # Neither available
        return (
            "⚠️ AI service unavailable in production. "
            "To enable AI features, add GROQ_API_KEY to your Render environment variables. "
            "Get a free key at: https://console.groq.com"
        )

    async def _ollama_generate(
        self,
        prompt: str,
        model: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Generate using local Ollama."""
        use_model = model or self.default_model
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": use_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                },
            )
            r.raise_for_status()
            data = r.json()
            return str(data.get("response", ""))

    async def _groq_generate(
        self,
        prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Generate using Groq API (free tier)."""
        headers = {
            "Authorization": f"Bearer {self.groq_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.groq_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{self.groq_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            r.raise_for_status()
            data = r.json()
            return str(data["choices"][0]["message"]["content"])

    async def stream_generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from available LLM backend."""

        if await self._check_ollama():
            async for token in self._ollama_stream(prompt, model, temperature):
                yield token
            return

        if self.groq_api_key:
            async for token in self._groq_stream(prompt, temperature):
                yield token
            return

        yield (
            "⚠️ AI service unavailable. "
            "Add GROQ_API_KEY to Render environment variables. "
            "Get a free key at: https://console.groq.com"
        )

    async def _ollama_stream(
        self,
        prompt: str,
        model: Optional[str],
        temperature: float,
    ) -> AsyncGenerator[str, None]:
        """Stream from Ollama."""
        use_model = model or self.default_model
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.ollama_url}/api/generate",
                json={
                    "model": use_model,
                    "prompt": prompt,
                    "stream": True,
                    "options": {"temperature": temperature},
                },
            ) as response:
                async for line in response.aiter_lines():
                    if line.strip():
                        import json
                        try:
                            data = json.loads(line)
                            token = data.get("response", "")
                            if token:
                                yield token
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue

    async def _groq_stream(
        self,
        prompt: str,
        temperature: float,
    ) -> AsyncGenerator[str, None]:
        """Stream from Groq API."""
        import json
        headers = {
            "Authorization": f"Bearer {self.groq_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.groq_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{self.groq_url}/chat/completions",
                json=payload,
                headers=headers,
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            token = data["choices"][0]["delta"].get("content", "")
                            if token:
                                yield token
                        except (json.JSONDecodeError, KeyError):
                            continue

    async def health_check(self) -> dict:
        """Return LLM service health status."""
        ollama_ok = await self._check_ollama()
        groq_ok = bool(self.groq_api_key)

        return {
            "ollama": {
                "available": ollama_ok,
                "url": self.ollama_url,
            },
            "groq": {
                "available": groq_ok,
                "model": self.groq_model if groq_ok else None,
            },
            "active_backend": "ollama" if ollama_ok else ("groq" if groq_ok else "none"),
        }


# Singleton
llm_service = LLMService()

# ── Backward compatibility aliases ───────────────────────────────────────────
# These names are used by existing imports throughout the codebase
OllamaService = LLMService
ollama_service = llm_service
get_llm_service = lambda: llm_service