# ================================================================
# E2E Test Runner — Playwright
# AI Codebase Assistant v2.0
# Run from: project root (ai-codebase-assistant/)
# Prerequisites: Backend on :8000, Frontend on :5173
# ================================================================

param(
    [switch]$Headed,
    [switch]$Debug,
    [string]$Filter = ""
)

$FRONTEND = "http://localhost:5173"
$BACKEND  = "http://localhost:8000"

Write-Host ""
Write-Host "================================================" -ForegroundColor Magenta
Write-Host " PLAYWRIGHT E2E TEST RUNNER" -ForegroundColor Magenta
Write-Host " Frontend: $FRONTEND" -ForegroundColor Gray
Write-Host " Backend:  $BACKEND" -ForegroundColor Gray
Write-Host "================================================" -ForegroundColor Magenta

# Check services
Write-Host "`nChecking services..." -ForegroundColor Yellow
try {
    $r = Invoke-RestMethod -Uri "$BACKEND/api/v1/health/" -TimeoutSec 5
    Write-Host "  Backend: $($r.status)" -ForegroundColor Green
} catch {
    Write-Host "  Backend: NOT RESPONDING" -ForegroundColor Red
    Write-Host "  Run: docker-compose up" -ForegroundColor Yellow
    exit 1
}

try {
    $r = Invoke-WebRequest -Uri $FRONTEND -TimeoutSec 5 -UseBasicParsing
    Write-Host "  Frontend: $($r.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "  Frontend: NOT RESPONDING" -ForegroundColor Red
    Write-Host "  Run: cd frontend && npm run dev" -ForegroundColor Yellow
    exit 1
}

Write-Host "`nRunning E2E tests..." -ForegroundColor Cyan

Set-Location frontend

$args = @("playwright", "test")

if ($Headed)  { $args += "--headed" }
if ($Debug)   { $args += "--debug" }
if ($Filter)  { $args += "--grep", $Filter }

npx @args

$exitCode = $LASTEXITCODE
Set-Location ..

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "ALL E2E TESTS PASSED" -ForegroundColor Green
} else {
    Write-Host "SOME E2E TESTS FAILED (exit: $exitCode)" -ForegroundColor Red
    Write-Host "View report: cd frontend && npx playwright show-report" -ForegroundColor Yellow
}

exit $exitCode