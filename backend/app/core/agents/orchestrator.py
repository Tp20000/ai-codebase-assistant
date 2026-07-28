"""
Multi-Agent Orchestrator - Step 27
AI Codebase Assistant v2.0

Coordinates all 7 specialized agents into unified analysis workflows:

    Available Agents:
        bug_finder           - Static + AI bug detection
        doc_generator        - Google/JSDoc documentation
        test_writer          - pytest/Jest test generation
        code_reviewer        - Style, design, complexity review
        security_scanner     - OWASP vulnerability scanning
        refactor_suggester   - SOLID/DRY/KISS refactoring
        performance_analyzer - Big-O, I/O, memory analysis

    Orchestration Modes:
        single   - Run one specific agent
        pipeline - Run multiple agents sequentially
        parallel - Run multiple agents concurrently (asyncio.gather)
        full     - Run ALL agents and aggregate results

    Master Report:
        Aggregates all agent outputs into a unified Markdown report
        with executive summary, risk matrix, and action plan.

Design:
    Does NOT extend BaseAgent (orchestrator has different contract).
    Uses AgentConfig and AgentResult directly.
    Exposes run_single(), run_pipeline(), run_parallel(), run_full().
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.agents.base_agent import (
    AgentConfig,
    AgentResult,
    AgentStatus,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Registry of all available agents
# =============================================================================

AGENT_REGISTRY: dict[str, dict[str, str]] = {
    "bug_finder": {
        "module": "app.core.agents.bug_finder",
        "class": "BugFinderAgent",
        "display": "Bug Finder",
        "description": "Detects bugs via static analysis and AI",
    },
    "doc_generator": {
        "module": "app.core.agents.doc_generator",
        "class": "DocumentationGeneratorAgent",
        "display": "Documentation Generator",
        "description": "Generates Google/JSDoc documentation",
    },
    "test_writer": {
        "module": "app.core.agents.test_writer",
        "class": "TestWriterAgent",
        "display": "Test Writer",
        "description": "Generates pytest/Jest test suites",
    },
    "code_reviewer": {
        "module": "app.core.agents.code_reviewer",
        "class": "CodeReviewerAgent",
        "display": "Code Reviewer",
        "description": "Reviews style, design, and complexity",
    },
    "security_scanner": {
        "module": "app.core.agents.security_scanner",
        "class": "SecurityScannerAgent",
        "display": "Security Scanner",
        "description": "OWASP-aligned vulnerability scanner",
    },
    "refactor_suggester": {
        "module": "app.core.agents.refactor_agent",
        "class": "RefactorSuggesterAgent",
        "display": "Refactor Suggester",
        "description": "SOLID/DRY/KISS refactoring suggestions",
    },
    "performance_analyzer": {
        "module": "app.core.agents.performance_agent",
        "class": "PerformanceAnalyzerAgent",
        "display": "Performance Analyzer",
        "description": "Big-O, I/O, and memory bottleneck detection",
    },
}


# =============================================================================
# Orchestration Result
# =============================================================================

@dataclass
class OrchestrationResult:
    """
    Aggregated result from running multiple agents.

    Attributes:
        orchestration_id: Unique ID for this orchestration run
        mode:             Execution mode (single/pipeline/parallel/full)
        agent_results:    Dict mapping agent_id to AgentResult
        master_report:    Aggregated Markdown report
        total_elapsed_ms: Total wall-clock time for all agents
        agents_succeeded: Count of agents that completed successfully
        agents_failed:    Count of agents that failed
        created_at:       Timestamp of orchestration completion
    """
    orchestration_id: str
    mode: str
    agent_results: dict[str, AgentResult]
    master_report: str
    total_elapsed_ms: float
    agents_succeeded: int
    agents_failed: int
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize the orchestration result to a JSON-safe dict.

        Returns:
            Dict representation of the orchestration result
        """
        return {
            "orchestration_id": self.orchestration_id,
            "mode": self.mode,
            "total_elapsed_ms": round(self.total_elapsed_ms, 2),
            "agents_succeeded": self.agents_succeeded,
            "agents_failed": self.agents_failed,
            "created_at": self.created_at.isoformat(),
            "agent_results": {
                agent_id: {
                    "task_id": r.task_id,
                    "status": r.status.value,
                    "error": r.error,
                    "elapsed_ms": round(r.elapsed_ms, 2),
                    "has_report": bool(r.report),
                    "has_result": bool(r.result),
                }
                for agent_id, r in self.agent_results.items()
            },
            "master_report_length": len(self.master_report),
        }


