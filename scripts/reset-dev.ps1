param([switch]$Force)
if (-not $Force) {
    $c = Read-Host "Delete all Docker volumes? Type 'yes' to confirm"
    if ($c -ne 'yes') { exit 0 }
}
docker-compose down -v --remove-orphans
Get-ChildItem -Path "backend" -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "Reset complete." -ForegroundColor Green
