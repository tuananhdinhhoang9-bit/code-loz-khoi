<#
.SYNOPSIS
  Unattended health check for Task Scheduler: services, API health, disk space, backup age.
.DESCRIPTION
  Appends one JSON line per run to <Root>\logs\health.log (rotated at 5 MB, one previous file kept)
  and writes a Windows Application event (source VideoPortal, ID 1001) when something is wrong, if
  the event source exists. Exit code 1 means at least one check failed.
  It changes nothing unless -RestartStopped is given, in which case it starts Video Portal services
  that are installed but stopped (crashes are already handled by the service recovery settings).
.EXAMPLE
  .\healthcheck.ps1 -MinFreeGb 5
#>
[CmdletBinding()]
param(
    [string]$Root = 'C:\VideoPortal',
    [int]$Port = 8000,
    [double]$MinFreeGb = 5,
    [int]$MaxBackupAgeHours = 26,
    [switch]$RestartStopped
)
. (Join-Path $PSScriptRoot '_common.ps1')
$ErrorActionPreference = 'Continue'
$paths = Get-PortalPaths -Root $Root
$failures = New-Object System.Collections.Generic.List[string]

foreach ($name in $script:ServiceNames) {
    $service = Get-Service -Name $name -ErrorAction SilentlyContinue
    if (-not $service) { $failures.Add("service_missing:$name"); continue }
    if ($service.Status -ne 'Running') {
        $failures.Add("service_stopped:$name")
        if ($RestartStopped) { try { Start-Service -Name $name -ErrorAction Stop } catch { $failures.Add("service_restart_failed:$name") } }
    }
}
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 10
    if ($response.StatusCode -ne 200) { $failures.Add("health_http_$($response.StatusCode)") }
} catch { $failures.Add('health_unreachable') }

$driveName = [System.IO.Path]::GetPathRoot($paths.Root).TrimEnd('\').TrimEnd(':')
$drive = Get-PSDrive -Name $driveName -ErrorAction SilentlyContinue
$freeGb = if ($drive) { [math]::Round($drive.Free / 1GB, 2) } else { -1 }
if ($freeGb -lt $MinFreeGb) { $failures.Add("disk_low:${freeGb}GB") }

$latest = Get-ChildItem -LiteralPath $paths.Backups -Filter 'videoportal-*.dump' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$backupAge = if ($latest) { [math]::Round(((Get-Date) - $latest.LastWriteTime).TotalHours, 1) } else { -1 }
if (-not $latest) { $failures.Add('backup_missing') } elseif ($backupAge -gt $MaxBackupAgeHours) { $failures.Add("backup_old:${backupAge}h") }

$record = [ordered]@{
    time = (Get-Date).ToUniversalTime().ToString('o'); ok = ($failures.Count -eq 0); failures = @($failures)
    disk_free_gb = $freeGb; backup_age_hours = $backupAge
}
$line = $record | ConvertTo-Json -Compress
$log = Join-Path $paths.Logs 'health.log'
if (Test-Path -LiteralPath $paths.Logs) {
    if ((Test-Path -LiteralPath $log) -and (Get-Item -LiteralPath $log).Length -gt 5MB) { Move-Item -LiteralPath $log -Destination "$log.1" -Force }
    Add-Content -LiteralPath $log -Value $line -Encoding utf8
}
Write-Host $line
if ($failures.Count -gt 0) {
    try {
        if ([System.Diagnostics.EventLog]::SourceExists('VideoPortal')) {
            Write-EventLog -LogName Application -Source 'VideoPortal' -EventId 1001 -EntryType Warning -Message ("Video Portal health check failed: " + ($failures -join ', '))
        }
    } catch { }
    exit 1
}
exit 0
