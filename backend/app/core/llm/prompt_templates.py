"""
Context-Aware Prompting System with Dynamic Template Selection.

Manages all LLM prompt templates for the AI Codebase Assistant.
Features:
- Task-specific system prompts (code QA, bug finding, docs, tests, etc.)
- Conversation history injection for multi-turn context
- Dynamic prompt selection based on query analysis
- Token budget management for context windows
- Prompt versioning for A/B testing
- Language-aware prompt adaptation

Architecture pattern: Strategy + Factory
Each PromptType maps to a complete prompt strategy (system + user template).
The PromptTemplateEngine selects and assembles the right strategy per request.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from string import Template
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# Prompt Type Enumeration
# ─────────────────────────────────────────────────────────────────

class PromptType(str, Enum):
    """All available prompt types for AI interactions."""

    CODE_QA = "code_qa"
    BUG_FINDER = "bug_finder"
    DOC_GENERATOR = "doc_generator"
    TEST_WRITER = "test_writer"
    CODE_REVIEWER = "code_reviewer"
    SECURITY_SCANNER = "security_scanner"
    REFACTOR = "refactor"
    PERFORMANCE = "performance"
    EXPLANATION = "explanation"
    ARCHITECTURE = "architecture"
    DEPENDENCY_ANALYSIS = "dependency_analysis"
    GENERAL = "general"


# ─────────────────────────────────────────────────────────────────
# Prompt Version Tracking
# ─────────────────────────────────────────────────────────────────

@dataclass
class PromptVersion:
    """Tracks a prompt template version for analytics and A/B testing."""

    version: str
    prompt_type: PromptType
    system_prompt: str
    user_template: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True
    usage_count: int = 0
    avg_quality_score: float = 0.0

    @property
    def content_hash(self) -> str:
        """Generate SHA256 hash of prompt content for deduplication."""
        content = f"{self.system_prompt}{self.user_template}"
        return hashlib.sha256(content.encode()).hexdigest()[:12]


# ─────────────────────────────────────────────────────────────────
# Query Analysis for Dynamic Prompt Selection
# ─────────────────────────────────────────────────────────────────

@dataclass
class QueryAnalysis:
    """Result of analyzing a user query to determine optimal prompt type."""

    detected_type: PromptType
    confidence: float
    keywords_matched: list[str]
    suggested_model: Optional[str] = None
    language_hint: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API responses and logging."""
        return {
            "detected_type": self.detected_type.value,
            "confidence": round(self.confidence, 3),
            "keywords_matched": self.keywords_matched,
            "suggested_model": self.suggested_model,
            "language_hint": self.language_hint,
        }


