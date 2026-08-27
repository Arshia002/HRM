param(
    [Parameter(Mandatory=$true)][string]$Installer,
    [string]$LogPath = ""
)

$ErrorActionPreference = "Stop"
$TranscriptStarted = $false
if ($LogPath) {
    $LogPath = [IO.Path]::GetFullPath($LogPath)
    New-Item -ItemType Directory -Force -Path (Split-Path $LogPath) | Out-Null
    Start-Transcript -Path $LogPath -Force | Out-Null
    $TranscriptStarted = $true
}

$ArtifactDir = if ($LogPath) { Split-Path $LogPath } else { Split-Path ([IO.Path]::GetFullPath($Installer)) }
$SetupLog = Join-Path $ArtifactDir "setup-install.log"
$UpgradeSetupLog = Join-Path $ArtifactDir "setup-upgrade.log"
$ServiceConfigLog = Join-Path $ArtifactDir "service-config.txt"
$ServiceStateLog = Join-Path $ArtifactDir "service-state.txt"
$ServiceCimLog = Join-Path $ArtifactDir "service-cim.json"
$AclLog = Join-Path $ArtifactDir "data-acl.txt"
$FailureSummaryLog = Join-Path $ArtifactDir "install-failure-summary.txt"
$DiagnosticCopyLog = Join-Path $ArtifactDir "diagnostic-copy-errors.txt"
$HrmData = Join-Path $env:ProgramData "HRM-Kermanshah"
$BuildManifestPath = Join-Path $ArtifactDir "build-manifest.json"

function Invoke-CheckedProcess {
    param(
        [Parameter(Mandatory=$true)][string]$FilePath,
        [string[]]$ArgumentList = @(),
        [Parameter(Mandatory=$true)][string]$Stage,
        [int]$TimeoutSeconds = 180,
        [switch]$NoNewWindow
    )
    Write-Host "[$(Get-Date -Format o)] START: $Stage"
    $start = @{
        FilePath = $FilePath
        ArgumentList = $ArgumentList
        PassThru = $true
    }
    if ($NoNewWindow) { $start["NoNewWindow"] = $true }
    $process = Start-Process @start
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        Write-Host "[$(Get-Date -Format o)] TIMEOUT: $Stage (PID $($process.Id))"
        & "$env:SystemRoot\System32\taskkill.exe" /PID $process.Id /T /F | Out-Host
        throw "$Stage timed out after $TimeoutSeconds seconds. The process tree was terminated."
    }
    $process.Refresh()
    if ($process.ExitCode -ne 0) {
        throw "$Stage failed with exit code $($process.ExitCode)."
    }
    Write-Host "[$(Get-Date -Format o)] PASS: $Stage"
}

