# ================================================================
# STEP 15 — Verification Script
# Run AFTER backend is started
# ================================================================

Write-Host "Verifying Step 15: Context-Aware Prompting..." -ForegroundColor Cyan

# Test 1: Prompt types endpoint (no auth required)
Write-Host "
[1/3] GET /api/v1/prompts/types" -ForegroundColor Yellow
try {
    $types = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/prompts/types" -Method GET
    Write-Host "  Prompt types: $($types.Count)" -ForegroundColor Green
    $types | ForEach-Object { Write-Host "    - $($_.value): $($_.description)" -ForegroundColor Cyan }
} catch {
    Write-Host "  FAIL: $_" -ForegroundColor Red
}

# Test 2: Query analysis
Write-Host "
[2/3] POST /api/v1/prompts/analyze" -ForegroundColor Yellow
try {
    $body = @{ query = "find bugs in the authentication module" } | ConvertTo-Json
    $analysis = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/prompts/analyze" -Method POST -Body $body -ContentType "application/json"
    Write-Host "  Detected type: $($analysis.detected_type)" -ForegroundColor Green
    Write-Host "  Confidence:    $($analysis.confidence)" -ForegroundColor Green
    Write-Host "  Keywords:      $($analysis.keywords_matched -join ', ')" -ForegroundColor Green
} catch {
    Write-Host "  FAIL: $_" -ForegroundColor Red
}

# Test 3: Another query
Write-Host "
[3/3] POST /api/v1/prompts/analyze (security query)" -ForegroundColor Yellow
try {
    $body = @{ query = "are there any SQL injection vulnerabilities?" } | ConvertTo-Json
    $analysis = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/prompts/analyze" -Method POST -Body $body -ContentType "application/json"
    Write-Host "  Detected type: $($analysis.detected_type)" -ForegroundColor Green
    Write-Host "  Confidence:    $($analysis.confidence)" -ForegroundColor Green
    Write-Host "  Keywords:      $($analysis.keywords_matched -join ', ')" -ForegroundColor Green
} catch {
    Write-Host "  FAIL: $_" -ForegroundColor Red
}

Write-Host "
✅ Step 15 verification complete" -ForegroundColor Green
