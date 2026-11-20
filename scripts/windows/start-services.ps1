<#
.SYNOPSIS
  Starts the Video Portal services in dependency order (API, Worker, then Caddy).
.EXAMPLE
  .\start-services.ps1
#>
[CmdletBinding()]
param([int]$TimeoutSeconds = 60)
. (Join-Path $PSScriptRoot '_common.ps1')
$ErrorActionPreference = 'Stop'
if (-not (Test-IsAdmin)) { throw 'Run this script from an elevated PowerShell.' }
$failed = $false
foreach ($name in $script:ServiceNames) {
    $service = Get-Service -Name $name -ErrorAction SilentlyContinue
    if (-not $service) { Write-Host "SKIP  $name is not installed"; continue }
    if ($service.Status -eq 'Running') { Write-Host "OK    $name already running"; continue }
    try {
        Start-Service -Name $name
        $service.WaitForStatus('Running', [TimeSpan]::FromSeconds($TimeoutSeconds))
        Write-Host "OK    $name started"
    } catch {
        $failed = $true
        Write-Host "FAIL  $name did not start: $($_.Exception.Message)"
        Write-Host "      Check C:\VideoPortal\logs\services\$name.err.log and the application logs."
    }
}
if ($failed) { exit 1 }
