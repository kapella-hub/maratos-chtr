#
# MaratOS Installer for Windows
# Usage: irm https://raw.githubusercontent.com/yourusername/maratos/main/install.ps1 | iex
#

$ErrorActionPreference = "Stop"

# Colors
function Write-Info { Write-Host "[INFO] $args" -ForegroundColor Blue }
function Write-Success { Write-Host "[✓] $args" -ForegroundColor Green }
function Write-Warn { Write-Host "[!] $args" -ForegroundColor Yellow }
function Write-Err { Write-Host "[✗] $args" -ForegroundColor Red; exit 1 }

function Write-Banner {
    Write-Host ""
    Write-Host "  __  __                 _    ___  ____  " -ForegroundColor Blue
    Write-Host " |  \/  | __ _ _ __ __ _| |_ / _ \/ ___| " -ForegroundColor Blue
    Write-Host " | |\/| |/ _`` | '__/ _`` | __| | | \___ \ " -ForegroundColor Blue
    Write-Host " | |  | | (_| | | | (_| | |_| |_| |___) |" -ForegroundColor Blue
    Write-Host " |_|  |_|\__,_|_|  \__,_|\__|\___/|____/ " -ForegroundColor Blue
    Write-Host ""
    Write-Host "  Your AI Operating System - Powered by MO" -ForegroundColor Cyan
    Write-Host ""
}

Write-Banner

$InstallDir = if ($env:MARATOS_DIR) { $env:MARATOS_DIR } else { "$env:USERPROFILE\.maratos" }
Write-Info "Installing to: $InstallDir"
Write-Host ""

# === Check Prerequisites ===
Write-Info "Checking prerequisites..."

# Python
try {
    $pyVersion = python --version 2>&1
    Write-Success "Python $pyVersion"
} catch {
    Write-Err "Python not found. Install from https://python.org"
}

# Node.js
try {
    $nodeVersion = node --version 2>&1
    Write-Success "Node.js $nodeVersion"
} catch {
    Write-Err "Node.js not found. Install from https://nodejs.org"
}

# npm
try {
    $npmVersion = npm --version 2>&1
    Write-Success "npm $npmVersion"
} catch {
    Write-Err "npm not found"
}

# Git
$hasGit = $false
try {
    git --version | Out-Null
    Write-Success "git found"
    $hasGit = $true
} catch {
    Write-Warn "git not found (will try alternative download)"
}

Write-Host ""

# === Download/Clone MaratOS ===
if (Test-Path $InstallDir) {
    Write-Warn "Directory exists: $InstallDir"
    $confirm = Read-Host "Overwrite? [y/N]"
    if ($confirm -eq "y" -or $confirm -eq "Y") {
        Remove-Item -Recurse -Force $InstallDir
    } else {
        Write-Err "Installation cancelled"
    }
}

Write-Info "Downloading MaratOS..."
if ($hasGit) {
    git clone --depth 1 https://github.com/yourusername/maratos.git $InstallDir 2>$null
    if (-not $?) {
        # Fallback: copy from current directory
        if (Test-Path ".\backend\app\main.py") {
            Write-Info "Copying from local directory..."
            Copy-Item -Recurse . $InstallDir
        } else {
            Write-Err "Could not download MaratOS"
        }
    }
} else {
    # Download as ZIP
    $zipUrl = "https://github.com/yourusername/maratos/archive/main.zip"
    $zipPath = "$env:TEMP\maratos.zip"
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath
    Expand-Archive -Path $zipPath -DestinationPath $env:TEMP -Force
    Move-Item "$env:TEMP\maratos-main" $InstallDir
    Remove-Item $zipPath
}
Write-Success "Downloaded"

Set-Location $InstallDir

# === Setup Backend ===
Write-Info "Setting up backend..."
Set-Location backend

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e . --quiet

Write-Success "Backend ready"

Set-Location ..

# === Setup Frontend ===
Write-Info "Setting up frontend..."
Set-Location frontend
npm install --silent
Write-Success "Frontend ready"

Set-Location ..

# === Create Launcher Script ===
Write-Info "Creating launcher..."

$startScript = @'
@echo off
cd /d "%~dp0"

REM Load .env if exists
if exist .env (
    for /f "tokens=*" %%a in (.env) do (
        set "%%a"
    )
)

REM Check for API key
if "%MARATOS_ANTHROPIC_API_KEY%"=="" (
    if "%ANTHROPIC_API_KEY%"=="" (
        echo.
        echo [!] No API key found!
        echo Set MARATOS_ANTHROPIC_API_KEY in .env
        echo.
        set /p API_KEY="Enter your Anthropic API key: "
        echo MARATOS_ANTHROPIC_API_KEY=%API_KEY%>> .env
        set MARATOS_ANTHROPIC_API_KEY=%API_KEY%
    ) else (
        set MARATOS_ANTHROPIC_API_KEY=%ANTHROPIC_API_KEY%
    )
)

