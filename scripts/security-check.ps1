# ================================================================
# Security Verification Script - AI Codebase Assistant v2.0
# ================================================================

param(
    [string]$BackendUrl = "https://ai-codebase-backend-r721.onrender.com",
    [string]$FrontendUrl = "https://ai-codebase-assistant-git-main-tirths-projects-9c208144.vercel.app"
)

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host " Security Verification - AI Codebase Assistant v2.0" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

$passed = 0
$failed = 0
$warnings = 0

function Test-Pass { param($msg) Write-Host "  ✅ PASS: $msg" -ForegroundColor Green; $script:passed++ }
function Test-Fail { param($msg) Write-Host "  ❌ FAIL: $msg" -ForegroundColor Red; $script:failed++ }
function Test-Warn { param($msg) Write-Host "  ⚠️  WARN: $msg" -ForegroundColor Yellow; $script:warnings++ }

Write-Host "1. HTTPS Check" -ForegroundColor Yellow
if ($BackendUrl.StartsWith("https://")) { Test-Pass "Backend uses HTTPS" } else { Test-Fail "Backend not HTTPS" }
if ($FrontendUrl.StartsWith("https://")) { Test-Pass "Frontend uses HTTPS" } else { Test-Fail "Frontend not HTTPS" }

Write-Host "
2. Auth Protection Check" -ForegroundColor Yellow
try {
    Invoke-WebRequest -Uri "$BackendUrl/api/v1/projects/" -Method GET -ErrorAction Stop | Out-Null
    Test-Fail "Projects endpoint accessible without auth"
} catch {
    if ($_.Exception.Message -match "401") {
        Test-Pass "Projects endpoint protected by auth"
    } else {
        Test-Warn "Unexpected auth check response: $($_.Exception.Message)"
    }
}

Write-Host "
3. Backend Root Check" -ForegroundColor Yellow
try {
    $resp = Invoke-WebRequest -Uri "$BackendUrl/" -Method GET -ErrorAction Stop
    if ($resp.StatusCode -eq 200) {
        Test-Pass "Backend root reachable"
    } else {
        Test-Warn "Backend root returned status $($resp.StatusCode)"
    }
} catch {
    Test-Fail "Backend root failed: $($_.Exception.Message)"
}

Write-Host "
4. Frontend Reachability Check" -ForegroundColor Yellow
try {
    $resp = Invoke-WebRequest -Uri "$FrontendUrl/login" -Method GET -ErrorAction Stop
    if ($resp.StatusCode -eq 200) {
        Test-Pass "Frontend login page reachable"
    } else {
        Test-Warn "Frontend login returned status $($resp.StatusCode)"
    }
} catch {
    Test-Fail "Frontend unreachable: $($_.Exception.Message)"
}

Write-Host "
5. Malicious Path Check" -ForegroundColor Yellow
$testPaths = @(
    "$BackendUrl/api/v1/../../../etc/passwd",
    "$BackendUrl/api/v1/%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "$BackendUrl/api/v1/projects/<script>alert(1)</script>"
)
foreach ($path in $testPaths) {
    try {
        Invoke-WebRequest -Uri $path -Method GET -ErrorAction Stop | Out-Null
        Test-Warn "Malicious path did not hard-fail: $path"
    } catch {
        Test-Pass "Blocked suspicious path"
    }
}

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host " Passed:   $passed" -ForegroundColor Green
Write-Host " Warnings: $warnings" -ForegroundColor Yellow
Write-Host " Failed:   $failed" -ForegroundColor Red
Write-Host "================================================================" -ForegroundColor Cyan
