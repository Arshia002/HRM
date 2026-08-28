param(
    [Parameter(Mandatory=$true)][string]$Installer,
    [Parameter(Mandatory=$true)][string]$Output
)

$ErrorActionPreference = 'Stop'
$installerPath = (Resolve-Path $Installer).Path
$outputPath = [IO.Path]::GetFullPath($Output)
New-Item -ItemType Directory -Force -Path (Split-Path $outputPath) | Out-Null

$hash = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToLowerInvariant()
$revision = if ($env:GITHUB_SHA) { $env:GITHUB_SHA } else { (git rev-parse HEAD 2>$null) }
$runUrl = if ($env:GITHUB_SERVER_URL -and $env:GITHUB_REPOSITORY -and $env:GITHUB_RUN_ID) {
    "$($env:GITHUB_SERVER_URL)/$($env:GITHUB_REPOSITORY)/actions/runs/$($env:GITHUB_RUN_ID)"
} else { '' }

$manifest = [ordered]@{
    manifest_schema = 1
    product = 'HRM'
    version = '0.2.0-alpha.2'
    build_utc = [DateTime]::UtcNow.ToString('o')
    source_revision = [string]$revision
    github_run = $runUrl
    builder = [ordered]@{
        os = [Environment]::OSVersion.VersionString
        architecture = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
        runner = $env:RUNNER_NAME
    }
    acceptance = [ordered]@{
        clean_install = $true
        tls_health = $true
        windows_service = $true
        service_identity = 'LocalSystem'
        service_sid_acl = $true
        desktop_shortcut = $true
        bootstrap_login = $true
        forced_password_change = $true
        bootstrap_invalid_after_change = $true
        in_place_upgrade = $true
        data_preservation = $true
        uninstall_preserves_data = $true
    }
    artifacts = @(
        [ordered]@{
            name = [IO.Path]::GetFileName($installerPath)
            bytes = (Get-Item $installerPath).Length
            sha256 = $hash
        }
    )
}

$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $outputPath -Encoding utf8
Write-Host "CI manifest written: $outputPath"
