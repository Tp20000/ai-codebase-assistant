# ================================================================
# STEP 17 — Verification Script
# Run from project root AFTER backend is running
# ================================================================
Set-Location "D:\AI codebase\ai-codebase-assistant"
Write-Host "=== Step 17: Chat History Verification ===" -ForegroundColor Cyan
$base = "http://localhost:8000/api/v1"

# 1. Check history routes in OpenAPI
Write-Host "
[1/4] History routes in OpenAPI..." -ForegroundColor Yellow
try {
    $api = Invoke-RestMethod -Uri "http://localhost:8000/openapi.json"
    $histRoutes = $api.paths.PSObject.Properties.Name | Where-Object { $_ -match "history" }
    if ($histRoutes) {
        $histRoutes | ForEach-Object { Write-Host "  ✅ $_" -ForegroundColor Green }
    } else {
        Write-Host "  ❌ No history routes found" -ForegroundColor Red
    }
} catch { Write-Host "  ❌ $_" -ForegroundColor Red }

# 2. Auth protection check
Write-Host "
[2/4] Auth protection on history endpoints..." -ForegroundColor Yellow
try {
    Invoke-RestMethod -Uri "$base/history/sessions?project_id=00000000-0000-0000-0000-000000000001"
    Write-Host "  ⚠️  Got 200 without auth" -ForegroundColor Yellow
} catch {
    $code = $_.Exception.Response.StatusCode.value__
    if ($code -eq 401) { Write-Host "  ✅ 401 Unauthorized (correct)" -ForegroundColor Green }
    else { Write-Host "  HTTP $code" -ForegroundColor Yellow }
}

# 3. Search endpoint auth check
Write-Host "
[3/4] Search endpoint..." -ForegroundColor Yellow
try {
    Invoke-RestMethod -Uri "$base/history/search?q=test"
    Write-Host "  ⚠️  Got 200 without auth" -ForegroundColor Yellow
} catch {
    $code = $_.Exception.Response.StatusCode.value__
    if ($code -eq 401) { Write-Host "  ✅ 401 Unauthorized (correct)" -ForegroundColor Green }
    else { Write-Host "  HTTP $code" -ForegroundColor Yellow }
}

# 4. Total route count
Write-Host "
[4/4] All registered routes..." -ForegroundColor Yellow
try {
    $api = Invoke-RestMethod -Uri "http://localhost:8000/openapi.json"
    $count = $api.paths.PSObject.Properties.Name.Count
    Write-Host "  ✅ Total API routes: $count" -ForegroundColor Green
    $api.paths.PSObject.Properties.Name | Sort-Object | ForEach-Object {
        Write-Host "    $_" -ForegroundColor Gray
    }
} catch { Write-Host "  ❌ $_" -ForegroundColor Red }

Write-Host "
✅ Step 17 verification complete!" -ForegroundColor Green
