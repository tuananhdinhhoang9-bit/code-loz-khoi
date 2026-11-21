<#
.SYNOPSIS
  Restarts the Video Portal services: graceful stop, then start in dependency order.
.EXAMPLE
  .\restart-services.ps1
#>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'stop-services.ps1')
if ($LASTEXITCODE -ne 0) { throw 'A service did not stop; not starting again. Run status.ps1.' }
& (Join-Path $PSScriptRoot 'start-services.ps1')
exit $LASTEXITCODE
