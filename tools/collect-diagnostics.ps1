$ErrorActionPreference = 'SilentlyContinue'
$Out = Join-Path $env:TEMP ("HRM-Diagnostics-Safe-{0}" -f ([guid]::NewGuid().ToString('N')))
$Zip = "$Out.zip"
New-Item -ItemType Directory -Force -Path $Out | Out-Null

Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber,OSArchitecture,LastBootUpTime | ConvertTo-Json | Set-Content (Join-Path $Out 'os.json') -Encoding UTF8
Get-CimInstance Win32_Service -Filter "Name='HRMCentralService'" | Select-Object Name,State,StartMode,StartName | ConvertTo-Json | Set-Content (Join-Path $Out 'service.json') -Encoding UTF8
Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue | Select-Object State,LocalPort,OwningProcess | ConvertTo-Json | Set-Content (Join-Path $Out 'port-8765.json') -Encoding UTF8

$configPath = Join-Path $env:ProgramData 'HRM-Kermanshah\server.json'
if (Test-Path $configPath) {
  $c = Get-Content $configPath -Raw | ConvertFrom-Json
  [pscustomobject]@{ host=$c.host; port=$c.port; tls_mode=$c.tls_mode; backup_interval_hours=$c.backup_interval_hours; backup_retention=$c.backup_retention; backup_secondary_configured=[bool](-not [string]::IsNullOrWhiteSpace([string]$c.backup_secondary_dir)); backup_secondary_retention=$c.backup_secondary_retention; log_level=$c.log_level } |
    ConvertTo-Json | Set-Content (Join-Path $Out 'server-config-safe.json') -Encoding UTF8
}

$logDir = Join-Path $env:ProgramData 'HRM-Kermanshah\logs'
Get-ChildItem $logDir -Filter 'server.jsonl*' -File -ErrorAction SilentlyContinue | ForEach-Object {
  $dest = Join-Path $Out ($_.Name + '.safe.jsonl')
  Get-Content $_.FullName -ErrorAction SilentlyContinue | ForEach-Object {
    try {
      $x = $_ | ConvertFrom-Json
      [pscustomobject]@{ time=$x.time; level=$x.level; logger=$x.logger; message=$x.message; request_id=$x.request_id } | ConvertTo-Json -Compress
    } catch { }
  } | Set-Content $dest -Encoding UTF8
}

$hashes = Join-Path $Out 'installed-hashes.txt'
@("$env:ProgramFiles\HRM\Client\HRM.exe", "$env:ProgramFiles\HRM\Server\HRMServer.exe", "$env:ProgramFiles\HRM\Server\HRMService.exe") | ForEach-Object {
  if (Test-Path $_) { "$_`n$((Get-FileHash $_ -Algorithm SHA256).Hash)" | Add-Content $hashes }
}

Compress-Archive -Path (Join-Path $Out '*') -DestinationPath $Zip -Force
Write-Host "Diagnostics ZIP created: $Zip"
Write-Host 'Sensitive bootstrap/login material, database contents, request details, client IPs, exception traces and raw server logs were not collected.'