class QueryAnalyzer:
    """
    Analyzes user queries to automatically detect the best prompt type.

    Uses keyword matching and pattern detection to classify queries
    into the appropriate PromptType without requiring the user to
    explicitly select one.
    """

    KEYWORD_MAP: dict[PromptType, list[str]] = {
        PromptType.BUG_FINDER: [
            "bug", "error", "issue", "wrong", "fix", "broken",
            "crash", "exception", "fail", "problem", "debug",
            "not working", "doesn't work", "incorrect",
        ],
        PromptType.DOC_GENERATOR: [
            "document", "docstring", "jsdoc", "documentation",
            "comment", "describe", "annotate", "readme", "docs",
        ],
        PromptType.TEST_WRITER: [
            "test", "unit test", "pytest", "jest", "testing",
            "coverage", "mock", "assert", "test case", "spec",
        ],
        PromptType.CODE_REVIEWER: [
            "review", "code review", "feedback", "quality",
            "best practice", "pattern", "clean code", "improve",
        ],
        PromptType.SECURITY_SCANNER: [
            "security", "vulnerability", "owasp", "injection",
            "xss", "csrf", "auth", "secret", "leak", "exploit",
            "cve", "attack", "unsafe", "sanitize",
        ],
        PromptType.REFACTOR: [
            "refactor", "restructure", "clean up", "simplify",
            "solid", "dry", "extract", "decompose", "modular",
        ],
        PromptType.PERFORMANCE: [
            "performance", "slow", "optimize", "speed", "fast",
            "complexity", "bottleneck", "memory", "efficient",
            "o(n)", "big o", "cache", "latency",
        ],
        PromptType.EXPLANATION: [
            "explain", "how does", "what does", "walk through",
            "understand", "clarify", "break down", "step by step",
            "teach", "learn",
        ],
        PromptType.ARCHITECTURE: [
            "architecture", "design", "structure", "pattern",
            "component", "module", "layer", "coupling",
            "cohesion", "dependency", "diagram",
        ],
        PromptType.DEPENDENCY_ANALYSIS: [
            "dependency", "import", "require", "package",
            "module", "circular", "unused", "version",
        ],
    }

    LANGUAGE_PATTERNS: dict[str, list[str]] = {
        "python": ["python", ".py", "def ", "class ", "import ", "pip", "pytest"],
        "javascript": ["javascript", "js", "node", "npm", "const ", "let ", "var ", "=>"],
        "typescript": ["typescript", "ts", "interface ", "type ", "tsx"],
        "java": ["java", "public class", "spring", "maven", "gradle"],
        "go": ["golang", "go", "func ", "package ", "goroutine"],
        "rust": ["rust", "cargo", "fn ", "let mut", "impl "],
        "cpp": ["c++", "cpp", "#include", "std::", "nullptr"],
    }

    def analyze(self, query: str) -> QueryAnalysis:
        """
        Analyze a query to determine the optimal prompt type.

        Examines the query text for keywords associated with each
        prompt type and returns the best match with a confidence score.

        Args:
            query: The user's natural language question

        Returns:
            QueryAnalysis with detected type, confidence, and metadata
        """
        query_lower = query.lower().strip()
        scores: dict[PromptType, tuple[float, list[str]]] = {}

        for prompt_type, keywords in self.KEYWORD_MAP.items():
            matched = []
            for kw in keywords:
                if kw in query_lower:
                    matched.append(kw)
            if matched:
                # Score based on number of matches and keyword specificity
                score = len(matched) / len(keywords)
                # Boost for multi-word matches (more specific)
                multi_word_bonus = sum(0.1 for kw in matched if " " in kw)
                scores[prompt_type] = (score + multi_word_bonus, matched)

        # Detect language hint
        language_hint = self._detect_language(query_lower)

        if not scores:
            return QueryAnalysis(
                detected_type=PromptType.CODE_QA,
                confidence=0.5,
                keywords_matched=[],
                language_hint=language_hint,
            )

        # Pick highest scoring type
        best_type = max(scores, key=lambda k: scores[k][0])
        best_score, best_keywords = scores[best_type]
        confidence = min(best_score, 1.0)

        # Suggest code model for code-heavy tasks
        suggested_model = None
        code_heavy = {
            PromptType.BUG_FINDER, PromptType.TEST_WRITER,
            PromptType.REFACTOR, PromptType.PERFORMANCE,
        }
        if best_type in code_heavy:
            suggested_model = "codellama"

        logger.debug(
            "Query analyzed: type=%s, confidence=%.2f, keywords=%s",
            best_type.value, confidence, best_keywords,
        )

        return QueryAnalysis(
            detected_type=best_type,
            confidence=confidence,
            keywords_matched=best_keywords,
            suggested_model=suggested_model,
            language_hint=language_hint,
        )

    def _detect_language(self, query_lower: str) -> Optional[str]:
        """Detect programming language mentioned in the query."""
        for lang, patterns in self.LANGUAGE_PATTERNS.items():
            for pattern in patterns:
                if pattern in query_lower:
                    return lang
        return None


# ─────────────────────────────────────────────────────────────────
# System Prompts — Task-Specific AI Role Definitions
# ─────────────────────────────────────────────────────────────────

