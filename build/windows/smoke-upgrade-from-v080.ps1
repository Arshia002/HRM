param(
  [Parameter(Mandatory=$true)][string]$BaselineInstaller,
  [Parameter(Mandatory=$true)][string]$CandidateInstaller,
  [Parameter(Mandatory=$true)][string]$LogPath
)
$ErrorActionPreference='Stop'
Start-Transcript -Path $LogPath -Force | Out-Null
$Data=Join-Path $env:ProgramData 'HRM-Kermanshah'; $Api='https://127.0.0.1:8765'; $User='arshia.shahbazi'; $Changed='V100RC1-Upgrade!Password1401'
function Install([string]$Exe,[string]$Log){ $p=Start-Process $Exe -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/TYPE=full',"/LOG=`"$Log`"") -PassThru; $p.WaitForExit(); if($p.ExitCode-ne 0){throw "Setup failed: $($p.ExitCode)"} }
function Api([string]$Method,[string]$Path,[hashtable]$Body=$null,[string]$Token=''){ $h=@{}; if($Token){$h.Authorization="Bearer $Token"}; $x=@{Method=$Method;Uri="$Api$Path";SkipCertificateCheck=$true;TimeoutSec=8;Headers=$h}; if($Body){$x.ContentType='application/json';$x.Body=$Body|ConvertTo-Json -Compress}; Invoke-RestMethod @x }
function Health([string]$Version){ for($i=0;$i-lt 40;$i++){try{$h=Api GET '/api/health';if($h.status-eq'ok'){break}}catch{};Start-Sleep -Milliseconds 500}; if($h.version-ne $Version -or -not $h.tls -or $h.database-ne'ready'){throw "Health mismatch: $($h|ConvertTo-Json -Compress)"} }
try {
  Remove-Item -Recurse -Force $Data -ErrorAction SilentlyContinue
  Install (Resolve-Path $BaselineInstaller).Path (Join-Path (Split-Path $LogPath) 'v080-install.log')
  Health '0.8.0-rc.1'
  $first=Get-Content (Join-Path $Data 'FIRST_LOGIN.txt') -Raw; $pw=[regex]::Match($first,'(?m)^Password:\s*(.+)\s*$').Groups[1].Value.Trim()
  $login=Api POST '/api/login' @{username=$User;password=$pw}; Api POST '/api/change-password' @{current_password=$pw;new_password=$Changed} $login.token|Out-Null
  $sentinel=Join-Path $Data 'ci-v080-to-v100rc1-sentinel.txt'; Set-Content $sentinel 'preserve-v080-to-v100rc1' -Encoding ASCII; $hash=(Get-FileHash $sentinel -Algorithm SHA256).Hash
  Install (Resolve-Path $CandidateInstaller).Path (Join-Path (Split-Path $LogPath) 'v100rc1-upgrade.log')
  Health '1.0.0-rc.1'
  if((Get-FileHash $sentinel -Algorithm SHA256).Hash-ne$hash){throw 'Sentinel changed during v0.8-to-v1.0-rc.1 upgrade.'}
  $again=Api POST '/api/login' @{username=$User;password=$Changed}; if(-not $again.token){throw 'Changed credential not preserved.'}
  Write-Host 'PASS: real v0.8.0-rc.1 -> v1.0.0-rc.1 installer upgrade preserved service, TLS, database and credentials.'
  $u=Join-Path $env:ProgramFiles 'HRM\unins000.exe'; if(Test-Path $u){$p=Start-Process $u -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-') -PassThru;$p.WaitForExit()}
} finally { try{Stop-Transcript|Out-Null}catch{} }
