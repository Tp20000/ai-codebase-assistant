Set-Location "D:\AI codebase\ai-codebase-assistant"
Write-Host "=== Step 20 Verify ===" -ForegroundColor Cyan
$base = "http://localhost:8000/api/v1"
try {
    $types = Invoke-RestMethod -Uri "$base/agents/types"
    Write-Host "Agents: $($types.Count)" -ForegroundColor Green
    $types | ForEach-Object { Write-Host "  $($_.type)" -ForegroundColor Cyan }
    $bf = $types | Where-Object { $_.type -eq "bug_finder" }
    if ($bf) { Write-Host "PASS: bug_finder OK" -ForegroundColor Green }
    else { Write-Host "WARN: restart backend" -ForegroundColor Yellow }
} catch { Write-Host "Error: $_" -ForegroundColor Red }
