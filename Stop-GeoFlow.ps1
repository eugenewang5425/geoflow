$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
function Invoke-Wsl {
    param([Parameter(Mandatory = $true)][string[]]$WslArgs)
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & wsl.exe -d Ubuntu-24.04 --exec @WslArgs 2>$null } finally { $ErrorActionPreference = $old }
}
$linuxRoot = (Invoke-Wsl -WslArgs @('wslpath','-u', $projectRoot.Replace('\','/'))).Trim()
Invoke-Wsl -WslArgs @('bash',"$linuxRoot/scripts/hadoop.sh",'stop')
$apiPidPath = Join-Path $projectRoot '.runtime\api.pid'
if (Test-Path -LiteralPath $apiPidPath) {
    $candidate = Get-CimInstance Win32_Process -Filter "ProcessId=$([int](Get-Content $apiPidPath))"
    if ($candidate -and $candidate.ExecutablePath -eq (Join-Path $projectRoot '.venv\Scripts\python.exe') -and $candidate.CommandLine -match 'geoflow.*serve') {
        Stop-Process -Id $candidate.ProcessId
    }
}
$marker = Join-Path $projectRoot '.runtime\session-active'
if (Test-Path -LiteralPath $marker) { Remove-Item -LiteralPath $marker }
Write-Host 'GeoFlow services stopped. Source data, HDFS blocks and experiment results are preserved.'