# =============================================================================
# Agent Loader
# =============================================================================

class AgentLoader:
    """
    Lazy-loads agent instances from the registry on demand.

    Caches loaded agents per (agent_id, retriever, streaming_client)
    combination to avoid repeated imports for the same configuration.
    """

    _cache: dict[str, Any] = {}

    @classmethod
    def load(
        cls,
        agent_id: str,
        retriever: Any = None,
        streaming_client: Any = None,
    ) -> Any:
        """
        Load and return an agent instance by agent_id.

        Args:
            agent_id:         Registry key e.g. "bug_finder"
            retriever:        Optional RAG retriever to inject
            streaming_client: Optional Ollama client to inject

        Returns:
            Instantiated agent object

        Raises:
            ValueError: If agent_id is not in AGENT_REGISTRY
            ImportError: If agent module cannot be imported
        """
        if agent_id not in AGENT_REGISTRY:
            raise ValueError(
                f"Unknown agent_id: '{agent_id}'. "
                f"Available: {list(AGENT_REGISTRY.keys())}"
            )

        # Simple cache key (retriever/client identity)
        cache_key = f"{agent_id}:{id(retriever)}:{id(streaming_client)}"
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        entry = AGENT_REGISTRY[agent_id]
        module = importlib.import_module(entry["module"])
        agent_class = getattr(module, entry["class"])
        instance = agent_class(
            retriever=retriever,
            streaming_client=streaming_client,
        )

        cls._cache[cache_key] = instance
        logger.info("[Orchestrator] Loaded agent: %s", agent_id)
        return instance

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the agent instance cache (useful for testing)."""
        cls._cache.clear()


# =============================================================================
# Multi-Agent Orchestrator
# =============================================================================

class AgentOrchestrator:
    """
    Coordinates multiple AI agents into unified analysis workflows.

    Supports four execution modes:
        single   - One agent, immediate result
        pipeline - Sequential: each agent runs after the previous completes
        parallel - Concurrent: all agents run via asyncio.gather()
        full     - All 7 agents in parallel, full master report

    Usage:
        orchestrator = AgentOrchestrator(retriever=..., streaming_client=...)

        # Run single agent
        result = await orchestrator.run_single("bug_finder", config)

        # Run multiple agents in parallel
        orch_result = await orchestrator.run_parallel(
            ["security_scanner", "code_reviewer"], config
        )

        # Full suite
        orch_result = await orchestrator.run_full(config)
    """

    def __init__(
        self,
        retriever: Any = None,
        streaming_client: Any = None,
    ) -> None:
        """
        Initialise the orchestrator with shared infrastructure.

        Args:
            retriever:        RAG retriever shared across all agents
            streaming_client: Ollama client shared across all agents
        """
        self._retriever = retriever
        self._streaming_client = streaming_client

    # ── Public API ──────────────────────────────────────────────────

    async def run_single(
        self,
        agent_id: str,
        config: AgentConfig,
    ) -> AgentResult:
        """
        Run a single agent and return its AgentResult directly.

        Args:
            agent_id: Registry key e.g. "bug_finder"
            config:   AgentConfig with project_id, extra, etc.

        Returns:
            AgentResult from the agent
        """
        logger.info("[Orchestrator] run_single: agent=%s", agent_id)
        agent = AgentLoader.load(
            agent_id,
            retriever=self._retriever,
            streaming_client=self._streaming_client,
        )
        return await agent.run(config)

    async def run_pipeline(
        self,
        agent_ids: list[str],
        config: AgentConfig,
    ) -> OrchestrationResult:
        """
        Run agents sequentially — each waits for the previous to finish.

        Useful when later agents depend on earlier results (future use).
        Failures are recorded but do not stop the pipeline.

        Args:
            agent_ids: Ordered list of agent registry keys
            config:    Shared AgentConfig for all agents

        Returns:
            OrchestrationResult with all agent results
        """
        logger.info(
            "[Orchestrator] run_pipeline: agents=%s", agent_ids
        )
        orch_id = str(uuid.uuid4())
        start = time.perf_counter()
        results: dict[str, AgentResult] = {}

        for agent_id in agent_ids:
            try:
                result = await self.run_single(agent_id, config)
                results[agent_id] = result
                logger.info(
                    "[Orchestrator] pipeline step done: %s status=%s",
                    agent_id, result.status,
                )
            except Exception as exc:
                logger.error(
                    "[Orchestrator] pipeline step failed: %s err=%s",
                    agent_id, exc,
                )
                results[agent_id] = self._make_error_result(
                    agent_id, str(exc)
                )

        elapsed = (time.perf_counter() - start) * 1000
        return self._build_orch_result(orch_id, "pipeline", results, elapsed)

    async def run_parallel(
        self,
        agent_ids: list[str],
        config: AgentConfig,
    ) -> OrchestrationResult:
        """
        Run agents concurrently using asyncio.gather().

        All agents start at the same time and results are collected
        when all complete. Individual failures are captured without
        stopping other agents.

        Args:
            agent_ids: List of agent registry keys to run concurrently
            config:    Shared AgentConfig for all agents

        Returns:
            OrchestrationResult with all agent results
        """
        logger.info(
            "[Orchestrator] run_parallel: agents=%s", agent_ids
        )
        orch_id = str(uuid.uuid4())
        start = time.perf_counter()

        # Create coroutines for all agents
        async def safe_run(agent_id: str) -> tuple[str, AgentResult]:
            """Run agent safely, capturing exceptions as failed results."""
            try:
                result = await self.run_single(agent_id, config)
                return agent_id, result
            except Exception as exc:
                logger.error(
                    "[Orchestrator] parallel agent failed: %s err=%s",
                    agent_id, exc,
                )
                return agent_id, self._make_error_result(agent_id, str(exc))

        # Run all agents concurrently
        pairs = await asyncio.gather(
            *[safe_run(aid) for aid in agent_ids]
        )
        results: dict[str, AgentResult] = dict(pairs)

        elapsed = (time.perf_counter() - start) * 1000
        return self._build_orch_result(orch_id, "parallel", results, elapsed)

    async def run_full(
        self, config: AgentConfig
    ) -> OrchestrationResult:
        """
        Run ALL 7 registered agents in parallel.

        Produces the most comprehensive analysis possible by combining
        results from every specialized agent into one master report.

        Args:
            config: AgentConfig with code_content, language, file_path
                    in extra dict

        Returns:
            OrchestrationResult with all 7 agent results + master report
        """
        logger.info("[Orchestrator] run_full: all agents")
        all_agent_ids = list(AGENT_REGISTRY.keys())
        return await self.run_parallel(all_agent_ids, config)

    def list_agents(self) -> list[dict[str, str]]:
        """
        Return metadata for all registered agents.

        Returns:
            List of dicts with agent_id, display, description
        """
        return [
            {
                "agent_id": agent_id,
                "display": info["display"],
                "description": info["description"],
            }
            for agent_id, info in AGENT_REGISTRY.items()
        ]

    # ── Private helpers ─────────────────────────────────────────────

    def _make_error_result(
        self, agent_id: str, error_msg: str
    ) -> AgentResult:
        """
        Create a failed AgentResult for an agent that threw an exception.

        Args:
            agent_id:  Registry key of the failed agent
            error_msg: Exception message string

        Returns:
            AgentResult with FAILED status and error message
        """
        return AgentResult(
            task_id=str(uuid.uuid4()),
            agent_type=agent_id,
            status=AgentStatus.FAILED,
            result=None,
            report=None,
            sources=[],
            error=error_msg,
            elapsed_ms=0.0,
            tokens_used=0,
            retrieval_time_ms=0.0,
            llm_time_ms=0.0,
        )

    def _build_orch_result(
        self,
        orch_id: str,
        mode: str,
        results: dict[str, AgentResult],
        elapsed_ms: float,
    ) -> OrchestrationResult:
        """
        Build an OrchestrationResult from a dict of agent results.

        Assembles the master report by combining all individual reports.

        Args:
            orch_id:    Unique orchestration run ID
            mode:       Execution mode string
            results:    Dict of agent_id -> AgentResult
            elapsed_ms: Total wall-clock time

        Returns:
            Complete OrchestrationResult
        """
        succeeded = sum(
            1 for r in results.values()
            if r.status == AgentStatus.COMPLETED
        )
        failed = sum(
            1 for r in results.values()
            if r.status == AgentStatus.FAILED
        )

        master_report = self._build_master_report(
            orch_id, mode, results, elapsed_ms
        )

        return OrchestrationResult(
            orchestration_id=orch_id,
            mode=mode,
            agent_results=results,
            master_report=master_report,
            total_elapsed_ms=elapsed_ms,
            agents_succeeded=succeeded,
            agents_failed=failed,
        )

    def _build_master_report(
        self,
        orch_id: str,
        mode: str,
        results: dict[str, AgentResult],
        elapsed_ms: float,
    ) -> str:
        """
        Assemble a comprehensive Markdown master report from all results.

        Sections:
            1. Executive Summary (counts, timing, success rate)
            2. Agent Status Table
            3. Critical Findings (highest priority from each agent)
            4. Individual Agent Reports (full content)
            5. Recommended Action Plan

        Args:
            orch_id:    Orchestration run ID
            mode:       Execution mode
            results:    Dict of agent results
            elapsed_ms: Total elapsed time

        Returns:
            Complete Markdown report string
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        succeeded = sum(
            1 for r in results.values()
            if r.status == AgentStatus.COMPLETED
        )
        failed = len(results) - succeeded

        lines: list[str] = [
            "# Master Code Analysis Report",
            "",
            "**Orchestration ID:** `" + orch_id + "`",
            "**Mode:** " + mode,
            "**Generated:** " + now,
            "**Total Time:** " + str(round(elapsed_ms / 1000, 2)) + "s",
            "**Agents Run:** " + str(len(results)),
            "**Succeeded:** " + str(succeeded)
            + " | **Failed:** " + str(failed),
            "",
            "---",
            "",
            "## Executive Summary",
            "",
        ]

        # Collect key metrics from each agent result
        metrics: list[str] = []
        for agent_id, result in results.items():
            display = AGENT_REGISTRY.get(agent_id, {}).get("display", agent_id)
            if result.status == AgentStatus.FAILED:
                metrics.append(
                    "- **" + display + ":** FAILED — " + (result.error or "unknown error")
                )
            elif result.result:
                r = result.result
                # Extract key metric per agent type
                if agent_id == "security_scanner":
                    vulns = r.get("total_vulnerabilities", 0)
                    risk = r.get("risk_level", "UNKNOWN")
                    metrics.append(
                        "- **" + display + ":** "
                        + str(vulns) + " vulnerabilities | Risk: " + risk
                    )
                elif agent_id == "code_reviewer":
                    score = r.get("quality_score", 0)
                    grade = r.get("grade", "?")
                    findings = r.get("total_findings", 0)
                    metrics.append(
                        "- **" + display + ":** Quality " + str(score)
                        + "/100 (Grade " + grade + ") | "
                        + str(findings) + " findings"
                    )
                elif agent_id == "performance_analyzer":
                    total = r.get("total_findings", 0)
                    pg = r.get("perf_grade", "UNKNOWN")
                    metrics.append(
                        "- **" + display + ":** "
                        + str(total) + " issues | " + pg
                    )
                elif agent_id == "bug_finder":
                    bugs = r.get("total_bugs", 0)
                    metrics.append(
                        "- **" + display + ":** " + str(bugs) + " bugs found"
                    )
                elif agent_id == "test_writer":
                    targets = r.get("targets_found", 0)
                    fw = r.get("framework", "unknown")
                    metrics.append(
                        "- **" + display + ":** "
                        + str(targets) + " test targets | Framework: " + fw
                    )
                elif agent_id == "doc_generator":
                    total = r.get("total_count", r.get("elements_documented", 0))
                    metrics.append(
                        "- **" + display + ":** "
                        + str(total) + " elements documented"
                    )
                elif agent_id == "refactor_suggester":
                    total = r.get("total_suggestions", 0)
                    metrics.append(
                        "- **" + display + ":** "
                        + str(total) + " refactor suggestions"
                    )
                else:
                    metrics.append(
                        "- **" + display + ":** Completed ("
                        + str(round(result.elapsed_ms, 0)) + "ms)"
                    )
            else:
                metrics.append(
                    "- **" + display + ":** Completed (no structured result)"
                )

        lines.extend(metrics)
        lines += ["", "---", ""]

        # Agent status table
        lines += [
            "## Agent Status",
            "",
            "| Agent | Status | Time (ms) | Key Metric |",
            "|-------|--------|-----------|------------|",
        ]
        for agent_id, result in results.items():
            display = AGENT_REGISTRY.get(agent_id, {}).get("display", agent_id)
            status = "COMPLETED" if result.status == AgentStatus.COMPLETED else "FAILED"
            elapsed = str(round(result.elapsed_ms, 0))
            metric = ""
            if result.result:
                r = result.result
                if "total_vulnerabilities" in r:
                    metric = str(r["total_vulnerabilities"]) + " vulns"
                elif "quality_score" in r:
                    metric = "Score " + str(r["quality_score"]) + "/100"
                elif "total_findings" in r:
                    metric = str(r["total_findings"]) + " findings"
                elif "total_suggestions" in r:
                    metric = str(r["total_suggestions"]) + " suggestions"
                elif "targets_found" in r:
                    metric = str(r["targets_found"]) + " targets"
                elif "elements_documented" in r:
                    metric = str(r["elements_documented"]) + " elements"
            elif result.error:
                metric = result.error[:40]

            lines.append(
                "| " + display + " | " + status
                + " | " + elapsed + " | " + metric + " |"
            )

        lines += ["", "---", ""]

        # Critical findings across all agents
        critical_sections: list[str] = []
        for agent_id, result in results.items():
            if result.status != AgentStatus.COMPLETED or not result.result:
                continue
            r = result.result
            display = AGENT_REGISTRY.get(agent_id, {}).get("display", agent_id)

            # Security critical findings
            if agent_id == "security_scanner":
                crit = r.get("critical_findings") or []
                if crit:
                    critical_sections.append(
                        "**" + display + " — Critical Vulnerabilities:**"
                    )
                    for f in crit[:3]:
                        critical_sections.append(
                            "- [" + str(f.get("vuln_id", "")) + "] "
                            + str(f.get("title", "")) + " (line "
                            + str(f.get("line", 0)) + ")"
                        )

            # Performance critical
            elif agent_id == "performance_analyzer":
                crit = r.get("critical_findings") or []
                if crit:
                    critical_sections.append(
                        "**" + display + " — Critical Bottlenecks:**"
                    )
                    for f in crit[:3]:
                        critical_sections.append(
                            "- [" + str(f.get("perf_id", "")) + "] "
                            + str(f.get("title", "")) + " "
                            + str(f.get("complexity", ""))
                        )

            # Code review top issues
            elif agent_id == "code_reviewer":
                top = r.get("top_issues") or []
                if top:
                    critical_sections.append(
                        "**" + display + " — Top Issues:**"
                    )
                    for f in top[:3]:
                        critical_sections.append(
                            "- [" + str(f.get("severity", "")) + "] "
                            + str(f.get("title", ""))
                            + " (line " + str(f.get("line", 0)) + ")"
                        )

        if critical_sections:
            lines += ["## Critical Findings Across All Agents", ""]
            lines.extend(critical_sections)
            lines += ["", "---", ""]

        # Individual agent reports
        lines += ["## Individual Agent Reports", ""]

        for agent_id, result in results.items():
            display = AGENT_REGISTRY.get(agent_id, {}).get("display", agent_id)
            lines += [
                "### " + display,
                "",
            ]

            if result.status == AgentStatus.FAILED:
                lines.append("**Status:** FAILED")
                lines.append("")
                lines.append("**Error:** " + (result.error or "Unknown error"))
                lines.append("")
            elif result.report:
                # Include first 2000 chars of each agent report
                report_preview = result.report[:2000]
                if len(result.report) > 2000:
                    report_preview += (
                        "\n\n*[Report truncated — "
                        + str(len(result.report))
                        + " chars total]*"
                    )
                lines.append(report_preview)
                lines.append("")
            else:
                lines.append("*No detailed report generated.*")
                lines.append("")

            lines += ["---", ""]

        # Action plan
        lines += [
            "## Recommended Action Plan",
            "",
            "Priority order based on combined agent analysis:",
            "",
        ]

        action_items: list[tuple[int, str]] = []

        for agent_id, result in results.items():
            if result.status != AgentStatus.COMPLETED or not result.result:
                continue
            r = result.result

            # Security always highest priority
            if agent_id == "security_scanner":
                crit_count = (r.get("severity_counts") or {}).get("CRITICAL", 0)
                high_count = (r.get("severity_counts") or {}).get("HIGH", 0)
                if crit_count > 0:
                    action_items.append((
                        1,
                        "**[URGENT]** Fix " + str(crit_count)
                        + " CRITICAL security vulnerabilities immediately",
                    ))
                if high_count > 0:
                    action_items.append((
                        2,
                        "Fix " + str(high_count)
                        + " HIGH security vulnerabilities before next release",
                    ))

            # Performance critical issues
            elif agent_id == "performance_analyzer":
                crit = r.get("critical_findings") or []
                if crit:
                    action_items.append((
                        3,
                        "Resolve " + str(len(crit))
                        + " critical performance bottleneck(s) "
                        "(potential production incidents)",
                    ))

            # Code quality
            elif agent_id == "code_reviewer":
                score = r.get("quality_score") or 100
                if score < 70:
                    action_items.append((
                        4,
                        "Improve code quality score from "
                        + str(score) + "/100 (target: >= 80)",
                    ))

            # Refactoring
            elif agent_id == "refactor_suggester":
                high_sug = (r.get("by_severity") or {}).get("HIGH", 0)
                if high_sug > 0:
                    action_items.append((
                        5,
                        "Apply " + str(high_sug)
                        + " HIGH-priority refactoring suggestions",
                    ))

            # Tests
            elif agent_id == "test_writer":
                targets = r.get("targets_found") or 0
                if targets > 0:
                    action_items.append((
                        6,
                        "Add generated tests for "
                        + str(targets) + " untested functions/classes",
                    ))

            # Documentation
            elif agent_id == "doc_generator":
                needs = r.get("elements_needing_docs") or 0
                if needs > 0:
                    action_items.append((
                        7,
                        "Add documentation for "
                        + str(needs) + " undocumented elements",
                    ))

        action_items.sort(key=lambda x: x[0])
        if action_items:
            for priority, item in action_items:
                lines.append(str(priority) + ". " + item)
        else:
            lines.append("No urgent action items. Code is in good shape!")

        lines += [
            "",
            "---",
            "",
            "*Generated by AI Codebase Assistant — Multi-Agent Orchestrator*",
            "*Run individual agents for detailed analysis of specific concerns.*",
        ]

        return "\n".join(lines)
