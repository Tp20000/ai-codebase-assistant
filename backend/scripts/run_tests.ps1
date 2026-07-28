# ================================================================
# Backend Test Runner
# AI Codebase Assistant v2.0
# Run from: ai-codebase-assistant/
# ================================================================

param(
    [string]$Filter = "",
    [switch]$Coverage,
    [switch]$UnitOnly,
    [switch]$Verbose
)

$CONTAINER = "ai-backend"

Write-Host ""
Write-Host "================================================" -ForegroundColor Magenta
Write-Host " BACKEND TEST RUNNER" -ForegroundColor Magenta
Write-Host "================================================" -ForegroundColor Magenta

# Build pytest command
$cmd = "cd /app && python -m pytest tests/"

if ($UnitOnly) {
    $cmd += " -m unit"
    Write-Host " Mode: Unit tests only" -ForegroundColor Yellow
}

if ($Filter) {
    $cmd += " -k `"$Filter`""
    Write-Host " Filter: $Filter" -ForegroundColor Yellow
}

if ($Coverage) {
    $cmd += " --cov=app --cov-report=term-missing --cov-fail-under=60"
    Write-Host " Coverage: enabled (60% minimum)" -ForegroundColor Yellow
}

if ($Verbose) {
    $cmd += " -vv"
}

Write-Host ""
Write-Host "Running: $cmd" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Magenta
Write-Host ""

docker exec -it $CONTAINER bash -c $cmd

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "ALL TESTS PASSED" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "SOME TESTS FAILED (exit code: $LASTEXITCODE)" -ForegroundColor Red
}