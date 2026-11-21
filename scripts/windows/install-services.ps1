<#
.SYNOPSIS
  Registers VideoPortal-API, VideoPortal-Worker and VideoPortal-Caddy as Windows services (WinSW).
.DESCRIPTION
  Without -Apply this prints the plan and changes nothing.
  With -Apply (elevated) it writes WinSW configs, installs the services under per-service virtual
  accounts (NT SERVICE\<name>, no password anywhere) and grants each only the folders it needs.
  It refuses to replace an existing service. It does NOT start the services, open firewall ports,
  or change Defender/RDP. Start them with start-services.ps1 after reviewing the config.
.EXAMPLE
  .\install-services.ps1                    # plan
  .\install-services.ps1 -WriteConfigOnly   # write the WinSW definitions and let WinSW parse them; installs nothing
  .\install-services.ps1 -Apply             # install (elevated PowerShell)
#>
[CmdletBinding()]
param(
    [string]$Root = 'C:\VideoPortal',
    [string]$PostgresService = '',
    [switch]$Apply,
    [switch]$WriteConfigOnly,
    [switch]$SkipCaddy
)
. (Join-Path $PSScriptRoot '_common.ps1')
$ErrorActionPreference = 'Stop'
$paths = Get-PortalPaths -Root $Root
$python = Join-Path $paths.Venv 'Scripts\python.exe'
$winsw = Join-Path $paths.Tools 'winsw\WinSW-x64.exe'
$caddy = Join-Path $paths.Tools 'caddy\caddy.exe'
$caddyfile = Join-Path $paths.Config 'Caddyfile'
if (-not $PostgresService) {
    $found = Get-Service -Name 'postgresql*' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { $PostgresService = $found.Name }
}

