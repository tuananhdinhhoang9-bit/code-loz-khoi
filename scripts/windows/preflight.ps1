<#
.SYNOPSIS
  Read-only readiness check for hosting Video Portal natively on a Windows Server VPS.
.DESCRIPTION
  Installs nothing and changes nothing. Prints PASS / WARN / FAIL per check with a fix hint.
  Network checks (DNS, outbound HTTPS) run only with -AllowNetwork.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\windows\preflight.ps1
  powershell -ExecutionPolicy Bypass -File scripts\windows\preflight.ps1 -AllowNetwork -Domain video.example.com -ReportPath C:\Temp\preflight.json
#>
[CmdletBinding()]
param(
    [string]$Root = 'C:\VideoPortal',
    [string]$PostgresBin = '',
    [int]$ApiPort = 8000,
    [int]$PostgresPort = 5432,
    [switch]$AllowNetwork,
    [string]$Domain = '',
    [string]$ReportPath = ''
)
. (Join-Path $PSScriptRoot '_common.ps1')
$ErrorActionPreference = 'Continue'
$results = New-Object System.Collections.Generic.List[object]

function Add-Check {
    param([ValidateSet('PASS', 'WARN', 'FAIL')][string]$Status, [string]$Name, [string]$Detail, [string]$Fix = '')
    $results.Add([pscustomobject]@{ Status = $Status; Check = $Name; Detail = $Detail; Fix = $Fix })
}

function Get-ToolVersion {
    param([string]$Path, [string[]]$Arguments)
    try { (& $Path @Arguments 2>&1 | Select-Object -First 1).ToString().Trim() } catch { '' }
}

$paths = Get-PortalPaths -Root $Root

# --- Operating system, rights, hardware ---
$os = Get-CimInstance Win32_OperatingSystem
$build = [int]$os.BuildNumber
if ($os.ProductType -eq 1) {
    Add-Check WARN 'Windows edition' "$($os.Caption) build $build is a client edition" 'Production target is Windows Server 2016 or newer; a client edition is fine for a rehearsal only.'
} elseif ($build -lt 14393) {
    Add-Check FAIL 'Windows edition' "$($os.Caption) build $build" 'Windows Server 2016 (build 14393) or newer is required.'
} else {
    Add-Check PASS 'Windows edition' "$($os.Caption) build $build"
}
if (Test-IsAdmin) { Add-Check PASS 'Current rights' 'Running as Administrator' }
else { Add-Check WARN 'Current rights' 'Not elevated' 'Preflight works without elevation, but install-prerequisites.ps1 and install-services.ps1 need an elevated PowerShell.' }

$major = $PSVersionTable.PSVersion.Major; $minor = $PSVersionTable.PSVersion.Minor
if ($major -gt 5 -or ($major -eq 5 -and $minor -ge 1)) { Add-Check PASS 'PowerShell' "Version $($PSVersionTable.PSVersion)" }
else { Add-Check FAIL 'PowerShell' "Version $($PSVersionTable.PSVersion)" 'Install Windows Management Framework 5.1.' }

