<#
.SYNOPSIS
  Creates the least-privilege application role and database on an existing PostgreSQL, then runs init-db.
.DESCRIPTION
  Without -Apply this prints the plan and changes nothing.
  With -Apply it creates ONLY what is missing. An existing role or database is never dropped,
  altered or overwritten. The application role is not a superuser, cannot create databases or
  roles, and has a connection limit. The generated password is written to the config file only;
  it is never printed and never placed on a command line (SQL is piped to psql through stdin).
  The superuser password is asked interactively, or taken from $env:PGPASSWORD if already set.
.EXAMPLE
  .\setup-database.ps1 -Apply
#>
[CmdletBinding()]
param(
    [string]$Root = 'C:\VideoPortal',
    [string]$EnvFile = '',
    [string]$PostgresBin = '',
    [string]$AdminUser = 'postgres',
    [int]$ConnectionLimit = 20,
    [switch]$Apply,
    [switch]$SkipInitDb
)
. (Join-Path $PSScriptRoot '_common.ps1')
$ErrorActionPreference = 'Stop'
$paths = Get-PortalPaths -Root $Root
if (-not $EnvFile) { $EnvFile = $paths.EnvFile }
$config = Read-EnvFile $EnvFile
$dbHost = Get-EnvValue $config 'POSTGRES_HOST' '127.0.0.1'
$dbPort = Get-EnvValue $config 'POSTGRES_PORT' '5432'
$dbName = Get-EnvValue $config 'POSTGRES_DB' 'video_portal'
$dbUser = Get-EnvValue $config 'POSTGRES_USER' 'video_portal'
foreach ($value in @($dbName, $dbUser, $AdminUser)) {
    if ($value -notmatch '^[a-z_][a-z0-9_]{0,62}$') { throw "Unsafe PostgreSQL identifier: $value" }
}
if ($dbUser -eq $AdminUser -or $dbUser -eq 'postgres') { throw 'The application must not use the superuser account.' }
if ($dbHost -notin @('127.0.0.1', 'localhost', '::1')) { throw "POSTGRES_HOST is $dbHost; this script only configures a local PostgreSQL." }
$psql = Find-PostgresTool 'psql' $PostgresBin
if (-not $psql) { throw 'psql.exe not found. Install PostgreSQL or pass -PostgresBin.' }

Write-Step 'Plan'
Write-Host "  server      $dbHost`:$dbPort (administrator role: $AdminUser)"
Write-Host "  role        $dbUser  LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE CONNECTION LIMIT $ConnectionLimit (created only if missing)"
Write-Host "  database    $dbName  owned by $dbUser, PUBLIC connect revoked (created only if missing)"
Write-Host "  password    generated, stored in $EnvFile only if POSTGRES_PASSWORD is empty"
Write-Host "  schema      flask init-db (creates missing tables/columns, never drops)"
if (-not (Confirm-Apply $Apply.IsPresent 'create missing role/database and initialise the schema')) { exit 0 }

$hadPassword = [bool]$env:PGPASSWORD
if (-not $hadPassword) {
    $secure = Read-Host -AsSecureString "Password for PostgreSQL role '$AdminUser' (not stored)"
    $env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
}
function Invoke-Sql {
    # SQL goes through stdin so passwords never appear in a process command line.
    param([string]$Sql, [string]$Database = 'postgres')
    $output = $Sql | & $psql -h $dbHost -p $dbPort -U $AdminUser -d $Database -v ON_ERROR_STOP=1 -X -q -A -t -f - 2>&1
    if ($LASTEXITCODE -ne 0) { throw "psql failed: $(($output | Out-String).Trim())" }
    ($output | Out-String).Trim()
}

try {
    Write-Step 'Checking the server'
    Write-Host "  $(Invoke-Sql 'SELECT version();')"
    $listen = Invoke-Sql 'SHOW listen_addresses;'
    if ($listen -notin @('localhost', '127.0.0.1')) { Write-Warning "listen_addresses is '$listen'. Set it to 'localhost' in postgresql.conf and restart PostgreSQL in a maintenance window." }
    Write-Host "  max_connections = $(Invoke-Sql 'SHOW max_connections;') (suggested for 4 GB RAM: 30; shared_buffers 512MB; work_mem 8MB)"

    $roleExists = (Invoke-Sql "SELECT 1 FROM pg_roles WHERE rolname = '$dbUser';") -eq '1'
    $password = Get-EnvValue $config 'POSTGRES_PASSWORD' ''
    if ($roleExists) {
        Write-Host "  role $dbUser already exists - left unchanged"
        if (-not $password) { Write-Warning "POSTGRES_PASSWORD is empty in $EnvFile but the role exists. Put the existing password there yourself." }
    } else {
        if (-not $password) {
            $bytes = New-Object byte[] 24
            [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
            $password = [BitConverter]::ToString($bytes).Replace('-', '').ToLower()
            $lines = [System.IO.File]::ReadAllLines($EnvFile)
            $found = $false
            $lines = $lines | ForEach-Object { if ($_ -match '^\s*POSTGRES_PASSWORD\s*=') { $found = $true; "POSTGRES_PASSWORD=$password" } else { $_ } }
            if (-not $found) { $lines = @($lines) + "POSTGRES_PASSWORD=$password" }
            [System.IO.File]::WriteAllLines($EnvFile, [string[]]$lines, (New-Object System.Text.UTF8Encoding($false)))
            Write-Host "  generated a password and stored it in $EnvFile (not shown)"
        }
        Invoke-Sql "CREATE ROLE $dbUser LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION CONNECTION LIMIT $ConnectionLimit PASSWORD '$password';" | Out-Null
        Write-Host "  created role $dbUser"
    }
    $dbExists = (Invoke-Sql "SELECT 1 FROM pg_database WHERE datname = '$dbName';") -eq '1'
    if ($dbExists) { Write-Host "  database $dbName already exists - left unchanged (no data touched)" }
    else {
        Invoke-Sql "CREATE DATABASE $dbName OWNER $dbUser ENCODING 'UTF8';" | Out-Null
        Invoke-Sql "REVOKE ALL ON DATABASE $dbName FROM PUBLIC;" | Out-Null
        Write-Host "  created database $dbName"
    }
} finally {
    if (-not $hadPassword) { $env:PGPASSWORD = $null }
}

if (-not $SkipInitDb) {
    Write-Step 'Initialising the schema as the application role'
    $python = Join-Path $paths.Venv 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) { throw "Virtual environment not found at $($paths.Venv). Run install-prerequisites.ps1 -Apply first." }
    $env:VIDEO_PORTAL_ENV_FILE = $EnvFile
    try {
        Push-Location $paths.App
        & $python -m flask --app app.main init-db
        if ($LASTEXITCODE -ne 0) { throw 'flask init-db failed' }
    } finally { Pop-Location; $env:VIDEO_PORTAL_ENV_FILE = $null }
}
Write-Step 'Done'
Write-Host 'Create the first account with:  flask --app app.main create-user you@example.com --admin   (asks for the password)'
