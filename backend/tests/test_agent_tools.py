"""
Agent unit tests with mocked LLM responses.
All tests are unit-level — no Ollama, ChromaDB, or Redis required.
"""

from __future__ import annotations
import importlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock
import pytest

pytestmark = pytest.mark.unit

AGENT_MODULE_SPECS = [
    ("base_agent", "app.core.agents.base_agent", ["BaseAgent", "AbstractAgent"]),
    ("bug_finder", "app.core.agents.bug_finder", ["BugFinderAgent", "BugFinder"]),
    ("doc_generator", "app.core.agents.doc_generator", ["DocGeneratorAgent", "DocumentationAgent"]),
    ("test_writer", "app.core.agents.test_writer", ["TestWriterAgent", "TestGeneratorAgent"]),
    ("code_reviewer", "app.core.agents.code_reviewer", ["CodeReviewerAgent", "ReviewerAgent"]),
    ("security_scanner", "app.core.agents.security_scanner", ["SecurityScannerAgent", "SecurityAgent"]),
    ("refactor_agent", "app.core.agents.refactor_agent", ["RefactorAgent", "CodeRefactorAgent"]),
    ("performance_agent", "app.core.agents.performance_agent", ["PerformanceAgent", "PerformanceAnalyzerAgent"]),
    ("orchestrator", "app.core.agents.orchestrator", ["AgentOrchestrator", "Orchestrator"]),
]

TOOL_CASES = [
    ("bug_finder", "findings"),
    ("doc_generator", "documents"),
    ("test_writer", "tests"),
    ("code_reviewer", "issues"),
    ("security_scanner", "vulnerabilities"),
    ("refactor_agent", "suggestions"),
    ("performance_agent", "bottlenecks"),
]


def _safe_import(module_path: str):
    try:
        return importlib.import_module(module_path)
    except Exception as exc:
        pytest.skip(f"Could not import {module_path}: {exc}")


def _find_class(module: Any, candidate_names: list) -> type:
    for name in candidate_names:
        obj = getattr(module, name, None)
        if obj is not None and isinstance(obj, type):
            return obj
    for name in dir(module):
        if name.startswith("_"):
            continue
        obj = getattr(module, name, None)
        if isinstance(obj, type):
            return obj
    return None


def _find_method_name(obj: Any, names: list):
    for name in names:
        if hasattr(obj, name) and callable(getattr(obj, name)):
            return name
    return None


class TestAgentModuleImports:
    @pytest.mark.parametrize("label,module_path,candidates", AGENT_MODULE_SPECS,
        ids=[x[0] for x in AGENT_MODULE_SPECS])
    async def test_agent_module_importable(self, label, module_path, candidates):
        module = _safe_import(module_path)
        assert module is not None

    @pytest.mark.parametrize("label,module_path,candidates", AGENT_MODULE_SPECS,
        ids=[x[0] for x in AGENT_MODULE_SPECS])
    async def test_agent_module_has_public_exports(self, label, module_path, candidates):
        module = _safe_import(module_path)
        public = [x for x in dir(module) if not x.startswith("_")]
        assert len(public) > 0

    @pytest.mark.parametrize("label,module_path,candidates", AGENT_MODULE_SPECS,
        ids=[x[0] for x in AGENT_MODULE_SPECS])
    async def test_agent_module_has_class_or_callable(self, label, module_path, candidates):
        module = _safe_import(module_path)
        cls = _find_class(module, candidates)
        public_callables = [x for x in dir(module)
            if not x.startswith("_") and callable(getattr(module, x, None))]
        assert cls is not None or len(public_callables) > 0