$cpu = (Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors
if ($cpu -ge 3) { Add-Check PASS 'CPU' "$cpu logical processors" }
elseif ($cpu -eq 2) { Add-Check WARN 'CPU' '2 logical processors' 'Set FFMPEG_THREADS=1 so the API keeps one core while a video is encoding.' }
else { Add-Check FAIL 'CPU' "$cpu logical processor" 'At least 2 are needed to encode video and serve requests at the same time.' }

$totalGb = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
$freeGb = [math]::Round($os.FreePhysicalMemory / 1MB, 1)
if ($totalGb -ge 3.5) { Add-Check PASS 'Memory' "$totalGb GB total, $freeGb GB free" }
elseif ($totalGb -ge 2) { Add-Check WARN 'Memory' "$totalGb GB total, $freeGb GB free" 'Lower WORKER_MEMORY_LIMIT_MB and PostgreSQL shared_buffers; expect slower encodes.' }
else { Add-Check FAIL 'Memory' "$totalGb GB total" 'Less than 2 GB cannot hold PostgreSQL, the API and FFmpeg together.' }
if ($freeGb -lt 1) { Add-Check WARN 'Free memory' "$freeGb GB free right now" 'Find what is using memory (Task Manager) before installing more services.' }

$driveName = [System.IO.Path]::GetPathRoot($Root).TrimEnd('\').TrimEnd(':')
$drive = Get-PSDrive -Name $driveName -ErrorAction SilentlyContinue
if (-not $drive) { Add-Check FAIL 'Disk' "Drive $($driveName): not found" "Choose an existing drive with -Root." }
else {
    $diskFree = [math]::Round($drive.Free / 1GB, 1)
    if ($diskFree -ge 20) { Add-Check PASS 'Disk' "Drive $($driveName): $diskFree GB free" }
    elseif ($diskFree -ge 10) { Add-Check WARN 'Disk' "Drive $($driveName): $diskFree GB free" 'Enough to start; videos, logs and local backups share this space. Plan off-VPS backups and cleanup.' }
    else { Add-Check FAIL 'Disk' "Drive $($driveName): $diskFree GB free" 'Free at least 10 GB or use another drive (-Root).' }
}
if (Test-Path -LiteralPath $Root) {
    $count = @(Get-ChildItem -LiteralPath $Root -Force -ErrorAction SilentlyContinue).Count
    Add-Check WARN 'Target folder' "$Root already exists ($count entries)" 'Existing content is never overwritten by the install scripts; confirm it belongs to this application.'
} else { Add-Check PASS 'Target folder' "$Root does not exist yet" }

$longPaths = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -ErrorAction SilentlyContinue).LongPathsEnabled
if ($longPaths -eq 1) { Add-Check PASS 'Long paths' 'Enabled' }
else { Add-Check WARN 'Long paths' 'Disabled (260 character limit)' "Keep the install root short such as $Root. The app already uses short object names." }

# --- Software ---
$python = Find-Python
if (-not $python) { Add-Check FAIL 'Python' 'python.exe not found' 'Install Python 3.12 (64-bit) from python.org and tick "Install for all users".' }
else {
    $version = Get-ToolVersion $python @('--version')
    if ($version -match 'Python 3\.(\d+)') {
        if ([int]$Matches[1] -lt 12) { Add-Check FAIL 'Python' "$version at $python (no 3.12+ found)" 'Install Python 3.12 (64-bit) from python.org with "Install for all users". It installs side by side; the existing Python can stay and does not need to be removed.' }
        elseif ($python -like "$env:SystemDrive\Users\*") { Add-Check WARN 'Python' "$version at $python" 'This is a per-user install; service accounts cannot read it. Install Python for all users (Program Files).' }
        else { Add-Check PASS 'Python' "$version at $python" }
        $pip = Get-ToolVersion $python @('-m', 'pip', '--version')
        if ($pip -match '^pip ') { Add-Check PASS 'pip' ($pip -replace ' from .*', '') } else { Add-Check FAIL 'pip' 'python -m pip failed' 'Run: python -m ensurepip --upgrade' }
    } else { Add-Check FAIL 'Python' "Unexpected output: $version" 'Disable the Microsoft Store python alias and install Python 3.12 from python.org.' }
}

$psql = Find-PostgresTool 'psql' $PostgresBin
$pgDump = Find-PostgresTool 'pg_dump' $PostgresBin
if (-not $psql -or -not $pgDump) { Add-Check FAIL 'PostgreSQL tools' 'psql/pg_dump not found' 'Install PostgreSQL 16 for Windows (EDB installer) or pass -PostgresBin.' }
else {
    $version = Get-ToolVersion $psql @('--version')
    if ($version -match '(\d+)\.\d+') {
        if ([int]$Matches[1] -ge 14) { Add-Check PASS 'PostgreSQL tools' "$version ($psql)" }
        else { Add-Check FAIL 'PostgreSQL tools' $version 'PostgreSQL 14 or newer is required; the project is tested on 16.' }
    } else { Add-Check WARN 'PostgreSQL tools' "Unexpected output: $version" 'Check the installation.' }
}
$pgServices = @(Get-Service -Name 'postgresql*' -ErrorAction SilentlyContinue)
if ($pgServices.Count -eq 0) { Add-Check FAIL 'PostgreSQL service' 'No postgresql* Windows service' 'Install PostgreSQL as a Windows service; the application does not start its own database.' }
else {
    foreach ($service in $pgServices) {
        if ($service.Status -eq 'Running') { Add-Check PASS 'PostgreSQL service' "$($service.Name) is running ($($service.StartType))" }
        else { Add-Check WARN 'PostgreSQL service' "$($service.Name) is $($service.Status)" "Start it when ready: Start-Service $($service.Name)" }
    }
}

foreach ($tool in @('ffmpeg', 'ffprobe')) {
    $path = Find-Tool $tool @((Join-Path $paths.Tools 'ffmpeg\bin'))
    if (-not $path) { Add-Check FAIL $tool "$tool.exe not found" "Unpack an FFmpeg Windows build into $($paths.Tools)\ffmpeg (install-prerequisites.ps1 can do this)." }
    else {
        Add-Check PASS $tool ((Get-ToolVersion $path @('-version')) -replace ' Copyright.*', '')
        if ($path -like "$env:SystemDrive\Users\*") { Add-Check WARN "$tool location" $path "A per-user path is not readable by service accounts. Copy FFmpeg to $($paths.Tools)\ffmpeg and set FFMPEG_BIN/FFPROBE_BIN." }
        if ($tool -eq 'ffmpeg') {
            $encoders = (& $path -hide_banner -encoders 2>&1 | Out-String)
            if ($encoders -match 'libx264' -and $encoders -match '\baac\b') { Add-Check PASS 'FFmpeg encoders' 'libx264 and aac available' }
            else { Add-Check FAIL 'FFmpeg encoders' 'libx264 or aac missing' 'Use a full/essentials GPL build (gyan.dev or BtbN); LGPL builds lack libx264.' }
        }
    }
}

$git = Find-Tool 'git' @('C:\Program Files\Git\cmd')
if ($git) { Add-Check PASS 'Git' (Get-ToolVersion $git @('--version')) } else { Add-Check WARN 'Git' 'git.exe not found' 'Needed only to pull updates; alternatively copy a release ZIP to the server.' }
$caddy = Find-Tool 'caddy' @((Join-Path $paths.Tools 'caddy'))
if ($caddy) { Add-Check PASS 'Caddy' (Get-ToolVersion $caddy @('version')) } else { Add-Check WARN 'Caddy' 'caddy.exe not found' "Place caddy.exe in $($paths.Tools)\caddy (install-prerequisites.ps1 -Download)." }
$winsw = Find-Tool 'WinSW-x64' @((Join-Path $paths.Tools 'winsw'))
if ($winsw) { Add-Check PASS 'WinSW' $winsw } else { Add-Check WARN 'WinSW' 'WinSW-x64.exe not found' "Place WinSW-x64.exe (v2.12.0) in $($paths.Tools)\winsw (install-prerequisites.ps1 -Download)." }

# --- Ports, firewall, services ---
$listeners = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue)
function Get-Listener { param([int]$Port) @($listeners | Where-Object { $_.LocalPort -eq $Port }) }
function Get-OwnerName { param($Connection) try { (Get-Process -Id $Connection.OwningProcess -ErrorAction Stop).ProcessName } catch { "pid $($Connection.OwningProcess)" } }

