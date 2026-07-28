# ================================================================
# STEP 16 — Verification Script
# Run AFTER backend is started on port 8000
# ================================================================

Write-Host "=== Step 16: WebSocket Verification ===" -ForegroundColor Cyan
$base = "http://localhost:8000/api/v1"

# Test 1: REST health check
Write-Host "
[1/4] Backend health..." -ForegroundColor Yellow
try {
    $r = Invoke-RestMethod -Uri "http://localhost:8000/docs" -Method GET
    Write-Host "  ✅ Backend responding (docs loaded)" -ForegroundColor Green
} catch {
    Write-Host "  Backend: $($_.Exception.Response.StatusCode.value__)" -ForegroundColor Cyan
}

# Test 2: WebSocket stats endpoint
Write-Host "
[2/4] GET /api/v1/ws/stats..." -ForegroundColor Yellow
try {
    $stats = Invoke-RestMethod -Uri "$base/ws/stats" -Method GET
    Write-Host "  ✅ Stats: $($stats | ConvertTo-Json -Compress)" -ForegroundColor Green
} catch {
    Write-Host "  ❌ $_" -ForegroundColor Red
}

# Test 3: Check OpenAPI has WebSocket route
Write-Host "
[3/4] WebSocket routes in OpenAPI..." -ForegroundColor Yellow
try {
    $api = Invoke-RestMethod -Uri "http://localhost:8000/openapi.json"
    $wsPaths = $api.paths.PSObject.Properties.Name | Where-Object { $_ -match "ws|websocket" }
    if ($wsPaths) {
        $wsPaths | ForEach-Object { Write-Host "  ✅ $_" -ForegroundColor Green }
    } else {
        Write-Host "  ⚠️  No WebSocket paths in OpenAPI (expected for WS endpoints)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  ❌ $_" -ForegroundColor Red
}

# Test 4: Prompt types still work
Write-Host "
[4/4] GET /api/v1/prompts/types (regression check)..." -ForegroundColor Yellow
try {
    $types = Invoke-RestMethod -Uri "$base/prompts/types"
    Write-Host "  ✅ $($types.Count) prompt types available" -ForegroundColor Green
} catch {
    Write-Host "  ❌ $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "WebSocket endpoint: ws://localhost:8000/api/v1/ws/chat?token=JWT" -ForegroundColor Yellow
Write-Host "Stats endpoint:     http://localhost:8000/api/v1/ws/stats" -ForegroundColor Yellow
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "To test WebSocket manually (install wscat: npm install -g wscat):" -ForegroundColor Yellow
Write-Host "  wscat -c 'ws://localhost:8000/api/v1/ws/chat?token=YOUR_JWT'" -ForegroundColor Cyan
Write-Host "  Then send: {"type":"ping"}" -ForegroundColor Cyan
Write-Host "  Expect:    {"type":"pong", "server_time": ...}" -ForegroundColor Cyan