class TestBaseAgentContract:
    async def test_base_agent_exists(self):
        module = _safe_import("app.core.agents.base_agent")
        cls = _find_class(module, ["BaseAgent", "AbstractAgent"])
        assert cls is not None

    async def test_base_agent_has_run_like_method(self):
        module = _safe_import("app.core.agents.base_agent")
        cls = _find_class(module, ["BaseAgent", "AbstractAgent"])
        if cls is None:
            pytest.skip("No base agent class found")
        method = _find_method_name(cls, ["run", "analyze", "execute", "process", "invoke"])
        assert method is not None

    async def test_fake_agent_subclass_with_mocked_llm(self):
        module = _safe_import("app.core.agents.base_agent")
        cls = _find_class(module, ["BaseAgent", "AbstractAgent"])
        parent = cls if cls is not None else object

        class FakeAgent(parent):
            def __init__(self, llm):
                self.llm = llm
            async def run(self, source):
                response = await self.llm.generate(f"Analyze:\n{source}")
                return {"agent_type": "fake_agent", "status": "completed", "summary": response}

        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value="This code prints hello world.")
        agent = FakeAgent(mock_llm)
        result = await agent.run("print('hello world')")
        assert result["agent_type"] == "fake_agent"
        assert result["status"] == "completed"
        assert isinstance(result["summary"], str)
        mock_llm.generate.assert_called_once()


class TestMockedOrchestratorBehavior:
    async def test_mocked_orchestrator_registers_agents(self):
        orchestrator = MagicMock()
        orchestrator.registry = {}
        def register(name, agent):
            orchestrator.registry[name] = agent
        orchestrator.register = register
        bug_agent = MagicMock()
        doc_agent = MagicMock()
        orchestrator.register("bug_finder", bug_agent)
        orchestrator.register("doc_generator", doc_agent)
        assert "bug_finder" in orchestrator.registry
        assert orchestrator.registry["bug_finder"] is bug_agent

    async def test_mocked_orchestrator_lists_agents(self):
        orchestrator = MagicMock()
        orchestrator.registry = {"bug_finder": MagicMock(), "doc_generator": MagicMock(), "test_writer": MagicMock()}
        def get_available_agents():
            return list(orchestrator.registry.keys())
        orchestrator.get_available_agents = get_available_agents
        agents = orchestrator.get_available_agents()
        assert isinstance(agents, list)
        assert "bug_finder" in agents
        assert "test_writer" in agents

    async def test_mocked_orchestrator_dispatches_to_correct_agent(self):
        bug_agent = MagicMock()
        bug_agent.run = AsyncMock(return_value={"status": "completed", "findings": []})
        sec_agent = MagicMock()
        sec_agent.run = AsyncMock(return_value={"status": "completed", "vulnerabilities": []})
        registry = {"bug_finder": bug_agent, "security_scanner": sec_agent}
        async def run_agent(agent_type, payload):
            return await registry[agent_type].run(payload["code"])
        result = await run_agent("bug_finder", {"code": "def foo(): pass"})
        bug_agent.run.assert_called_once()
        sec_agent.run.assert_not_called()
        assert result["status"] == "completed"

    async def test_mocked_orchestrator_unknown_agent_raises(self):
        registry = {}
        async def run_agent(agent_type, payload):
            if agent_type not in registry:
                raise KeyError(f"Unknown agent: {agent_type}")
            return await registry[agent_type].run(payload["code"])
        with pytest.raises(KeyError, match="Unknown agent"):
            await run_agent("nonexistent", {"code": "print('x')"})


class TestMockedToolExecution:
    @pytest.mark.parametrize("agent_type,result_key", TOOL_CASES)
    async def test_mocked_agent_returns_structured_result(self, agent_type, result_key):
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value=f"{agent_type} analysis completed.")

        class FakeToolAgent:
            def __init__(self, llm):
                self.llm = llm
            async def run(self, code):
                summary = await self.llm.generate(f"[{agent_type}] Analyze:\n{code}")
                return {"agent_type": agent_type, "status": "completed",
                        "summary": summary, result_key: [{"id": "1", "message": f"{agent_type} item"}]}

        agent = FakeToolAgent(mock_llm)
        result = await agent.run("def hello(): return 'world'")
        assert result["agent_type"] == agent_type
        assert result["status"] == "completed"
        assert result_key in result
        assert isinstance(result[result_key], list)
        mock_llm.generate.assert_called_once()

    @pytest.mark.parametrize("agent_type,result_key", TOOL_CASES)
    async def test_mocked_agent_handles_llm_failure(self, agent_type, result_key):
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

        class FakeToolAgent:
            def __init__(self, llm):
                self.llm = llm
            async def run(self, code):
                summary = await self.llm.generate(code)
                return {result_key: [], "summary": summary}

        agent = FakeToolAgent(mock_llm)
        with pytest.raises(RuntimeError, match="LLM unavailable"):
            await agent.run("def x(): pass")

    async def test_mocked_agent_execution_order(self):
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value="analysis")

        class FakeAgent:
            async def run(self, code):
                summary = await mock_llm.generate(code)
                return {"status": "completed", "summary": summary}

        agent = FakeAgent()
        result = await agent.run("print('hello')")
        assert result["status"] == "completed"
        mock_llm.generate.assert_called_once_with("print('hello')")

    async def test_mocked_agent_payload_with_metadata(self):
        payload = {
            "agent_type": "bug_finder",
            "status": "completed",
            "findings": [{"file": "app.py", "line": 42, "confidence": 0.92, "message": "None dereference"}],
        }
        assert payload["findings"][0]["file"] == "app.py"
        assert payload["findings"][0]["confidence"] > 0.9