foreach ($port in @(80, 443)) {
    $used = @(Get-Listener $port)
    if ($used.Count -eq 0) { Add-Check PASS "TCP $port" 'Free for Caddy' }
    else {
        $owner = Get-OwnerName $used[0]
        if ($owner -eq 'caddy') { Add-Check PASS "TCP $port" 'Already served by caddy' }
        else { Add-Check FAIL "TCP $port" "In use by $owner" 'Caddy needs this port. If it is IIS (System/http.sys), stop the Default Web Site or remove the IIS role after approval.' }
    }
}
$used = @(Get-Listener $ApiPort)
if ($used.Count -eq 0) { Add-Check PASS "TCP $ApiPort" 'Free for the API (loopback only)' }
else {
    $owner = Get-OwnerName $used[0]
    $addresses = ($used | ForEach-Object { $_.LocalAddress } | Sort-Object -Unique) -join ', '
    if ($owner -match 'python') { Add-Check WARN "TCP $ApiPort" "Already used by $owner on $addresses" 'Fine if this is the Video Portal API; otherwise set BIND_PORT to a free port.' }
    else { Add-Check FAIL "TCP $ApiPort" "In use by $owner on $addresses" 'Set BIND_PORT in the config and the Caddyfile upstream to a free port.' }
}
$used = @(Get-Listener $PostgresPort)
if ($used.Count -eq 0) { Add-Check WARN "TCP $PostgresPort" 'Nothing is listening' 'Expected once PostgreSQL runs. If it uses another port, pass -PostgresPort.' }
else {
    $addresses = @($used | ForEach-Object { $_.LocalAddress } | Sort-Object -Unique)
    $public = @($addresses | Where-Object { $_ -notin @('127.0.0.1', '::1') })
    if ($public.Count -eq 0) { Add-Check PASS "TCP $PostgresPort" 'PostgreSQL listens on loopback only' }
    else { Add-Check WARN "TCP $PostgresPort" "Listening on $($addresses -join ', ')" "Set listen_addresses = 'localhost' in postgresql.conf and restart PostgreSQL during a maintenance window. Never allow $PostgresPort through the firewall." }
}