echo.
echo  Starting MaratOS...
echo.

REM Start backend
start "MaratOS Backend" cmd /c "cd backend && .venv\Scripts\activate && python run.py"

REM Wait for backend
timeout /t 3 /nobreak > nul

REM Start frontend
start "MaratOS Frontend" cmd /c "cd frontend && npm run dev"

echo.
echo  MaratOS is running!
echo    Frontend: http://localhost:5173
echo    Backend:  http://localhost:8000
echo.
echo  Close this window to stop MaratOS
pause
taskkill /fi "WINDOWTITLE eq MaratOS*" /f > nul 2>&1
'@

$startScript | Out-File -FilePath "$InstallDir\start.bat" -Encoding ASCII

# Create PowerShell launcher too
$psScript = @'
# MaratOS Launcher
$ErrorActionPreference = "SilentlyContinue"
Set-Location $PSScriptRoot

# Load .env
if (Test-Path .env) {
    Get-Content .env | ForEach-Object {
        if ($_ -match "^([^#][^=]+)=(.*)$") {
            [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
        }
    }
}

# Check API key
if (-not $env:MARATOS_ANTHROPIC_API_KEY -and -not $env:ANTHROPIC_API_KEY) {
    Write-Host "`n[!] No API key found!" -ForegroundColor Yellow
    $key = Read-Host "Enter your Anthropic API key"
    Add-Content .env "MARATOS_ANTHROPIC_API_KEY=$key"
    $env:MARATOS_ANTHROPIC_API_KEY = $key
}
if (-not $env:MARATOS_ANTHROPIC_API_KEY) {
    $env:MARATOS_ANTHROPIC_API_KEY = $env:ANTHROPIC_API_KEY
}

Write-Host "`n  Starting MaratOS..." -ForegroundColor Cyan

# Start backend
$backend = Start-Process -FilePath "cmd" -ArgumentList "/c cd backend && .venv\Scripts\activate && python run.py" -PassThru -WindowStyle Hidden

Start-Sleep 3

# Start frontend  
$frontend = Start-Process -FilePath "cmd" -ArgumentList "/c cd frontend && npm run dev" -PassThru -WindowStyle Hidden

Write-Host ""
Write-Host "  MaratOS is running!" -ForegroundColor Green
Write-Host "    Frontend: http://localhost:5173"
Write-Host "    Backend:  http://localhost:8000"
Write-Host ""

# Open browser
Start-Process "http://localhost:5173"

Write-Host "Press Enter to stop MaratOS..."
Read-Host

$backend | Stop-Process -Force
$frontend | Stop-Process -Force
'@

$psScript | Out-File -FilePath "$InstallDir\Start-MaratOS.ps1" -Encoding UTF8

# === Create .env template ===
if (-not (Test-Path "$InstallDir\.env")) {
    @"
# MaratOS Configuration
# Get your API key from: https://console.anthropic.com/

MARATOS_ANTHROPIC_API_KEY=
# MARATOS_OPENAI_API_KEY=
# MARATOS_DEFAULT_MODEL=claude-sonnet-4-20250514
"@ | Out-File -FilePath "$InstallDir\.env" -Encoding UTF8
}

# === Create Desktop Shortcut ===
$shortcutPath = "$env:USERPROFILE\Desktop\MaratOS.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-ExecutionPolicy Bypass -File `"$InstallDir\Start-MaratOS.ps1`""
$shortcut.WorkingDirectory = $InstallDir
$shortcut.Description = "Start MaratOS"
$shortcut.Save()
Write-Success "Created desktop shortcut"

# === Done! ===
Write-Host ""
Write-Host "════════════════════════════════════════" -ForegroundColor Green
Write-Host "  MaratOS installed successfully!  " -ForegroundColor Green
Write-Host "════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host ""
Write-Host "  1. Add your Anthropic API key:"
Write-Host "     notepad $InstallDir\.env" -ForegroundColor Blue
Write-Host ""
Write-Host "  2. Start MaratOS:"
Write-Host "     Double-click 'MaratOS' on your Desktop" -ForegroundColor Blue
Write-Host "     Or run: $InstallDir\start.bat" -ForegroundColor Blue
Write-Host ""
Write-Host "  3. Open http://localhost:5173"
Write-Host ""
Write-Host "MO is ready to help! " -ForegroundColor Cyan
