# Start all development services
Write-Host "Starting AI Codebase Assistant..." -ForegroundColor Cyan

try { docker info | Out-Null }
catch { Write-Host "Docker not running. Start Docker Desktop first." -ForegroundColor Red; exit 1 }

docker-compose up -d postgres redis chromadb
Write-Host "Waiting 15s for databases..." -ForegroundColor Yellow
Start-Sleep 15

docker-compose up -d ollama backend celery_worker frontend

Write-Host ""
Write-Host "All services started!" -ForegroundColor Green
Write-Host "Frontend:   http://localhost:5173" -ForegroundColor White
Write-Host "Backend:    http://localhost:8000" -ForegroundColor White
Write-Host "API Docs:   http://localhost:8000/docs" -ForegroundColor White
Write-Host "ChromaDB:   http://localhost:8001" -ForegroundColor White
Write-Host "Ollama:     http://localhost:11434" -ForegroundColor White
