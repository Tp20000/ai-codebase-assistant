"""
Streaming response handler for LLM outputs.

Handles real-time token streaming from Ollama over HTTP,
formats chunks for WebSocket delivery, and provides both
synchronous and async iteration interfaces.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class StreamChunk:
    """A single token chunk from the LLM streaming response."""

    token: str
    is_final: bool = False
    model: str = ""
    elapsed_ms: float = 0.0
    total_tokens: int = 0


@dataclass
class StreamingResult:
    """Final result after collecting all streaming chunks."""

    full_text: str
    model: str
    total_tokens: int
    elapsed_ms: float
    chunks_received: int
    tokens_per_second: float = field(init=False)

    def __post_init__(self) -> None:
        """Calculate tokens per second after initialization."""
        elapsed_sec = self.elapsed_ms / 1000.0
        self.tokens_per_second = (
            self.total_tokens / elapsed_sec if elapsed_sec > 0 else 0.0
        )

    def to_dict(self) -> dict:
        """Serialize to dictionary for API responses."""
        return {
            "full_text": self.full_text,
            "model": self.model,
            "total_tokens": self.total_tokens,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "tokens_per_second": round(self.tokens_per_second, 2),
            "chunks_received": self.chunks_received,
        }


class OllamaStreamingClient:
    """
    Async streaming client for Ollama's chat completion API.

    Connects to Ollama's /api/chat endpoint and streams tokens
    as they are generated, enabling real-time UI updates.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        timeout_seconds: float = 120.0,
    ) -> None:
        """
        Initialize the streaming client.

        Args:
            base_url: Ollama server URL
            timeout_seconds: Max time to wait for complete response
        """
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        logger.info("OllamaStreamingClient initialized: %s", self._base_url)

    async def stream_chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Stream chat completion tokens from Ollama.

        Args:
            model: Ollama model name (e.g., "llama3.2", "codellama")
            messages: Chat messages in OpenAI format
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate

        Yields:
            StreamChunk objects as tokens are generated

        Raises:
            ConnectionError: If Ollama is not reachable
            RuntimeError: If the model is not available
        """
        url = f"{self._base_url}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "top_p": 0.9,
            },
        }

        start_time = time.perf_counter()
        chunks_received = 0

        logger.info(
            "Starting stream: model=%s, messages=%d", model, len(messages)
        )

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout)
            ) as client:
                async with client.stream(
                    "POST", url, json=payload
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        raise RuntimeError(
                            f"Ollama returned {response.status_code}: {error_text.decode()}"
                        )

                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue

                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            logger.warning("Invalid JSON from Ollama: %s", line[:100])
                            continue

                        message = data.get("message", {})
                        token = message.get("content", "")
                        is_done = data.get("done", False)

                        if token:
                            chunks_received += 1
                            elapsed = (time.perf_counter() - start_time) * 1000
                            yield StreamChunk(
                                token=token,
                                is_final=False,
                                model=model,
                                elapsed_ms=elapsed,
                                total_tokens=data.get("eval_count", 0),
                            )

                        if is_done:
                            elapsed = (time.perf_counter() - start_time) * 1000
                            yield StreamChunk(
                                token="",
                                is_final=True,
                                model=model,
                                elapsed_ms=elapsed,
                                total_tokens=data.get("eval_count", chunks_received),
                            )
                            logger.info(
                                "Stream complete: %d chunks, %.1fms",
                                chunks_received,
                                elapsed,
                            )
                            return

        except httpx.ConnectError as exc:
            logger.error("Cannot connect to Ollama at %s: %s", self._base_url, exc)
            raise ConnectionError(
                f"Ollama is not reachable at {self._base_url}. "
                "Ensure Ollama is running with: ollama serve"
            ) from exc
        except httpx.TimeoutException as exc:
            logger.error("Ollama stream timeout after %.1fs", self._timeout)
            raise TimeoutError(
                f"LLM response timed out after {self._timeout}s. "
                "Try a shorter query or smaller model."
            ) from exc

    async def collect_stream(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> StreamingResult:
        """
        Collect all streaming chunks into a complete response.

        Use this when you need the full text but still want streaming
        internally (e.g., for background processing or non-WebSocket paths).

        Args:
            model: Ollama model name
            messages: Chat messages
            temperature: Sampling temperature
            max_tokens: Max tokens to generate

        Returns:
            Complete StreamingResult with full text and metrics
        """
        tokens: list[str] = []
        final_chunk: Optional[StreamChunk] = None

        async for chunk in self.stream_chat(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            if chunk.is_final:
                final_chunk = chunk
            else:
                tokens.append(chunk.token)

        full_text = "".join(tokens)
        elapsed = final_chunk.elapsed_ms if final_chunk else 0.0
        total_tokens = final_chunk.total_tokens if final_chunk else len(tokens)

        return StreamingResult(
            full_text=full_text,
            model=model,
            total_tokens=total_tokens,
            elapsed_ms=elapsed,
            chunks_received=len(tokens),
        )


class WebSocketStreamBroadcaster:
    """
    Broadcasts LLM stream chunks to a WebSocket connection.

    Handles the protocol between the streaming LLM client and
    the WebSocket endpoint, including error propagation and
    completion signaling.
    """

    @staticmethod
    async def broadcast(
        websocket: object,
        stream: AsyncGenerator[StreamChunk, None],
        message_id: str,
    ) -> StreamingResult:
        """
        Broadcast all stream chunks to a WebSocket client.

        Message protocol:
            {type: "token", token: str, message_id: str}
            {type: "done", full_text: str, metrics: dict, message_id: str}
            {type: "error", message: str, message_id: str}

        Args:
            websocket: FastAPI WebSocket instance
            stream: Async generator of StreamChunk objects
            message_id: Unique ID to correlate streamed messages

        Returns:
            Complete StreamingResult after stream ends
        """
        tokens: list[str] = []
        final_chunk: Optional[StreamChunk] = None

        try:
            async for chunk in stream:
                if chunk.is_final:
                    final_chunk = chunk
                else:
                    tokens.append(chunk.token)
                    await websocket.send_json(  # type: ignore[attr-defined]
                        {
                            "type": "token",
                            "token": chunk.token,
                            "message_id": message_id,
                        }
                    )

            full_text = "".join(tokens)
            result = StreamingResult(
                full_text=full_text,
                model=final_chunk.model if final_chunk else "",
                total_tokens=final_chunk.total_tokens if final_chunk else len(tokens),
                elapsed_ms=final_chunk.elapsed_ms if final_chunk else 0.0,
                chunks_received=len(tokens),
            )

            await websocket.send_json(  # type: ignore[attr-defined]
                {
                    "type": "done",
                    "full_text": full_text,
                    "message_id": message_id,
                    "metrics": result.to_dict(),
                }
            )

            return result

        except Exception as exc:
            logger.error("WebSocket broadcast error: %s", exc)
            try:
                await websocket.send_json(  # type: ignore[attr-defined]
                    {
                        "type": "error",
                        "message": str(exc),
                        "message_id": message_id,
                    }
                )
            except Exception:
                pass  # WebSocket may already be closed
            raise
