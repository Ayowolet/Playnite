# Playnite Python Service Installation Script
# Installs Python service and dependencies

param(
    [switch]$SkipPythonCheck,
    [switch]$Dev
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Playnite Python Service Installer" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if running as administrator (optional but recommended)
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "Warning: Not running as administrator. Some operations may fail." -ForegroundColor Yellow
    Write-Host ""
}

# Step 1: Check Python installation
Write-Host "[1/5] Checking Python installation..." -ForegroundColor Green

if (-not $SkipPythonCheck) {
    try {
        $pythonVersion = python --version 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "Python not found"
        }

        Write-Host "  ✓ Python found: $pythonVersion" -ForegroundColor Green

        # Check version is 3.8+
        if ($pythonVersion -match "Python (\d+)\.(\d+)") {
            $major = [int]$matches[1]
            $minor = [int]$matches[2]

            if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 8)) {
                Write-Host "  ✗ Python version 3.8+ required, found $pythonVersion" -ForegroundColor Red
                Write-Host ""
                Write-Host "Please install Python 3.8 or later from:" -ForegroundColor Yellow
                Write-Host "  https://www.python.org/downloads/" -ForegroundColor Cyan
                exit 1
            }
        }
    }
    catch {
        Write-Host "  ✗ Python not found in PATH" -ForegroundColor Red
        Write-Host ""
        Write-Host "Please install Python 3.8+ from:" -ForegroundColor Yellow
        Write-Host "  https://www.python.org/downloads/" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "Make sure to check 'Add Python to PATH' during installation!" -ForegroundColor Yellow
        exit 1
    }
}
else {
    Write-Host "  ⊙ Skipping Python check" -ForegroundColor Yellow
}

Write-Host ""

# Step 2: Create virtual environment
Write-Host "[2/5] Creating virtual environment..." -ForegroundColor Green

$venvPath = "venv"

if (Test-Path $venvPath) {
    Write-Host "  ⊙ Virtual environment already exists" -ForegroundColor Yellow
}
else {
    python -m venv $venvPath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ✗ Failed to create virtual environment" -ForegroundColor Red
        exit 1
    }
    Write-Host "  ✓ Virtual environment created" -ForegroundColor Green
}

Write-Host ""

# Step 3: Activate virtual environment and install dependencies
Write-Host "[3/5] Installing Python dependencies..." -ForegroundColor Green

$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"

if (-not (Test-Path $activateScript)) {
    Write-Host "  ✗ Activation script not found: $activateScript" -ForegroundColor Red
    exit 1
}

# Activate and install
& $activateScript

if ($Dev) {
    Write-Host "  Installing in development mode with dev dependencies..." -ForegroundColor Cyan
    pip install -e ".[dev]"
}
else {
    pip install -e .
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "  ✗ Failed to install dependencies" -ForegroundColor Red
    exit 1
}

Write-Host "  ✓ Dependencies installed successfully" -ForegroundColor Green
Write-Host ""

# Step 4: Initialize database
Write-Host "[4/5] Initializing database..." -ForegroundColor Green

$dataDir = "data"
if (-not (Test-Path $dataDir)) {
    New-Item -ItemType Directory -Path $dataDir | Out-Null
    Write-Host "  ✓ Created data directory" -ForegroundColor Green
}
else {
    Write-Host "  ⊙ Data directory already exists" -ForegroundColor Yellow
}

Write-Host ""

# Step 5: Verify installation
Write-Host "[5/5] Verifying installation..." -ForegroundColor Green

try {
    $version = python -m playnite_python --version 2>&1
    Write-Host "  ✓ CLI is working: $version" -ForegroundColor Green
}
catch {
    Write-Host "  ✗ CLI verification failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Installation Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "To start the service:" -ForegroundColor White
Write-Host "  .\venv\Scripts\Activate.ps1" -ForegroundColor Cyan
Write-Host "  python -m playnite_python serve" -ForegroundColor Cyan
Write-Host ""
Write-Host "To test recommendations:" -ForegroundColor White
Write-Host "  python -m playnite_python recommend generate \" -ForegroundColor Cyan
Write-Host "    --user-id=test-user \" -ForegroundColor Cyan
Write-Host "    --library-file=tests\fixtures\sample_game_library.json" -ForegroundColor Cyan
Write-Host ""
Write-Host "Service will be available at: http://localhost:5555" -ForegroundColor White
Write-Host "API Documentation: http://localhost:5555/docs" -ForegroundColor White
Write-Host ""

# Optional: Create start script
$startScriptPath = "start-service.ps1"
$startScriptContent = @"
# Quick start script for Playnite Python service
& ".\venv\Scripts\Activate.ps1"
python -m playnite_python serve
"@

Set-Content -Path $startScriptPath -Value $startScriptContent
Write-Host "Created start script: $startScriptPath" -ForegroundColor Green
Write-Host "  Run: .\$startScriptPath to start the service" -ForegroundColor Cyan
Write-Host ""
