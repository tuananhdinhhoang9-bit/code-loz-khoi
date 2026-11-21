# Dung cho dien tap loi tren Azure: dung lan chay dang Running cua job chuyen ma (Container Apps Job).
# Mac dinh chi liet ke; chi dung that khi co -Apply. Can phien `az login` cua nguoi co quyen tren resource group.
#   powershell -File scripts\azure\Stop-TranscodeExecution.ps1                 # xem lan chay nao dang Running
#   powershell -File scripts\azure\Stop-TranscodeExecution.ps1 -Apply          # dung lan chay do
param(
  [string]$ResourceGroup = 'videoportal-rg',
  [string]$Job = 'videoportal-transcode',
  # Lenh goi Azure CLI. Mac dinh la `az` tren PATH; co the tro toi python.exe cua ban CLI giai nen.
  [string]$AzPython = '',
  [switch]$Apply
)

function Invoke-Az {
  if ($AzPython) { & $AzPython -IBm azure.cli @args } else { & az @args }
}

$all = Invoke-Az containerapp job execution list --name $Job --resource-group $ResourceGroup -o json | Out-String | ConvertFrom-Json
$running = @($all | Where-Object { $_.properties.status -eq 'Running' })
$now = (Get-Date).ToUniversalTime().ToString('HH:mm:ss')
if ($running.Count -eq 0) {
  Write-Output "$($now)Z no Running execution of $Job"
  exit 2
}
foreach ($execution in $running) {
  Write-Output "$($now)Z Running: $($execution.name) started $($execution.properties.startTime)"
}
if (-not $Apply) {
  Write-Output 'Plan only. Add -Apply to stop it.'
  exit 0
}
foreach ($execution in $running) {
  Invoke-Az containerapp job stop --name $Job --resource-group $ResourceGroup --job-execution-name $execution.name --no-wait | Out-Null
  Write-Output "$((Get-Date).ToUniversalTime().ToString('HH:mm:ss'))Z stop requested for $($execution.name) (exit code $LASTEXITCODE)"
}
exit 0
