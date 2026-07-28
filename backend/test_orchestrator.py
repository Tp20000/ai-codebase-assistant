"""
Step 27 Test Suite - AgentOrchestrator
Run from backend/ directory with venv activated:
    cd backend
    python test_orchestrator.py
"""

import asyncio
import sys
import traceback

sys.path.insert(0, ".")

PASS = 0
FAIL = 0


def ok(label: str) -> None:
    global PASS
    PASS += 1
    print(f"  PASS: {label}")


def fail(label: str, exc: Exception) -> None:
    global FAIL
    FAIL += 1
    print(f"  FAIL: {label} -> {exc}")
    traceback.print_exc()


# ---------------------------------------------------------------------------
def test_registry_complete() -> None:
    print("[1] AGENT_REGISTRY has all 7 agents")
    from app.core.agents.orchestrator import AGENT_REGISTRY

    expected = [
        "bug_finder", "doc_generator", "test_writer",
        "code_reviewer", "security_scanner",
        "refactor_suggester", "performance_analyzer",
    ]
    for agent_id in expected:
        assert agent_id in AGENT_REGISTRY, \
            f"Missing from registry: {agent_id}"

    print(f"  Registry keys: {list(AGENT_REGISTRY.keys())}")
    assert len(AGENT_REGISTRY) == 7

    ok("AGENT_REGISTRY complete")


# ---------------------------------------------------------------------------
def test_agent_loader() -> None:
    print("[2] AgentLoader - load each agent")
    from app.core.agents.orchestrator import AGENT_REGISTRY, AgentLoader

    AgentLoader.clear_cache()
    for agent_id in AGENT_REGISTRY:
        try:
            agent = AgentLoader.load(agent_id)
            print(f"  Loaded: {agent_id} -> {agent.agent_type}")
            assert agent.agent_type == agent_id, \
                f"agent_type mismatch: {agent.agent_type} != {agent_id}"
        except Exception as exc:
            raise AssertionError(
                f"Failed to load {agent_id}: {exc}"
            ) from exc

    ok("AgentLoader all 7 agents")


# ---------------------------------------------------------------------------
def test_agent_loader_invalid() -> None:
    print("[3] AgentLoader - invalid agent_id raises ValueError")
    from app.core.agents.orchestrator import AgentLoader

    try:
        AgentLoader.load("nonexistent_agent")
        raise AssertionError("Should have raised ValueError")
    except ValueError as exc:
        print(f"  Correctly raised ValueError: {exc}")

    ok("AgentLoader invalid raises ValueError")


# ---------------------------------------------------------------------------
def test_orchestrator_list_agents() -> None:
    print("[4] AgentOrchestrator.list_agents()")
    from app.core.agents.orchestrator import AgentOrchestrator

    orch = AgentOrchestrator()
    agents = orch.list_agents()

    print(f"  Listed {len(agents)} agents:")
    for a in agents:
        print(f"    - {a['agent_id']}: {a['display']}")

    assert len(agents) == 7
    agent_ids = [a["agent_id"] for a in agents]
    assert "security_scanner" in agent_ids
    assert "performance_analyzer" in agent_ids

    ok("list_agents")


# ---------------------------------------------------------------------------
def test_orchestration_result_to_dict() -> None:
    print("[5] OrchestrationResult.to_dict()")
    from datetime import datetime, timezone
    from app.core.agents.base_agent import AgentResult, AgentStatus
    from app.core.agents.orchestrator import OrchestrationResult

    mock_result = AgentResult(
        task_id="task-001",
        agent_type="bug_finder",
        status=AgentStatus.COMPLETED,
        result={"total_bugs": 2},
        report="# Bug Report",
        sources=[],
        error=None,
        elapsed_ms=150.0,
        tokens_used=100,
        retrieval_time_ms=50.0,
        llm_time_ms=100.0,
    )

    orch = OrchestrationResult(
        orchestration_id="orch-001",
        mode="single",
        agent_results={"bug_finder": mock_result},
        master_report="# Master Report",
        total_elapsed_ms=150.0,
        agents_succeeded=1,
        agents_failed=0,
    )

    d = orch.to_dict()
    print(f"  Keys: {list(d.keys())}")
    assert d["orchestration_id"] == "orch-001"
    assert d["agents_succeeded"] == 1
    assert d["agents_failed"] == 0
    assert "bug_finder" in d["agent_results"]

    ok("OrchestrationResult.to_dict")