function New-ServiceXml {
    param([string]$Id, [string]$Description, [string]$Executable, [string]$Arguments, [string]$WorkingDirectory, [string[]]$Environment, [string]$Depend, [int]$StopSeconds)
    $envLines = ($Environment | ForEach-Object { $pair = $_.Split('=', 2); "  <env name=`"$($pair[0])`" value=`"$($pair[1])`"/>" }) -join "`r`n"
    $dependLine = if ($Depend) { "  <depend>$Depend</depend>" } else { '' }
@"
<service>
  <id>$Id</id>
  <name>$Id</name>
  <description>$Description</description>
  <executable>$Executable</executable>
  <arguments>$Arguments</arguments>
  <workingdirectory>$WorkingDirectory</workingdirectory>
$envLines
$dependLine
  <startmode>Automatic</startmode>
  <delayedAutoStart>true</delayedAutoStart>
  <onfailure action="restart" delay="10 sec"/>
  <onfailure action="restart" delay="30 sec"/>
  <onfailure action="restart" delay="60 sec"/>
  <resetfailure>1 hour</resetfailure>
  <stoptimeout>$StopSeconds sec</stoptimeout>
  <logpath>$(Join-Path $paths.Logs 'services')</logpath>
  <log mode="roll-by-size">
    <sizeThreshold>10240</sizeThreshold>
    <keepFiles>5</keepFiles>
  </log>
</service>
"@
}

$common = @("VIDEO_PORTAL_ENV_FILE=$($paths.EnvFile)", 'PYTHONUNBUFFERED=1', 'PYTHONDONTWRITEBYTECODE=1')
$definitions = @(
    @{ Id = 'VideoPortal-API'; Description = 'Video Portal web API (Waitress, loopback only)'; Executable = $python; Arguments = '-m app.serve';
       WorkingDirectory = $paths.App; Environment = $common; Depend = $PostgresService; StopSeconds = 30;
       Read = @($paths.App, $paths.Venv, $paths.Config); Modify = @($paths.Objects, $paths.Logs) },
    # The worker gets 180 s to finish the clip it is encoding before Windows gives up waiting.
    @{ Id = 'VideoPortal-Worker'; Description = 'Video Portal FFmpeg worker (one job at a time)'; Executable = $python; Arguments = '-m app.worker_service';
       WorkingDirectory = $paths.App; Environment = $common; Depend = $PostgresService; StopSeconds = 180;
       Read = @($paths.App, $paths.Venv, $paths.Config, (Join-Path $paths.Tools 'ffmpeg')); Modify = @($paths.Objects, $paths.Temporary, $paths.Logs) }
)
if (-not $SkipCaddy) {
    $definitions += @{ Id = 'VideoPortal-Caddy'; Description = 'Video Portal HTTPS reverse proxy (Caddy)'; Executable = $caddy;
        Arguments = "run --config `"$caddyfile`" --adapter caddyfile"; WorkingDirectory = $paths.CaddyData;
        Environment = @("XDG_DATA_HOME=$($paths.CaddyData)", "XDG_CONFIG_HOME=$($paths.CaddyData)", "VIDEOPORTAL_LOGS=$($paths.Logs)");
        Depend = ''; StopSeconds = 30; Read = @((Join-Path $paths.Tools 'caddy'), $caddyfile); Modify = @($paths.CaddyData, $paths.Logs) }
}

Write-Step 'Plan'
foreach ($item in $definitions) {
    Write-Host "  service  $($item.Id)  ->  $($item.Executable) $($item.Arguments)"
    Write-Host "           account NT SERVICE\$($item.Id); automatic (delayed) start; restart on failure after 10/30/60 s; stop timeout $($item.StopSeconds) s"
    Write-Host "           read:   $($item.Read -join '; ')"
    Write-Host "           modify: $($item.Modify -join '; ')"
}
Write-Host "  ACL      $($paths.Root): inheritance removed; Administrators and SYSTEM full control; no Everyone/Users entries"
Write-Host "  depends  API and Worker wait for PostgreSQL service: $(if ($PostgresService) { $PostgresService } else { '(not found - no dependency set)' })"
Write-Host '  NOT done here: starting services, firewall rules, certificates'

function Write-ServiceFiles {
    # Puts <id>.exe (a copy of WinSW) and <id>.xml side by side; WinSW reads the XML named like the exe.
    param($Item)
    $exe = Join-Path $paths.Services "$($Item.Id).exe"
    $xml = Join-Path $paths.Services "$($Item.Id).xml"
    Copy-Item -LiteralPath $winsw -Destination $exe -Force
    $content = New-ServiceXml -Id $Item.Id -Description $Item.Description -Executable $Item.Executable -Arguments $Item.Arguments `
        -WorkingDirectory $Item.WorkingDirectory -Environment $Item.Environment -Depend $Item.Depend -StopSeconds $Item.StopSeconds
    [System.IO.File]::WriteAllText($xml, $content, (New-Object System.Text.UTF8Encoding($false)))
    $exe
}

if ($WriteConfigOnly) {
    # No elevation needed: writes the definitions for review and lets WinSW parse them. Installs nothing.
    if (-not (Test-Path -LiteralPath $winsw)) { throw "Missing $winsw. Run install-prerequisites.ps1 -Apply -Download first." }
    foreach ($item in $definitions) {
        if (Get-Service -Name $item.Id -ErrorAction SilentlyContinue) { throw "Service $($item.Id) is already installed; its files were left untouched." }
        $exe = Write-ServiceFiles $item
        $state = (& $exe status 2>&1 | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { throw "WinSW rejected the definition for $($item.Id): $state" }
        Write-Host "  wrote $($item.Id).xml - WinSW parsed it (service state: $state)"
    }
    Write-Host "Definitions are in $($paths.Services). Nothing was installed."
    exit 0
}
if (-not (Confirm-Apply $Apply.IsPresent 'install the services and set folder permissions')) { exit 0 }

if (-not (Test-IsAdmin)) { throw 'Run this script from an elevated PowerShell (Run as Administrator).' }
foreach ($required in @($python, $winsw, $paths.EnvFile, $paths.App)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing prerequisite: $required. Run install-prerequisites.ps1 -Apply first." }
}
if (-not $SkipCaddy) {
    foreach ($required in @($caddy, $caddyfile)) {
        if (-not (Test-Path -LiteralPath $required)) { throw "Missing $required. Copy deploy\windows\Caddyfile to $caddyfile and edit the site address, or use -SkipCaddy." }
    }
}
foreach ($item in $definitions) {
    if (Get-Service -Name $item.Id -ErrorAction SilentlyContinue) { throw "Service $($item.Id) already exists. Nothing was changed. Uninstall it deliberately before reinstalling." }
}

Write-Step 'Locking down the root folder'
& icacls $paths.Root /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'icacls failed on the root folder' }

foreach ($item in $definitions) {
    Write-Step "Installing $($item.Id)"
    $exe = Write-ServiceFiles $item
    & $exe install
    if ($LASTEXITCODE -ne 0) { throw "WinSW install failed for $($item.Id)" }
    # Virtual service account: no password to store, rotate or leak.
    & sc.exe config $item.Id obj= "NT SERVICE\$($item.Id)" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not assign the virtual account to $($item.Id)" }
    $account = "NT SERVICE\$($item.Id)"
    & icacls $paths.Root /grant "${account}:(RX)" | Out-Null
    & icacls $paths.Services /grant "${account}:(OI)(CI)RX" | Out-Null
    foreach ($target in $item.Read) {
        if (Test-Path -LiteralPath $target -PathType Container) { & icacls $target /grant "${account}:(OI)(CI)RX" | Out-Null }
        elseif (Test-Path -LiteralPath $target) { & icacls $target /grant "${account}:(R)" | Out-Null }
    }
    foreach ($target in $item.Modify) { & icacls $target /grant "${account}:(OI)(CI)M" | Out-Null }
    if ($item.Id -ne 'VideoPortal-Caddy') { & icacls $paths.Storage /grant "${account}:(RX)" | Out-Null }
}

Write-Step 'Done'
Get-Service -Name $script:ServiceNames -ErrorAction SilentlyContinue | Format-Table Name, Status, StartType -AutoSize | Out-String | Write-Host
Write-Host 'Services are installed but NOT started. Review the config, then run start-services.ps1.'
