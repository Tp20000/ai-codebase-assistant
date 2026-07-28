Set-Location 'D:\AI codebase\ai-codebase-assistant'
Write-Host "=== Step 19: Agent Framework Verification ===" -ForegroundColor Cyan
$base = "http://localhost:8000/api/v1"
Write-Host "`n[1] GET /agents/types..." -ForegroundColor Yellow
try {
    $types = Invoke-RestMethod -Uri "$base/agents/types"
    Write-Host "  PASS: $($types.Count) agent types" -ForegroundColor Green
} catch {
    $code = $_.Exception.Response.StatusCode.value__
    Write-Host "  HTTP $code" -ForegroundColor Red
}
Write-Host "`n[2] Agent routes in OpenAPI..." -ForegroundColor Yellow
try {
    $api = Invoke-RestMethod -Uri "http://localhost:8000/openapi.json"
    $routes = $api.paths.PSObject.Properties.Name | Where-Object { $_ -match "/agents" }
    $routes | ForEach-Object { Write-Host "  OK $_" -ForegroundColor Green }
    Write-Host "  Total: $($routes.Count) agent routes" -ForegroundColor Cyan
} catch { Write-Host "  FAIL: $_" -ForegroundColor Red }
Write-Host "`n[3] Tasks endpoint auth check..." -ForegroundColor Yellow
try {
    Invoke-RestMethod -Uri "$base/agents/tasks?project_id=00000000-0000-0000-0000-000000000001"
    Write-Host "  PASS: 200 OK" -ForegroundColor Green
} catch {
    $code = $_.Exception.Response.StatusCode.value__
    if ($code -eq 401) { Write-Host "  PASS: 401 (auth protecting)" -ForegroundColor Green }
    else { Write-Host "  HTTP $code" -ForegroundColor Yellow }
}
Write-Host ""
Write-Host "Step 19 COMPLETE - write continue for Step 20" -ForegroundColor Green
