<#
.SYNOPSIS
  Runs the whole stack as ordinary foreground processes (no services, no firewall change, loopback
  only) and executes the end-to-end smoke test through Caddy with its internal certificate.
.DESCRIPTION
  For a safe rehearsal before installing services. It starts Waitress (API), the FFmpeg worker and
  Caddy on https://localhost:<HttpsPort>, creates a throw-away account, uploads a generated clip,
  waits for processing, plays it back with Range, measures peak memory/CPU of each process, then
  stops everything it started. Nothing is installed and no port is opened to other machines by this
  script (Caddy listens on the chosen port; Windows Firewall is left as it is).
  Requires: a config file with APP_ENV=production and a working database (setup-database.ps1).
.EXAMPLE
  .\rehearsal.ps1 -Root C:\VideoPortal -Python C:\VideoPortal\venv\Scripts\python.exe
#>
[CmdletBinding()]
param(
    [string]$Root = 'C:\VideoPortal',
    [string]$EnvFile = '',
    [string]$AppDir = '',
    [string]$Python = '',
    [string]$CaddyExe = '',
    [string]$FfmpegExe = '',
    [int]$HttpsPort = 8443,
    [int]$ClipSeconds = 30,
    [switch]$KeepClip
)
. (Join-Path $PSScriptRoot '_common.ps1')
$ErrorActionPreference = 'Stop'
$paths = Get-PortalPaths -Root $Root
if (-not $EnvFile) { $EnvFile = $paths.EnvFile }
if (-not $AppDir) { $AppDir = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path }
if (-not $Python) { $Python = Join-Path $paths.Venv 'Scripts\python.exe' }
if (-not $CaddyExe) { $CaddyExe = Find-Tool 'caddy' @((Join-Path $paths.Tools 'caddy')) }
if (-not $FfmpegExe) { $FfmpegExe = Find-Tool 'ffmpeg' @((Join-Path $paths.Tools 'ffmpeg\bin')) }
foreach ($required in @($EnvFile, $Python, $CaddyExe, $FfmpegExe)) {
    if (-not $required -or -not (Test-Path -LiteralPath $required)) { throw "Missing prerequisite: $required" }
}
$config = Read-EnvFile $EnvFile
$apiPort = Get-EnvValue $config 'BIND_PORT' '8000'
$work = Join-Path $paths.Root 'rehearsal'
New-Item -ItemType Directory -Force -Path $work | Out-Null
$env:VIDEO_PORTAL_ENV_FILE = $EnvFile
$env:PYTHONUNBUFFERED = '1'
$started = New-Object System.Collections.Generic.List[object]

function Start-Background {
    param([string]$Name, [string]$File, [string[]]$Arguments, [string]$Directory)
    $process = Start-Process -FilePath $File -ArgumentList $Arguments -WorkingDirectory $Directory -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $work "$Name.out.log") -RedirectStandardError (Join-Path $work "$Name.err.log")
    $started.Add([pscustomobject]@{ Name = $Name; Id = $process.Id })
    Write-Host "  started $Name (pid $($process.Id))"
}

function Get-Tree {
    # All process ids below the given root, found through ParentProcessId.
    param([int]$RootId, $All)
    $ids = @($RootId)
    foreach ($child in @($All | Where-Object { $_.ParentProcessId -eq $RootId })) { $ids += Get-Tree -RootId $child.ProcessId -All $All }
    $ids
}

