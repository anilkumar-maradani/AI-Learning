# setup.ps1 — one-shot Windows setup for PolicyLens
# Usage (from the project folder):  .\setup.ps1
# If scripts are blocked:           powershell -ExecutionPolicy Bypass -File .\setup.ps1

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment (.venv)..." -ForegroundColor Cyan
    python -m venv .venv
}

Write-Host "Installing dependencies (torch is large — this can take several minutes)..." -ForegroundColor Cyan
.\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env — open it and paste your Groq API key." -ForegroundColor Yellow
}

Write-Host "Building the vector index..." -ForegroundColor Cyan
.\.venv\Scripts\python.exe src\ingest.py

Write-Host ""
Write-Host "Done. Next steps:" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "  python chat.py                       # interactive console"
Write-Host "  python src\evaluate_w4.py --strategy both   # retrieval eval"
Write-Host "  python run_all.py                    # full report -> results.md"
