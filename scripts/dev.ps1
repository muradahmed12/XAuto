$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Get-Command vercel -ErrorAction SilentlyContinue)) {
  Write-Host "Vercel CLI not found. Install with: npm i -g vercel" -ForegroundColor Red
  exit 1
}

if (-not (Test-Path ".env.local")) {
  if (Test-Path ".env.example") {
    Copy-Item ".env.example" ".env.local"
    Write-Host "Created .env.local from .env.example — fill in your keys before generating or publishing."
  } else {
    Write-Host "Warning: no .env.local found. Create one or run: npm run pull-env"
  }
}

if (Test-Path ".venv\Scripts\Activate.ps1") {
  . .\.venv\Scripts\Activate.ps1
} elseif (-not (Test-Path ".venv")) {
  Write-Host "Creating Python virtualenv and installing dependencies…"
  python -m venv .venv
  . .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt -q
}

Write-Host "Starting local server at http://127.0.0.1:3000 (no Vercel login required)"
python scripts/local_server.py @args