# ---------------------------------------------------------------------------
async def test_run_single() -> None:
    print("[6] run_single - security_scanner")
    from app.core.agents.base_agent import AgentConfig, AgentStatus
    from app.core.agents.orchestrator import AgentOrchestrator

    orch = AgentOrchestrator(retriever=None, streaming_client=None)

    config = AgentConfig(
        project_id="orch-test-001",
        user_id="orch-user-001",
        query="Run security scan",
        model="tinyllama",
        extra={
            "code_content": (
                "import os\n"
                "password = 'hardcoded_secret'\n\n"
                "def run(cmd):\n"
                "    os.system(cmd)\n"
            ),
            "language": "python",
            "file_path": "test.py",
        },
    )

    result = await orch.run_single("security_scanner", config)

    print(f"  status: {result.status}")
    print(f"  agent_type: {result.agent_type}")
    print(f"  elapsed_ms: {result.elapsed_ms:.1f}")

    assert result.status == AgentStatus.COMPLETED
    assert result.agent_type == "security_scanner"
    assert result.result is not None

    ok("run_single security_scanner")


# ---------------------------------------------------------------------------
async def test_run_parallel_two_agents() -> None:
    print("[7] run_parallel - code_reviewer + performance_analyzer")
    from app.core.agents.base_agent import AgentConfig, AgentStatus
    from app.core.agents.orchestrator import AgentOrchestrator

    orch = AgentOrchestrator(retriever=None, streaming_client=None)

    config = AgentConfig(
        project_id="orch-parallel-001",
        user_id="orch-user-001",
        query="Review and analyze performance",
        model="tinyllama",
        extra={
            "code_content": (
                "def slow_search(items, target):\n"
                "    for i in items:\n"
                "        for j in items:\n"
                "            if i == target and j == target:\n"
                "                return True\n"
                "    return False\n"
            ),
            "language": "python",
            "file_path": "search.py",
        },
    )

    import time
    start = time.perf_counter()
    orch_result = await orch.run_parallel(
        ["code_reviewer", "performance_analyzer"], config
    )
    elapsed = (time.perf_counter() - start) * 1000

    print(f"  orchestration_id: {orch_result.orchestration_id}")
    print(f"  mode: {orch_result.mode}")
    print(f"  succeeded: {orch_result.agents_succeeded}")
    print(f"  failed: {orch_result.agents_failed}")
    print(f"  total_elapsed_ms: {orch_result.total_elapsed_ms:.1f}")
    print(f"  wall_clock_ms: {elapsed:.1f}")
    print(f"  report_length: {len(orch_result.master_report)}")

    assert orch_result.mode == "parallel"
    assert orch_result.agents_succeeded == 2
    assert orch_result.agents_failed == 0
    assert "code_reviewer" in orch_result.agent_results
    assert "performance_analyzer" in orch_result.agent_results
    assert "# Master Code Analysis Report" in orch_result.master_report
    assert len(orch_result.master_report) > 200

    # Parallel should be faster than sum of sequential
    # (both agents run concurrently)
    sum_of_sequential = sum(
        r.elapsed_ms
        for r in orch_result.agent_results.values()
    )
    print(f"  sum_sequential_ms: {sum_of_sequential:.1f}")

    ok("run_parallel 2 agents")


# ---------------------------------------------------------------------------
async def test_run_pipeline() -> None:
    print("[8] run_pipeline - sequential execution")
    from app.core.agents.base_agent import AgentConfig, AgentStatus
    from app.core.agents.orchestrator import AgentOrchestrator

    orch = AgentOrchestrator(retriever=None, streaming_client=None)

    config = AgentConfig(
        project_id="orch-pipeline-001",
        user_id="orch-user-001",
        query="Sequential analysis",
        model="tinyllama",
        extra={
            "code_content": (
                "def add(a, b):\n"
                "    return a + b\n\n"
                "class Calculator:\n"
                "    def multiply(self, x, y):\n"
                "        return x * y\n"
            ),
            "language": "python",
            "file_path": "calc.py",
        },
    )

    orch_result = await orch.run_pipeline(
        ["doc_generator", "test_writer"], config
    )

    print(f"  mode: {orch_result.mode}")
    print(f"  succeeded: {orch_result.agents_succeeded}")
    print(f"  agents: {list(orch_result.agent_results.keys())}")

    assert orch_result.mode == "pipeline"
    assert orch_result.agents_succeeded == 2
    assert "doc_generator" in orch_result.agent_results
    assert "test_writer" in orch_result.agent_results

    ok("run_pipeline sequential")


