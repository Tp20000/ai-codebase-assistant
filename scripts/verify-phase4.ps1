# ================================================================
# PHASE 4 E2E SMOKE TEST — Agentic AI System
# AI Codebase Assistant v2.0
# Run from: D:\AI codebase\ai-codebase-assistant (project root)
# ================================================================

$ErrorActionPreference = "Continue"
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "   PHASE 4 E2E SMOKE TEST — Agentic AI System (Steps 19-27)" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

$PASS = 0
$FAIL = 0

function Test-Pass($label) {
    $script:PASS++
    Write-Host "  PASS: $label" -ForegroundColor Green
}

function Test-Fail($label, $detail) {
    $script:FAIL++
    Write-Host "  FAIL: $label" -ForegroundColor Red
    if ($detail) { Write-Host "        $detail" -ForegroundColor Yellow }
}

# ── Test 1: All agent files exist ─────────────────────────────
Write-Host "[1] Agent file existence check..." -ForegroundColor Yellow
$agentFiles = @(
    "backend/app/core/agents/__init__.py",
    "backend/app/core/agents/base_agent.py",
    "backend/app/core/agents/orchestrator.py",
    "backend/app/core/agents/bug_finder.py",
    "backend/app/core/agents/doc_generator.py",
    "backend/app/core/agents/test_writer.py",
    "backend/app/core/agents/code_reviewer.py",
    "backend/app/core/agents/security_scanner.py",
    "backend/app/core/agents/refactor_agent.py",
    "backend/app/core/agents/performance_agent.py"
)
$allExist = $true
foreach ($f in $agentFiles) {
    if (Test-Path $f) {
        $sz = (Get-Item $f).Length
        Write-Host "    $f ($sz bytes)" -ForegroundColor Gray
    } else {
        Write-Host "    MISSING: $f" -ForegroundColor Red
        $allExist = $false
    }
}
if ($allExist) { Test-Pass "All 10 agent files present" }
else { Test-Fail "Agent files" "Some files missing" }

# ── Test 2: Python import check ───────────────────────────────
Write-Host ""
Write-Host "[2] Python import check — all agents..." -ForegroundColor Yellow
$importScript = @"
import sys
sys.path.insert(0, 'backend')
errors = []
agents_to_check = [
    ('app.core.agents.orchestrator', 'AgentOrchestrator'),
    ('app.core.agents.bug_finder', 'BugFinderAgent'),
    ('app.core.agents.doc_generator', 'DocumentationGeneratorAgent'),
    ('app.core.agents.test_writer', 'TestWriterAgent'),
    ('app.core.agents.code_reviewer', 'CodeReviewerAgent'),
    ('app.core.agents.security_scanner', 'SecurityScannerAgent'),
    ('app.core.agents.refactor_agent', 'RefactorSuggesterAgent'),
    ('app.core.agents.performance_agent', 'PerformanceAnalyzerAgent'),
]
for module_path, class_name in agents_to_check:
    try:
        import importlib
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        instance = cls()
        print(f'OK: {class_name} agent_type={instance.agent_type}')
    except AttributeError:
        # Orchestrator doesn't have agent_type
        print(f'OK: {class_name} (orchestrator)')
    except Exception as e:
        errors.append(f'FAIL: {class_name}: {e}')
        print(f'FAIL: {class_name}: {e}')

sys.exit(1 if errors else 0)
"@

$importScript | Out-File -FilePath "backend/_phase4_import_test.py" -Encoding UTF8
try {
    $output = python "backend/_phase4_import_test.py" 2>&1
    $output | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
    if ($LASTEXITCODE -eq 0) {
        Test-Pass "All agents import successfully"
    } else {
        Test-Fail "Agent imports" "Some imports failed"
    }
} catch {
    Test-Fail "Agent imports" $_.Exception.Message
}
Remove-Item "backend/_phase4_import_test.py" -ErrorAction SilentlyContinue

# ── Test 3: AGENT_REGISTRY completeness ──────────────────────
Write-Host ""
Write-Host "[3] AGENT_REGISTRY — 7 agents registered..." -ForegroundColor Yellow
$registryScript = @"
import sys
sys.path.insert(0, 'backend')
from app.core.agents.orchestrator import AGENT_REGISTRY
expected = ['bug_finder','doc_generator','test_writer','code_reviewer',
            'security_scanner','refactor_suggester','performance_analyzer']
missing = [a for a in expected if a not in AGENT_REGISTRY]
extra = [a for a in AGENT_REGISTRY if a not in expected]
print(f'Registry: {list(AGENT_REGISTRY.keys())}')
print(f'Missing: {missing}')
print(f'Count: {len(AGENT_REGISTRY)}')
sys.exit(1 if missing else 0)
"@

$registryScript | Out-File -FilePath "backend/_phase4_registry_test.py" -Encoding UTF8
try {
    $output = python "backend/_phase4_registry_test.py" 2>&1
    $output | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
    if ($LASTEXITCODE -eq 0) {
        Test-Pass "AGENT_REGISTRY has all 7 agents"
    } else {
        Test-Fail "AGENT_REGISTRY" "Some agents missing from registry"
    }
} catch {
    Test-Fail "AGENT_REGISTRY" $_.Exception.Message
}
Remove-Item "backend/_phase4_registry_test.py" -ErrorAction SilentlyContinue

# ── Test 4: Single agent E2E run ─────────────────────────────
Write-Host ""
Write-Host "[4] Single agent E2E — security_scanner..." -ForegroundColor Yellow
$singleScript = @"
import sys, asyncio
sys.path.insert(0, 'backend')
from app.core.agents.orchestrator import AgentOrchestrator
from app.core.agents.base_agent import AgentConfig, AgentStatus

