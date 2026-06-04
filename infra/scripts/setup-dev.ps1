# PariKrama — Dev Setup Script (Windows PowerShell)
# Usage: .\infra\scripts\setup-dev.ps1

Write-Host "🚀 Setting up PariKrama development environment..." -ForegroundColor Cyan

# check prerequisites
$prereqs = @("docker", "uv", "node")
foreach ($cmd in $prereqs) {
    if (!(Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Host "❌ $cmd is not installed. Please install it first." -ForegroundColor Red
        exit 1
    }
}
Write-Host "✅ All prerequisites found" -ForegroundColor Green

# create .env from example if it doesn't exist
if (!(Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "✅ Created .env from .env.example — edit it with your API keys" -ForegroundColor Green
} else {
    Write-Host "ℹ️  .env already exists, skipping" -ForegroundColor Yellow
}

# install Python dependencies
Write-Host "📦 Installing Python dependencies..." -ForegroundColor Cyan
uv sync --all-packages --group dev
Write-Host "✅ Python dependencies installed" -ForegroundColor Green

# install pre-commit hooks
Write-Host "🔧 Installing pre-commit hooks..." -ForegroundColor Cyan
uv run pre-commit install
Write-Host "✅ Pre-commit hooks installed" -ForegroundColor Green

# start Docker services
Write-Host "🐳 Starting Docker services..." -ForegroundColor Cyan
docker compose -f infra/docker/docker-compose.yml up -d
Write-Host "✅ Docker services started" -ForegroundColor Green

# create data directories
New-Item -ItemType Directory -Path "data/knowledge_base" -Force | Out-Null
New-Item -ItemType Directory -Path "data/models" -Force | Out-Null
Write-Host "✅ Data directories created" -ForegroundColor Green

# wait for postgres
Write-Host "⏳ Waiting for PostgreSQL..." -ForegroundColor Cyan
$retries = 0
while ($retries -lt 30) {
    $result = docker exec parikrama-postgres pg_isready -U parikrama 2>&1
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 1
    $retries++
}
Write-Host "✅ PostgreSQL ready" -ForegroundColor Green

Write-Host ""
Write-Host "🎉 Setup complete! Next steps:" -ForegroundColor Green
Write-Host "  1. Edit .env with your API keys (GEMINI_API_KEY, GROQ_API_KEY)" -ForegroundColor White
Write-Host "  2. Run: make backend     (start FastAPI)" -ForegroundColor White
Write-Host "  3. Visit: http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
