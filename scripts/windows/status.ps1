<#
.SYNOPSIS
  Read-only status of the Video Portal installation: services, health endpoint, disk, queue, backups.
.EXAMPLE
  .\status.ps1
#>
[CmdletBinding()]
param(
    [string]$Root = 'C:\VideoPortal',
    [string]$EnvFile = '',
    [string]$BackupDir = ''
)
. (Join-Path $PSScriptRoot '_common.ps1')
$ErrorActionPreference = 'Continue'
$paths = Get-PortalPaths -Root $Root
if (-not $EnvFile) { $EnvFile = $paths.EnvFile }
if (-not $BackupDir) { $BackupDir = $paths.Backups }
$problems = 0

Write-Step 'Services'
$names = @($script:ServiceNames) + @(Get-Service -Name 'postgresql*' -ErrorAction SilentlyContinue | ForEach-Object { $_.Name })
foreach ($name in $names) {
    $service = Get-Service -Name $name -ErrorAction SilentlyContinue
    if (-not $service) { Write-Host ("  {0,-22} not installed" -f $name); $problems++ }
    else {
        Write-Host ("  {0,-22} {1,-9} start={2}" -f $name, $service.Status, $service.StartType)
        if ($service.Status -ne 'Running') { $problems++ }
    }
}

Write-Step 'API health (loopback)'
$port = '8000'
if (Test-Path -LiteralPath $EnvFile) { $port = Get-EnvValue (Read-EnvFile $EnvFile) 'BIND_PORT' '8000' }
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:$port/health" -UseBasicParsing -TimeoutSec 10
    Write-Host "  HTTP $($response.StatusCode) $($response.Content.Trim())"
} catch {
    $problems++
    Write-Host "  FAILED: $($_.Exception.Message)"
}

Write-Step 'Disk'
foreach ($folder in @($paths.Objects, $paths.Temporary, $paths.Logs, $BackupDir)) {
    if (-not (Test-Path -LiteralPath $folder)) { Write-Host "  $folder (missing)"; continue }
    $size = 0
    foreach ($file in @(Get-ChildItem -LiteralPath $folder -Recurse -File -Force -ErrorAction SilentlyContinue)) { $size += $file.Length }
    Write-Host ("  {0,-40} {1,10:N1} MB" -f $folder, ($size / 1MB))
}
$driveName = [System.IO.Path]::GetPathRoot($paths.Root).TrimEnd('\').TrimEnd(':')
$drive = Get-PSDrive -Name $driveName -ErrorAction SilentlyContinue
if ($drive) {
    $freeGb = [math]::Round($drive.Free / 1GB, 1)
    Write-Host "  drive $($driveName): $freeGb GB free"
    if ($freeGb -lt 5) { $problems++; Write-Host '  WARNING: less than 5 GB free' }
}

Write-Step 'Queue and storage (application view)'
$python = Join-Path $paths.Venv 'Scripts\python.exe'
if ((Test-Path -LiteralPath $python) -and (Test-Path -LiteralPath $paths.App)) {
    $env:VIDEO_PORTAL_ENV_FILE = $EnvFile
    try {
        Push-Location $paths.App
        & $python -m flask --app app.main system-status 2>&1 | ForEach-Object { Write-Host "  $_" }
        & $python -m flask --app app.main local-jobs 2>&1 | Select-Object -Last 15 | ForEach-Object { Write-Host "  $_" }
    } finally { Pop-Location; $env:VIDEO_PORTAL_ENV_FILE = $null }
} else { Write-Host '  application or virtual environment not installed' }

Write-Step 'Backups'
$latest = Get-ChildItem -LiteralPath $BackupDir -Filter 'videoportal-*.dump' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $latest) { $problems++; Write-Host '  no backup found' }
else {
    $ageHours = [math]::Round(((Get-Date) - $latest.LastWriteTime).TotalHours, 1)
    Write-Host "  latest: $($latest.Name) ($ageHours h old)"
    if ($ageHours -gt 26) { $problems++; Write-Host '  WARNING: latest backup is older than 26 hours' }
}

Write-Host ''
if ($problems -eq 0) { Write-Host 'STATUS OK' ; exit 0 }
Write-Host "STATUS: $problems item(s) need attention"
exit 1
