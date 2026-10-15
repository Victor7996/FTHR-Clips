# PowerShell script to deploy FTHR Clips Stream Deck plugin to Elgato StreamDeck
$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$source = Join-Path $scriptDir "com.fthrclips.streamdeck.sdPlugin"
$targetDir = "$env:APPDATA\Elgato\StreamDeck\Plugins\com.fthrclips.streamdeck.sdPlugin"

Write-Host "Deploying FTHR Clips Stream Deck plugin..." -ForegroundColor Cyan

# Stop StreamDeck process if running
$sdProcess = Get-Process -Name StreamDeck -ErrorAction SilentlyContinue
$wasRunning = $false
if ($sdProcess) {
    Write-Host "Stopping Stream Deck application..." -ForegroundColor Yellow
    $wasRunning = $true
    Stop-Process -Name StreamDeck -Force
    Start-Sleep -Milliseconds 800
}

# Ensure parent directory exists
$parentDir = Split-Path -Parent $targetDir
if (-not (Test-Path $parentDir)) {
    New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
}

# Copy plugin files
Copy-Item -Path $source -Destination $targetDir -Recurse -Force
Write-Host "Plugin copied successfully to $targetDir" -ForegroundColor Green

# Restart Stream Deck if it was running or if executable exists
$streamDeckExe = "${env:ProgramFiles}\Elgato\StreamDeck\StreamDeck.exe"
if (Test-Path $streamDeckExe) {
    Write-Host "Restarting Stream Deck..." -ForegroundColor Cyan
    Start-Process -FilePath $streamDeckExe
}

Write-Host "Klart! FTHR Clips Stream Deck plugin är installerat och redo att användas!" -ForegroundColor Green