SYSTEM_PROMPTS: dict[PromptType, str] = {
    PromptType.CODE_QA: (
        "You are an expert software engineer and code analyst. "
        "You have been given relevant excerpts from a codebase to answer the user's question.\n\n"
        "RULES:\n"
        "- Answer ONLY based on the provided code context when available\n"
        "- If the context does not contain enough information, clearly state what you can and cannot determine\n"
        "- Always cite the specific file path and line numbers when referencing code\n"
        "- Format code examples using markdown code blocks with the correct language\n"
        "- Be precise, concise, and technically accurate\n"
        "- If you spot potential issues while answering, mention them briefly"
    ),

    PromptType.BUG_FINDER: (
        "You are an expert software engineer specializing in debugging and code quality.\n"
        "Analyze the provided code for bugs, logic errors, and potential runtime issues.\n\n"
        "OUTPUT FORMAT (use exactly):\n"
        "## Bugs Found: [COUNT]\n\n"
        "### Bug [N]: [Short Title]\n"
        "- **Severity**: Critical | High | Medium | Low\n"
        "- **File**: [file_path]:[line_number]\n"
        "- **Description**: [What is wrong and why]\n"
        "- **Reproduction**: [How to trigger this bug]\n"
        "- **Fix**: [Exact code fix with explanation]\n\n"
        "## Summary\n"
        "[Overall assessment of code reliability]"
    ),

    PromptType.DOC_GENERATOR: (
        "You are a technical writer and software engineer.\n"
        "Generate comprehensive, accurate documentation for the provided code.\n\n"
        "STANDARDS:\n"
        "- Use Google-style docstrings for Python\n"
        "- Use JSDoc for JavaScript/TypeScript\n"
        "- Use Javadoc for Java\n"
        "- Document every parameter with its type and purpose\n"
        "- Include return types and possible exceptions\n"
        "- Add usage examples for complex functions\n"
        "- Write in clear, professional English"
    ),

    PromptType.TEST_WRITER: (
        "You are a senior software engineer specializing in test-driven development.\n"
        "Write comprehensive tests for the provided code.\n\n"
        "STANDARDS:\n"
        "- Use pytest for Python, Jest for JavaScript/TypeScript\n"
        "- Cover: happy path, edge cases, error conditions, boundary values\n"
        "- Name tests: test_[function]_[scenario]_[expected_result]\n"
        "- Mock external dependencies properly\n"
        "- Include setup/teardown when needed\n"
        "- Aim for meaningful coverage, not just line coverage\n"
        "- Include both unit and integration test examples"
    ),

    PromptType.CODE_REVIEWER: (
        "You are a staff-level software engineer conducting a thorough code review.\n"
        "Review the provided code for quality, maintainability, and best practices.\n\n"
        "REVIEW CATEGORIES (rate each):\n"
        "- Architecture and Design: [rating]\n"
        "- Code Quality and Readability: [rating]\n"
        "- Performance: [rating]\n"
        "- Security: [rating]\n"
        "- Testability: [rating]\n"
        "- Documentation: [rating]\n\n"
        "Ratings: Excellent | Good | Needs Improvement | Critical Issue\n"
        "For each issue found, provide a specific code suggestion."
    ),

    PromptType.SECURITY_SCANNER: (
        "You are a security engineer specializing in application security and OWASP.\n"
        "Perform a thorough security analysis of the provided code.\n\n"
        "OUTPUT FORMAT:\n"
        "## Security Analysis Report\n\n"
        "### Finding [N]: [Vulnerability Name]\n"
        "- **OWASP Category**: [e.g., A03:2021 - Injection]\n"
        "- **Severity**: Critical | High | Medium | Low | Informational\n"
        "- **CWE**: CWE-[NUMBER]\n"
        "- **Location**: [file]:[lines]\n"
        "- **Description**: [What the vulnerability is]\n"
        "- **Impact**: [What an attacker could do]\n"
        "- **Remediation**: [Exact fix with code example]"
    ),

    PromptType.REFACTOR: (
        "You are a software architect specializing in clean code and design patterns.\n"
        "Analyze the provided code and suggest concrete refactoring improvements.\n\n"
        "PRINCIPLES TO APPLY: SOLID, DRY, KISS, YAGNI\n"
        "Show before/after code examples for each suggestion.\n"
        "Prioritize changes by impact and implementation effort.\n"
        "Explain WHY each refactoring improves the code."
    ),

    PromptType.PERFORMANCE: (
        "You are a performance engineering specialist.\n"
        "Analyze the provided code for performance bottlenecks and optimization opportunities.\n\n"
        "For each issue provide:\n"
        "- Current time/space complexity (Big O notation)\n"
        "- Bottleneck explanation with profiling insight\n"
        "- Optimized implementation with complexity analysis\n"
        "- Expected improvement estimate (e.g., 10x faster for large inputs)\n"
        "- Tradeoffs of the optimization"
    ),

    PromptType.EXPLANATION: (
        "You are a patient, expert software engineer and educator.\n"
        "Explain the provided code clearly for developers who may be unfamiliar with it.\n\n"
        "Structure your explanation:\n"
        "1. **Purpose**: What this code does (high-level)\n"
        "2. **How It Works**: Step-by-step walkthrough\n"
        "3. **Key Decisions**: Design choices and why they were made\n"
        "4. **Dependencies**: What this code relies on\n"
        "5. **Gotchas**: Edge cases or potential pitfalls"
    ),

    PromptType.ARCHITECTURE: (
        "You are a principal software architect.\n"
        "Analyze the codebase structure and provide architectural insights.\n\n"
        "Cover:\n"
        "- Overall architecture pattern (MVC, microservices, layered, etc.)\n"
        "- Component responsibilities and boundaries\n"
        "- Data flow through the system\n"
        "- Coupling and cohesion assessment\n"
        "- Scalability considerations\n"
        "- Improvement recommendations with diagrams (ASCII if needed)"
    ),

    PromptType.DEPENDENCY_ANALYSIS: (
        "You are a software engineer specializing in dependency management.\n"
        "Analyze the import/dependency structure of the provided code.\n\n"
        "Report on:\n"
        "- Direct dependencies and their purposes\n"
        "- Circular dependency risks\n"
        "- Unused imports\n"
        "- Coupling between modules\n"
        "- Suggestions for reducing dependency complexity"
    ),

    PromptType.GENERAL: (
        "You are an expert software engineer assistant.\n"
        "Help with any software development question.\n"
        "Be precise, practical, and concise.\n"
        "Use code examples when helpful.\n"
        "Cite file paths when referencing the codebase."
    ),
}


