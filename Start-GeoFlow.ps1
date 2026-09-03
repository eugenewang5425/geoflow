param([switch]$SkipCluster)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run uv sync --no-install-project first.' }
New-Item -ItemType Directory -Force -Path (Join-Path $projectRoot 'logs') | Out-Null

function Invoke-Wsl {
    param([Parameter(Mandatory = $true)][string[]]$WslArgs, [string]$User)
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        if ($User) { & wsl.exe -d Ubuntu-24.04 --user $User --exec @WslArgs 2>$null }
        else { & wsl.exe -d Ubuntu-24.04 --exec @WslArgs 2>$null }
    } finally { $ErrorActionPreference = $old }
}

$linuxRoot = (Invoke-Wsl -WslArgs @('wslpath','-u', $projectRoot.Replace('\','/'))).Trim()
if (-not $SkipCluster) {
    $sessionMarker = Join-Path $projectRoot '.runtime\session-active'
    Set-Content -LiteralPath $sessionMarker -Value 'GeoFlow WSL session' -Encoding utf8
    $pidPath = Join-Path $projectRoot '.runtime\session.pid'
    $existing = if (Test-Path $pidPath) { Get-Process -Id ([int](Get-Content $pidPath)) -ErrorAction SilentlyContinue } else { $null }
    if (-not $existing) {
        foreach ($name in @('session-start','session-ready','session-failed')) {
            $candidate = Join-Path $projectRoot ".runtime\$name"
            if (Test-Path -LiteralPath $candidate) { Remove-Item -LiteralPath $candidate }
        }
        $keeper = Start-Process -FilePath 'wsl.exe' -ArgumentList @('-d','Ubuntu-24.04','--exec','bash',"$linuxRoot/scripts/keepalive.sh") -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'logs\wsl-session.out.log') -RedirectStandardError (Join-Path $projectRoot 'logs\wsl-session.err.log')
        Set-Content -LiteralPath $pidPath -Value $keeper.Id
        for ($i = 1; $i -le 20; $i++) {
            Invoke-Wsl -WslArgs @('mountpoint','-q',"$linuxRoot/.runtime/posix")
            if ($LASTEXITCODE -eq 0) { break }
            Invoke-Wsl -User 'root' -WslArgs @('mkdir','-p',"$linuxRoot/.runtime/posix")
            $uid = (Invoke-Wsl -WslArgs @('id','-u')).Trim()
            $gid = (Invoke-Wsl -WslArgs @('id','-g')).Trim()
            Invoke-Wsl -User 'root' -WslArgs @('mount','-t','tmpfs','-o',"size=2G,mode=0755,uid=$uid,gid=$gid",'geoflow-yarn',"$linuxRoot/.runtime/posix")
            if ($LASTEXITCODE -eq 0) { break }
            Start-Sleep -Seconds 2
        }
        Invoke-Wsl -WslArgs @('mountpoint','-q',"$linuxRoot/.runtime/posix")
        if ($LASTEXITCODE -ne 0) {
            $uid = (Invoke-Wsl -WslArgs @('id','-u')).Trim()
            $gid = (Invoke-Wsl -WslArgs @('id','-g')).Trim()
            Invoke-Wsl -User 'root' -WslArgs @('mount','-t','tmpfs','-o',"size=2G,mode=0755,uid=$uid,gid=$gid",'geoflow-yarn',"$linuxRoot/.runtime/posix")
            if ($LASTEXITCODE -ne 0) { throw 'Failed to create the isolated YARN POSIX workspace.' }
        }
        Invoke-Wsl -WslArgs @('python3',"$linuxRoot/scripts/configure_hadoop.py")
        New-Item -ItemType File -Force -Path (Join-Path $projectRoot '.runtime\session-start') | Out-Null
        $ready = Join-Path $projectRoot '.runtime\session-ready'
        $failed = Join-Path $projectRoot '.runtime\session-failed'
        foreach ($attempt in 1..300) {
            if (Test-Path -LiteralPath $ready) { break }
            if ((Test-Path -LiteralPath $failed) -or $keeper.HasExited) { throw 'Hadoop startup failed. Inspect logs/session-start.log.' }
            Start-Sleep -Seconds 1
        }
        if (-not (Test-Path -LiteralPath $ready)) { throw 'Hadoop startup timed out. Inspect logs/session-start.log.' }
    } elseif (-not (Test-Path -LiteralPath (Join-Path $projectRoot '.runtime\session-ready'))) {
        throw 'A stale GeoFlow WSL session was found. Run Stop-GeoFlow.ps1 once, then start again.'
    }
}
$apiPidPath = Join-Path $projectRoot '.runtime\api.pid'
$apiProcess = if (Test-Path $apiPidPath) { Get-Process -Id ([int](Get-Content $apiPidPath)) -ErrorAction SilentlyContinue } else { $null }
if (-not $apiProcess) {
    $apiProcess = Start-Process -FilePath $pythonExe -ArgumentList @('-m','geoflow','serve') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'logs\api.out.log') -RedirectStandardError (Join-Path $projectRoot 'logs\api.err.log')
    Set-Content -LiteralPath $apiPidPath -Value $apiProcess.Id
}
Write-Host 'GeoFlow: http://127.0.0.1:8765'
Write-Host 'HDFS: http://127.0.0.1:19870 | YARN: http://127.0.0.1:18088 | History: http://127.0.0.1:19888'
