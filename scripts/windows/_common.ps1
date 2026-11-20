# Shared helpers for the Video Portal Windows scripts. Dot-sourced; changes nothing by itself.
Set-StrictMode -Version 2.0

$script:ServiceNames = @('VideoPortal-API', 'VideoPortal-Worker', 'VideoPortal-Caddy')

function Get-PortalPaths {
    param([string]$Root = 'C:\VideoPortal')
    # Layout: the app keeps originals in objects\inputs and finished MP4/JPG in objects\outputs\<job>\<attempt>.
    [ordered]@{
        Root      = $Root
        App       = Join-Path $Root 'app'
        Venv      = Join-Path $Root 'venv'
        Config    = Join-Path $Root 'config'
        EnvFile   = Join-Path $Root 'config\.env'
        Logs      = Join-Path $Root 'logs'
        Storage   = Join-Path $Root 'storage'
        Objects   = Join-Path $Root 'storage\objects'
        Temporary = Join-Path $Root 'storage\temporary'
        Backups   = Join-Path $Root 'backups'
        Services  = Join-Path $Root 'services'
        Tools     = Join-Path $Root 'tools'
        CaddyData = Join-Path $Root 'caddy'
    }
}

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    ([Security.Principal.WindowsPrincipal]$identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Read-EnvFile {
    # Returns a hashtable of KEY=VALUE pairs. Values are never printed by these scripts.
    param([Parameter(Mandatory)][string]$Path)
    $values = @{}
    if (-not (Test-Path -LiteralPath $Path)) { throw "Config file not found: $Path" }
    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        $text = $line.Trim()
        if ($text -eq '' -or $text.StartsWith('#')) { continue }
        $index = $text.IndexOf('=')
        if ($index -lt 1) { continue }
        $values[$text.Substring(0, $index).Trim()] = $text.Substring($index + 1).Trim().Trim('"').Trim("'")
    }
    $values
}

function Get-EnvValue {
    param([hashtable]$Values, [string]$Name, [string]$Default = '')
    if ($Values.ContainsKey($Name) -and $Values[$Name] -ne '') { $Values[$Name] } else { $Default }
}

function Find-Tool {
    # Looks in PATH first, then in the given folders. Returns the full path or $null.
    param([Parameter(Mandatory)][string]$Name, [string[]]$Folders = @())
    $command = Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) { return $command.Source }
    foreach ($folder in $Folders) {
        if (-not $folder) { continue }
        $match = Get-ChildItem -Path $folder -Filter "$Name.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($match) { return $match.FullName }
    }
    $null
}

function Find-Python {
    # Returns the first Python that is 3.12 or newer, preferring an all-users install over whatever
    # "python" on PATH happens to be (a server may already have an older Python that must stay).
    # If none qualifies, returns the first interpreter found so the caller can report its version.
    param([string]$Preferred = '')
    $candidates = @($Preferred, 'C:\Program Files\Python312\python.exe', 'C:\Program Files\Python313\python.exe')
    $launcher = Get-Command 'py' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($launcher) {
        foreach ($version in @('-3.12', '-3.13')) {
            try { $candidates += (& $launcher.Source $version -c 'import sys; print(sys.executable)' 2>$null | Select-Object -First 1) } catch { }
        }
    }
    $onPath = Get-Command 'python' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($onPath) { $candidates += $onPath.Source }
    $existing = @($candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) })
    foreach ($path in $existing) {
        $text = ''
        try { $text = (& $path --version 2>&1 | Select-Object -First 1).ToString() } catch { }
        if ($text -match 'Python 3\.(\d+)' -and [int]$Matches[1] -ge 12) { return $path }
    }
    if ($existing.Count -gt 0) { return $existing[0] }
    $null
}

function Find-PostgresTool {
    param([Parameter(Mandatory)][string]$Name, [string]$BinDir = '')
    $folders = @($BinDir)
    $folders += Get-ChildItem 'C:\Program Files\PostgreSQL' -Directory -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName 'bin' }
    Find-Tool -Name $Name -Folders $folders
}

function Write-Step {
    param([string]$Text)
    Write-Host "==> $Text"
}

function Confirm-Apply {
    # Scripts that change the system only do so with -Apply. Without it they print the plan.
    param([bool]$Apply, [string]$What)
    if (-not $Apply) {
        Write-Host "PLAN ONLY: $What"
        Write-Host 'Nothing was changed. Re-run with -Apply after reviewing the plan.'
        return $false
    }
    $true
}
