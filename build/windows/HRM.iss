#ifndef ProjectRoot
  #error ProjectRoot is required
#endif
#ifndef DistDir
  #error DistDir is required
#endif
#ifndef ServiceRuntimeGeneration
  #error ServiceRuntimeGeneration is required
#endif

[Setup]
AppId={{4F82A3C7-1D55-4B80-9F21-6B3D4E7A1600}
AppName=HRM
AppVersion=1.0.0-rc.4
AppPublisher=Arshia Shahbazi
DefaultDirName={autopf}\HRM
DefaultGroupName=HRM
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#ProjectRoot}\build-output\installer
OutputBaseFilename=HRM-Setup-x64
SetupIconFile={#ProjectRoot}\assets\HRM.ico
UninstallDisplayIcon={app}\Client\HRM.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
ChangesAssociations=no
CloseApplications=yes
RestartApplications=no

[Types]
Name: "full"; Description: "سرور مرکزی و کلاینت مدیریت"
Name: "client"; Description: "فقط کلاینت مدیریت"
Name: "server"; Description: "فقط سرور مرکزی"

[Components]
Name: "client"; Description: "کلاینت دسکتاپ"; Types: full client
Name: "server"; Description: "سرویس مرکزی"; Types: full server; Flags: fixed disablenouninstallwarning

[Files]
Source: "{#DistDir}\HRMServer.exe"; DestName: "HRMServerPreflight.exe"; Components: server; Flags: dontcopy noencryption
Source: "{#ProjectRoot}\data\seed\sazmanhr-seed.sqlite"; DestName: "hrm-seed.sqlite"; Components: server; Flags: dontcopy noencryption
Source: "{#DistDir}\HRM.exe"; DestDir: "{app}\Client"; Components: client; Flags: ignoreversion
Source: "{#DistDir}\HRMServer.exe"; DestDir: "{app}\Server"; Components: server; Flags: ignoreversion
Source: "{#DistDir}\HRMService\*"; DestDir: "{app}\ServiceRuntime\{#ServiceRuntimeGeneration}"; Components: server; Flags: recursesubdirs createallsubdirs onlyifdoesntexist
Source: "{#DistDir}\HRMMigration.exe"; DestDir: "{app}\Server"; Components: server; Flags: ignoreversion
Source: "{#ProjectRoot}\docs\deployment-guide-fa.md"; DestDir: "{app}\Docs"; Flags: ignoreversion
Source: "{#ProjectRoot}\docs\windows-test-checklist-fa.md"; DestDir: "{app}\Docs"; Flags: ignoreversion
Source: "{#ProjectRoot}\tools\collect-diagnostics.cmd"; DestDir: "{app}\Tools"; Flags: ignoreversion
Source: "{#ProjectRoot}\tools\collect-diagnostics.ps1"; DestDir: "{app}\Tools"; Flags: ignoreversion
Source: "{#ProjectRoot}\docs\V040A2-ENTERPRISE-DATA-INTEGRATION.md"; DestDir: "{app}\Docs"; Flags: ignoreversion
Source: "{#ProjectRoot}\docs\V100RC1-FINAL-PRODUCTION-CANDIDATE.md"; DestDir: "{app}\Docs"; Flags: ignoreversion
Source: "{#ProjectRoot}\docs\production-deployment-checklist-fa.md"; DestDir: "{app}\Docs"; Flags: ignoreversion
Source: "{#ProjectRoot}\docs\production-operations-fa.md"; DestDir: "{app}\Docs"; Flags: ignoreversion
Source: "{#ProjectRoot}\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\HRM"; Filename: "{app}\Client\HRM.exe"; Parameters: "--server {code:GetServerUrl}"; WorkingDir: "{app}\Client"; Components: client
Name: "{group}\HRM"; Filename: "{app}\Client\HRM.exe"; Parameters: "--server {code:GetServerUrl}"; Components: client
Name: "{group}\راهنمای استقرار"; Filename: "{app}\Docs\deployment-guide-fa.md"
Name: "{group}\چک‌لیست تست Windows"; Filename: "{app}\Docs\windows-test-checklist-fa.md"
Name: "{group}\جمع‌آوری گزارش عیب‌یابی"; Filename: "{cmd}"; Parameters: "/c """"{app}\Tools\collect-diagnostics.cmd"""""; WorkingDir: "{app}\Tools"
Name: "{group}\اطلاعات ورود اولیه"; Filename: "{commonappdata}\HRM-Kermanshah\FIRST_LOGIN.txt"; Components: server

[Run]
Filename: "{app}\Client\HRM.exe"; Parameters: "--server {code:GetServerUrl}"; Components: client; Flags: nowait postinstall skipifsilent runasoriginaluser; Description: "اجرای HRM"

[UninstallRun]
Filename: "{app}\Server\HRMServer.exe"; Parameters: "--data-dir ""{commonappdata}\HRM-Kermanshah"" --stop-windows-service HRMCentralService --service-stop-timeout 30"; RunOnceId: "StopEnterpriseService"; Flags: runhidden waituntilterminated; Components: server
Filename: "{app}\Server\HRMServer.exe"; Parameters: "--delete-windows-service HRMCentralService"; RunOnceId: "RemoveEnterpriseService"; Flags: runhidden waituntilterminated; Components: server
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""HRM Central Service 8765"""; RunOnceId: "RemoveEnterpriseFirewall"; Flags: runhidden waituntilterminated; Components: server

[Code]
var
  ServerPage: TInputQueryWizardPage;
  ServiceExistedBeforeInstall: Boolean;
  ServiceWasRunningBeforeInstall: Boolean;
  ServiceStoppedForUpgrade: Boolean;
  PreInstallServiceHandled: Boolean;
  ServiceCutoverAttempted: Boolean;
  ServiceTransactionReady: Boolean;
  ServiceTransactionCommitted: Boolean;
  DatabaseUpgradeAttempted: Boolean;
  DatabaseUpgradeStatePath: String;
  ServiceCutoverStatePath: String;
  OriginalServiceImagePath: String;
  OriginalServiceExe: String;
  OriginalServiceStartType: Cardinal;
  OriginalServiceObjectName: String;
  OriginalServiceSidType: Cardinal;
  SetupCompleted: Boolean;
  ProvisionFailed: Boolean;
  LegacyServicesHandled: Boolean;
  LegacyEnterpriseExists: Boolean;
  LegacyEnterpriseWasRunning: Boolean;
  LegacyEnterpriseStartType: Cardinal;
  LegacyCentralExists: Boolean;
  LegacyCentralWasRunning: Boolean;
  LegacyCentralStartType: Cardinal;
  LegacyNetworkExists: Boolean;
  LegacyNetworkWasRunning: Boolean;
  LegacyNetworkStartType: Cardinal;

function EnterpriseDataDir: String;
begin
  Result := ExpandConstant('{commonappdata}\HRM-Kermanshah');
end;

function ServiceRuntimeDir: String;
begin
  Result := ExpandConstant('{app}\ServiceRuntime\{#ServiceRuntimeGeneration}');
end;

function ServiceRuntimeExe: String;
begin
  Result := ServiceRuntimeDir + '\HRMService.exe';
end;

function ServiceExecutableFromImagePath(ImagePath: String): String;
var
  Value: String;
  Tail: String;
  ClosingQuote: Integer;
begin
  Value := Trim(ImagePath);
  Result := '';
  if Value = '' then
    exit;
  if Copy(Value, 1, 1) = '"' then
  begin
    Tail := Copy(Value, 2, Length(Value) - 1);
    ClosingQuote := Pos('"', Tail);
    if ClosingQuote > 0 then
      Result := Copy(Tail, 1, ClosingQuote - 1);
  end
  else
    Result := Value;
end;

function ServiceSidTypeArgument(SidType: Cardinal): String;
begin
  case SidType of
    0: Result := 'none';
    1: Result := 'unrestricted';
    3: Result := 'restricted';
  else
    Result := '';
  end;
end;

procedure LogSetupStage(Status: String; StageName: String; ResultCode: Integer); forward;

function ServiceRegistryPath(ServiceName: String): String; forward;
function ServiceExistsInScm(ServiceName: String): Boolean; forward;

procedure SnapshotOriginalServiceConfiguration(var FailureText: String);
var
  RawImage: String;
begin
  if not ServiceExistedBeforeInstall then
    exit;

  LogSetupStage('START', 'service-snapshot-before-copy', -1);
  if not RegQueryStringValue(HKLM, ServiceRegistryPath('HRMCentralService'),
    'ImagePath', OriginalServiceImagePath) then
  begin
    FailureText := 'مسیر اجرایی سرویس فعلی قابل خواندن نیست.';
    LogSetupStage('FAIL', 'service-snapshot-before-copy', -1);
    exit;
  end;

  OriginalServiceExe := ServiceExecutableFromImagePath(OriginalServiceImagePath);
  if OriginalServiceExe = '' then
  begin
    FailureText := 'مسیر اجرایی سرویس فعلی قابل تفسیر نیست.';
    LogSetupStage('FAIL', 'service-snapshot-before-copy', -1);
    exit;
  end;

  RawImage := Trim(OriginalServiceImagePath);
  if (RawImage <> OriginalServiceExe) and
     (RawImage <> '"' + OriginalServiceExe + '"') then
  begin
    FailureText := 'ImagePath سرویس فعلی شامل آرگومان پشتیبانی‌نشده است؛ ارتقا متوقف شد.';
    LogSetupStage('FAIL', 'service-snapshot-before-copy', -1);
    exit;
  end;

  if not FileExists(OriginalServiceExe) then
  begin
    FailureText := 'فایل اجرایی سرویس فعلی وجود ندارد؛ ابتدا نصب فعلی باید بازیابی شود.';
    LogSetupStage('FAIL', 'service-snapshot-image-missing', -1);
    exit;
  end;

  if not RegQueryDWordValue(HKLM, ServiceRegistryPath('HRMCentralService'),
    'Start', OriginalServiceStartType) then
  begin
    FailureText := 'نوع راه‌اندازی سرویس فعلی قابل خواندن نیست.';
    LogSetupStage('FAIL', 'service-snapshot-before-copy', -1);
    exit;
  end;
  if (OriginalServiceStartType < 2) or (OriginalServiceStartType > 4) then
  begin
    FailureText := 'نوع راه‌اندازی سرویس فعلی پشتیبانی نمی‌شود.';
    LogSetupStage('FAIL', 'service-snapshot-before-copy', -1);
    exit;
  end;

  if not RegQueryStringValue(HKLM, ServiceRegistryPath('HRMCentralService'),
    'ObjectName', OriginalServiceObjectName) then
  begin
    FailureText := 'حساب سرویس فعلی قابل خواندن نیست.';
    LogSetupStage('FAIL', 'service-snapshot-before-copy', -1);
    exit;
  end;
  if Lowercase(OriginalServiceObjectName) <> 'nt authority\localservice' then
  begin
    FailureText := 'حساب سرویس فعلی خارج از قرارداد امن LocalService است.';
    LogSetupStage('FAIL', 'service-snapshot-before-copy', -1);
    exit;
  end;

  if not RegQueryDWordValue(HKLM, ServiceRegistryPath('HRMCentralService'),
    'ServiceSidType', OriginalServiceSidType) then
    OriginalServiceSidType := 0;
  if ServiceSidTypeArgument(OriginalServiceSidType) = '' then
  begin
    FailureText := 'نوع Service SID فعلی پشتیبانی نمی‌شود.';
    LogSetupStage('FAIL', 'service-snapshot-before-copy', -1);
    exit;
  end;

  LogSetupStage('PASS', 'service-snapshot-before-copy', 0);
end;

procedure LogSetupStage(Status: String; StageName: String; ResultCode: Integer);
begin
  Log('HRM_STAGE|' + Status + '|' + StageName + '|exit=' + IntToStr(ResultCode));
end;

procedure LogDiagnosticFile(LabelName: String; FileName: String);
var
  Content: AnsiString;
begin
  if LoadStringFromLockedFile(FileName, Content) then
  begin
    Log('HRM_DIAGNOSTIC_BEGIN|' + LabelName);
    Log(String(Content));
    Log('HRM_DIAGNOSTIC_END|' + LabelName);
  end
  else
    Log('HRM_DIAGNOSTIC_MISSING|' + LabelName + '|' + FileName);
end;

procedure LogProtectedDiagnostics;
begin
  LogDiagnosticFile('setup-server.log', EnterpriseDataDir + '\logs\setup-server.log');
  LogDiagnosticFile('startup-failure.log', EnterpriseDataDir + '\logs\startup-failure.log');
end;

procedure RunIgnored(Filename: String; Parameters: String);
var
  IgnoredCode: Integer;
begin
  Exec(Filename, Parameters, '', SW_HIDE, ewWaitUntilTerminated, IgnoredCode);
end;

function ServiceRegistryPath(ServiceName: String): String;
begin
  Result := 'SYSTEM\CurrentControlSet\Services\' + ServiceName;
end;

function ServiceExistsInScm(ServiceName: String): Boolean;
var
  ResultCode: Integer;
  Started: Boolean;
begin
  ResultCode := -1;
  Started := Exec(ExpandConstant('{sys}\sc.exe'),
    'query ' + ServiceName,
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

  if not Started then
    RaiseException('SCM query could not be started for service ' + ServiceName + '.');

  if ResultCode = 0 then
    Result := True
  else if ResultCode = 1060 then
    Result := False
  else
    RaiseException('SCM query failed for service ' + ServiceName +
      ' with exit code ' + IntToStr(ResultCode) + '.');
end;


function ServiceStartModeArgument(StartType: Cardinal): String;
begin
  case StartType of
    2: Result := 'auto';
    3: Result := 'demand';
    4: Result := 'disabled';
  else
    Result := 'demand';
  end;
end;

procedure RestoreOneLegacyService(ServiceName: String; ExistsBefore: Boolean;
  WasRunningBefore: Boolean; StartTypeBefore: Cardinal);
var
  ResultCode: Integer;
  Started: Boolean;
begin
  if not ExistsBefore then
    exit;

  ResultCode := -1;
  Started := Exec(ExpandConstant('{sys}\sc.exe'),
    'config ' + ServiceName + ' start= ' + ServiceStartModeArgument(StartTypeBefore),
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if Started and (ResultCode = 0) then
    LogSetupStage('PASS', 'restore-legacy-start-' + ServiceName, ResultCode)
  else
    LogSetupStage('FAIL', 'restore-legacy-start-' + ServiceName, ResultCode);

  if WasRunningBefore then
  begin
    ResultCode := -1;
    Started := Exec(ExpandConstant('{sys}\sc.exe'), 'start ' + ServiceName,
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    if Started and (ResultCode = 0) then
      LogSetupStage('PASS', 'restore-legacy-running-' + ServiceName, ResultCode)
    else
      LogSetupStage('FAIL', 'restore-legacy-running-' + ServiceName, ResultCode);
  end;
end;

procedure RestoreLegacyServicesIfNeeded;
begin
  if not LegacyServicesHandled then
    exit;

  RestoreOneLegacyService('SazmanHREnterpriseCentral',
    LegacyEnterpriseExists, LegacyEnterpriseWasRunning, LegacyEnterpriseStartType);
  RestoreOneLegacyService('SazmanHRCentral',
    LegacyCentralExists, LegacyCentralWasRunning, LegacyCentralStartType);
  RestoreOneLegacyService('SazmanHRNetworkServer',
    LegacyNetworkExists, LegacyNetworkWasRunning, LegacyNetworkStartType);
  LegacyServicesHandled := False;
end;

procedure HandleLegacyServiceBeforeCopy(PreflightExe: String; DiagnosticPath: String;
  ServiceName: String; var ExistsBefore: Boolean; var WasRunningBefore: Boolean;
  var StartTypeBefore: Cardinal; var FailureText: String);
var
  ServiceStatePath: String;
  ServiceStateContent: AnsiString;
  ResultCode: Integer;
  Started: Boolean;
  CurrentStartType: Cardinal;
begin
  ExistsBefore := RegKeyExists(HKLM, ServiceRegistryPath(ServiceName));
  WasRunningBefore := False;
  StartTypeBefore := 0;
  if not ExistsBefore then
    exit;

  if not RegQueryDWordValue(HKLM, ServiceRegistryPath(ServiceName), 'Start', StartTypeBefore) then
  begin
    { No service mutation happened yet, so rollback must not rewrite its start mode. }
    ExistsBefore := False;
    FailureText := 'نوع راه‌اندازی سرویس قدیمی ' + ServiceName + ' قابل خواندن نیست.';
    exit;
  end;

  if (StartTypeBefore < 2) or (StartTypeBefore > 4) then
  begin
    { Unsupported state was not modified; exclude it from rollback. }
    ExistsBefore := False;
    FailureText := 'نوع راه‌اندازی سرویس قدیمی ' + ServiceName + ' پشتیبانی نمی‌شود.';
    exit;
  end;

  ServiceStatePath := ExpandConstant('{tmp}\legacy-service-' + ServiceName + '.json');
  DeleteFile(ServiceStatePath);
  ResultCode := -1;
  LogSetupStage('START', 'legacy-service-stop-before-copy-' + ServiceName, ResultCode);
  Started := Exec(PreflightExe,
    '--data-dir "' + EnterpriseDataDir +
    '" --stop-windows-service ' + ServiceName + ' --service-stop-timeout 30' +
    ' --service-state-file "' + ServiceStatePath +
    '" --diagnostic-log "' + DiagnosticPath + '"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if (not Started) or (ResultCode <> 0) then
  begin
    LogSetupStage('FAIL', 'legacy-service-stop-before-copy-' + ServiceName, ResultCode);
    FailureText := 'توقف ایمن سرویس قدیمی ' + ServiceName +
      ' پیش از ارتقا شکست خورد (کد ' + IntToStr(ResultCode) + ').';
    exit;
  end;

  if not LoadStringFromLockedFile(ServiceStatePath, ServiceStateContent) then
  begin
    LogSetupStage('FAIL', 'legacy-service-state-' + ServiceName, -1);
    FailureText := 'وضعیت سرویس قدیمی ' + ServiceName + ' قابل اعتبارسنجی نیست.';
    exit;
  end;

  WasRunningBefore :=
    Pos('"was_running": true', Lowercase(String(ServiceStateContent))) > 0;
  LogSetupStage('PASS', 'legacy-service-stop-before-copy-' + ServiceName, 0);

  ResultCode := -1;
  LogSetupStage('START', 'legacy-service-disable-before-copy-' + ServiceName, ResultCode);
  Started := Exec(ExpandConstant('{sys}\sc.exe'),
    'config ' + ServiceName + ' start= disabled',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if (not Started) or (ResultCode <> 0) then
  begin
    LogSetupStage('FAIL', 'legacy-service-disable-before-copy-' + ServiceName, ResultCode);
    FailureText := 'غیرفعال‌سازی سرویس قدیمی ' + ServiceName +
      ' شکست خورد (کد ' + IntToStr(ResultCode) + ').';
    exit;
  end;

  if (not RegQueryDWordValue(HKLM, ServiceRegistryPath(ServiceName), 'Start', CurrentStartType)) or
     (CurrentStartType <> 4) then
  begin
    LogSetupStage('FAIL', 'legacy-service-disable-validation-' + ServiceName, -1);
    FailureText := 'غیرفعال‌سازی سرویس قدیمی ' + ServiceName + ' قابل تأیید نیست.';
    exit;
  end;

  LogSetupStage('PASS', 'legacy-service-disable-before-copy-' + ServiceName, 0);
end;

function RestoreDatabaseUpgradeIfNeeded: Boolean;
var
  ResultCode: Integer;
  Started: Boolean;
begin
  Result := True;
  if not DatabaseUpgradeAttempted then
    exit;

  ResultCode := -1;
  LogSetupStage('START', 'restore-database-upgrade', ResultCode);
  Started := Exec(ExpandConstant('{tmp}\HRMServerPreflight.exe'),
    '--data-dir "' + EnterpriseDataDir +
    '" --restore-legacy-database-upgrade --database-upgrade-state-file "' +
    DatabaseUpgradeStatePath + '"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if Started and (ResultCode = 0) then
  begin
    LogSetupStage('PASS', 'restore-database-upgrade', ResultCode);
    DatabaseUpgradeAttempted := False;
  end
  else
  begin
    LogSetupStage('FAIL', 'restore-database-upgrade', ResultCode);
    Result := False;
  end;
end;


procedure RestoreOriginalServiceIfNeeded;
var
  ResultCode: Integer;
  Started: Boolean;
  SidArgument: String;
  RestoreOK: Boolean;
begin
  if ServiceTransactionCommitted or (not ServiceExistedBeforeInstall) then
    exit;
  if not (ServiceStoppedForUpgrade or ServiceCutoverAttempted) then
    exit;

  RestoreOK := True;
  LogSetupStage('START', 'restore-original-service-transaction', -1);

  RunIgnored(ExpandConstant('{tmp}\HRMServerPreflight.exe'),
    '--data-dir "' + EnterpriseDataDir +
    '" --stop-windows-service HRMCentralService --service-stop-timeout 30');

  if not RestoreDatabaseUpgradeIfNeeded then
    RestoreOK := False;

  if ServiceCutoverAttempted then
  begin
    ResultCode := -1;
    Started := Exec(ExpandConstant('{tmp}\HRMServerPreflight.exe'),
      '--set-windows-service-image HRMCentralService --service-image-executable "' +
      OriginalServiceExe + '"',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    if Started and (ResultCode = 0) then
      LogSetupStage('PASS', 'restore-original-service-image', ResultCode)
    else
    begin
      LogSetupStage('FAIL', 'restore-original-service-image', ResultCode);
      RestoreOK := False;
    end;

    ResultCode := -1;
    Started := Exec(ExpandConstant('{sys}\sc.exe'),
      'config HRMCentralService start= ' +
      ServiceStartModeArgument(OriginalServiceStartType),
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    if Started and (ResultCode = 0) then
      LogSetupStage('PASS', 'restore-original-service-startmode', ResultCode)
    else
    begin
      LogSetupStage('FAIL', 'restore-original-service-startmode', ResultCode);
      RestoreOK := False;
    end;

    SidArgument := ServiceSidTypeArgument(OriginalServiceSidType);
    ResultCode := -1;
    Started := Exec(ExpandConstant('{sys}\sc.exe'),
      'sidtype HRMCentralService ' + SidArgument,
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    if Started and (ResultCode = 0) then
      LogSetupStage('PASS', 'restore-original-service-sidtype', ResultCode)
    else
    begin
      LogSetupStage('FAIL', 'restore-original-service-sidtype', ResultCode);
      RestoreOK := False;
    end;

    ResultCode := -1;
    Started := Exec(ExpandConstant('{sys}\sc.exe'),
      'config HRMCentralService obj= "NT AUTHORITY\LocalService" password= ""',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    if Started and (ResultCode = 0) then
      LogSetupStage('PASS', 'restore-original-service-account', ResultCode)
    else
    begin
      LogSetupStage('FAIL', 'restore-original-service-account', ResultCode);
      RestoreOK := False;
    end;
  end;

  if ServiceWasRunningBeforeInstall and RestoreOK then
  begin
    ResultCode := -1;
    Started := Exec(ExpandConstant('{tmp}\HRMServerPreflight.exe'),
      '--data-dir "' + EnterpriseDataDir +
      '" --start-windows-service HRMCentralService --service-start-timeout 30',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    if Started and (ResultCode = 0) then
    begin
      LogSetupStage('PASS', 'restore-original-service-running', ResultCode);
      ResultCode := -1;
      Started := Exec(ExpandConstant('{tmp}\HRMServerPreflight.exe'),
        '--data-dir "' + EnterpriseDataDir +
        '" --health-check https://127.0.0.1:8765 --health-timeout 30',
        '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      if Started and (ResultCode = 0) then
        LogSetupStage('PASS', 'restore-original-service-health', ResultCode)
      else
      begin
        LogSetupStage('FAIL', 'restore-original-service-health', ResultCode);
        RestoreOK := False;
      end;
    end
    else
    begin
      LogSetupStage('FAIL', 'restore-original-service-running', ResultCode);
      RestoreOK := False;
    end;
  end;

  if RestoreOK then
  begin
    LogSetupStage('PASS', 'restore-original-service-transaction', 0);
    ServiceStoppedForUpgrade := False;
    ServiceCutoverAttempted := False;
  end
  else
    LogSetupStage('FAIL', 'restore-original-service-transaction', -1);
end;

procedure RecoverServerAfterFailure;
var
  ResultCode: Integer;
  Started: Boolean;
begin
  if (ServiceCutoverStatePath <> '') and FileExists(ServiceCutoverStatePath) then
  begin
    ResultCode := -1;
    LogSetupStage('START', 'recover-durable-installer-transaction', ResultCode);
    Started := Exec(ExpandConstant('{tmp}\HRMServerPreflight.exe'),
      '--data-dir "' + EnterpriseDataDir +
      '" --recover-installer-upgrade --service-cutover-state-file "' +
      ServiceCutoverStatePath + '" --database-upgrade-state-file "' +
      DatabaseUpgradeStatePath + '"',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    if Started and (ResultCode = 0) then
    begin
      LogSetupStage('PASS', 'recover-durable-installer-transaction', ResultCode);
      ServiceStoppedForUpgrade := False;
      ServiceCutoverAttempted := False;
      ServiceTransactionReady := False;
      DatabaseUpgradeAttempted := False;
    end
    else
      LogSetupStage('FAIL', 'recover-durable-installer-transaction', ResultCode);
    exit;
  end;

  if ServiceExistedBeforeInstall then
    RestoreOriginalServiceIfNeeded
  else
  begin
    if ServiceCutoverAttempted then
      RunIgnored(ExpandConstant('{tmp}\HRMServerPreflight.exe'),
        '--data-dir "' + EnterpriseDataDir +
        '" --stop-windows-service HRMCentralService --service-stop-timeout 30');

    RestoreDatabaseUpgradeIfNeeded;

    if ServiceCutoverAttempted then
    begin
      RunIgnored(ExpandConstant('{tmp}\HRMServerPreflight.exe'),
        '--delete-windows-service HRMCentralService');
      RunIgnored(ExpandConstant('{sys}\netsh.exe'),
        'advfirewall firewall delete rule name="HRM Central Service 8765"');
      ServiceCutoverAttempted := False;
    end;
  end;
end;


procedure VerifyOneLegacyServiceDisabled(ServiceName: String);
var
  StartType: Cardinal;
begin
  if not RegKeyExists(HKLM, ServiceRegistryPath(ServiceName)) then
    exit;

  if (not RegQueryDWordValue(HKLM, ServiceRegistryPath(ServiceName), 'Start', StartType)) or
     (StartType <> 4) then
  begin
    LogSetupStage('FAIL', 'legacy-service-final-validation-' + ServiceName, -1);
    ProvisionFailed := True;
    RecoverServerAfterFailure;
    RaiseException('Legacy Windows Service was not disabled: ' + ServiceName);
  end;

  LogSetupStage('PASS', 'legacy-service-final-validation-' + ServiceName, 0);
end;

procedure VerifyLegacyServicesDisabled;
begin
  VerifyOneLegacyServiceDisabled('SazmanHREnterpriseCentral');
  VerifyOneLegacyServiceDisabled('SazmanHRCentral');
  VerifyOneLegacyServiceDisabled('SazmanHRNetworkServer');
end;

procedure RunRequired(Filename: String; Parameters: String; StageName: String);
var
  ResultCode: Integer;
  Started: Boolean;
begin
  ResultCode := -1;
  LogSetupStage('START', StageName, ResultCode);
  Started := Exec(Filename, Parameters, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if (not Started) or (ResultCode <> 0) then
  begin
    LogSetupStage('FAIL', StageName, ResultCode);
    LogProtectedDiagnostics;
    ProvisionFailed := True;
    RecoverServerAfterFailure;
    SuppressibleMsgBox('راه‌اندازی سرور مرکزی در مرحله «' + StageName + '» شکست خورد.' + #13#10 +
      'کد خروج: ' + IntToStr(ResultCode) + #13#10 +
      'گزارش عیب‌یابی:' + #13#10 +
      EnterpriseDataDir + '\logs\setup-server.log' + #13#10 + #13#10 +
      'نصب موفق اعلام نمی‌شود و باید گزارش بررسی شود.', mbError, MB_OK, IDOK);
    RaiseException('HRM server provisioning failed: ' + StageName);
  end
  else
    LogSetupStage('PASS', StageName, ResultCode);
end;

procedure ProvisionEnterpriseServer;
var
  DataDir: String;
  ServerExe: String;
  ServiceExe: String;
  ServiceControlExe: String;
  SeedPath: String;
  DiagnosticPath: String;
  ServiceStatePath: String;
  ServiceStateContent: AnsiString;
  ResultCode: Integer;
  Started: Boolean;
begin
  DataDir := EnterpriseDataDir;
  ServerExe := ExpandConstant('{app}\Server\HRMServer.exe');
  ServiceExe := ServiceRuntimeExe;
  ServiceControlExe := ExpandConstant('{tmp}\HRMServerPreflight.exe');
  SeedPath := ExpandConstant('{tmp}\hrm-seed.sqlite');
  DiagnosticPath := DataDir + '\logs\setup-server.log';
  DatabaseUpgradeStatePath := DataDir + '\backups\upgrade-transactions\installer-upgrade-state.json';
  ServiceCutoverStatePath := DataDir + '\backups\upgrade-transactions\service-cutover-state.json';

  RunRequired(ServiceControlExe,
    '--verify-service-runtime "' + ServiceRuntimeDir +
    '" --diagnostic-log "' + DiagnosticPath + '"',
    'اعتبارسنجی کامل runtime سرویس');

  if ServiceExistedBeforeInstall then
  begin
    ServiceStatePath := ExpandConstant('{tmp}\service-cutover-state.json');
    DeleteFile(ServiceStatePath);
    ResultCode := -1;
    LogSetupStage('START', 'service-stop-for-cutover', ResultCode);
    Started := Exec(ServiceControlExe,
      '--data-dir "' + DataDir +
      '" --stop-windows-service HRMCentralService --service-stop-timeout 30' +
      ' --service-state-file "' + ServiceStatePath +
      '" --diagnostic-log "' + DiagnosticPath + '"',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    if (not Started) or (ResultCode <> 0) then
    begin
      LogSetupStage('FAIL', 'service-stop-for-cutover', ResultCode);
      ProvisionFailed := True;
      RecoverServerAfterFailure;
      RaiseException('HRM service cutover stop failed.');
    end;
    if not LoadStringFromLockedFile(ServiceStatePath, ServiceStateContent) then
    begin
      LogSetupStage('FAIL', 'service-cutover-state-validation', -1);
      ProvisionFailed := True;
      ServiceStoppedForUpgrade := True;
      RecoverServerAfterFailure;
      RaiseException('HRM service cutover state could not be validated.');
    end;
    ServiceStoppedForUpgrade := True;
    LogSetupStage('PASS', 'service-stop-for-cutover', 0);

    RunRequired(ServiceControlExe,
      '--advance-service-cutover service_stopped --service-cutover-state-file "' +
      ServiceCutoverStatePath + '" --diagnostic-log "' + DiagnosticPath + '"',
      'ثبت durable phase توقف سرویس');
  end
  else
  begin
    RunRequired(ServiceControlExe,
      '--data-dir "' + DataDir +
      '" --prepare-service-install HRMCentralService --service-image-executable "' +
      ServiceExe + '" --service-cutover-state-file "' + ServiceCutoverStatePath +
      '" --diagnostic-log "' + DiagnosticPath + '"',
      'ثبت durable transaction نصب سرویس جدید');
    RunRequired(ServiceControlExe,
      '--advance-service-cutover service_stopped --service-cutover-state-file "' +
      ServiceCutoverStatePath + '" --diagnostic-log "' + DiagnosticPath + '"',
      'ثبت durable phase نبود سرویس قبلی');
  end;

  if FileExists(DataDir + '\hrm.sqlite') then
  begin
    DeleteFile(DatabaseUpgradeStatePath);
    DatabaseUpgradeAttempted := True;
    RunRequired(ServiceControlExe,
      '--data-dir "' + DataDir +
      '" --upgrade-legacy-database --database-upgrade-state-file "' +
      DatabaseUpgradeStatePath +
      '" --diagnostic-log "' + DiagnosticPath + '"',
      'database-upgrade-alpha4');
  end;

  RunRequired(ServerExe,
    '--data-dir "' + DataDir + '" --seed "' + SeedPath +
    '" --init-only --diagnostic-log "' + DiagnosticPath + '"',
    'ساخت و اعتبارسنجی دیتابیس جدید');

  if ServiceExistedBeforeInstall then
  begin
    ServiceCutoverAttempted := True;
    RunRequired(ServiceControlExe,
      '--set-windows-service-image HRMCentralService --service-image-executable "' +
      ServiceExe + '" --diagnostic-log "' + DiagnosticPath + '"',
      'سوئیچ تراکنشی ImagePath سرویس');
  end
  else
  begin
    ServiceCutoverAttempted := True;
    RunRequired(ServiceExe, '--startup auto install', 'نصب Windows Service');
  end;

  RunRequired(ServiceControlExe,
    '--advance-service-cutover image_switched --service-cutover-state-file "' +
    ServiceCutoverStatePath + '" --diagnostic-log "' + DiagnosticPath + '"',
    'ثبت durable phase فعال‌سازی نسل سرویس');

  RunRequired(ExpandConstant('{sys}\sc.exe'),
    'config HRMCentralService start= auto',
    'اعمال Automatic start برای سرویس');
  RunRequired(ExpandConstant('{sys}\sc.exe'),
    'sidtype HRMCentralService unrestricted',
    'فعال‌سازی Service SID اختصاصی');
  RunRequired(ExpandConstant('{sys}\sc.exe'),
    'qsidtype HRMCentralService',
    'اعتبارسنجی Service SID اختصاصی');
  RunRequired(ExpandConstant('{sys}\sc.exe'),
    'config HRMCentralService obj= "NT AUTHORITY\LocalService" password= ""',
    'اعمال حساب داخلی کم‌اختیار برای سرویس');

  RunRequired(ExpandConstant('{sys}\icacls.exe'),
    '"' + DataDir + '" /grant:r *S-1-5-32-544:(OI)(CI)F ' +
    '"NT SERVICE\HRMCentralService:(OI)(CI)M" /T',
    'اعمال دسترسی اولیه Service SID');

  RunIgnored(ExpandConstant('{sys}\netsh.exe'),
    'advfirewall firewall delete rule name="HRM Central Service 8765"');
  RunRequired(ExpandConstant('{sys}\netsh.exe'),
    'advfirewall firewall add rule name="HRM Central Service 8765" dir=in action=allow protocol=TCP localport=8765 profile=domain,private',
    'ثبت قانون Firewall');

  RunRequired(ServiceControlExe,
    '--data-dir "' + DataDir +
    '" --start-windows-service HRMCentralService --service-start-timeout 30' +
    ' --diagnostic-log "' + DiagnosticPath + '"',
    'شروع Windows Service');
  RunRequired(ServiceControlExe,
    '--advance-service-cutover service_started --service-cutover-state-file "' +
    ServiceCutoverStatePath + '" --diagnostic-log "' + DiagnosticPath + '"',
    'ثبت durable phase شروع سرویس');
  RunRequired(ServerExe,
    '--data-dir "' + DataDir + '" --health-check https://127.0.0.1:8765 --health-timeout 30' +
    ' --diagnostic-log "' + DiagnosticPath + '"',
    'آزمون دسترسی سرویس پیش از سخت‌سازی ACL');

  RunRequired(ExpandConstant('{sys}\icacls.exe'),
    '"' + DataDir + '" /inheritance:d /T',
    'تبدیل ارث‌بری ACL به مجوزهای صریح');
  RunRequired(ExpandConstant('{sys}\icacls.exe'),
    '"' + DataDir + '" /remove:g *S-1-1-0 *S-1-5-11 *S-1-5-32-545 /T',
    'حذف دسترسی گروه‌های عمومی از داده‌های عملیاتی');
  RunRequired(ExpandConstant('{sys}\icacls.exe'),
    '"' + DataDir + '" /grant:r *S-1-5-32-544:(OI)(CI)F ' +
    '"NT SERVICE\HRMCentralService:(OI)(CI)M" /T',
    'اعمال دسترسی صریح مدیران و Service SID');
  RunRequired(ExpandConstant('{sys}\icacls.exe'),
    '"' + DataDir + '" /verify /T',
    'اعتبارسنجی نهایی ACL');

  RunRequired(ServiceControlExe,
    '--data-dir "' + DataDir +
    '" --stop-windows-service HRMCentralService --service-stop-timeout 30' +
    ' --diagnostic-log "' + DiagnosticPath + '"',
    'توقف سرویس پس از سخت‌سازی ACL');
  RunRequired(ServiceControlExe,
    '--data-dir "' + DataDir +
    '" --start-windows-service HRMCentralService --service-start-timeout 30' +
    ' --diagnostic-log "' + DiagnosticPath + '"',
    'راه‌اندازی مجدد سرویس پس از سخت‌سازی ACL');
  RunRequired(ServerExe,
    '--data-dir "' + DataDir + '" --health-check https://127.0.0.1:8765 --health-timeout 30' +
    ' --diagnostic-log "' + DiagnosticPath + '"',
    'آزمون نهایی TLS و سرویس پس از سخت‌سازی ACL');

  VerifyLegacyServicesDisabled;
  if ServiceExistedBeforeInstall and (not ServiceWasRunningBeforeInstall) then
  begin
    RunRequired(ServiceControlExe,
      '--data-dir "' + DataDir +
      '" --stop-windows-service HRMCentralService --service-stop-timeout 30' +
      ' --diagnostic-log "' + DiagnosticPath + '"',
      'بازگردانی وضعیت توقف قبلی سرویس');
    ServiceStoppedForUpgrade := False;
  end;

  RunRequired(ServiceControlExe,
    '--advance-service-cutover ready --service-cutover-state-file "' +
    ServiceCutoverStatePath + '" --diagnostic-log "' + DiagnosticPath + '"',
    'ثبت durable phase آمادگی transaction');

  ServiceTransactionReady := True;
  LogSetupStage('PASS', 'service-runtime-transaction-ready', 0);
end;


procedure InitializeWizard;
begin
  ProvisionFailed := False;
  ServiceExistedBeforeInstall := False;
  ServiceWasRunningBeforeInstall := False;
  ServiceStoppedForUpgrade := False;
  PreInstallServiceHandled := False;
  ServiceCutoverAttempted := False;
  ServiceTransactionReady := False;
  ServiceTransactionCommitted := False;
  DatabaseUpgradeStatePath := EnterpriseDataDir + '\backups\upgrade-transactions\installer-upgrade-state.json';
  ServiceCutoverStatePath := EnterpriseDataDir + '\backups\upgrade-transactions\service-cutover-state.json';
  OriginalServiceImagePath := '';
  OriginalServiceExe := '';
  OriginalServiceStartType := 0;
  OriginalServiceObjectName := '';
  OriginalServiceSidType := 0;
  SetupCompleted := False;
  LegacyServicesHandled := False;
  LegacyEnterpriseExists := False;
  LegacyEnterpriseWasRunning := False;
  LegacyEnterpriseStartType := 0;
  LegacyCentralExists := False;
  LegacyCentralWasRunning := False;
  LegacyCentralStartType := 0;
  LegacyNetworkExists := False;
  LegacyNetworkWasRunning := False;
  LegacyNetworkStartType := 0;
  ServerPage := CreateInputQueryPage(wpSelectComponents,
    'اتصال به سرور مرکزی',
    'آدرس سرویس مرکزی را مشخص کنید.',
    'در نصب کامل مقدار محلی مناسب است. در رایانه مدیر، IP سرور اداره را وارد کنید.');
  ServerPage.Add('آدرس (نمونه: https://192.168.1.10:8765):', False);
  ServerPage.Values[0] := 'https://127.0.0.1:8765';
end;

function GetServerUrl(Param: String): String;
begin
  Result := Trim(ServerPage.Values[0]);
  if Result = '' then
    Result := 'https://127.0.0.1:8765';
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  PreflightExe: String;
  PreflightDataDir: String;
  DiagnosticPath: String;
  ServiceStateContent: AnsiString;
  ResultCode: Integer;
  Started: Boolean;
begin
  if WizardIsComponentSelected('client') and (Trim(ServerPage.Values[0]) = '') then
    Result := 'آدرس سرور مرکزی الزامی است.'
  else
    Result := '';

  if (Result = '') and WizardIsComponentSelected('server') then
  begin
    ProvisionFailed := False;
    try
      ExtractTemporaryFile('HRMServerPreflight.exe');
      ExtractTemporaryFile('hrm-seed.sqlite');
      PreflightExe := ExpandConstant('{tmp}\HRMServerPreflight.exe');
      PreflightDataDir := ExpandConstant('{tmp}\hrm-server-preflight-data');
      DiagnosticPath := EnterpriseDataDir + '\logs\setup-server.log';
      DatabaseUpgradeStatePath := EnterpriseDataDir +
        '\backups\upgrade-transactions\installer-upgrade-state.json';
      ServiceCutoverStatePath := EnterpriseDataDir +
        '\backups\upgrade-transactions\service-cutover-state.json';

      if FileExists(ServiceCutoverStatePath) and (not PreInstallServiceHandled) then
      begin
        ResultCode := -1;
        LogSetupStage('START', 'recover-previous-installer-transaction', ResultCode);
        Started := Exec(PreflightExe,
          '--data-dir "' + EnterpriseDataDir +
          '" --recover-installer-upgrade --service-cutover-state-file "' +
          ServiceCutoverStatePath + '" --database-upgrade-state-file "' +
          DatabaseUpgradeStatePath + '" --diagnostic-log "' + DiagnosticPath + '"',
          '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
        if (not Started) or (ResultCode <> 0) then
        begin
          LogSetupStage('FAIL', 'recover-previous-installer-transaction', ResultCode);
          LogProtectedDiagnostics;
          ProvisionFailed := True;
          Result := 'بازیابی transaction ناتمام نصب قبلی شکست خورد (کد ' +
            IntToStr(ResultCode) + '). نصب جدید بدون بازیابی ایمن ادامه پیدا نمی‌کند.';
          exit;
        end;
        LogSetupStage('PASS', 'recover-previous-installer-transaction', ResultCode);
        ServiceStoppedForUpgrade := False;
        ServiceCutoverAttempted := False;
        ServiceTransactionReady := False;
        ServiceTransactionCommitted := False;
        DatabaseUpgradeAttempted := False;
        PreInstallServiceHandled := False;
      end;

      if not LegacyServicesHandled then
      begin
        LegacyServicesHandled := True;
        HandleLegacyServiceBeforeCopy(PreflightExe, DiagnosticPath,
          'SazmanHREnterpriseCentral', LegacyEnterpriseExists,
          LegacyEnterpriseWasRunning, LegacyEnterpriseStartType, Result);
        if Result = '' then
          HandleLegacyServiceBeforeCopy(PreflightExe, DiagnosticPath,
            'SazmanHRCentral', LegacyCentralExists,
            LegacyCentralWasRunning, LegacyCentralStartType, Result);
        if Result = '' then
          HandleLegacyServiceBeforeCopy(PreflightExe, DiagnosticPath,
            'SazmanHRNetworkServer', LegacyNetworkExists,
            LegacyNetworkWasRunning, LegacyNetworkStartType, Result);
        if Result <> '' then
        begin
          LogProtectedDiagnostics;
          ProvisionFailed := True;
          RestoreLegacyServicesIfNeeded;
          exit;
        end;
      end;

      ServiceExistedBeforeInstall := ServiceExistsInScm('HRMCentralService');

      if ServiceExistedBeforeInstall and (not PreInstallServiceHandled) then
      begin
        SnapshotOriginalServiceConfiguration(Result);
        if Result = '' then
        begin
          ResultCode := -1;
          LogSetupStage('START', 'prepare-existing-service-cutover-before-copy', ResultCode);
          Started := Exec(PreflightExe,
            '--data-dir "' + EnterpriseDataDir +
            '" --prepare-service-cutover HRMCentralService --service-image-executable "' +
            ServiceRuntimeExe + '" --service-cutover-state-file "' + ServiceCutoverStatePath +
            '" --diagnostic-log "' + DiagnosticPath + '"',
            '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
          if (not Started) or (ResultCode <> 0) then
          begin
            LogSetupStage('FAIL', 'prepare-existing-service-cutover-before-copy', ResultCode);
            ProvisionFailed := True;
            Result := 'ثبت snapshot پایدار سرویس فعلی پیش از RestartManager شکست خورد (کد ' +
              IntToStr(ResultCode) + ').';
          end
          else if not LoadStringFromLockedFile(ServiceCutoverStatePath, ServiceStateContent) then
          begin
            LogSetupStage('FAIL', 'prepare-existing-service-cutover-state-validation', -1);
            ProvisionFailed := True;
            Result := 'وضعیت پایدار سرویس فعلی پس از snapshot قابل اعتبارسنجی نیست.';
          end
          else if
            (Pos('"was_running": true', Lowercase(String(ServiceStateContent))) = 0) and
            (Pos('"was_running": false', Lowercase(String(ServiceStateContent))) = 0) then
          begin
            LogSetupStage('FAIL', 'prepare-existing-service-cutover-state-validation', -1);
            ProvisionFailed := True;
            Result := 'فیلد was_running در snapshot پایدار سرویس فعلی معتبر نیست.';
          end
          else
          begin
            ServiceWasRunningBeforeInstall :=
              Pos('"was_running": true', Lowercase(String(ServiceStateContent))) > 0;
            PreInstallServiceHandled := True;
            LogSetupStage('PASS', 'prepare-existing-service-cutover-before-copy', 0);
          end;
        end;
      end
      else if not ServiceExistedBeforeInstall then
        PreInstallServiceHandled := True;

      if Result = '' then
      begin
        DelTree(PreflightDataDir, True, True, True);
        ResultCode := -1;
        LogSetupStage('START', 'server-preflight-isolated', ResultCode);
        Started := Exec(PreflightExe,
          '--data-dir "' + PreflightDataDir + '" --seed "' +
          ExpandConstant('{tmp}\hrm-seed.sqlite') +
          '" --init-only --diagnostic-log "' + DiagnosticPath + '"',
          '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
        if (not Started) or (ResultCode <> 0) then
        begin
          LogSetupStage('FAIL', 'server-preflight-isolated', ResultCode);
          LogProtectedDiagnostics;
          ProvisionFailed := True;
          Result := 'پیش‌آزمون ایزوله سرور مرکزی شکست خورد (کد ' +
            IntToStr(ResultCode) + ').' + #13#10 +
            'گزارش: ' + DiagnosticPath + #13#10 +
            'نصب متوقف شد و نصب فعلی دست‌نخورده می‌ماند.';
        end
        else
          LogSetupStage('PASS', 'server-preflight-isolated', ResultCode);
        DelTree(PreflightDataDir, True, True, True);
      end;
    except
      LogSetupStage('EXCEPTION', 'server-preflight-isolated', -1);
      LogProtectedDiagnostics;
      ProvisionFailed := True;
      Result := 'اجرای پیش‌آزمون بسته مستقل ممکن نشد: ' + GetExceptionMessage;
    end;

    if Result <> '' then
    begin
      RestoreOriginalServiceIfNeeded;
      RestoreLegacyServicesIfNeeded;
      PreInstallServiceHandled := False;
    end;
  end;
end;


function GetCustomSetupExitCode: Integer;
begin
  if ProvisionFailed then
    Result := 1603
  else
    Result := 0;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if WizardIsComponentSelected('server') then
    begin
      ProvisionEnterpriseServer;
      if FileExists(EnterpriseDataDir + '\FIRST_LOGIN.txt') then
        SuppressibleMsgBox('سرور مرکزی با موفقیت نصب و آزمون شد. اطلاعات ورود یک‌بارمصرف:' + #13#10 +
          EnterpriseDataDir + '\FIRST_LOGIN.txt' + #13#10 +
          'این فایل فقط برای مدیران سیستم قابل دسترسی است.' + #13#10 +
          'پس از اولین ورود تغییر رمز اجباری است.', mbInformation, MB_OK, IDOK)
      else
        SuppressibleMsgBox('سرور مرکزی با موفقیت نصب، به‌روزرسانی و آزمون شد.', mbInformation, MB_OK, IDOK);
    end;
  end
  else if CurStep = ssDone then
  begin
    if WizardIsComponentSelected('server') and ServiceTransactionReady then
    begin
      RunRequired(ExpandConstant('{tmp}\HRMServerPreflight.exe'),
        '--data-dir "' + EnterpriseDataDir +
        '" --commit-installer-upgrade --service-cutover-state-file "' +
        ServiceCutoverStatePath + '" --database-upgrade-state-file "' +
        DatabaseUpgradeStatePath + '" --diagnostic-log "' +
        EnterpriseDataDir + '\logs\setup-server.log"',
        'ثبت durable commit نهایی installer transaction');
      ServiceTransactionCommitted := True;
      DatabaseUpgradeAttempted := False;
      LogSetupStage('PASS', 'service-runtime-transaction-commit', 0);
    end;
    SetupCompleted := True;
  end;
end;

procedure DeinitializeSetup;
var
  ResultCode: Integer;
  Started: Boolean;
begin
  if not SetupCompleted then
  begin
    if WizardIsComponentSelected('server') and
       (ServiceCutoverStatePath <> '') and FileExists(ServiceCutoverStatePath) then
    begin
      ResultCode := -1;
      LogSetupStage('START', 'deinitialize-durable-installer-recovery', ResultCode);
      Started := Exec(ExpandConstant('{tmp}\HRMServerPreflight.exe'),
        '--data-dir "' + EnterpriseDataDir +
        '" --recover-installer-upgrade --service-cutover-state-file "' +
        ServiceCutoverStatePath + '" --database-upgrade-state-file "' +
        DatabaseUpgradeStatePath + '"',
        '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      if Started and (ResultCode = 0) then
      begin
        LogSetupStage('PASS', 'deinitialize-durable-installer-recovery', ResultCode);
        ServiceStoppedForUpgrade := False;
        ServiceCutoverAttempted := False;
        ServiceTransactionReady := False;
        DatabaseUpgradeAttempted := False;
      end
      else
        LogSetupStage('FAIL', 'deinitialize-durable-installer-recovery', ResultCode);
    end
    else
      RestoreOriginalServiceIfNeeded;
    RestoreLegacyServicesIfNeeded;
  end;
end;