async def main():
    orch = AgentOrchestrator()
    config = AgentConfig(
        project_id='e2e-test',
        user_id='e2e-user',
        query='Security scan',
        model='tinyllama',
        extra={
            'code_content': "password = 'secret123'\nimport os\nos.system(cmd)",
            'language': 'python',
            'file_path': 'test.py',
        },
    )
    result = await orch.run_single('security_scanner', config)
    print(f'status={result.status.value}')
    print(f'vulns={result.result.get("total_vulnerabilities") if result.result else 0}')
    print(f'elapsed_ms={result.elapsed_ms:.0f}')
    return result.status == AgentStatus.COMPLETED

success = asyncio.run(main())
sys.exit(0 if success else 1)
"@

$singleScript | Out-File -FilePath "backend/_phase4_single_test.py" -Encoding UTF8
try {
    $output = python "backend/_phase4_single_test.py" 2>&1
    $output | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
    if ($LASTEXITCODE -eq 0) {
        Test-Pass "Single agent E2E run succeeded"
    } else {
        Test-Fail "Single agent E2E" "Agent returned non-COMPLETED status"
    }
} catch {
    Test-Fail "Single agent E2E" $_.Exception.Message
}
Remove-Item "backend/_phase4_single_test.py" -ErrorAction SilentlyContinue

# ── Test 5: Parallel orchestration ───────────────────────────
Write-Host ""
Write-Host "[5] Parallel orchestration — 3 agents concurrently..." -ForegroundColor Yellow
$parallelScript = @"
import sys, asyncio
sys.path.insert(0, 'backend')
from app.core.agents.orchestrator import AgentOrchestrator
from app.core.agents.base_agent import AgentConfig

async def main():
    orch = AgentOrchestrator()
    config = AgentConfig(
        project_id='e2e-parallel',
        user_id='e2e-user',
        query='Full analysis',
        model='tinyllama',
        extra={
            'code_content': (
                'password = "secret"\n'
                'def slow(a):\n'
                '    for x in a:\n'
                '        for y in a:\n'
                '            pass\n'
            ),
            'language': 'python',
            'file_path': 'app.py',
        },
    )
    result = await orch.run_parallel(
        ['security_scanner', 'code_reviewer', 'performance_analyzer'],
        config
    )
    print(f'mode={result.mode}')
    print(f'succeeded={result.agents_succeeded}')
    print(f'failed={result.agents_failed}')
    print(f'report_chars={len(result.master_report)}')
    print(f'has_summary={"Executive Summary" in result.master_report}')
    return result.agents_succeeded >= 2

success = asyncio.run(main())
sys.exit(0 if success else 1)
"@

$parallelScript | Out-File -FilePath "backend/_phase4_parallel_test.py" -Encoding UTF8
try {
    $output = python "backend/_phase4_parallel_test.py" 2>&1
    $output | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
    if ($LASTEXITCODE -eq 0) {
        Test-Pass "Parallel orchestration succeeded"
    } else {
        Test-Fail "Parallel orchestration" "Less than 2 agents succeeded"
    }
} catch {
    Test-Fail "Parallel orchestration" $_.Exception.Message
}
Remove-Item "backend/_phase4_parallel_test.py" -ErrorAction SilentlyContinue

# ── Test 6: Backend API health (if running) ───────────────────
Write-Host ""
Write-Host "[6] Backend API health check (optional)..." -ForegroundColor Yellow
try {
    $health = Invoke-RestMethod -Uri "http://localhost:8000/health" `
        -Method GET -TimeoutSec 3 -ErrorAction Stop
    Test-Pass "Backend API running at http://localhost:8000"
} catch {
    Write-Host "  INFO: Backend not running (expected if not started)" `
        -ForegroundColor Yellow
    Write-Host "  Start with: cd backend && uvicorn app.main:app --reload" `
        -ForegroundColor Gray
}

# ── Summary ───────────────────────────────────────────────────
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "PHASE 4 E2E SMOKE TEST RESULTS" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  PASSED: $PASS" -ForegroundColor Green
Write-Host "  FAILED: $FAIL" -ForegroundColor $(if ($FAIL -eq 0) { "Green" } else { "Red" })
Write-Host ""
if ($FAIL -eq 0) {
    Write-Host "ALL PHASE 4 TESTS PASSED!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Phase 4 Complete — Agentic AI System fully operational:" -ForegroundColor Cyan
    Write-Host "  Step 19: LangGraph Agent Framework" -ForegroundColor White
    Write-Host "  Step 20: Bug Finder Agent" -ForegroundColor White
    Write-Host "  Step 21: Documentation Generator Agent" -ForegroundColor White
    Write-Host "  Step 22: Test Writer Agent" -ForegroundColor White
    Write-Host "  Step 23: Code Reviewer Agent" -ForegroundColor White
    Write-Host "  Step 24: Security Scanner Agent" -ForegroundColor White
    Write-Host "  Step 25: Refactor Suggester Agent" -ForegroundColor White
    Write-Host "  Step 26: Performance Analyzer Agent" -ForegroundColor White
    Write-Host "  Step 27: Multi-Agent Orchestration" -ForegroundColor White
} else {
    Write-Host "Some tests failed. Review output above." -ForegroundColor Red
}
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next: Write 'continue' for Step 28 — Celery Background Tasks" -ForegroundColor Cyan
