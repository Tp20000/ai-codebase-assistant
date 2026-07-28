"""
Bug Finder Agent — AI-powered bug detection using LangGraph.

Analyzes a codebase for bugs, logic errors, null pointer risks,
off-by-one errors, resource leaks, and common anti-patterns.

LangGraph flow:
  validate_input -> retrieve_context -> analyze_bugs -> format_output

Output format:
  {
    "bugs": [
      {
        "id": "BUG-001",
        "title": "Null pointer dereference",
        "severity": "critical|high|medium|low",
        "file_path": "src/main.py",
        "line_start": 42,
        "line_end": 45,
        "description": "...",
        "code_snippet": "...",
        "suggested_fix": "...",
        "category": "null_safety|logic|resource_leak|..."
      }
    ],
    "summary": "Found N bugs: X critical, Y high...",
    "total_bugs": N,
    "severity_counts": {"critical": 0, "high": 1, ...}
  }
"""

from __future__ import annotations

import logging
import re
from typing import Any

from langgraph.graph import StateGraph, END

from app.core.agents.base_agent import (
    AgentState,
    AgentStatus,
    BaseAgent,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# System prompt for bug detection
# ─────────────────────────────────────────────────────────────────

BUG_FINDER_SYSTEM_PROMPT = """You are an expert software engineer specializing in code quality and bug detection.
Analyze the provided code for bugs, logic errors, and potential runtime issues.

Look for these categories of bugs:
- null_safety: Null/None pointer dereferences, missing null checks
- logic_error: Incorrect conditions, wrong operators, inverted logic
- resource_leak: Unclosed files, connections, or handles
- off_by_one: Array index errors, loop boundary issues
- race_condition: Thread safety issues, shared state problems
- exception_handling: Swallowed exceptions, missing error handling
- security: SQL injection, XSS, hardcoded secrets, path traversal
- performance: Unnecessary loops, N+1 queries, memory leaks
- type_error: Type mismatches, incorrect conversions
- dead_code: Unreachable code, unused variables

OUTPUT FORMAT (follow exactly — this will be parsed programmatically):

## BUGS_FOUND: [NUMBER]

### BUG-001
- **Title**: [Short descriptive title]
- **Severity**: critical|high|medium|low
- **Category**: [category from list above]
- **File**: [file_path]:[line_number]
- **Description**: [Clear explanation of what is wrong and why it is dangerous]
- **Code**: [the problematic code snippet]
- **Fix**: [Exact code fix with explanation]

### BUG-002
[continue for each bug found]

## SUMMARY
[Overall code quality assessment in 2-3 sentences]

If no bugs are found, output:
## BUGS_FOUND: 0
## SUMMARY
The analyzed code appears to be free of obvious bugs."""

BUG_FINDER_USER_TEMPLATE = """=== CODEBASE CONTEXT ===
{context}

=== ANALYSIS REQUEST ===
{query}

=== INSTRUCTIONS ===
Analyze the code above for bugs following the exact output format specified.
Focus on real, actionable bugs — not style preferences.
Reference specific file paths and line numbers from the context."""


# ─────────────────────────────────────────────────────────────────
# Bug Report Parser
# ─────────────────────────────────────────────────────────────────

def _parse_bug_report(llm_output: str) -> dict[str, Any]:
    """
    Parse the structured LLM output into a list of bug dictionaries.

    Extracts the ## BUGS_FOUND count and each ### BUG-NNN section
    from the formatted LLM response.

    Args:
        llm_output: Raw string from the LLM

    Returns:
        Structured dict with bugs list and summary stats
    """
    if not llm_output:
        return {
            "bugs": [],
            "summary": "Analysis produced no output.",
            "total_bugs": 0,
            "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
        }

    bugs: list[dict[str, Any]] = []

    # Extract total bug count
    count_match = re.search(r"BUGS_FOUND:\s*(\d+)", llm_output, re.IGNORECASE)
    reported_count = int(count_match.group(1)) if count_match else 0

    # Extract summary
    summary_match = re.search(
        r"##\s*SUMMARY\s*\n(.*?)(?=###|$)", llm_output,
        re.DOTALL | re.IGNORECASE
    )
    summary = summary_match.group(1).strip() if summary_match else "Analysis complete."

    # Extract individual bug sections
    bug_sections = re.split(r"###\s*BUG-\d+", llm_output, flags=re.IGNORECASE)

    for i, section in enumerate(bug_sections[1:], start=1):
        bug: dict[str, Any] = {"id": f"BUG-{i:03d}"}

        # Extract each field
        def extract_field(pattern: str) -> str:
            m = re.search(pattern, section, re.IGNORECASE | re.DOTALL)
            return m.group(1).strip() if m else ""

        bug["title"]       = extract_field(r"\*\*Title\*\*:\s*(.+?)(?=\n-|\n###|$)")
        bug["severity"]    = extract_field(r"\*\*Severity\*\*:\s*(critical|high|medium|low)")
        bug["category"]    = extract_field(r"\*\*Category\*\*:\s*(.+?)(?=\n-|\n###|$)")
        bug["description"] = extract_field(r"\*\*Description\*\*:\s*(.+?)(?=\n-\s*\*\*|\n###|$)")
        bug["suggested_fix"] = extract_field(r"\*\*Fix\*\*:\s*(.+?)(?=\n###|$)")

        # Extract file path and line number
        file_line = extract_field(r"\*\*File\*\*:\s*(.+?)(?=\n-|\n###|$)")
        if ":" in file_line:
            parts = file_line.rsplit(":", 1)
            bug["file_path"] = parts[0].strip()
            try:
                bug["line_start"] = int(re.sub(r"[^\d]", "", parts[1]))
            except (ValueError, IndexError):
                bug["line_start"] = 0
        else:
            bug["file_path"] = file_line
            bug["line_start"] = 0

        bug["line_end"] = bug["line_start"]

        # Extract code snippet from backticks
        code_match = re.search(r"`([^`]+)`", section)
        bug["code_snippet"] = code_match.group(1).strip() if code_match else ""

        # Default severity if not found
        if not bug["severity"]:
            bug["severity"] = "medium"

        # Only include bugs with at least a title or description
        if bug["title"] or bug["description"]:
            bugs.append(bug)

    # Count severities
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for bug in bugs:
        sev = bug.get("severity", "medium").lower()
        if sev in severity_counts:
            severity_counts[sev] += 1

    # Generate summary if LLM didn't provide one
    if not summary or summary == "Analysis complete.":
        total = len(bugs)
        if total == 0:
            summary = "No bugs detected in the analyzed code."
        else:
            parts = []
            for sev in ["critical", "high", "medium", "low"]:
                count = severity_counts[sev]
                if count > 0:
                    parts.append(f"{count} {sev}")
            summary = f"Found {total} bug(s): {', '.join(parts)}."

    return {
        "bugs": bugs,
        "summary": summary,
        "total_bugs": len(bugs),
        "reported_count": reported_count,
        "severity_counts": severity_counts,
    }


# ─────────────────────────────────────────────────────────────────
# Bug Finder Agent
# ─────────────────────────────────────────────────────────────────

class BugFinderAgent(BaseAgent):
    """
    LangGraph-based agent that analyzes codebases for bugs.

    Uses semantic retrieval to find relevant code, then passes it to
    an LLM with a structured bug-finding prompt. Parses the output
    into a list of BugReport objects with severity and fix suggestions.

    Inherits:
        BaseAgent: Provides _node_validate, _node_retrieve, _node_analyze,
                   _node_format, and the run() execution loop.
    """

    @property
    def agent_type(self) -> str:
        """Unique identifier for this agent."""
        return "bug_finder"

    @property
    def description(self) -> str:
        """Human-readable description for the UI agent panel."""
        return (
            "Analyzes your codebase for bugs, logic errors, null pointer risks, "
            "resource leaks, and common anti-patterns with severity ratings."
        )

    def _build_graph(self) -> Any:
        """
        Build the LangGraph StateGraph for bug detection.

        Node flow:
          validate_input -> retrieve_context -> analyze_bugs -> format_output -> END
        """
        # Capture self for closures (required in LangGraph 1.x)
        _self = self
        graph = StateGraph(AgentState)

        # Wrap instance methods in async lambdas for LangGraph 1.2.9 compatibility
        async def validate_node(state):
            return await _self._validate(state)

        async def retrieve_node(state):
            return await _self._retrieve(state)

        async def analyze_node(state):
            return await _self._analyze(state)

        async def format_node(state):
            return await _self._format(state)

        # Register nodes
        graph.add_node("validate_input",   validate_node)
        graph.add_node("retrieve_context", retrieve_node)
        graph.add_node("analyze_bugs",     analyze_node)
        graph.add_node("format_output",    format_node)

        # Define edges
        graph.set_entry_point("validate_input")
        graph.add_edge("validate_input",   "retrieve_context")
        graph.add_edge("retrieve_context", "analyze_bugs")
        graph.add_edge("analyze_bugs",     "format_output")
        graph.add_edge("format_output",    END)

        return graph.compile()

    def _format_result(self, state: AgentState) -> dict[str, Any]:
        """
        Convert the raw LLM output into structured bug report data.

        Called by _node_format (inherited from BaseAgent).
        Parses the structured markdown output into BugReport dicts.
        """
        llm_response = state.get("llm_response") or ""
        return _parse_bug_report(llm_response)

    # ── Graph Nodes ───────────────────────────────────────────────

    async def _validate(self, state: AgentState) -> AgentState:
        """
        Validate input and add bug-finder specific query.

        If the user did not provide a query, default to a comprehensive
        scan query that asks for all bug types.
        """
        validated = await self._node_validate(state)

        # Add default bug-finding query if none provided
        if not validated.get("query"):
            validated = {
                **validated,
                "query": (
                    "Find all bugs, logic errors, null pointer dereferences, "
                    "resource leaks, race conditions, and security vulnerabilities "
                    "in this codebase."
                ),
            }

        logger.debug("BugFinder validated: task=%s", state.get("task_id"))
        return validated

    async def _retrieve(self, state: AgentState) -> AgentState:
        """
        Retrieve code chunks most likely to contain bugs.

        Uses the standard retrieval node with bug-specific query augmentation.
        """
        # Augment query for better retrieval of buggy code
        original_query = state.get("query", "")
        augmented_query = (
            f"{original_query} error handling exception null check boundary condition"
        )
        augmented_state = {**state, "query": augmented_query}

        retrieved = await self._node_retrieve(augmented_state)

        # Restore original query for the LLM (we only augmented for retrieval)
        return {**retrieved, "query": original_query}

    async def _analyze(self, state: AgentState) -> AgentState:
        """
        Run LLM bug analysis on retrieved code context.

        Passes the retrieved code chunks to Ollama with the bug-finding
        system prompt and structured output format.
        """
        return await self._node_analyze(
            state=state,
            system_prompt=BUG_FINDER_SYSTEM_PROMPT,
            user_prompt_template=BUG_FINDER_USER_TEMPLATE,
        )

    async def _format(self, state: AgentState) -> AgentState:
        """
        Parse and structure the LLM bug report output.

        Calls the inherited _node_format which invokes _format_result().
        """
        return await self._node_format(state)
