# ================================================================
# Start Celery Worker
# AI Codebase Assistant v2.0
# Run from: backend/ directory with venv activated
# ================================================================

Write-Host "Starting Celery worker..." -ForegroundColor Cyan
Write-Host "Queue: default, low, high" -ForegroundColor Gray
Write-Host "Press Ctrl+C to stop" -ForegroundColor Gray
Write-Host ""

# Start the worker with all queues
celery -A app.tasks.celery_app:celery_app worker `
    --queues=high,default,low `
    --concurrency=2 `
    --loglevel=info `
    --hostname=worker@%h