# ─────────────────────────────────────────────────────────────────
# User Prompt Templates
# ─────────────────────────────────────────────────────────────────

RAG_TEMPLATE = (
    "=== CODEBASE CONTEXT ===\n"
    "\n\n"
    "=== USER QUESTION ===\n"
    "\n\n"
    "=== INSTRUCTIONS ===\n"
    "Answer the question based on the code context above.\n"
    "Reference specific files and line numbers when citing code.\n"
    "If the context is insufficient, say so clearly."
)

NO_CONTEXT_TEMPLATE = (
    "=== USER QUESTION ===\n"
    "\n\n"
    "Note: No relevant code context was found for this query.\n"
    "Answer based on your general software engineering knowledge,\n"
    "but make it clear you are not referencing the user's specific codebase."
)

CONVERSATION_TEMPLATE = (
    "=== CONVERSATION HISTORY ===\n"
    "\n\n"
    "=== NEW CODEBASE CONTEXT ===\n"
    "\n\n"
    "=== USER FOLLOW-UP QUESTION ===\n"
    "\n\n"
    "=== INSTRUCTIONS ===\n"
    "Continue the conversation naturally. Reference the history for context.\n"
    "Use the new code context to inform your answer.\n"
    "If the user refers to 'it' or 'this', determine what from the history."
)

LANGUAGE_AWARE_TEMPLATE = (
    "=== CODEBASE CONTEXT (Language: ) ===\n"
    "\n\n"
    "=== USER QUESTION ===\n"
    "\n\n"
    "=== INSTRUCTIONS ===\n"
    "The code is written in . Use -specific conventions,\n"
    "idioms, and best practices in your response.\n"
    "Reference specific files and line numbers when citing code."
)

MULTI_FILE_TEMPLATE = (
    "=== CODEBASE CONTEXT (Multiple Files) ===\n"
    "Files referenced: \n\n"
    "\n\n"
    "=== USER QUESTION ===\n"
    "\n\n"
    "=== INSTRUCTIONS ===\n"
    "The context spans multiple files. Consider cross-file dependencies\n"
    "and interactions in your analysis. Cite each file specifically."
)


# ─────────────────────────────────────────────────────────────────
# Conversation History Formatter
# ─────────────────────────────────────────────────────────────────

