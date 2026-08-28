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
$SetupLog = Join-Path $ArtifactDir "setup-inno.log"
$UpgradeLog = Join-Path $ArtifactDir "setup-upgrade.log"
$ServiceConfigLog = Join-Path $ArtifactDir "service-config.txt"
$ServiceStateLog = Join-Path $ArtifactDir "service-state.txt"
$ServiceCimLog = Join-Path $ArtifactDir "service-cim.json"
$AclLog = Join-Path $ArtifactDir "data-acl.txt"
$FailureSummaryLog = Join-Path $ArtifactDir "install-failure-summary.txt"
$DiagnosticCopyLog = Join-Path $ArtifactDir "diagnostic-copy-errors.txt"
$EnterpriseData = Join-Path $env:ProgramData "HRM-Kermanshah"
$ApiBase = 'https://127.0.0.1:8765'
$BootstrapPassword = '13811381'
$ChangedPassword = 'CI-Changed!Password1401'
$Username = 'arshia.shahbazi'

function Invoke-CheckedProcess {
    param(
        [Parameter(Mandatory=$true)][string]$FilePath,
        [string[]]$ArgumentList = @(),
        [Parameter(Mandatory=$true)][string]$Stage,
        [int]$TimeoutSeconds = 180,
        [switch]$NoNewWindow
    )
    Write-Host "[$(Get-Date -Format o)] START: $Stage"
    $start = @{ FilePath = $FilePath; ArgumentList = $ArgumentList; PassThru = $true }
    if ($NoNewWindow) { $start["NoNewWindow"] = $true }
    $process = Start-Process @start
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        Write-Host "[$(Get-Date -Format o)] TIMEOUT: $Stage (PID $($process.Id))"
        & "$env:SystemRoot\System32\taskkill.exe" /PID $process.Id /T /F | Out-Host
        throw "$Stage timed out after $TimeoutSeconds seconds. The process tree was terminated."
    }
    $process.Refresh()
    if ($process.ExitCode -ne 0) { throw "$Stage failed with exit code $($process.ExitCode)." }
    Write-Host "[$(Get-Date -Format o)] PASS: $Stage"
}

function Invoke-ApiJson {
    param(
        [Parameter(Mandatory=$true)][ValidateSet('GET','POST')][string]$Method,
        [Parameter(Mandatory=$true)][string]$Path,
        [hashtable]$Body = $null,
        [string]$Token = ''
    )
    $headers = @{}
    if ($Token) { $headers['Authorization'] = "Bearer $Token" }
    $params = @{
        Method = $Method
        Uri = "$ApiBase$Path"
        SkipCertificateCheck = $true
        TimeoutSec = 8
        Headers = $headers
    }
    if ($null -ne $Body) {
        $params['ContentType'] = 'application/json'
        $params['Body'] = ($Body | ConvertTo-Json -Compress)
    }
    return Invoke-RestMethod @params
}

function Assert-ApiFailure {
    param(
        [Parameter(Mandatory=$true)][ValidateSet('GET','POST')][string]$Method,
        [Parameter(Mandatory=$true)][string]$Path,
        [hashtable]$Body = $null,
        [string]$Token = '',
        [Parameter(Mandatory=$true)][int]$StatusCode,
        [Parameter(Mandatory=$true)][string]$Stage
    )
    try {
        Invoke-ApiJson -Method $Method -Path $Path -Body $Body -Token $Token | Out-Null
        throw "$Stage unexpectedly succeeded."
    } catch {
        if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq $StatusCode) {
            Write-Host "[$(Get-Date -Format o)] PASS: $Stage returned expected HTTP $StatusCode"
            return
        }
        if ($_.Exception.Message -like '*unexpectedly succeeded*') { throw }
        throw "$Stage failed with an unexpected response: $($_.Exception.Message)"
    }
}

function Wait-HrmHealth {
    param([string]$Stage)
    $health = $null
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $health = Invoke-ApiJson -Method GET -Path '/api/health'
            if ($health.status -eq 'ok') { break }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    if (-not $health -or $health.status -ne 'ok' -or -not $health.tls -or
        $health.database -ne 'ready' -or $health.version -ne '0.4.0-alpha.1') {
        $detail = if ($health) { $health | ConvertTo-Json -Compress } else { 'no response' }
        throw "$Stage health check failed: $detail"
    }
    Write-Host "[$(Get-Date -Format o)] PASS: $Stage health/TLS/database/version"
}