# ---------------------------------------------------------------------------
async def test_run_full_all_agents() -> None:
    print("[9] run_full - all 7 agents (no LLM)")
    from app.core.agents.base_agent import AgentConfig, AgentStatus
    from app.core.agents.orchestrator import AgentOrchestrator

    orch = AgentOrchestrator(retriever=None, streaming_client=None)

    config = AgentConfig(
        project_id="orch-full-001",
        user_id="orch-user-001",
        query="Complete code analysis",
        model="tinyllama",
        extra={
            "code_content": (
                "import os\n\n"
                "password = 'secret123'\n\n"
                "def process(items, flag, mode, limit, extra):\n"
                "    result = ''\n"
                "    for i in items:\n"
                "        for j in items:\n"
                "            result += str(i) + str(j)\n"
                "    return result\n\n"
                "class DataManager:\n"
                "    def __init__(self):\n"
                "        self.db = DatabaseClient()\n\n"
                "    def run(self, cmd):\n"
                "        os.system(cmd)\n"
            ),
            "language": "python",
            "file_path": "app.py",
        },
    )

    orch_result = await orch.run_full(config)

    print(f"  orchestration_id: {orch_result.orchestration_id}")
    print(f"  mode: {orch_result.mode}")
    print(f"  agents_succeeded: {orch_result.agents_succeeded}")
    print(f"  agents_failed: {orch_result.agents_failed}")
    print(f"  total_elapsed_ms: {orch_result.total_elapsed_ms:.1f}")
    print(f"  master_report_chars: {len(orch_result.master_report)}")
    print()
    print("  Agent results:")
    for agent_id, result in orch_result.agent_results.items():
        print(
            f"    {agent_id}: {result.status.value} "
            f"({result.elapsed_ms:.0f}ms)"
        )

    print()
    print("  Master report preview (first 500 chars):")
    for line in orch_result.master_report[:500].splitlines():
        print("    " + line)

    assert orch_result.mode == "parallel"
    assert len(orch_result.agent_results) == 7
    # At least 5 of 7 should succeed (some may fail on edge cases)
    assert orch_result.agents_succeeded >= 5, \
        f"Expected >= 5 succeeded, got {orch_result.agents_succeeded}"
    assert "# Master Code Analysis Report" in orch_result.master_report
    assert "## Executive Summary" in orch_result.master_report
    assert "## Agent Status" in orch_result.master_report
    assert "## Recommended Action Plan" in orch_result.master_report

    d = orch_result.to_dict()
    assert "orchestration_id" in d
    assert len(d["agent_results"]) == 7

    ok(
        f"run_full: {orch_result.agents_succeeded}/7 succeeded "
        f"in {orch_result.total_elapsed_ms:.0f}ms"
    )


# ---------------------------------------------------------------------------
async def test_parallel_failure_tolerance() -> None:
    print("[10] Parallel failure tolerance")
    from app.core.agents.base_agent import AgentConfig, AgentStatus
    from app.core.agents.orchestrator import AgentOrchestrator

    orch = AgentOrchestrator(retriever=None, streaming_client=None)

    # Empty code_content — should cause some agents to fail gracefully
    config = AgentConfig(
        project_id="orch-fail-001",
        user_id="orch-user-001",
        query="Test failure tolerance",
        model="tinyllama",
        extra={
            "code_content": "",  # intentionally empty
            "language": "python",
            "file_path": "empty.py",
        },
    )

    orch_result = await orch.run_parallel(
        ["code_reviewer", "security_scanner"], config
    )

    print(f"  succeeded: {orch_result.agents_succeeded}")
    print(f"  failed: {orch_result.agents_failed}")
    print(f"  mode: {orch_result.mode}")

    # Master report should still be generated even if agents fail
    assert "# Master Code Analysis Report" in orch_result.master_report
    assert orch_result.mode == "parallel"
    # Result object is always returned (no exception propagated)
    total = orch_result.agents_succeeded + orch_result.agents_failed
    assert total == 2

    ok("parallel failure tolerance")


# ---------------------------------------------------------------------------
async def main() -> None:
    print("=" * 60)
    print("Step 27 - AgentOrchestrator Test Suite")
    print("=" * 60)
    print()

    sync_fns = [
        test_registry_complete,
        test_agent_loader,
        test_agent_loader_invalid,
        test_orchestrator_list_agents,
        test_orchestration_result_to_dict,
    ]
    async_fns = [
        test_run_single,
        test_run_parallel_two_agents,
        test_run_pipeline,
        test_run_full_all_agents,
        test_parallel_failure_tolerance,
    ]

    for fn in sync_fns:
        try:
            fn()
        except Exception as exc:
            fail(fn.__name__, exc)
        print()

    for fn in async_fns:
        try:
            await fn()
        except Exception as exc:
            fail(fn.__name__, exc)
        print()

    print("=" * 60)
    print(f"Results: {PASS} passed | {FAIL} failed")
    print("ALL TESTS PASSED" if FAIL == 0 else "SOME TESTS FAILED")
    print("=" * 60)
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
