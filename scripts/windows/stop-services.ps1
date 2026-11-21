<#
.SYNOPSIS
  Stops the Video Portal services gracefully (Caddy first, then Worker, then API).
.DESCRIPTION
  The worker is given time to finish the clip it is encoding. A job interrupted anyway is not lost:
  its lease expires and the next worker start retries it. PostgreSQL is never stopped by this script.
.EXAMPLE
  .\stop-services.ps1
#>
[CmdletBinding()]
param([int]$TimeoutSeconds = 200)
. (Join-Path $PSScriptRoot '_common.ps1')
$ErrorActionPreference = 'Stop'
if (-not (Test-IsAdmin)) { throw 'Run this script from an elevated PowerShell.' }
$failed = $false
$reverse = @($script:ServiceNames)
[array]::Reverse($reverse)
foreach ($name in $reverse) {
    $service = Get-Service -Name $name -ErrorAction SilentlyContinue
    if (-not $service) { Write-Host "SKIP  $name is not installed"; continue }
    if ($service.Status -eq 'Stopped') { Write-Host "OK    $name already stopped"; continue }
    try {
        Stop-Service -Name $name
        $service.WaitForStatus('Stopped', [TimeSpan]::FromSeconds($TimeoutSeconds))
        Write-Host "OK    $name stopped"
    } catch {
        $failed = $true
        Write-Host "FAIL  $name did not stop in $TimeoutSeconds s: $($_.Exception.Message)"
    }
}
if ($failed) { exit 1 }