try {
    $profiles = @(Get-NetFirewallProfile -ErrorAction Stop)
    $disabled = @($profiles | Where-Object { -not $_.Enabled })
    $portFilters = @(Get-NetFirewallRule -Enabled True -Direction Inbound -Action Allow -ErrorAction Stop | Get-NetFirewallPortFilter -ErrorAction SilentlyContinue)
    if ($disabled.Count -eq 0) {
        Add-Check PASS 'Windows Firewall' 'Enabled on all profiles'
        foreach ($port in @(80, 443)) {
            if ($portFilters | Where-Object { $_.Protocol -eq 'TCP' -and ($_.LocalPort -contains "$port") }) { Add-Check PASS "Firewall inbound $port" 'An allow rule exists' }
            else { Add-Check WARN "Firewall inbound $port" 'No allow rule' "Needed for public HTTPS. Add only after approval: New-NetFirewallRule -DisplayName 'VideoPortal HTTP(S)' -Direction Inbound -Protocol TCP -LocalPort 80,443 -Action Allow" }
        }
        foreach ($port in @($PostgresPort, $ApiPort)) {
            if ($portFilters | Where-Object { $_.Protocol -eq 'TCP' -and ($_.LocalPort -contains "$port") }) { Add-Check WARN "Firewall inbound $port" 'An inbound allow rule exists' "This port must stay private. Review and remove the rule after approval." }
            else { Add-Check PASS "Firewall inbound $port" 'Not allowed from outside' }
        }
    } else {
        # With the firewall off, allow rules mean nothing: every listening port is reachable unless
        # something outside Windows (the provider's network firewall) filters it.
        $names = ($disabled | ForEach-Object { $_.Name }) -join ', '
        Add-Check WARN 'Windows Firewall' "Disabled on: $names" 'Every port a program listens on is reachable from the network unless the VPS provider filters it. Decide before installing PostgreSQL: either confirm a provider-level firewall allows only RDP/80/443, or enable Windows Firewall AFTER checking that the Remote Desktop rule is enabled for the port you connect on (enabling it blindly can lock you out of RDP). This script never changes firewall state.'
        Add-Check WARN 'Firewall port rules' 'Not evaluated because the firewall is disabled' "Ports $PostgresPort and $ApiPort are protected only by the services listening on loopback. Set PostgreSQL listen_addresses = 'localhost' immediately after installing it."
        $rdp = @(Get-NetFirewallRule -DisplayGroup 'Remote Desktop' -ErrorAction SilentlyContinue | Where-Object { $_.Direction -eq 'Inbound' })
        $rdpOn = @($rdp | Where-Object { $_.Enabled -eq 'True' })
        $rdpPort = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp' -Name PortNumber -ErrorAction SilentlyContinue).PortNumber
        Add-Check WARN 'Remote Desktop rule' "RDP port $rdpPort; built-in 'Remote Desktop' inbound rules enabled: $($rdpOn.Count) of $($rdp.Count)" 'Before enabling the firewall, an enabled inbound allow rule must cover this RDP port on the active network profile. The built-in rules cover only port 3389.'
    }
} catch { Add-Check WARN 'Windows Firewall' 'Could not read firewall state' 'Run elevated to inspect firewall rules.' }

