"""Base Agent Architecture using LangGraph StateGraph."""
from __future__ import annotations
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, TypedDict

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    CANCELLED = "cancelled"


class AgentState(TypedDict, total=False):
    task_id: str
    agent_type: str
    project_id: str
    user_id: str
    query: str
    file_filter: Optional[str]
    language_filter: Optional[str]
    model: str
    config: dict
    validated: bool
    validation_error: Optional[str]
    context_chunks: list
    context_text: str
    retrieval_time_ms: float
    sources: list
    analysis_result: Optional[str]
    llm_response: Optional[str]
    llm_time_ms: float
    tokens_used: int
    final_result: Optional[dict]
    formatted_report: Optional[str]
    status: str
    error: Optional[str]
    progress: float
    current_step: str
    started_at: str
    completed_at: Optional[str]
    total_elapsed_ms: float


@dataclass
class AgentResult:
    task_id: str
    agent_type: str
    status: AgentStatus
    result: Optional[dict]
    report: Optional[str]
    sources: list
    error: Optional[str]
    elapsed_ms: float
    tokens_used: int
    retrieval_time_ms: float
    llm_time_ms: float
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_success(self) -> bool:
        return self.status == AgentStatus.COMPLETED

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "agent_type": self.agent_type,
            "status": self.status.value,
            "result": self.result,
            "report": self.report,
            "sources": self.sources,
            "error": self.error,
            "timing": {
                "elapsed_ms": round(self.elapsed_ms, 2),
                "retrieval_ms": round(self.retrieval_time_ms, 2),
                "llm_ms": round(self.llm_time_ms, 2),
            },
            "tokens_used": self.tokens_used,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class AgentConfig:
    project_id: str
    user_id: str
    query: str = ""
    file_filter: Optional[str] = None
    language_filter: Optional[str] = None
    model: str = "tinyllama"
    top_k: int = 8
    max_tokens: int = 2048
    temperature: float = 0.1
    extra: dict = field(default_factory=dict)

    def to_initial_state(self, agent_type: str) -> AgentState:
        return AgentState(
            task_id=str(uuid.uuid4()),
            agent_type=agent_type,
            project_id=self.project_id,
            user_id=self.user_id,
            query=self.query,
            file_filter=self.file_filter,
            language_filter=self.language_filter,
            model=self.model,
            config={
                "top_k": self.top_k,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                **self.extra,
            },
            validated=False,
            validation_error=None,
            context_chunks=[],
            context_text="",
            retrieval_time_ms=0.0,
            sources=[],
            analysis_result=None,
            llm_response=None,
            llm_time_ms=0.0,
            tokens_used=0,
            final_result=None,
            formatted_report=None,
            status=AgentStatus.PENDING.value,
            error=None,
            progress=0.0,
            current_step="initializing",
            started_at=datetime.now(timezone.utc).isoformat(),
            completed_at=None,
            total_elapsed_ms=0.0,
        )


