<#
.SYNOPSIS
  Registers the scheduled tasks for Video Portal: nightly backup and a 5-minute health check.
.DESCRIPTION
  Without -Apply this prints the plan and changes nothing. With -Apply (elevated) it creates
  VideoPortal-Backup and VideoPortal-HealthCheck, running as SYSTEM so no password is stored.
  Existing tasks with these names are left untouched. Temporary-file cleanup needs no task: the
  worker service runs it hourly.
.EXAMPLE
  .\register-tasks.ps1 -Apply -OffsitePath \\nas\videoportal
#>
[CmdletBinding()]
param(
    [string]$Root = 'C:\VideoPortal',
    [string]$BackupTime = '02:30',
    [string]$OffsitePath = '',
    [switch]$Apply
)
. (Join-Path $PSScriptRoot '_common.ps1')
$ErrorActionPreference = 'Stop'
$paths = Get-PortalPaths -Root $Root
$scripts = Join-Path $paths.App 'scripts\windows'
$backupArguments = "-NoProfile -ExecutionPolicy Bypass -File `"$scripts\backup.ps1`" -Root `"$Root`""
if ($OffsitePath) { $backupArguments += " -OffsitePath `"$OffsitePath`"" }
$tasks = @(
    @{ Name = 'VideoPortal-Backup'; Arguments = $backupArguments; Description = 'Nightly PostgreSQL dump with verification';
       Trigger = { New-ScheduledTaskTrigger -Daily -At $BackupTime } },
    @{ Name = 'VideoPortal-HealthCheck'; Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$scripts\healthcheck.ps1`" -Root `"$Root`"";
       Description = 'Checks services, API health, disk and backup age every 5 minutes';
       Trigger = { New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650) } }
)

Write-Step 'Plan'
foreach ($task in $tasks) { Write-Host "  task $($task.Name): powershell.exe $($task.Arguments)" }
Write-Host "  backup time $BackupTime daily; offsite copy: $(if ($OffsitePath) { $OffsitePath } else { 'NONE - backups stay on this disk only' })"
if (-not (Confirm-Apply $Apply.IsPresent 'register the scheduled tasks')) { exit 0 }
if (-not (Test-IsAdmin)) { throw 'Run this script from an elevated PowerShell.' }

foreach ($task in $tasks) {
    if (Get-ScheduledTask -TaskName $task.Name -ErrorAction SilentlyContinue) { Write-Host "  $($task.Name) already exists - left unchanged"; continue }
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $task.Arguments
    $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $task.Name -Action $action -Trigger (& $task.Trigger) -Principal $principal -Settings $settings -Description $task.Description | Out-Null
    Write-Host "  registered $($task.Name)"
}
if (-not [System.Diagnostics.EventLog]::SourceExists('VideoPortal')) { New-EventLog -LogName Application -Source 'VideoPortal' }
Write-Step 'Done'