$iis = Get-Service -Name 'W3SVC' -ErrorAction SilentlyContinue
if ($iis -and $iis.Status -eq 'Running') { Add-Check WARN 'IIS (W3SVC)' 'Running' 'IIS holds ports 80/443. Stop it only after confirming nothing else depends on it.' }
foreach ($name in $script:ServiceNames) {
    $service = Get-Service -Name $name -ErrorAction SilentlyContinue
    if ($service) { Add-Check WARN "Service $name" "Already installed ($($service.Status))" 'install-services.ps1 will refuse to replace it; use stop-services.ps1 and uninstall deliberately.' }
    else { Add-Check PASS "Service $name" 'Not installed yet' }
}
$defender = Get-Service -Name 'WinDefend' -ErrorAction SilentlyContinue
if ($defender) { Add-Check PASS 'Microsoft Defender' "Service is $($defender.Status) (left unchanged)" }

# --- Network (opt-in) ---
if ($AllowNetwork) {
    try { $null = Resolve-DnsName 'github.com' -Type A -ErrorAction Stop; Add-Check PASS 'DNS' 'Resolved github.com' }
    catch { Add-Check FAIL 'DNS' 'Could not resolve github.com' 'Check the DNS servers of the network adapter.' }
    $https = Test-NetConnection -ComputerName 'github.com' -Port 443 -WarningAction SilentlyContinue
    if ($https.TcpTestSucceeded) { Add-Check PASS 'Outbound HTTPS' 'github.com:443 reachable' }
    else { Add-Check WARN 'Outbound HTTPS' 'github.com:443 not reachable' 'Outbound 443 is needed for pip, updates and public certificates (ACME).' }
    if ($Domain) {
        try {
            $records = @(Resolve-DnsName $Domain -Type A -ErrorAction Stop | Where-Object { $_.Type -eq 'A' } | ForEach-Object { $_.IPAddress })
            $local = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | ForEach-Object { $_.IPAddress })
            if ($records | Where-Object { $_ -in $local }) { Add-Check PASS "Domain $Domain" "Points to this server ($($records -join ', '))" }
            else { Add-Check WARN "Domain $Domain" "Resolves to $($records -join ', '), not an address of this server" 'Correct the A record, or ignore this if the VPS sits behind NAT with that public IP. A public certificate needs the name to reach this server on ports 80/443.' }
        } catch { Add-Check FAIL "Domain $Domain" 'No A record' 'Create an A record pointing to the VPS public IP before requesting a public certificate.' }
    }
} else {
    Add-Check WARN 'Network checks' 'Skipped' 'Re-run with -AllowNetwork (and -Domain your.name) to test DNS and outbound HTTPS.'
}

# --- Report ---
$results | Sort-Object @{ Expression = { @('FAIL', 'WARN', 'PASS').IndexOf($_.Status) } }, Check | Format-Table Status, Check, Detail -AutoSize -Wrap | Out-String -Width 200 | Write-Host
$needFix = @($results | Where-Object { $_.Status -ne 'PASS' -and $_.Fix })
if ($needFix.Count -gt 0) {
    Write-Host 'How to fix:'
    foreach ($item in $needFix) { Write-Host "  [$($item.Status)] $($item.Check): $($item.Fix)" }
}
$summary = "PASS=$(@($results | Where-Object Status -eq 'PASS').Count) WARN=$(@($results | Where-Object Status -eq 'WARN').Count) FAIL=$(@($results | Where-Object Status -eq 'FAIL').Count)"
Write-Host ''
Write-Host "Preflight summary: $summary"
if ($ReportPath) {
    $results | ConvertTo-Json -Depth 3 | Out-File -LiteralPath $ReportPath -Encoding utf8
    Write-Host "Report written to $ReportPath"
}
if (@($results | Where-Object Status -eq 'FAIL').Count -gt 0) { exit 1 }
exit 0
