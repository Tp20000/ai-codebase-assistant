"""
LLM Streaming Client — supports Ollama (local) and Groq API (production).
AI Codebase Assistant v2.0

Automatically falls back to Groq when Ollama is unavailable.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import AsyncGenerator, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class StreamChunk:
    """A single streamed token from the LLM."""
    text: str = ""
    done: bool = False
    model: str = ""
    error: Optional[str] = None


@dataclass
class StreamingResult:
    """Complete result after streaming finishes."""
    full_text: str = ""
    model: str = ""
    tokens_generated: int = 0
    elapsed_ms: float = 0.0
    llm_elapsed_ms: float = 0.0
    retrieval_elapsed_ms: float = 0.0
    error: Optional[str] = None
    chunks: list[StreamChunk] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.error is None and bool(self.full_text)


class OllamaStreamingClient:
    """
    Streaming LLM client with automatic Groq fallback.

    Priority:
    1. Ollama (local dev) — full streaming
    2. Groq API (production) — streaming via SSE
    3. Error message — if neither available
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2",
        timeout_seconds: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_model = model
        self.timeout = timeout_seconds
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        self.groq_model = os.getenv("GROQ_MODEL", "llama3-8b-8192")
        self.groq_url = "https://api.groq.com/openai/v1"
        self._ollama_ok: Optional[bool] = None

    async def _check_ollama(self) -> bool:
        """Check if Ollama is reachable (cached per instance)."""
        if self._ollama_ok is not None:
            return self._ollama_ok
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                self._ollama_ok = r.status_code == 200
        except Exception:
            self._ollama_ok = False
        logger.info(
            "Ollama available: %s | Groq available: %s",
            self._ollama_ok,
            bool(self.groq_api_key),
        )
        return self._ollama_ok

    # ── Public streaming API ──────────────────────────────────────────────────

    async def stream(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        system_prompt: Optional[str] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream tokens from the best available backend."""
        use_model = model or self.default_model

        if await self._check_ollama():
            async for chunk in self._stream_ollama(
                prompt, use_model, temperature, max_tokens, system_prompt
            ):
                yield chunk
        elif self.groq_api_key:
            async for chunk in self._stream_groq(
                prompt, temperature, max_tokens, system_prompt
            ):
                yield chunk
        else:
            yield StreamChunk(
                text=(
                    "AI service unavailable in production. "
                    "Please add GROQ_API_KEY to your Render environment variables. "
                    "Get a free key at: https://console.groq.com"
                ),
                done=True,
                error="no_llm_backend",
            )

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        system_prompt: Optional[str] = None,
    ) -> StreamingResult:
        """Generate a complete response (non-streaming)."""
        start = time.perf_counter()
        use_model = model or self.default_model
        full_text = ""
        error = None

        try:
            if await self._check_ollama():
                full_text = await self._generate_ollama(
                    prompt, use_model, temperature, max_tokens
                )
            elif self.groq_api_key:
                full_text = await self._generate_groq(
                    prompt, temperature, max_tokens, system_prompt
                )
            else:
                full_text = (
                    "AI service unavailable. "
                    "Add GROQ_API_KEY to Render environment to enable AI features."
                )
                error = "no_llm_backend"
        except Exception as exc:
            logger.error("LLM generation error: %s", exc)
            full_text = f"AI generation failed: {exc}"
            error = str(exc)

        elapsed = (time.perf_counter() - start) * 1000
        return StreamingResult(
            full_text=full_text,
            model=use_model if await self._check_ollama() else self.groq_model,
            tokens_generated=len(full_text.split()),
            elapsed_ms=elapsed,
            llm_elapsed_ms=elapsed,
            error=error,
        )

    # ── Ollama backend ────────────────────────────────────────────────────────

    async def _stream_ollama(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str],
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream from local Ollama."""
        payload: dict = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
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
                            token = data.get("response", "")
                            done = data.get("done", False)
                            if token:
                                yield StreamChunk(text=token, done=done, model=model)
                            if done:
                                yield StreamChunk(text="", done=True, model=model)
                                return
                        except json.JSONDecodeError:
                            continue
        except Exception as exc:
            logger.error("Ollama stream error: %s", exc)
            yield StreamChunk(text="", done=True, error=str(exc))

    async def _generate_ollama(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Non-streaming generate from Ollama."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                },
            )
            r.raise_for_status()
            return str(r.json().get("response", ""))

    # ── Groq backend ──────────────────────────────────────────────────────────

    async def _stream_groq(
        self,
        prompt: str,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str],
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream from Groq API using SSE."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.groq_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.groq_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.groq_url}/chat/completions",
                    json=payload,
                    headers=headers,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            yield StreamChunk(
                                text="", done=True, model=self.groq_model
                            )
                            return
                        try:
                            data = json.loads(data_str)
                            token = (
                                data["choices"][0]
                                .get("delta", {})
                                .get("content", "")
                            )
                            if token:
                                yield StreamChunk(
                                    text=token,
                                    done=False,
                                    model=self.groq_model,
                                )
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        except Exception as exc:
            logger.error("Groq stream error: %s", exc)
            yield StreamChunk(text="", done=True, error=str(exc))

    async def _generate_groq(
        self,
        prompt: str,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str],
    ) -> str:
        """Non-streaming generate from Groq API."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.groq_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.groq_model,
            "messages": messages,
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
            return str(r.json()["choices"][0]["message"]["content"])

    # ── Health check ──────────────────────────────────────────────────────────

    async def health(self) -> dict:
        """Return health status of all backends."""
        ollama_ok = await self._check_ollama()
        return {
            "ollama": {
                "available": ollama_ok,
                "url": self.base_url,
            },
            "groq": {
                "available": bool(self.groq_api_key),
                "model": self.groq_model,
            },
            "active_backend": (
                "ollama" if ollama_ok
                else "groq" if self.groq_api_key
                else "none"
            ),
        }