class ConversationFormatter:
    """
    Formats conversation history for injection into prompts.

    Handles token budget management by summarizing older messages
    and preserving recent ones in full detail.
    """

    MAX_HISTORY_TURNS: int = 6
    MAX_HISTORY_TOKENS: int = 800
    CHARS_PER_TOKEN: int = 4

    def format_history(
        self,
        messages: list[dict[str, str]],
        max_turns: Optional[int] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Format conversation messages into a prompt-ready history string.

        Recent messages are kept in full. Older messages are summarized
        if the history exceeds the token budget.

        Args:
            messages: List of {"role": str, "content": str} dicts
            max_turns: Override max conversation turns to include
            max_tokens: Override max tokens for history

        Returns:
            Formatted history string ready for template injection
        """
        if not messages:
            return ""

        limit_turns = max_turns or self.MAX_HISTORY_TURNS
        limit_chars = (max_tokens or self.MAX_HISTORY_TOKENS) * self.CHARS_PER_TOKEN

        # Take most recent turns
        recent = messages[-limit_turns:]
        parts: list[str] = []
        total_chars = 0

        for msg in recent:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            prefix = "User" if role == "user" else "Assistant"

            # Truncate long messages
            if len(content) > 500 and total_chars + len(content) > limit_chars:
                content = content[:300] + "\n... [message truncated for brevity]"

            formatted = f"{prefix}: {content}"
            parts.append(formatted)
            total_chars += len(formatted)

            if total_chars > limit_chars:
                break

        return "\n\n".join(parts)

    def summarize_long_history(
        self, messages: list[dict[str, str]]
    ) -> str:
        """
        Create a brief summary of a long conversation.

        Used when history exceeds the token budget to provide
        a compressed context of what was discussed.

        Args:
            messages: Full conversation message list

        Returns:
            Summarized history string
        """
        if len(messages) <= 4:
            return self.format_history(messages)

        # Summarize: mention topics discussed and keep last 2 turns in full
        topics: list[str] = []
        for msg in messages[:-2]:
            if msg["role"] == "user":
                # Extract first sentence as topic
                first_line = msg["content"].split("\n")[0][:100]
                topics.append(first_line)

        summary = "Previous topics discussed:\n"
        for i, topic in enumerate(topics, 1):
            summary += f"  {i}. {topic}\n"
        summary += "\nMost recent exchange:\n"
        summary += self.format_history(messages[-2:], max_turns=2)

        return summary


# ─────────────────────────────────────────────────────────────────
# Prompt Template Engine — Main Interface
# ─────────────────────────────────────────────────────────────────

class PromptTemplateEngine:
    """
    Factory for building complete, context-aware prompts.

    Separates prompt construction from the RAG pipeline to enable:
    - Easy prompt iteration without changing retrieval logic
    - A/B testing of prompt variants
    - Dynamic prompt selection based on query analysis
    - Language and context-aware template adaptation

    This is the ONLY class external code should interact with.
    """

    def __init__(self) -> None:
        """Initialize the engine with query analyzer and history formatter."""
        self._analyzer = QueryAnalyzer()
        self._formatter = ConversationFormatter()
        self._version_registry: dict[str, PromptVersion] = {}
        logger.info("PromptTemplateEngine initialized with %d prompt types", len(PromptType))

    def analyze_query(self, query: str) -> QueryAnalysis:
        """
        Analyze a query to detect the optimal prompt type.

        Useful for auto-detecting intent when the user does not
        explicitly select a prompt type in the UI.

        Args:
            query: User's natural language question

        Returns:
            QueryAnalysis with detected type and confidence
        """
        return self._analyzer.analyze(query)

    def build_system_prompt(
        self,
        prompt_type: PromptType,
        language: Optional[str] = None,
    ) -> str:
        """
        Get the system prompt for a given task type.

        Optionally appends language-specific instructions.

        Args:
            prompt_type: The type of AI task
            language: Optional programming language for specialized guidance

        Returns:
            Complete system prompt string
        """
        base = SYSTEM_PROMPTS.get(prompt_type, SYSTEM_PROMPTS[PromptType.GENERAL])

        if language:
            lang_suffix = (
                f"\n\nIMPORTANT: The codebase is primarily written in {language}. "
                f"Use {language}-specific conventions, idioms, and best practices "
                f"in all code examples and suggestions."
            )
            return base + lang_suffix

        return base

    def build_user_prompt(
        self,
        query: str,
        context: str,
        conversation_history: Optional[str] = None,
        language: Optional[str] = None,
        file_paths: Optional[list[str]] = None,
    ) -> str:
        """
        Build the user prompt with context, history, and language awareness.

        Selects the appropriate template based on available data:
        - No context → NO_CONTEXT_TEMPLATE
        - With history → CONVERSATION_TEMPLATE
        - With language → LANGUAGE_AWARE_TEMPLATE
        - Multiple files → MULTI_FILE_TEMPLATE
        - Default → RAG_TEMPLATE

        Args:
            query: User's question
            context: Retrieved code context (may be empty)
            conversation_history: Optional formatted prior conversation
            language: Optional detected programming language
            file_paths: Optional list of referenced file paths

        Returns:
            Complete user prompt string
        """
        if not context:
            template = Template(NO_CONTEXT_TEMPLATE)
            return template.safe_substitute(query=query)

        if conversation_history:
            template = Template(CONVERSATION_TEMPLATE)
            return template.safe_substitute(
                history=conversation_history,
                context=context,
                query=query,
            )

        if language:
            template = Template(LANGUAGE_AWARE_TEMPLATE)
            return template.safe_substitute(
                language=language,
                context=context,
                query=query,
            )

        if file_paths and len(file_paths) > 1:
            template = Template(MULTI_FILE_TEMPLATE)
            file_list = ", ".join(file_paths[:10])
            return template.safe_substitute(
                file_list=file_list,
                context=context,
                query=query,
            )

        template = Template(RAG_TEMPLATE)
        return template.safe_substitute(context=context, query=query)

    def build_messages(
        self,
        query: str,
        context: str,
        prompt_type: PromptType = PromptType.CODE_QA,
        conversation_history: Optional[str] = None,
        language: Optional[str] = None,
        file_paths: Optional[list[str]] = None,
    ) -> list[dict[str, str]]:
        """
        Build the complete message list for the LLM API.

        This is the primary method used by the RAG pipeline.

        Args:
            query: User's question
            context: Retrieved code context
            prompt_type: Type of AI analysis
            conversation_history: Prior conversation text
            language: Detected programming language
            file_paths: Referenced file paths

        Returns:
            List of message dicts in OpenAI chat format:
            [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
        """
        system_prompt = self.build_system_prompt(prompt_type, language)
        user_prompt = self.build_user_prompt(
            query=query,
            context=context,
            conversation_history=conversation_history,
            language=language,
            file_paths=file_paths,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        logger.debug(
            "Prompt built: type=%s, system=%d chars, user=%d chars",
            prompt_type.value,
            len(system_prompt),
            len(user_prompt),
        )

        return messages

    def build_messages_auto(
        self,
        query: str,
        context: str,
        conversation_history: Optional[str] = None,
        language: Optional[str] = None,
        file_paths: Optional[list[str]] = None,
    ) -> tuple[list[dict[str, str]], QueryAnalysis]:
        """
        Auto-detect prompt type from query and build messages.

        Combines query analysis with prompt building for a fully
        automatic prompt construction pipeline.

        Args:
            query: User's question
            context: Retrieved code context
            conversation_history: Prior conversation
            language: Language hint
            file_paths: Referenced files

        Returns:
            Tuple of (messages, analysis) where analysis contains
            the detected prompt type and confidence
        """
        analysis = self.analyze_query(query)
        language = language or analysis.language_hint

        messages = self.build_messages(
            query=query,
            context=context,
            prompt_type=analysis.detected_type,
            conversation_history=conversation_history,
            language=language,
            file_paths=file_paths,
        )

        return messages, analysis

    def format_conversation_history(
        self,
        messages: list[dict[str, str]],
        max_turns: int = 6,
    ) -> str:
        """
        Format raw message list into a conversation history string.

        Convenience method that delegates to ConversationFormatter.

        Args:
            messages: List of {"role": str, "content": str} dicts
            max_turns: Max turns to include

        Returns:
            Formatted history string
        """
        return self._formatter.format_history(messages, max_turns=max_turns)

    def get_all_prompt_types(self) -> list[dict[str, str]]:
        """
        Return all available prompt types with descriptions.

        Used by the frontend to populate the prompt type selector.

        Returns:
            List of dicts with 'value', 'label', 'description' keys
        """
        descriptions = {
            PromptType.CODE_QA: "Ask questions about your codebase",
            PromptType.BUG_FINDER: "Find bugs and potential issues",
            PromptType.DOC_GENERATOR: "Generate documentation for code",
            PromptType.TEST_WRITER: "Write unit and integration tests",
            PromptType.CODE_REVIEWER: "Get a comprehensive code review",
            PromptType.SECURITY_SCANNER: "Scan for security vulnerabilities",
            PromptType.REFACTOR: "Get refactoring suggestions",
            PromptType.PERFORMANCE: "Find performance bottlenecks",
            PromptType.EXPLANATION: "Get code explanations",
            PromptType.ARCHITECTURE: "Analyze codebase architecture",
            PromptType.DEPENDENCY_ANALYSIS: "Analyze dependencies and imports",
            PromptType.GENERAL: "General software engineering help",
        }
        return [
            {
                "value": pt.value,
                "label": pt.value.replace("_", " ").title(),
                "description": descriptions.get(pt, ""),
            }
            for pt in PromptType
        ]

    @staticmethod
    def estimate_token_count(text: str) -> int:
        """
        Rough token count estimate (4 characters per token).

        Args:
            text: Text to estimate

        Returns:
            Approximate token count
        """
        return len(text) // 4