try {
    $Installer = (Resolve-Path $Installer).Path
    $Target = Join-Path $env:ProgramFiles "HRM"
    $LegacyData = Join-Path $env:ProgramData "SazmanHR"
    $LegacyDatabase = Join-Path $LegacyData "sazmanhr.sqlite"

    # Prove the HRM package never opens/migrates the old SazmanHR ProgramData path.
    New-Item -ItemType Directory -Force -Path $LegacyData | Out-Null
    [IO.File]::WriteAllText($LegacyDatabase, "legacy-sentinel-must-remain-untouched")
    $LegacyHash = (Get-FileHash $LegacyDatabase -Algorithm SHA256).Hash

    Invoke-CheckedProcess -FilePath $Installer `
        -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/TYPE=full', "/LOG=`"$SetupLog`"") `
        -Stage 'Clean silent full Setup installation' -TimeoutSeconds 260

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
    $acl = Get-Acl $EnterpriseData
    $rules = $acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier])
    $serviceRule = $rules | Where-Object {
        $_.IdentityReference.Value -eq $serviceSid.Value -and
        $_.AccessControlType -eq [System.Security.AccessControl.AccessControlType]::Allow -and
        ($_.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::Modify)
    }
    if (-not $serviceRule) { throw "ProgramData ACL does not grant Modify to the dedicated Service SID." }

    Wait-HrmHealth -Stage 'Clean install'

    if (-not (Test-Path (Join-Path $Target 'Client\HRM.exe'))) { throw 'Desktop client missing.' }
    if (Test-Path (Join-Path $Target 'Server\data\seed\sazmanhr-seed.sqlite')) {
        throw 'Synthetic seed was left behind in Program Files.'
    }
    $desktopShortcut = Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) 'HRM.lnk'
    if (-not (Test-Path $desktopShortcut)) { throw 'Desktop shortcut missing.' }
    $database = Join-Path $EnterpriseData 'hrm.sqlite'
    if (-not (Test-Path $database)) { throw 'Enterprise database missing.' }
    $firstLogin = Join-Path $EnterpriseData 'FIRST_LOGIN.txt'
    if (-not (Test-Path $firstLogin)) { throw 'First-login notice missing.' }
    if ((Get-FileHash $LegacyDatabase -Algorithm SHA256).Hash -ne $LegacyHash) {
        throw 'Legacy ProgramData was modified by the clean HRM installer.'
    }

    # First-login acceptance: login works, dashboard is blocked, password change is required.
    $login = Invoke-ApiJson -Method POST -Path '/api/login' -Body @{ username=$Username; password=$BootstrapPassword }
    if (-not $login.token) { throw 'Bootstrap login did not return a session token.' }
    if ([int]$login.user.must_change_password -ne 1) { throw 'Bootstrap account is not marked must_change_password.' }
    $bootstrapToken = [string]$login.token
    Assert-ApiFailure -Method GET -Path '/api/dashboard' -Token $bootstrapToken -StatusCode 403 -Stage 'Dashboard blocked before password change'

    $change = Invoke-ApiJson -Method POST -Path '/api/change-password' -Token $bootstrapToken -Body @{
        current_password=$BootstrapPassword
        new_password=$ChangedPassword
    }
    if (-not $change.ok) { throw 'Password change endpoint did not return ok.' }
    if (Test-Path $firstLogin) { throw 'FIRST_LOGIN.txt was not removed after initial owner changed password.' }

    Assert-ApiFailure -Method POST -Path '/api/login' -Body @{ username=$Username; password=$BootstrapPassword } -StatusCode 401 -Stage 'Bootstrap password invalidated after change'
    $changedLogin = Invoke-ApiJson -Method POST -Path '/api/login' -Body @{ username=$Username; password=$ChangedPassword }
    if (-not $changedLogin.token -or [int]$changedLogin.user.must_change_password -ne 0) {
        throw 'Changed password login failed or still requires password change.'
    }
    $dashboard = Invoke-ApiJson -Method GET -Path '/api/dashboard' -Token ([string]$changedLogin.token)
    if (-not $dashboard.stats) { throw 'Dashboard did not become available after password change.' }
    Write-Host "[$(Get-Date -Format o)] PASS: bootstrap login, forced password change and dashboard gate"

    # Create a data-preservation sentinel and capture DB hash before upgrade.
    $sentinel = Join-Path $EnterpriseData 'ci-upgrade-sentinel.txt'
    [IO.File]::WriteAllText($sentinel, "HRM-UPGRADE-PRESERVE-$(Get-Date -Format o)")
    $sentinelHash = (Get-FileHash $sentinel -Algorithm SHA256).Hash
    $dbHashBeforeUpgrade = (Get-FileHash $database -Algorithm SHA256).Hash

    Invoke-CheckedProcess -FilePath $Installer `
        -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/TYPE=full', "/LOG=`"$UpgradeLog`"") `
        -Stage 'Silent in-place upgrade installation' -TimeoutSeconds 260

    $UpgradeSetupText = Get-Content -LiteralPath $UpgradeLog -Raw
    $StopBeforeCopyIndex = $UpgradeSetupText.IndexOf('HRM_STAGE|PASS|service-stop-before-copy')
    $FirstFileEntryIndex = $UpgradeSetupText.IndexOf('-- File entry --')
    if ($StopBeforeCopyIndex -lt 0 -or $FirstFileEntryIndex -lt 0 -or $StopBeforeCopyIndex -gt $FirstFileEntryIndex) {
        throw 'Upgrade did not prove the existing service stopped before Setup replaced files.'
    }
    if ($UpgradeSetupText -match 'RestartManager found an application using one of our files: HRM') {
        throw 'An HRM process still held an installed file when the upgrade copy phase started.'
    }
    if (Test-Path (Join-Path $Target 'Server\data\seed\sazmanhr-seed.sqlite')) {
        throw 'Synthetic seed was persisted in Program Files during in-place upgrade.'
    }

    $service = Get-Service HRMCentralService -ErrorAction Stop
    if ($service.Status -ne 'Running') {
        Start-Service HRMCentralService
        $service.WaitForStatus('Running', [TimeSpan]::FromSeconds(20))
    }
    Wait-HrmHealth -Stage 'Post-upgrade'

    if (-not (Test-Path $sentinel) -or (Get-FileHash $sentinel -Algorithm SHA256).Hash -ne $sentinelHash) {
        throw 'Upgrade did not preserve the operational sentinel.'
    }
    if (-not (Test-Path $database)) { throw 'Upgrade removed the enterprise database.' }
    # DB hash may legitimately change because sessions/audit timestamps are written. Its presence and login state are authoritative.
    $dbHashAfterUpgrade = (Get-FileHash $database -Algorithm SHA256).Hash
    Write-Host "DB SHA256 before upgrade: $dbHashBeforeUpgrade"
    Write-Host "DB SHA256 after upgrade : $dbHashAfterUpgrade"

    Assert-ApiFailure -Method POST -Path '/api/login' -Body @{ username=$Username; password=$BootstrapPassword } -StatusCode 401 -Stage 'Bootstrap password remains invalid after upgrade'
    $postUpgradeLogin = Invoke-ApiJson -Method POST -Path '/api/login' -Body @{ username=$Username; password=$ChangedPassword }
    if (-not $postUpgradeLogin.token -or [int]$postUpgradeLogin.user.must_change_password -ne 0) {
        throw 'Changed password or must_change_password state was not preserved through upgrade.'
    }
    if (Test-Path $firstLogin) { throw 'Upgrade recreated FIRST_LOGIN.txt for an existing initialized database.' }
    Write-Host "[$(Get-Date -Format o)] PASS: in-place upgrade and account/data preservation"

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
    if (-not (Test-Path $database)) { throw 'Operational database was removed by uninstall.' }
    if (-not (Test-Path $sentinel) -or (Get-FileHash $sentinel -Algorithm SHA256).Hash -ne $sentinelHash) {
        throw 'Operational data sentinel was removed or changed by uninstall.'
    }

    Write-Host "ALL ACCEPTANCE TESTS PASSED: clean install, TLS, service, ACL, desktop, bootstrap login, forced password change, in-place upgrade, data preservation and uninstall."
} catch {
    try { ($_ | Format-List * -Force | Out-String) | Out-File -FilePath $FailureSummaryLog -Encoding utf8 -Force } catch { }
    throw
} finally {
    if ($TranscriptStarted) {
        try { Stop-Transcript | Out-Null } catch { }
        $TranscriptStarted = $false
    }
    try { & "$env:SystemRoot\System32\sc.exe" qc HRMCentralService 2>&1 | Out-File -FilePath $ServiceConfigLog -Encoding utf8 -Force } catch { }
    try { & "$env:SystemRoot\System32\sc.exe" queryex HRMCentralService 2>&1 | Out-File -FilePath $ServiceStateLog -Encoding utf8 -Force } catch { }
    try { Get-CimInstance Win32_Service -Filter "Name='HRMCentralService'" | ConvertTo-Json -Depth 4 | Out-File -FilePath $ServiceCimLog -Encoding utf8 -Force } catch { }
    try { & "$env:SystemRoot\System32\icacls.exe" $EnterpriseData /T 2>&1 | Out-File -FilePath $AclLog -Encoding utf8 -Force } catch { }
    $serverLog = Join-Path $EnterpriseData 'logs\setup-server.log'
    $startupLog = Join-Path $EnterpriseData 'logs\startup-failure.log'
    try { if (Test-Path $serverLog) { Copy-Item -Force $serverLog (Join-Path $ArtifactDir 'setup-server.log') } } catch {
        try { "setup-server.log copy failed: $($_.Exception.Message)" | Out-File $DiagnosticCopyLog -Encoding utf8 -Append } catch { }
    }
    try { if (Test-Path $startupLog) { Copy-Item -Force $startupLog (Join-Path $ArtifactDir 'startup-failure.log') } } catch {
        try { "startup-failure.log copy failed: $($_.Exception.Message)" | Out-File $DiagnosticCopyLog -Encoding utf8 -Append } catch { }
    }
}