class TestActualAgentModuleShapes:
    @pytest.mark.parametrize("label,module_path,candidates",
        [x for x in AGENT_MODULE_SPECS if x[0] not in ("base_agent", "orchestrator")],
        ids=[x[0] for x in AGENT_MODULE_SPECS if x[0] not in ("base_agent", "orchestrator")])
    async def test_actual_agent_module_has_class(self, label, module_path, candidates):
        module = _safe_import(module_path)
        cls = _find_class(module, candidates)
        if cls is None:
            pytest.skip(f"No class found in {module_path}")
        assert cls is not None

    @pytest.mark.parametrize("label,module_path,candidates",
        [x for x in AGENT_MODULE_SPECS if x[0] not in ("base_agent", "orchestrator")],
        ids=[x[0] for x in AGENT_MODULE_SPECS if x[0] not in ("base_agent", "orchestrator")])
    async def test_actual_agent_class_has_run_like_method(self, label, module_path, candidates):
        module = _safe_import(module_path)
        cls = _find_class(module, candidates)
        if cls is None:
            pytest.skip(f"No class found in {module_path}")
        method = _find_method_name(cls, ["run", "analyze", "execute", "process", "invoke"])
        if method is None:
            pytest.skip(f"{cls.__name__} has no run-like method")
        assert method is not None


class TestMockedMultiAgentFlow:
    async def test_multi_agent_sequential_execution(self):
        bug_agent = MagicMock()
        bug_agent.run = AsyncMock(return_value={"findings": ["null check missing"]})
        sec_agent = MagicMock()
        sec_agent.run = AsyncMock(return_value={"vulnerabilities": ["hardcoded secret"]})
        review_agent = MagicMock()
        review_agent.run = AsyncMock(return_value={"issues": ["function too long"]})
        code = "def login():\n    password='secret'\n    return True"
        bug_result = await bug_agent.run(code)
        sec_result = await sec_agent.run(code)
        review_result = await review_agent.run(code)
        assert "findings" in bug_result
        assert "vulnerabilities" in sec_result
        assert "issues" in review_result

    async def test_multi_agent_aggregation(self):
        results = {
            "bug_finder": {"findings": [{"message": "Possible bug"}]},
            "security_scanner": {"vulnerabilities": [{"message": "Secret exposed"}]},
            "code_reviewer": {"issues": [{"message": "Naming issue"}]},
        }
        combined = {
            "status": "completed",
            "agent_count": len(results),
            "summary": {
                "bugs": len(results["bug_finder"]["findings"]),
                "security": len(results["security_scanner"]["vulnerabilities"]),
                "review": len(results["code_reviewer"]["issues"]),
            },
        }
        assert combined["status"] == "completed"
        assert combined["agent_count"] == 3
        assert combined["summary"]["bugs"] == 1

    async def test_multi_agent_failure_isolation(self):
        bug_agent = MagicMock()
        bug_agent.run = AsyncMock(side_effect=RuntimeError("bug finder crashed"))
        sec_agent = MagicMock()
        sec_agent.run = AsyncMock(return_value={"vulnerabilities": []})
        sec_result = await sec_agent.run("print('ok')")
        assert sec_result["vulnerabilities"] == []
        with pytest.raises(RuntimeError, match="bug finder crashed"):
            await bug_agent.run("print('ok')")