class BaseAgent(ABC):
    """Abstract base class for all AI agents."""

    def __init__(self, retriever=None, streaming_client=None) -> None:
        self._retriever = retriever
        self._streaming_client = streaming_client
        self._graph = None

    @property
    @abstractmethod
    def agent_type(self) -> str:
        ...

    @property
    def display_name(self) -> str:
        return self.agent_type.replace("_", " ").title()

    @property
    def description(self) -> str:
        return f"{self.display_name} agent"

    @abstractmethod
    def _build_graph(self):
        ...

    @abstractmethod
    def _format_result(self, state: AgentState) -> dict:
        ...

    def _get_graph(self):
        if self._graph is None:
            self._graph = self._build_graph()
        return self._graph

    async def run(self, config: AgentConfig) -> AgentResult:
        """Execute the agent with the given configuration."""
        start_time = time.perf_counter()
        initial_state = config.to_initial_state(self.agent_type)
        task_id = initial_state["task_id"]
        logger.info("Agent starting: type=%s task=%s", self.agent_type, task_id)
        try:
            graph = self._get_graph()
            final_state = await graph.ainvoke(initial_state)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            if final_state.get("error"):
                return AgentResult(
                    task_id=task_id, agent_type=self.agent_type,
                    status=AgentStatus.FAILED, result=None, report=None,
                    sources=final_state.get("sources", []),
                    error=final_state["error"], elapsed_ms=elapsed_ms,
                    tokens_used=final_state.get("tokens_used", 0),
                    retrieval_time_ms=final_state.get("retrieval_time_ms", 0.0),
                    llm_time_ms=final_state.get("llm_time_ms", 0.0),
                )
            return AgentResult(
                task_id=task_id, agent_type=self.agent_type,
                status=AgentStatus.COMPLETED,
                result=final_state.get("final_result"),
                report=final_state.get("formatted_report"),
                sources=final_state.get("sources", []), error=None,
                elapsed_ms=elapsed_ms,
                tokens_used=final_state.get("tokens_used", 0),
                retrieval_time_ms=final_state.get("retrieval_time_ms", 0.0),
                llm_time_ms=final_state.get("llm_time_ms", 0.0),
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.error("Agent failed: %s", exc, exc_info=True)
            return AgentResult(
                task_id=task_id, agent_type=self.agent_type,
                status=AgentStatus.FAILED, result=None, report=None,
                sources=[], error=str(exc), elapsed_ms=elapsed_ms,
                tokens_used=0, retrieval_time_ms=0.0, llm_time_ms=0.0,
            )

    async def _node_validate(self, state: AgentState) -> AgentState:
        """Validate required fields."""
        if not state.get("project_id"):
            return {**state, "error": "project_id required", "status": AgentStatus.FAILED.value}
        return {**state, "validated": True, "status": AgentStatus.RUNNING.value,
                "current_step": "validated", "progress": 0.1}

    async def _node_retrieve(self, state: AgentState) -> AgentState:
        """Semantic search for relevant code chunks."""
        if not self._retriever:
            return {**state, "context_chunks": [], "context_text": "No retriever.",
                    "sources": [], "retrieval_time_ms": 0.0,
                    "current_step": "retrieved", "progress": 0.3}
        try:
            agent_type = state.get("agent_type", "analysis")
            query = state.get("query") or f"Analyze codebase for {agent_type}"
            top_k = state.get("config", {}).get("top_k", 8)
            result = await self._retriever.retrieve(
                query=query, project_id=state["project_id"],
                top_k=top_k, strategy="mmr",
            )
            chunks = result.chunks
            context_text = "\n\n".join(c.to_context_string() for c in chunks) or "No code found."
            return {**state,
                    "context_chunks": [c.to_dict() for c in chunks],
                    "context_text": context_text,
                    "sources": [c.to_dict() for c in chunks],
                    "retrieval_time_ms": result.retrieval_time_ms,
                    "current_step": "retrieved", "progress": 0.3}
        except Exception as exc:
            return {**state, "context_chunks": [], "context_text": f"Error: {exc}",
                    "sources": [], "retrieval_time_ms": 0.0,
                    "current_step": "retrieved", "progress": 0.3}

    async def _node_analyze(self, state: AgentState,
                             system_prompt: str, user_prompt_template: str) -> AgentState:
        """LLM generation with code context."""
        context = state.get("context_text", "No context")
        query = state.get("query", "Analyze this codebase")
        user_prompt = user_prompt_template.format(
            context=context, query=query,
            project_id=state.get("project_id", ""),
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        if not self._streaming_client:
            return {**state, "llm_response": f"No LLM. Query: {query}",
                    "llm_time_ms": 0.0, "tokens_used": 0,
                    "current_step": "analyzed", "progress": 0.7}
        try:
            import time as _t
            s = _t.perf_counter()
            cfg = state.get("config", {})
            sr = await self._streaming_client.collect_stream(
                model=state.get("model", "tinyllama"),
                messages=messages,
                temperature=cfg.get("temperature", 0.1),
                max_tokens=cfg.get("max_tokens", 2048),
            )
            return {**state, "llm_response": sr.full_text, "analysis_result": sr.full_text,
                    "llm_time_ms": (_t.perf_counter() - s) * 1000, "tokens_used": sr.total_tokens,
                    "current_step": "analyzed", "progress": 0.7}
        except Exception as exc:
            return {**state, "llm_response": None, "llm_time_ms": 0.0, "tokens_used": 0,
                    "current_step": "analyzed", "progress": 0.7, "error": f"LLM failed: {exc}"}

    async def _node_format(self, state: AgentState) -> AgentState:
        """Structure the LLM output."""
        try:
            result = self._format_result(state)
            return {**state, "final_result": result,
                    "formatted_report": state.get("llm_response", ""),
                    "status": AgentStatus.COMPLETED.value,
                    "current_step": "completed", "progress": 1.0,
                    "completed_at": datetime.now(timezone.utc).isoformat()}
        except Exception:
            return {**state, "final_result": None,
                    "formatted_report": state.get("llm_response"),
                    "status": AgentStatus.COMPLETED.value,
                    "current_step": "completed", "progress": 1.0,
                    "completed_at": datetime.now(timezone.utc).isoformat()}