try {
    $Installer = (Resolve-Path $Installer).Path
    if (-not (Test-Path $BuildManifestPath)) { throw 'Build manifest is missing.' }
    $ExpectedVersion = (Get-Content -LiteralPath $BuildManifestPath -Raw | ConvertFrom-Json).version
    if (-not $ExpectedVersion) { throw 'Build manifest does not contain a product version.' }
    $Target = Join-Path $env:ProgramFiles "HRM"
    $LegacyData = Join-Path $env:ProgramData "HRM"
    $LegacyDatabase = Join-Path $LegacyData "hrm.sqlite"

    # A poisoned legacy path proves the new installer never opens or migrates it.
    New-Item -ItemType Directory -Force -Path $LegacyData | Out-Null
    [IO.File]::WriteAllText($LegacyDatabase, "legacy-sentinel-must-remain-untouched")
    $LegacyHash = (Get-FileHash $LegacyDatabase -Algorithm SHA256).Hash

    Invoke-CheckedProcess -FilePath $Installer `
        -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/TYPE=full', "/LOG=`"$SetupLog`"") `
        -Stage 'Silent full Setup installation' -TimeoutSeconds 240

    $service = Get-Service HRMCentralService -ErrorAction Stop
    if ($service.Status -ne 'Running') {
        Start-Service HRMCentralService
        $service.WaitForStatus('Running', [TimeSpan]::FromSeconds(20))
    }
    $serviceInfo = Get-CimInstance Win32_Service -Filter "Name='HRMCentralService'"
    if (-not $serviceInfo -or $serviceInfo.StartName -ne 'NT AUTHORITY\LocalService') {
        throw "Windows Service is not running under the low-privilege LocalService account."
    }

    $serviceAccount = New-Object System.Security.Principal.NTAccount('NT SERVICE', 'HRMCentralService')
    $serviceSid = $serviceAccount.Translate([System.Security.Principal.SecurityIdentifier])
    $acl = Get-Acl $HrmData
    $rules = $acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier])
    $serviceRule = $rules | Where-Object {
        $_.IdentityReference.Value -eq $serviceSid.Value -and
        $_.AccessControlType -eq [System.Security.AccessControl.AccessControlType]::Allow -and
        ($_.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::Modify)
    }
    if (-not $serviceRule) {
        throw "ProgramData ACL does not grant Modify to the dedicated Service SID."
    }

    $health = $null
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        try {
            $health = Invoke-RestMethod https://127.0.0.1:8765/api/health -SkipCertificateCheck -TimeoutSec 3
            break
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $health -or $health.status -ne 'ok' -or -not $health.tls -or
        $health.database -ne 'ready' -or $health.version -ne $ExpectedVersion) {
        $healthDetail = if ($health) { $health | ConvertTo-Json -Compress } else { 'no response' }
        throw "TLS/service/database-ready health check failed after installation: $healthDetail"
    }
    if (-not (Test-Path (Join-Path $Target 'Client\HRM.exe'))) { throw 'Desktop client missing.' }
    if (Test-Path (Join-Path $Target 'Server\data\seed\hrm-seed.sqlite')) {
        throw 'Private/demo seed was left behind in Program Files.'
    }
    $desktopShortcut = Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) 'HRM.lnk'
    if (-not (Test-Path $desktopShortcut)) { throw 'Desktop shortcut missing.' }
    if (-not (Test-Path (Join-Path $HrmData 'hrm.sqlite'))) { throw 'HRM database missing.' }
    if (-not (Test-Path (Join-Path $HrmData 'FIRST_LOGIN.txt'))) { throw 'First-login notice missing.' }
    if ((Get-FileHash $LegacyDatabase -Algorithm SHA256).Hash -ne $LegacyHash) {
        throw 'Legacy ProgramData was modified by the clean enterprise installer.'
    }

    # An in-place reinstall exercises the same path used by an alpha upgrade.
    # Operational data and the original one-time credential must not be replaced.
    $PreservationMarker = Join-Path $HrmData 'ci-preserve-marker.txt'
    [IO.File]::WriteAllText($PreservationMarker, 'must-survive-upgrade-and-uninstall')
    $FirstLogin = Join-Path $HrmData 'FIRST_LOGIN.txt'
    $FirstLoginHash = (Get-FileHash $FirstLogin -Algorithm SHA256).Hash
    Invoke-CheckedProcess -FilePath $Installer `
        -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/TYPE=full', "/LOG=`"$UpgradeSetupLog`"") `
        -Stage 'Silent in-place upgrade installation' -TimeoutSeconds 240
    if (-not (Test-Path $PreservationMarker)) { throw 'Operational marker was removed by in-place upgrade.' }
    if ((Get-FileHash $FirstLogin -Algorithm SHA256).Hash -ne $FirstLoginHash) {
        throw 'Initial owner credentials were regenerated during in-place upgrade.'
    }
    if (Test-Path (Join-Path $Target 'Server\data\seed\hrm-seed.sqlite')) {
        throw 'Seed was persisted in Program Files during in-place upgrade.'
    }
    $service = Get-Service HRMCentralService -ErrorAction Stop
    if ($service.Status -ne 'Running') { throw 'Service is not running after in-place upgrade.' }

    $uninstaller = Join-Path $Target 'unins000.exe'
    if (-not (Test-Path $uninstaller)) { throw 'Uninstaller missing.' }
    Invoke-CheckedProcess -FilePath $uninstaller `
        -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-') `
        -Stage 'Silent uninstall' -TimeoutSeconds 180
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        if (-not (Get-Service HRMCentralService -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 500
    }
    if (Get-Service HRMCentralService -ErrorAction SilentlyContinue) { throw 'Service was not removed.' }
    if (-not (Test-Path (Join-Path $HrmData 'hrm.sqlite'))) {
        throw 'Operational data was removed by uninstall.'
    }
    if (-not (Test-Path $PreservationMarker)) {
        throw 'Operational marker was removed by uninstall.'
    }

    Write-Host "Windows install, upgrade, TLS, service, data-preservation and uninstall smoke test passed."
} catch {
    try {
        ($_ | Format-List * -Force | Out-String) | Out-File -FilePath $FailureSummaryLog -Encoding utf8 -Force
    } catch { }
    throw
} finally {
    if ($TranscriptStarted) {
        try { Stop-Transcript | Out-Null } catch { }
        $TranscriptStarted = $false
    }
    try { & "$env:SystemRoot\System32\sc.exe" qc HRMCentralService 2>&1 | Out-File -FilePath $ServiceConfigLog -Encoding utf8 -Force } catch { }
    try { & "$env:SystemRoot\System32\sc.exe" queryex HRMCentralService 2>&1 | Out-File -FilePath $ServiceStateLog -Encoding utf8 -Force } catch { }
    try { Get-CimInstance Win32_Service -Filter "Name='HRMCentralService'" | ConvertTo-Json -Depth 4 | Out-File -FilePath $ServiceCimLog -Encoding utf8 -Force } catch { }
    try { & "$env:SystemRoot\System32\icacls.exe" $HrmData /T 2>&1 | Out-File -FilePath $AclLog -Encoding utf8 -Force } catch { }
    $serverLog = Join-Path $HrmData 'logs\setup-server.log'
    $startupLog = Join-Path $HrmData 'logs\startup-failure.log'
    try {
        if (Test-Path $serverLog) { Copy-Item -Force $serverLog (Join-Path $ArtifactDir 'setup-server.log') }
    } catch {
        try { "setup-server.log: $($_.Exception.Message)" | Add-Content -Path $DiagnosticCopyLog -Encoding utf8 } catch { }
    }
    try {
        if (Test-Path $startupLog) { Copy-Item -Force $startupLog (Join-Path $ArtifactDir 'startup-failure.log') }
    } catch {
        try { "startup-failure.log: $($_.Exception.Message)" | Add-Content -Path $DiagnosticCopyLog -Encoding utf8 } catch { }
    }
}