$exitCode = 1
try {
    Write-Step 'Preparing schema, account and test clip'
    Push-Location $AppDir
    & $Python -m flask --app app.main init-db
    if ($LASTEXITCODE -ne 0) { throw 'init-db failed' }
    $bytes = New-Object byte[] 18
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $env:SMOKE_PASSWORD = [Convert]::ToBase64String($bytes)
    $email = "rehearsal-$([guid]::NewGuid().ToString('N').Substring(0, 8))@example.com"
    $env:SMOKE_EMAIL = $email
    & $Python -c "import os; from app.main import create_app; from app.auth_local import create_user; create_user(create_app().extensions['db_engine'], os.environ['SMOKE_EMAIL'], os.environ['SMOKE_PASSWORD'])"
    if ($LASTEXITCODE -ne 0) { throw 'could not create the rehearsal account' }
    Pop-Location
    $clip = Join-Path $work 'clip.mp4'
    if (-not (Test-Path -LiteralPath $clip)) {
        & $FfmpegExe -nostdin -v error -f lavfi -i "testsrc2=size=1280x720:rate=30" -f lavfi -i "sine=frequency=440:sample_rate=44100" -t $ClipSeconds -c:v libx264 -preset ultrafast -crf 28 -c:a aac -shortest $clip
        if ($LASTEXITCODE -ne 0) { throw 'could not generate the test clip' }
    }
    Write-Host "  clip: $([math]::Round((Get-Item -LiteralPath $clip).Length / 1MB, 2)) MB, $ClipSeconds s, 1280x720"

    Write-Step 'Starting API, worker and Caddy (loopback rehearsal)'
    $caddyfile = Join-Path $work 'Caddyfile'
    $template = [System.IO.File]::ReadAllText((Join-Path $AppDir 'deploy\windows\Caddyfile'))
    $template = $template.Replace("admin 127.0.0.1:2019", "admin 127.0.0.1:2021`r`n`tauto_https disable_redirects")
    $template = $template.Replace("`nlocalhost {", "`nlocalhost:$HttpsPort {").Replace('127.0.0.1:8000', "127.0.0.1:$apiPort")
    [System.IO.File]::WriteAllText($caddyfile, $template, (New-Object System.Text.UTF8Encoding($false)))
    $env:XDG_DATA_HOME = Join-Path $work 'caddy-data'
    $env:XDG_CONFIG_HOME = Join-Path $work 'caddy-data'
    $env:VIDEOPORTAL_LOGS = $work
    Start-Background 'api' $Python @('-m', 'app.serve') $AppDir
    Start-Background 'worker' $Python @('-m', 'app.worker_service') $AppDir
    Start-Background 'caddy' $CaddyExe @('run', '--config', "`"$caddyfile`"", '--adapter', 'caddyfile') $work

    $base = "https://localhost:$HttpsPort"
    $ready = $false
    foreach ($attempt in 1..60) {
        $code = & curl.exe -k -s -o NUL -w '%{http_code}' "$base/health"
        if ($code -eq '200') { $ready = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw "The stack did not answer on $base/health. See logs in $work." }
    Write-Host "  $base/health -> 200 through Caddy"

    Write-Step 'Running the smoke test and sampling resources'
    # Start-Process joins arguments with spaces, so paths that may contain spaces are quoted here.
    $smokeArgs = @("`"$(Join-Path $AppDir 'scripts\smoke_test.py')`"", '--base-url', $base, '--email', $email, '--clip', "`"$clip`"", '--insecure')
    if ($KeepClip) { $smokeArgs += '--keep' }
    $smoke = Start-Process -FilePath $Python -ArgumentList $smokeArgs -WorkingDirectory $AppDir -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $work 'smoke.out.log') -RedirectStandardError (Join-Path $work 'smoke.err.log')
    # Reading Handle now keeps the exit code available after the process ends (PowerShell 5.1 quirk).
    $null = $smoke.Handle
    $peak =@{ api = 0; worker = 0; ffmpeg = 0; caddy = 0; postgres = 0 }
    $ffmpegCpu = 0.0; $ffmpegFirst = $null; $ffmpegLast = $null
    while (-not $smoke.HasExited) {
        $all = @(Get-CimInstance Win32_Process -Property ProcessId, ParentProcessId, Name)
        foreach ($item in $started) {
            $ids = Get-Tree -RootId $item.Id -All $all
            $own = @(Get-Process -Id $ids -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -notmatch 'ffmpeg|ffprobe' })
            $sum = 0
            foreach ($process in $own) { $sum += $process.WorkingSet64 }
            if ($sum -gt $peak[$item.Name]) { $peak[$item.Name] = $sum }
            if ($item.Name -eq 'worker') {
                $encoders = @(Get-Process -Id $ids -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -eq 'ffmpeg' })
                foreach ($encoder in $encoders) {
                    if ($encoder.WorkingSet64 -gt $peak.ffmpeg) { $peak.ffmpeg = $encoder.WorkingSet64 }
                    if ($encoder.TotalProcessorTime.TotalSeconds -gt $ffmpegCpu) { $ffmpegCpu = $encoder.TotalProcessorTime.TotalSeconds }
                    if (-not $ffmpegFirst) { $ffmpegFirst = Get-Date }
                    $ffmpegLast = Get-Date
                }
            }
        }
        $database = 0
        foreach ($process in @(Get-Process -Name postgres -ErrorAction SilentlyContinue)) { $database += $process.WorkingSet64 }
        if ($database -gt $peak.postgres) { $peak.postgres = $database }
        Start-Sleep -Milliseconds 400
    }
    Get-Content (Join-Path $work 'smoke.out.log') | ForEach-Object { Write-Host "  $_" }
    $smoke.WaitForExit()
    $exitCode = $smoke.ExitCode

    Write-Step 'Measured on this machine (not a VPS benchmark)'
    foreach ($name in @('api', 'worker', 'ffmpeg', 'caddy', 'postgres')) { Write-Host ("  peak working set {0,-9} {1,7:N0} MB" -f $name, ($peak[$name] / 1MB)) }
    if ($ffmpegFirst) {
        $wall = [math]::Max(0.4, ($ffmpegLast - $ffmpegFirst).TotalSeconds)
        Write-Host ("  ffmpeg CPU time {0:N1} s over about {1:N1} s observed ({2:N1} cores average)" -f $ffmpegCpu, $wall, ($ffmpegCpu / $wall))
    }

    Write-Step 'Proxy checks'
    $limit = [int64](Get-EnvValue $config 'MAX_UPLOAD_BYTES' '50000000')
    $big = Join-Path $work 'too-big.bin'
    if (-not (Test-Path -LiteralPath $big)) { & fsutil file createnew $big 215000000 | Out-Null }
    $code = & curl.exe -k -s -o NUL -w '%{http_code}' -X PUT -H 'Content-Type: video/mp4' --data-binary "@$big" "$base/local-storage/upload?ticket=rehearsal-not-a-real-ticket"
    Write-Host "  215 MB request body (app limit $limit bytes, Caddy 201MB) -> HTTP $code (expected 413)"
    if ($code -ne '413') { $exitCode = 1 }
    Start-Sleep -Seconds 1
    $access = Join-Path $work 'caddy-access.log'
    $leak = (Test-Path -LiteralPath $access) -and (Select-String -LiteralPath $access -Pattern 'ticket=[A-Za-z0-9]' -Quiet)
    Write-Host "  Caddy access log contains storage tickets: $leak (expected False)"
    if ($leak) { $exitCode = 1 }
    $headers = & curl.exe -k -s -D - -o NUL "$base/"
    Write-Host "  security headers: HSTS=$([bool]($headers -match 'Strict-Transport-Security')) X-Frame-Options=$([bool]($headers -match 'X-Frame-Options')) Server-hidden=$(-not [bool]($headers -match '(?m)^Server:'))"
} finally {
    if ((Get-Location).Path -eq $AppDir) { Pop-Location }
    Write-Step 'Stopping rehearsal processes'
    foreach ($item in $started) {
        & taskkill /PID $item.Id /T /F 2>&1 | Out-Null
        Write-Host "  stopped $($item.Name)"
    }
    foreach ($name in @('SMOKE_PASSWORD', 'SMOKE_EMAIL', 'VIDEO_PORTAL_ENV_FILE', 'XDG_DATA_HOME', 'XDG_CONFIG_HOME', 'VIDEOPORTAL_LOGS')) { Remove-Item "Env:$name" -ErrorAction SilentlyContinue }
}
if ($exitCode -eq 0) { Write-Host 'REHEARSAL OK' } else { Write-Host "REHEARSAL FAILED - see logs in $work" }
exit $exitCode
