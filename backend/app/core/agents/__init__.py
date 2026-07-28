"""
Agents Package - AI Codebase Assistant v2.0

Registered agents (Steps 19-26):
    BaseAgent, AgentResult, AgentStatus, AgentConfig, AgentState
    AgentOrchestrator
    BugFinderAgent
    DocumentationGeneratorAgent
    TestWriterAgent
    CodeReviewerAgent
    SecurityScannerAgent
    RefactorSuggesterAgent
    PerformanceAnalyzerAgent
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.agents.base_agent import (
        BaseAgent, AgentResult, AgentStatus, AgentConfig, AgentState
    )
    from app.core.agents.orchestrator import AgentOrchestrator
    from app.core.agents.bug_finder import BugFinderAgent
    from app.core.agents.doc_generator import DocumentationGeneratorAgent
    from app.core.agents.test_writer import TestWriterAgent
    from app.core.agents.code_reviewer import CodeReviewerAgent
    from app.core.agents.security_scanner import SecurityScannerAgent
    from app.core.agents.refactor_agent import RefactorSuggesterAgent
    from app.core.agents.performance_agent import PerformanceAnalyzerAgent

AGENT_REGISTRY: dict[str, dict[str, str]] = {
    "bug_finder": {
        "module": "app.core.agents.bug_finder",
        "class": "BugFinderAgent",
    },
    "doc_generator": {
        "module": "app.core.agents.doc_generator",
        "class": "DocumentationGeneratorAgent",
    },
    "test_writer": {
        "module": "app.core.agents.test_writer",
        "class": "TestWriterAgent",
    },
    "code_reviewer": {
        "module": "app.core.agents.code_reviewer",
        "class": "CodeReviewerAgent",
    },
    "security_scanner": {
        "module": "app.core.agents.security_scanner",
        "class": "SecurityScannerAgent",
    },
    "refactor_suggester": {
        "module": "app.core.agents.refactor_agent",
        "class": "RefactorSuggesterAgent",
    },
    "performance_analyzer": {
        "module": "app.core.agents.performance_agent",
        "class": "PerformanceAnalyzerAgent",
    },
}


def __getattr__(name: str) -> object:
    """
    Lazy import handler for agent classes.

    Args:
        name: Attribute name being accessed

    Returns:
        The requested class

    Raises:
        AttributeError: If name is not a known agent class
    """
    import importlib

    _lazy_map: dict[str, tuple[str, str]] = {
        "BaseAgent":      ("app.core.agents.base_agent", "BaseAgent"),
        "AgentResult":    ("app.core.agents.base_agent", "AgentResult"),
        "AgentStatus":    ("app.core.agents.base_agent", "AgentStatus"),
        "AgentConfig":    ("app.core.agents.base_agent", "AgentConfig"),
        "AgentState":     ("app.core.agents.base_agent", "AgentState"),
        "AgentOrchestrator": (
            "app.core.agents.orchestrator", "AgentOrchestrator"
        ),
        "BugFinderAgent": (
            "app.core.agents.bug_finder", "BugFinderAgent"
        ),
        "DocumentationGeneratorAgent": (
            "app.core.agents.doc_generator", "DocumentationGeneratorAgent"
        ),
        "TestWriterAgent": (
            "app.core.agents.test_writer", "TestWriterAgent"
        ),
        "CodeReviewerAgent": (
            "app.core.agents.code_reviewer", "CodeReviewerAgent"
        ),
        "SecurityScannerAgent": (
            "app.core.agents.security_scanner", "SecurityScannerAgent"
        ),
        "RefactorSuggesterAgent": (
            "app.core.agents.refactor_agent", "RefactorSuggesterAgent"
        ),
        "PerformanceAnalyzerAgent": (
            "app.core.agents.performance_agent", "PerformanceAnalyzerAgent"
        ),
    }

    if name in _lazy_map:
        module_path, class_name = _lazy_map[name]
        module = importlib.import_module(module_path)
        return getattr(module, class_name)

    raise AttributeError(
        f"Module 'app.core.agents' has no attribute '{name}'"
    )


__all__ = [
    "AGENT_REGISTRY",
    "BaseAgent",
    "AgentResult",
    "AgentStatus",
    "AgentConfig",
    "AgentState",
    "AgentOrchestrator",
    "BugFinderAgent",
    "DocumentationGeneratorAgent",
    "TestWriterAgent",
    "CodeReviewerAgent",
    "SecurityScannerAgent",
    "RefactorSuggesterAgent",
    "PerformanceAnalyzerAgent",
]
