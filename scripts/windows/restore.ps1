<#
.SYNOPSIS
  Restores a Video Portal dump into a NEW database and reports what it contains.
.DESCRIPTION
  This script never drops, overwrites or restores into an existing database. It creates
  -TargetDatabase (default: a timestamped test name), restores the dump into it and prints row
  counts so you can compare with production. To recover production, restore into a new database,
  check it, then point POSTGRES_DB in the config at it and restart the services (see
  docs\WINDOWS_VPS_BACKUP.md).
  -DropAfterVerify removes ONLY the database this run created (for routine restore drills).
  The connecting role needs CREATEDB (use the PostgreSQL administrator with -AdminUser). The
  password is asked interactively or taken from $env:PGPASSWORD; it is never printed.
.EXAMPLE
  .\restore.ps1 -DumpFile C:\VideoPortal\backups\videoportal-20261117-023000.dump -AdminUser postgres -DropAfterVerify
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$DumpFile,
    [string]$Root = 'C:\VideoPortal',
    [string]$EnvFile = '',
    [string]$PostgresBin = '',
    [string]$TargetDatabase = '',
    [string]$AdminUser = '',
    [switch]$DropAfterVerify
)
. (Join-Path $PSScriptRoot '_common.ps1')
$ErrorActionPreference = 'Stop'
$paths = Get-PortalPaths -Root $Root
if (-not $EnvFile) { $EnvFile = $paths.EnvFile }
$config = Read-EnvFile $EnvFile
$dbHost = Get-EnvValue $config 'POSTGRES_HOST' '127.0.0.1'
$dbPort = Get-EnvValue $config 'POSTGRES_PORT' '5432'
$owner = Get-EnvValue $config 'POSTGRES_USER' 'video_portal'
if (-not $AdminUser) { $AdminUser = $owner }
if (-not $TargetDatabase) { $TargetDatabase = 'videoportal_restore_' + (Get-Date).ToUniversalTime().ToString('yyyyMMdd_HHmmss') }
foreach ($value in @($TargetDatabase, $AdminUser, $owner)) {
    if ($value -notmatch '^[a-z_][a-z0-9_]{0,62}$') { throw "Unsafe PostgreSQL identifier: $value" }
}
if ($TargetDatabase -eq (Get-EnvValue $config 'POSTGRES_DB' 'video_portal')) { throw 'Refusing to restore into the live application database. Choose another -TargetDatabase.' }
if (-not (Test-Path -LiteralPath $DumpFile)) { throw "Dump file not found: $DumpFile" }
$psql = Find-PostgresTool 'psql' $PostgresBin
$pgRestore = Find-PostgresTool 'pg_restore' $PostgresBin
if (-not $psql -or -not $pgRestore) { throw 'psql/pg_restore not found. Pass -PostgresBin.' }

Write-Step 'Checking the dump file'
$hashFile = "$DumpFile.sha256"
if (Test-Path -LiteralPath $hashFile) {
    $expected = ([System.IO.File]::ReadAllText($hashFile).Trim() -split '\s+')[0]
    $actual = (Get-FileHash -LiteralPath $DumpFile -Algorithm SHA256).Hash.ToLower()
    if ($expected -ne $actual) { throw 'SHA256 mismatch: the dump file is damaged or was modified. Nothing was restored.' }
    Write-Host '  sha256 matches'
} else { Write-Warning 'No .sha256 file next to the dump; integrity was not checked.' }

$hadPassword = [bool]$env:PGPASSWORD
if (-not $hadPassword) {
    if ($AdminUser -eq $owner) { $env:PGPASSWORD = Get-EnvValue $config 'POSTGRES_PASSWORD' '' }
    if (-not $env:PGPASSWORD) {
        $secure = Read-Host -AsSecureString "Password for PostgreSQL role '$AdminUser' (not stored)"
        $env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
    }
}
function Invoke-Sql {
    param([string]$Sql, [string]$Database = 'postgres')
    $output = $Sql | & $psql -h $dbHost -p $dbPort -U $AdminUser -d $Database -v ON_ERROR_STOP=1 -X -q -A -t -f - 2>&1
    if ($LASTEXITCODE -ne 0) { throw "psql failed: $(($output | Out-String).Trim())" }
    ($output | Out-String).Trim()
}

$created = $false
try {
    if ((Invoke-Sql "SELECT 1 FROM pg_database WHERE datname = '$TargetDatabase';") -eq '1') {
        throw "Database $TargetDatabase already exists. This script never restores over an existing database."
    }
    Write-Step "Creating database $TargetDatabase"
    Invoke-Sql "CREATE DATABASE $TargetDatabase OWNER $owner ENCODING 'UTF8' TEMPLATE template0;" | Out-Null
    $created = $true
    Write-Step 'Restoring'
    & $pgRestore -h $dbHost -p $dbPort -U $AdminUser -d $TargetDatabase --no-owner --no-acl --role=$owner --exit-on-error $DumpFile
    if ($LASTEXITCODE -ne 0) { throw "pg_restore failed with exit code $LASTEXITCODE" }

    Write-Step 'Verifying restored data'
    $counts = [ordered]@{}
    foreach ($table in @('videos', 'transcode_jobs', 'output_objects', 'video_permissions', 'outbox_events', 'users')) {
        $exists = Invoke-Sql "SELECT to_regclass('public.$table') IS NOT NULL;" $TargetDatabase
        $counts[$table] = if ($exists -eq 't') { [int](Invoke-Sql "SELECT count(*) FROM public.$table;" $TargetDatabase) } else { 'missing' }
    }
    $counts.GetEnumerator() | ForEach-Object { Write-Host ("  {0,-18} {1}" -f $_.Key, $_.Value) }
    if ($counts['videos'] -eq 'missing' -or $counts['transcode_jobs'] -eq 'missing') { throw 'Core tables are missing from the restored database.' }
    $broken = Invoke-Sql "SELECT count(*) FROM public.transcode_jobs j LEFT JOIN public.videos v ON v.id = j.video_id WHERE v.id IS NULL;" $TargetDatabase
    if ($broken -ne '0') { throw "$broken jobs reference a missing video: the restore is inconsistent." }
    Write-Host "RESTORE OK: database $TargetDatabase"
    Write-Host ('RESTORE_COUNTS ' + ($counts | ConvertTo-Json -Compress))
    if ($DropAfterVerify) {
        Invoke-Sql "DROP DATABASE $TargetDatabase;" | Out-Null
        $created = $false
        Write-Host "  drill database $TargetDatabase dropped (it was created by this run)"
    } else {
        Write-Host "  To use it for production: stop services, set POSTGRES_DB=$TargetDatabase in $EnvFile, start services."
    }
} catch {
    if ($created) { Write-Warning "Database $TargetDatabase was created by this run and may be incomplete. Inspect it, then drop it manually: DROP DATABASE $TargetDatabase;" }
    throw
} finally {
    if (-not $hadPassword) { $env:PGPASSWORD = $null }
}
exit 0
