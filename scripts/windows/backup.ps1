<#
.SYNOPSIS
  Backs up the Video Portal PostgreSQL database, verifies the dump and optionally copies it off the VPS.
.DESCRIPTION
  Creates <BackupDir>\videoportal-<UTC timestamp>.dump (pg_dump custom format) plus a .sha256 file.
  Verification: pg_restore --list must read the archive and find the application tables.
  The database password is read from the config file into this process only (PGPASSWORD); it is
  never printed or put on a command line.
  A dump on the same disk as the database is NOT a full recovery plan: pass -OffsitePath (another
  machine/share/synced folder) or copy the files off the VPS another way.
  Retention removes only this script's own dump files older than -KeepDays, and always keeps the newest three.
.EXAMPLE
  .\backup.ps1
  .\backup.ps1 -OffsitePath \\nas\videoportal -IncludeStorage
#>
[CmdletBinding()]
param(
    [string]$Root = 'C:\VideoPortal',
    [string]$EnvFile = '',
    [string]$BackupDir = '',
    [string]$PostgresBin = '',
    [string]$OffsitePath = '',
    [int]$KeepDays = 14,
    [switch]$IncludeStorage
)
. (Join-Path $PSScriptRoot '_common.ps1')
$ErrorActionPreference = 'Stop'
$paths = Get-PortalPaths -Root $Root
if (-not $EnvFile) { $EnvFile = $paths.EnvFile }
if (-not $BackupDir) { $BackupDir = $paths.Backups }
$config = Read-EnvFile $EnvFile
$dbHost = Get-EnvValue $config 'POSTGRES_HOST' '127.0.0.1'
$dbPort = Get-EnvValue $config 'POSTGRES_PORT' '5432'
$dbName = Get-EnvValue $config 'POSTGRES_DB' 'video_portal'
$dbUser = Get-EnvValue $config 'POSTGRES_USER' 'video_portal'
$password = Get-EnvValue $config 'POSTGRES_PASSWORD' ''
if (-not $password) { throw "POSTGRES_PASSWORD is empty in $EnvFile" }
$pgDump = Find-PostgresTool 'pg_dump' $PostgresBin
$pgRestore = Find-PostgresTool 'pg_restore' $PostgresBin
if (-not $pgDump -or -not $pgRestore) { throw 'pg_dump/pg_restore not found. Pass -PostgresBin.' }
if (-not (Test-Path -LiteralPath $BackupDir)) { New-Item -ItemType Directory -Path $BackupDir | Out-Null }

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$dump = Join-Path $BackupDir "videoportal-$stamp.dump"
$partial = "$dump.partial"
$started = Get-Date
$env:PGPASSWORD = $password
try {
    Write-Step "Dumping database $dbName"
    & $pgDump -h $dbHost -p $dbPort -U $dbUser -d $dbName -Fc --no-owner --no-acl -f $partial
    if ($LASTEXITCODE -ne 0) { throw "pg_dump failed with exit code $LASTEXITCODE" }
} finally {
    $env:PGPASSWORD = $null
    if ($LASTEXITCODE -ne 0 -and (Test-Path -LiteralPath $partial)) { Remove-Item -LiteralPath $partial -Force -Confirm:$false }
}

Write-Step 'Verifying the archive'
$listing = & $pgRestore --list $partial 2>&1
if ($LASTEXITCODE -ne 0) { Remove-Item -LiteralPath $partial -Force -Confirm:$false; throw 'pg_restore could not read the new archive; backup discarded' }
$tables = @($listing | Where-Object { $_ -match ' TABLE DATA ' })
foreach ($required in @('videos', 'transcode_jobs', 'outbox_events')) {
    if (-not ($tables | Where-Object { $_ -match " $required( |$)" })) { Remove-Item -LiteralPath $partial -Force -Confirm:$false; throw "Archive has no data entry for table '$required'; backup discarded" }
}
# Rename only after verification so a half-written file is never mistaken for a backup.
Move-Item -LiteralPath $partial -Destination $dump
$hash = (Get-FileHash -LiteralPath $dump -Algorithm SHA256).Hash.ToLower()
[System.IO.File]::WriteAllText("$dump.sha256", "$hash  $(Split-Path $dump -Leaf)`n")
$sizeMb = [math]::Round((Get-Item -LiteralPath $dump).Length / 1MB, 2)
Write-Host "  $dump ($sizeMb MB, $($tables.Count) tables, sha256 $hash)"

$offsiteDone = $false
if ($OffsitePath) {
    Write-Step "Copying to $OffsitePath"
    if (-not (Test-Path -LiteralPath $OffsitePath)) { Write-Warning "Offsite path is not reachable: $OffsitePath" }
    else {
        Copy-Item -LiteralPath $dump, "$dump.sha256" -Destination $OffsitePath
        $copied = (Get-FileHash -LiteralPath (Join-Path $OffsitePath (Split-Path $dump -Leaf)) -Algorithm SHA256).Hash.ToLower()
        if ($copied -ne $hash) { throw 'Offsite copy hash mismatch' }
        $offsiteDone = $true
        if ($IncludeStorage) {
            # /E copies new and changed files; nothing is deleted on the destination (no /MIR, no /PURGE).
            $target = Join-Path $OffsitePath 'storage-objects'
            & robocopy $paths.Objects $target /E /R:2 /W:5 /NFL /NDL /NJH /NP /XF '.signing-key' '*.tmp' | Out-Null
            if ($LASTEXITCODE -ge 8) { throw "robocopy reported errors (exit $LASTEXITCODE)" }
            Write-Host "  video files copied to $target"
        }
    }
}

Write-Step 'Retention'
$cutoff = (Get-Date).AddDays(-$KeepDays)
$all = @(Get-ChildItem -LiteralPath $BackupDir -Filter 'videoportal-*.dump' | Sort-Object LastWriteTime -Descending)
$old = @($all | Select-Object -Skip 3 | Where-Object { $_.LastWriteTime -lt $cutoff })
foreach ($file in $old) {
    Remove-Item -LiteralPath $file.FullName -Force -Confirm:$false
    if (Test-Path -LiteralPath "$($file.FullName).sha256") { Remove-Item -LiteralPath "$($file.FullName).sha256" -Force -Confirm:$false }
}
Write-Host "  kept $($all.Count - $old.Count) local backups, removed $($old.Count) older than $KeepDays days"

$seconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
Write-Host "BACKUP OK in $seconds s: $dump"
if (-not $offsiteDone) { Write-Warning 'No off-VPS copy was made. A backup on the same disk does not survive disk loss; use -OffsitePath or copy the file elsewhere.' }
exit 0
