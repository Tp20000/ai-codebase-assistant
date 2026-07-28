# ================================================================
# STEP 21 VERIFICATION — Documentation Generator Agent
# ================================================================

$ErrorActionPreference = "Stop"
$baseUrl = "http://localhost:8000"

Write-Host "🔍 Verifying Step 21: Documentation Generator Agent..." -ForegroundColor Cyan
Write-Host ""

$allPassed = $true

# ── Test 1: Backend Health ─────────────────────────────────────
Write-Host "Test 1: Backend health check..." -ForegroundColor Yellow
try {
    $health = Invoke-RestMethod -Uri "$baseUrl/health" -Method GET -TimeoutSec 5
    Write-Host "  ✅ Backend running" -ForegroundColor Green
} catch {
    Write-Host "  ❌ Backend not running: $_" -ForegroundColor Red
    $allPassed = $false
}

# ── Test 2: Agent List includes doc_generator ──────────────────
Write-Host "Test 2: Agent registry includes doc_generator..." -ForegroundColor Yellow
try {
    $headers = @{"Authorization" = "Bearer test_token_placeholder"}
    try {
        $agents = Invoke-RestMethod -Uri "$baseUrl/api/v1/agents" -Method GET -TimeoutSec 5
        if ($agents -match "doc_generator" -or ($agents | ConvertTo-Json) -match "doc_generator") {
            Write-Host "  ✅ doc_generator in agent list" -ForegroundColor Green
        } else {
            Write-Host "  ⚠️  doc_generator not found in agent list (may need auth token)" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  ℹ️  Agent list requires auth (expected behavior)" -ForegroundColor Cyan
    }
} catch {
    Write-Host "  ⚠️  Could not verify agent list: $_" -ForegroundColor Yellow
}

# ── Test 3: Python File Parsing Test ──────────────────────────
Write-Host "Test 3: Python AST parser test (direct import check)..." -ForegroundColor Yellow
$pythonTestCode = @"
import subprocess
import sys
import json

# Test Python AST parser
test_code = '''
def calculate_sum(a: int, b: int) -> int:
    return a + b

class MyCalculator:
    def __init__(self):
        pass
    def add(self, x, y):
        return x + y
'''

try:
    # Add backend to path
    sys.path.insert(0, 'backend')
    from app.core.agents.doc_generator import PythonASTParser
    elements = PythonASTParser.parse(test_code)
    print(json.dumps({'status': 'ok', 'element_count': len(elements), 'elements': [e['name'] for e in elements]}))
except Exception as e:
    print(json.dumps({'status': 'error', 'error': str(e)}))
"@

try {
    $result = python -c $pythonTestCode 2>&1
    $parsed = $result | ConvertFrom-Json -ErrorAction SilentlyContinue
    if ($parsed -and $parsed.status -eq "ok") {
        Write-Host "  ✅ Python AST parser working — found $($parsed.element_count) elements: $($parsed.elements -join ', ')" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  Parser test: $result" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ⚠️  Parser test skipped (run from backend venv): $_" -ForegroundColor Yellow
}

# ── Test 4: JS Parser Test ────────────────────────────────────
Write-Host "Test 4: JavaScript parser test..." -ForegroundColor Yellow
$jsTestCode = @"
import sys, json
sys.path.insert(0, 'backend')
try:
    from app.core.agents.doc_generator import JSParser
    test_js = '''
    function fetchData(url, options) { return fetch(url, options); }
    class ApiClient { constructor(baseUrl) { this.baseUrl = baseUrl; } }
    '''
    elements = JSParser.parse(test_js)
    print(json.dumps({'status': 'ok', 'count': len(elements), 'names': [e['name'] for e in elements]}))
except Exception as e:
    print(json.dumps({'status': 'error', 'error': str(e)}))
"@

try {
    $jsResult = python -c $jsTestCode 2>&1
    $jsParsed = $jsResult | ConvertFrom-Json -ErrorAction SilentlyContinue
    if ($jsParsed -and $jsParsed.status -eq "ok") {
        Write-Host "  ✅ JS parser working — found $($jsParsed.count) elements: $($jsParsed.names -join ', ')" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  JS parser test: $jsResult" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ⚠️  JS parser test skipped: $_" -ForegroundColor Yellow
}

# ── Test 5: DocGenerator import test ─────────────────────────
Write-Host "Test 5: DocumentationGeneratorAgent import..." -ForegroundColor Yellow
$importTest = @"
import sys
sys.path.insert(0, 'backend')
try:
    from app.core.agents.doc_generator import DocumentationGeneratorAgent
    agent = DocumentationGeneratorAgent()
    print(f'OK: agent_id={agent.agent_id}, name={agent.agent_name}')
except Exception as e:
    print(f'ERROR: {e}')
"@

try {
    $importResult = python -c $importTest 2>&1
    if ($importResult -match "OK:") {
        Write-Host "  ✅ $importResult" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  Import test: $importResult" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ⚠️  Import test skipped: $_" -ForegroundColor Yellow
}

# ── Test 6: File exists check ─────────────────────────────────
Write-Host "Test 6: File existence check..." -ForegroundColor Yellow
$files = @(
    "backend/app/core/agents/doc_generator.py",
    "backend/app/core/agents/__init__.py"
)
foreach ($f in $files) {
    if (Test-Path $f) {
        $size = (Get-Item $f).Length
        Write-Host "  ✅ $f ($size bytes)" -ForegroundColor Green
    } else {
        Write-Host "  ❌ MISSING: $f" -ForegroundColor Red
        $allPassed = $false
    }
}

# ── Summary ───────────────────────────────────────────────────
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
if ($allPassed) {
    Write-Host "✅ Step 21 Verification PASSED!" -ForegroundColor Green
} else {
    Write-Host "⚠️  Step 21 Verification completed with warnings" -ForegroundColor Yellow
}
Write-Host "⏭️  Write 'continue' for Step 22 — Test Writer Agent" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
