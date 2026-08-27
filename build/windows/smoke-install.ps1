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

function Get-HealthyDeployment {
    param(
        [Parameter(Mandatory=$true)][string]$ExpectedVersion,
        [Parameter(Mandatory=$true)][string]$Stage
    )
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
        $health.database -ne 'ready' -or $health.version -ne $ExpectedVersion -or
        -not $health.deployment -or -not $health.deployment.id -or
        [int]$health.deployment.users -lt 1) {
        $healthDetail = if ($health) { $health | ConvertTo-Json -Depth 3 -Compress } else { 'no response' }
        throw "TLS/service/database-ready health check failed during ${Stage}: $healthDetail"
    }
    return $health
}

function Assert-ProtectedAcl {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)]
        [System.Security.Principal.SecurityIdentifier]$ServiceSid
    )
    if (-not (Test-Path -LiteralPath $Path)) { throw "Protected path is missing: $Path" }
    $acl = Get-Acl -LiteralPath $Path
    $rules = @($acl.GetAccessRules(
        $true, $true, [System.Security.Principal.SecurityIdentifier]
    ))
    $allow = [System.Security.AccessControl.AccessControlType]::Allow
    $serviceRule = $rules | Where-Object {
        $_.IdentityReference.Value -eq $ServiceSid.Value -and
        $_.AccessControlType -eq $allow -and
        (($_.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::Modify) -eq
            [System.Security.AccessControl.FileSystemRights]::Modify)
    }
    if (-not $serviceRule) {
        throw "Service SID does not have Modify access on protected path: $Path"
    }
    $adminRule = $rules | Where-Object {
        $_.IdentityReference.Value -eq 'S-1-5-32-544' -and
        $_.AccessControlType -eq $allow -and
        (($_.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::FullControl) -eq
            [System.Security.AccessControl.FileSystemRights]::FullControl)
    }
    if (-not $adminRule) {
        throw "Administrators do not have FullControl on protected path: $Path"
    }
    $forbiddenSids = @('S-1-1-0', 'S-1-5-11', 'S-1-5-32-545')
    $broadRule = $rules | Where-Object {
        $_.AccessControlType -eq $allow -and
        $forbiddenSids -contains $_.IdentityReference.Value
    }
    if ($broadRule) {
        throw "A broad user group still has access on protected path: $Path"
    }
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
    $protectedPaths = @(
        $HrmData,
        (Join-Path $HrmData 'hrm.sqlite'),
        (Join-Path $HrmData 'FIRST_LOGIN.txt'),
        (Join-Path $HrmData 'server.json'),
        (Join-Path $HrmData 'tls\server.key')
    )
    foreach ($protectedPath in $protectedPaths) {
        Assert-ProtectedAcl -Path $protectedPath -ServiceSid $serviceSid
    }

    $health = Get-HealthyDeployment -ExpectedVersion $ExpectedVersion -Stage 'initial installation'
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
    # Preservation is proven through the running service, without reading the
    # database, TLS key or one-time credential from the test account.
    $PreservationMarker = Join-Path $HrmData 'ci-preserve-marker.txt'
    [IO.File]::WriteAllText($PreservationMarker, 'must-survive-upgrade-and-uninstall')
    Assert-ProtectedAcl -Path $PreservationMarker -ServiceSid $serviceSid
    $DeploymentIdBefore = [string]$health.deployment.id
    $UserCountBefore = [int]$health.deployment.users
    $PersonnelCountBefore = [int]$health.deployment.personnel
    $ChartPageCountBefore = [int]$health.deployment.chart_pages
    Invoke-CheckedProcess -FilePath $Installer `
        -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/TYPE=full', "/LOG=`"$UpgradeSetupLog`"") `
        -Stage 'Silent in-place upgrade installation' -TimeoutSeconds 240
    $UpgradeSetupText = Get-Content -LiteralPath $UpgradeSetupLog -Raw
    $StopBeforeCopyIndex = $UpgradeSetupText.IndexOf('HRM_STAGE|PASS|service-stop-before-copy')
    $FirstFileEntryIndex = $UpgradeSetupText.IndexOf('-- File entry --')
    if ($StopBeforeCopyIndex -lt 0 -or $FirstFileEntryIndex -lt 0 -or
        $StopBeforeCopyIndex -gt $FirstFileEntryIndex) {
        throw 'Upgrade did not prove the existing service stopped before Setup replaced files.'
    }
    if ($UpgradeSetupText -match 'RestartManager found an application using one of our files: HRM') {
        throw 'An HRM process still held an installed file when the upgrade copy phase started.'
    }
    if (-not (Test-Path $PreservationMarker)) { throw 'Operational marker was removed by in-place upgrade.' }
    if (-not (Test-Path (Join-Path $HrmData 'FIRST_LOGIN.txt'))) { throw 'First-login notice was removed by in-place upgrade.' }
    if (Test-Path (Join-Path $Target 'Server\data\seed\hrm-seed.sqlite')) {
        throw 'Seed was persisted in Program Files during in-place upgrade.'
    }
    $service = Get-Service HRMCentralService -ErrorAction Stop
    if ($service.Status -ne 'Running') { throw 'Service is not running after in-place upgrade.' }
    $healthAfterUpgrade = Get-HealthyDeployment -ExpectedVersion $ExpectedVersion -Stage 'in-place upgrade'
    if ([string]$healthAfterUpgrade.deployment.id -ne $DeploymentIdBefore -or
        [int]$healthAfterUpgrade.deployment.users -ne $UserCountBefore -or
        [int]$healthAfterUpgrade.deployment.personnel -ne $PersonnelCountBefore -or
        [int]$healthAfterUpgrade.deployment.chart_pages -ne $ChartPageCountBefore) {
        throw 'Operational deployment identity or record counts changed during in-place upgrade.'
    }
    foreach ($protectedPath in ($protectedPaths + $PreservationMarker)) {
        Assert-ProtectedAcl -Path $protectedPath -ServiceSid $serviceSid
    }

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
    try {
        Get-CimInstance Win32_Service -Filter "Name='HRMCentralService'" |
            Select-Object Name, DisplayName, State, StartMode, StartName, PathName, ProcessId, ExitCode |
            ConvertTo-Json -Depth 2 |
            Out-File -FilePath $ServiceCimLog -Encoding utf8 -Force
    } catch { }
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
