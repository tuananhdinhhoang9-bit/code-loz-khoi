<#
.SYNOPSIS
  Prepares the folder layout, Python virtual environment and helper tools for Video Portal.
.DESCRIPTION
  Without -Apply this prints the plan and changes nothing.
  With -Apply it only creates what is missing. It never overwrites an existing config file, never
  installs PostgreSQL silently (the installer must ask YOU for the superuser password), never touches
  the firewall, Defender or RDP, and never deletes anything.
  -Download fetches FFmpeg, Caddy and WinSW from their publishers into <Root>\tools.
.EXAMPLE
  .\install-prerequisites.ps1                       # show the plan
  .\install-prerequisites.ps1 -Apply                # folders + venv + config template
  .\install-prerequisites.ps1 -Apply -Download      # also fetch FFmpeg, Caddy, WinSW
#>
[CmdletBinding()]
param(
    [string]$Root = 'C:\VideoPortal',
    [string]$SourceDir = '',
    [string]$Python = '',
    [switch]$Apply,
    [switch]$Download,
    [switch]$SkipVenv
)
. (Join-Path $PSScriptRoot '_common.ps1')
$ErrorActionPreference = 'Stop'
$paths = Get-PortalPaths -Root $Root
if (-not $SourceDir) { $SourceDir = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path }

$folders = @($paths.Root, $paths.Config, $paths.Logs, (Join-Path $paths.Logs 'services'), $paths.Storage, $paths.Objects,
             $paths.Temporary, $paths.Backups, $paths.Services, $paths.Tools, $paths.CaddyData)
$downloads = @(
    @{ Name = 'FFmpeg'; Url = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'; Target = (Join-Path $paths.Tools 'ffmpeg'); Check = 'bin\ffmpeg.exe' },
    @{ Name = 'Caddy'; Url = 'https://caddyserver.com/api/download?os=windows&arch=amd64'; Target = (Join-Path $paths.Tools 'caddy'); Check = 'caddy.exe' },
    @{ Name = 'WinSW'; Url = 'https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe'; Target = (Join-Path $paths.Tools 'winsw'); Check = 'WinSW-x64.exe' }
)

Write-Step 'Plan'
foreach ($folder in $folders) { if (-not (Test-Path -LiteralPath $folder)) { Write-Host "  create folder  $folder" } }
if (-not (Test-Path -LiteralPath $paths.App)) { Write-Host "  application    copy or clone the repository to $($paths.App) yourself (this script does not move source code)" }
if (-not $SkipVenv -and -not (Test-Path -LiteralPath (Join-Path $paths.Venv 'Scripts\python.exe'))) { Write-Host "  create venv    $($paths.Venv) and install requirements.txt from $SourceDir" }
if (-not (Test-Path -LiteralPath $paths.EnvFile)) { Write-Host "  config         copy .env.example to $($paths.EnvFile) (database password left empty)" }
foreach ($item in $downloads) {
    $present = Test-Path -LiteralPath (Join-Path $item.Target $item.Check)
    if ($present) { Write-Host "  $($item.Name) already present in $($item.Target)" }
    elseif ($Download) { Write-Host "  download       $($item.Name) from $($item.Url)" }
    else { Write-Host "  missing        $($item.Name): re-run with -Download, or place it in $($item.Target) manually" }
}
Write-Host '  NOT done here  PostgreSQL install (run the EDB installer yourself), firewall rules, services (install-services.ps1)'
if (-not (Confirm-Apply $Apply.IsPresent 'folder layout, virtual environment, config template and optional tool downloads')) { exit 0 }

Write-Step 'Creating folders'
foreach ($folder in $folders) {
    if (-not (Test-Path -LiteralPath $folder)) { New-Item -ItemType Directory -Path $folder | Out-Null; Write-Host "  created $folder" }
}

if (-not $SkipVenv) {
    $venvPython = Join-Path $paths.Venv 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venvPython)) {
        Write-Step 'Creating virtual environment'
        $interpreter = Find-Python -Preferred $Python
        $found = if ($interpreter) { (& $interpreter --version 2>&1 | Select-Object -First 1).ToString() } else { 'nothing' }
        if ($found -notmatch 'Python 3\.(\d+)' -or [int]$Matches[1] -lt 12) { throw "Python 3.12 or newer was not found (found: $found). Install Python 3.12 for all users, or pass -Python <path to python.exe>." }
        Write-Host "  using $found at $interpreter"
        & $interpreter -m venv $paths.Venv
        if ($LASTEXITCODE -ne 0) { throw 'python -m venv failed' }
    }
    Write-Step 'Installing Python packages'
    & $venvPython -m pip install --disable-pip-version-check --quiet -r (Join-Path $SourceDir 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'pip install failed; check outbound HTTPS and try again' }
    & $venvPython -m pip check
}

if (-not (Test-Path -LiteralPath $paths.EnvFile)) {
    Write-Step 'Writing config template'
    $template = [System.IO.File]::ReadAllText((Join-Path $SourceDir '.env.example'))
    $template = $template.Replace('C:\VideoPortal', $paths.Root)
    [System.IO.File]::WriteAllText($paths.EnvFile, $template, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "  wrote $($paths.EnvFile). POSTGRES_PASSWORD is empty until setup-database.ps1 runs."
} else { Write-Host "  kept existing $($paths.EnvFile)" }

if ($Download) {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    foreach ($item in $downloads) {
        if (Test-Path -LiteralPath (Join-Path $item.Target $item.Check)) { continue }
        Write-Step "Downloading $($item.Name)"
        New-Item -ItemType Directory -Force -Path $item.Target | Out-Null
        $temporary = Join-Path $paths.Tools ("download-" + [guid]::NewGuid().ToString('N'))
        $unpacked = Join-Path $paths.Tools ("unpack-" + [guid]::NewGuid().ToString('N'))
        try {
            Invoke-WebRequest -Uri $item.Url -OutFile $temporary -UseBasicParsing
            $hash = (Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash
            Write-Host "  SHA256 $hash  <- compare with the value published by the vendor before trusting it"
            if ($item.Name -eq 'FFmpeg') {
                $expected = (Invoke-WebRequest -Uri ($item.Url + '.sha256') -UseBasicParsing).Content.Trim()
                if ($expected -and $expected.ToUpper() -ne $hash) { throw 'FFmpeg archive hash does not match the published .sha256; nothing was installed' }
                # Expand-Archive in PowerShell 5.1 insists on a .zip extension; the .NET call does not.
                Add-Type -AssemblyName System.IO.Compression.FileSystem
                [System.IO.Compression.ZipFile]::ExtractToDirectory($temporary, $unpacked)
                $inner = Get-ChildItem -LiteralPath $unpacked -Directory | Select-Object -First 1
                Copy-Item -Path (Join-Path $inner.FullName '*') -Destination $item.Target -Recurse
            } else {
                Copy-Item -LiteralPath $temporary -Destination (Join-Path $item.Target $item.Check)
            }
        } finally {
            # Only the two temporary items created above are removed.
            if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force -Confirm:$false }
            if (Test-Path -LiteralPath $unpacked) { Remove-Item -LiteralPath $unpacked -Recurse -Force -Confirm:$false }
        }
        $signature = Get-AuthenticodeSignature -LiteralPath (Join-Path $item.Target $item.Check)
        Write-Host "  installed to $($item.Target) (Authenticode: $($signature.Status))"
    }
}

Write-Step 'Done'
Write-Host 'Next: 1) install PostgreSQL 16 with the EDB installer if missing  2) setup-database.ps1  3) install-services.ps1'
