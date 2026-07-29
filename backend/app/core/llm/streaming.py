"""
Streaming response handler for LLM outputs.
Supports Ollama (local) and Groq API (production fallback).
AI Codebase Assistant v2.0
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class StreamChunk:
    """A single token chunk from the LLM streaming response."""
    token: str = ""
    is_final: bool = False
    model: str = ""
    elapsed_ms: float = 0.0
    total_tokens: int = 0

    # Alias so code using .text also works
    @property
    def text(self) -> str:
        return self.token

    @property
    def done(self) -> bool:
        return self.is_final


@dataclass
class StreamingResult:
    """Final result after collecting all streaming chunks."""
    full_text: str = ""
    model: str = ""
    total_tokens: int = 0
    elapsed_ms: float = 0.0
    chunks_received: int = 0
    llm_elapsed_ms: float = 0.0
    retrieval_elapsed_ms: float = 0.0
    error: Optional[str] = None
    tokens_per_second: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        elapsed_sec = self.elapsed_ms / 1000.0
        self.tokens_per_second = (
            self.total_tokens / elapsed_sec if elapsed_sec > 0 else 0.0
        )

    @property
    def success(self) -> bool:
        return self.error is None and bool(self.full_text)

    def to_dict(self) -> dict:
        return {
            "full_text": self.full_text,
            "model": self.model,
            "total_tokens": self.total_tokens,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "tokens_per_second": round(self.tokens_per_second, 2),
        }


class OllamaStreamingClient:
    """
    Streaming LLM client with automatic Groq fallback.

    Priority:
    1. Ollama (local dev) — full streaming
    2. Groq API (production) — streaming via SSE
    3. Helpful error message if neither available
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

    def _messages_to_prompt(self, messages: list[dict]) -> tuple[str, Optional[str]]:
        """Convert chat messages list to prompt + system prompt."""
        system_prompt = None
        user_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_prompt = content
            elif role == "user":
                user_parts.append(content)
            elif role == "assistant":
                user_parts.append(f"Assistant: {content}")
        return "\n\n".join(user_parts), system_prompt

    # ── collect_stream — primary method called by chat.py ─────────────────────

    async def collect_stream(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> StreamingResult:
        """
        Collect full streaming response into StreamingResult.
        Called by chat.py direct Ollama path.
        """
        start = time.perf_counter()
        prompt, system_prompt = self._messages_to_prompt(messages)
        full_text = ""
        error = None

        try:
            if await self._check_ollama():
                full_text = await self._generate_ollama(
                    prompt=prompt,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    system_prompt=system_prompt,
                )
            elif self.groq_api_key:
                # Sanitize messages - Groq requires non-empty content
                clean_messages = [
                    {"role": m.get("role", "user"), "content": str(m.get("content", "")).strip()}
                    for m in messages
                    if m.get("content", "").strip()
                ]
                if not clean_messages:
                    clean_messages = [{"role": "user", "content": prompt or "Hello"}]
                full_text = await self._generate_groq(
                    messages=clean_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            else:
                full_text = (
                    "AI service unavailable in production. "
                    "Please add GROQ_API_KEY to your Render environment variables. "
                    "Get a free key at: https://console.groq.com"
                )
                error = "no_llm_backend"
        except Exception as exc:
            logger.error("collect_stream error: %s", exc)
            full_text = f"AI generation failed: {exc}"
            error = str(exc)

        elapsed = (time.perf_counter() - start) * 1000
        active_model = model if await self._check_ollama() else self.groq_model

        return StreamingResult(
            full_text=full_text,
            model=active_model,
            total_tokens=len(full_text.split()),
            elapsed_ms=elapsed,
            llm_elapsed_ms=elapsed,
            chunks_received=1,
            error=error,
        )

    # ── generate — used by RAG pipeline ──────────────────────────────────────

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        system_prompt: Optional[str] = None,
    ) -> StreamingResult:
        """Non-streaming generate — used by RAG pipeline."""
        use_model = model or self.default_model
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return await self.collect_stream(
            model=use_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    # ── stream_tokens — yields chunks for WebSocket ───────────────────────────

    async def stream_tokens(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        system_prompt: Optional[str] = None,
        messages: Optional[list[dict]] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream tokens for WebSocket delivery."""
        use_model = model or self.default_model

        if messages is None:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

        if await self._check_ollama():
            async for chunk in self._stream_ollama(messages, use_model, temperature, max_tokens):
                yield chunk
        elif self.groq_api_key:
            async for chunk in self._stream_groq(messages, temperature, max_tokens):
                yield chunk
        else:
            yield StreamChunk(
                token=(
                    "AI service unavailable. "
                    "Add GROQ_API_KEY to Render environment variables."
                ),
                is_final=True,
                error="no_llm_backend",
            )

    # ── Ollama backend ────────────────────────────────────────────────────────

    async def _generate_ollama(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Non-streaming generate from local Ollama."""
        payload: dict = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(f"{self.base_url}/api/generate", json=payload)
            r.raise_for_status()
            return str(r.json().get("response", ""))

    async def _stream_ollama(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Streaming from local Ollama."""
        prompt, system_prompt = self._messages_to_prompt(messages)
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
                    "POST", f"{self.base_url}/api/generate", json=payload
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
                                yield StreamChunk(token=token, is_final=done, model=model)
                            if done:
                                return
                        except json.JSONDecodeError:
                            continue
        except Exception as exc:
            logger.error("Ollama stream error: %s", exc)
            yield StreamChunk(token="", is_final=True, error=str(exc))

    # ── Groq backend ──────────────────────────────────────────────────────────

    async def _generate_groq(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Non-streaming generate from Groq API."""
        headers = {
            "Authorization": f"Bearer {self.groq_api_key}",
            "Content-Type": "application/json",
        }
        # Groq limits: max 8192 tokens for llama3-8b-8192
        # Cap max_tokens to safe value
        safe_max_tokens = min(max_tokens, 4096)
        payload = {
            "model": self.groq_model,
            "messages": messages,
            "temperature": min(max(temperature, 0.0), 1.0),
            "max_tokens": safe_max_tokens,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{self.groq_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            if r.status_code == 400:
                error_body = r.text
                logger.error("Groq 400 error: %s | payload: %s", error_body, payload)
                raise ValueError(f"Groq API error: {error_body}")
            r.raise_for_status()
            data = r.json()
            return str(data["choices"][0]["message"]["content"])

    async def _stream_groq(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Streaming from Groq API via SSE."""
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
                                token="", is_final=True, model=self.groq_model
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
                                    token=token,
                                    is_final=False,
                                    model=self.groq_model,
                                )
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        except Exception as exc:
            logger.error("Groq stream error: %s", exc)
            yield StreamChunk(token="", is_final=True, error=str(exc))

    # ── Health check ──────────────────────────────────────────────────────────

    async def health(self) -> dict:
        """Return health status of all backends."""
        ollama_ok = await self._check_ollama()
        return {
            "ollama": {"available": ollama_ok, "url": self.base_url},
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


# ── StreamChunk needs error attribute for compat ──────────────────────────────
# Patch dataclass to add error field used in some places
StreamChunk.__dataclass_fields__["error"] = None  # type: ignore[attr-defined]

def _stream_chunk_init(self, token="", is_final=False, model="",
                        elapsed_ms=0.0, total_tokens=0, error=None):
    self.token = token
    self.is_final = is_final
    self.model = model
    self.elapsed_ms = elapsed_ms
    self.total_tokens = total_tokens
    self.error = error

StreamChunk.__init__ = _stream_chunk_init  # type: ignore[method-assign]