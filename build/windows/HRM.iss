#ifndef ProjectRoot
  #error ProjectRoot is required
#endif
#ifndef DistDir
  #error DistDir is required
#endif

[Setup]
AppId={{4F82A3C7-1D55-4B80-9F21-6B3D4E7A1600}
AppName=HRM
AppVersion=0.4.0-alpha.2
AppPublisher=HRM
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
Source: "{#DistDir}\HRMService.exe"; DestDir: "{app}\Server"; Components: server; Flags: ignoreversion
Source: "{#DistDir}\HRMMigration.exe"; DestDir: "{app}\Server"; Components: server; Flags: ignoreversion
Source: "{#ProjectRoot}\docs\deployment-guide-fa.md"; DestDir: "{app}\Docs"; Flags: ignoreversion
Source: "{#ProjectRoot}\docs\windows-test-checklist-fa.md"; DestDir: "{app}\Docs"; Flags: ignoreversion
Source: "{#ProjectRoot}\tools\collect-diagnostics.cmd"; DestDir: "{app}\Tools"; Flags: ignoreversion
Source: "{#ProjectRoot}\docs\V040A2-ENTERPRISE-DATA-INTEGRATION.md"; DestDir: "{app}\Docs"; Flags: ignoreversion
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
Filename: "{app}\Server\HRMService.exe"; Parameters: "--wait 30 stop"; RunOnceId: "StopEnterpriseService"; Flags: runhidden waituntilterminated; Components: server
Filename: "{app}\Server\HRMService.exe"; Parameters: "remove"; RunOnceId: "RemoveEnterpriseService"; Flags: runhidden waituntilterminated; Components: server
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""HRM Central Service 8765"""; RunOnceId: "RemoveEnterpriseFirewall"; Flags: runhidden waituntilterminated; Components: server

[Code]
var
  ServerPage: TInputQueryWizardPage;
  ServiceExistedBeforeInstall: Boolean;
  ServiceWasRunningBeforeInstall: Boolean;
  ServiceStoppedForUpgrade: Boolean;
  PreInstallServiceHandled: Boolean;
  SetupCompleted: Boolean;
  ProvisionFailed: Boolean;

function EnterpriseDataDir: String;
begin
  Result := ExpandConstant('{commonappdata}\HRM-Kermanshah');
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

procedure RestoreOriginalServiceIfNeeded;
var
  ResultCode: Integer;
  Started: Boolean;
begin
  if ServiceStoppedForUpgrade and ServiceExistedBeforeInstall then
  begin
    LogSetupStage('START', 'restore-original-service', -1);
    ResultCode := -1;
    Started := Exec(ExpandConstant('{app}\Server\HRMService.exe'),
      '--wait 30 start', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    if Started and (ResultCode = 0) then
    begin
      LogSetupStage('PASS', 'restore-original-service', ResultCode);
      ServiceStoppedForUpgrade := False;
    end
    else
      LogSetupStage('FAIL', 'restore-original-service', ResultCode);
  end;
end;

procedure RecoverServerAfterFailure;
begin
  if ServiceExistedBeforeInstall then
    { Keep the upgraded binary stopped while Inno rolls files back. The old
      binary is restarted from DeinitializeSetup after rollback completes. }
    RunIgnored(ExpandConstant('{app}\Server\HRMService.exe'), '--wait 30 stop')
  else
  begin
    RunIgnored(ExpandConstant('{app}\Server\HRMService.exe'), '--wait 30 stop');
    RunIgnored(ExpandConstant('{app}\Server\HRMService.exe'), 'remove');
    RunIgnored(ExpandConstant('{sys}\netsh.exe'),
      'advfirewall firewall delete rule name="HRM Central Service 8765"');
  end;
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
  SeedPath: String;
  DiagnosticPath: String;
begin
  DataDir := EnterpriseDataDir;
  ServerExe := ExpandConstant('{app}\Server\HRMServer.exe');
  ServiceExe := ExpandConstant('{app}\Server\HRMService.exe');
  SeedPath := ExpandConstant('{tmp}\hrm-seed.sqlite');
  DiagnosticPath := DataDir + '\logs\setup-server.log';

  RunRequired(ServerExe,
    '--data-dir "' + DataDir + '" --seed "' + SeedPath +
    '" --init-only --diagnostic-log "' + DiagnosticPath + '"',
    'ساخت و اعتبارسنجی دیتابیس جدید');

  if ServiceExistedBeforeInstall then
    RunRequired(ServiceExe, '--startup auto update', 'به‌روزرسانی Windows Service')
  else
    RunRequired(ServiceExe, '--startup auto install', 'نصب Windows Service');

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
  RunRequired(ServiceExe, '--wait 30 start', 'شروع Windows Service');
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

  RunRequired(ServiceExe, '--wait 30 stop', 'توقف سرویس پس از سخت‌سازی ACL');
  RunRequired(ServiceExe, '--wait 30 start', 'راه‌اندازی مجدد سرویس پس از سخت‌سازی ACL');
  RunRequired(ServerExe,
    '--data-dir "' + DataDir + '" --health-check https://127.0.0.1:8765 --health-timeout 30' +
    ' --diagnostic-log "' + DiagnosticPath + '"',
    'آزمون نهایی TLS و سرویس پس از سخت‌سازی ACL');

  if ServiceExistedBeforeInstall and (not ServiceWasRunningBeforeInstall) then
    RunRequired(ServiceExe, '--wait 30 stop', 'بازگردانی وضعیت توقف قبلی سرویس');
  ServiceStoppedForUpgrade := False;
end;

procedure InitializeWizard;
begin
  ProvisionFailed := False;
  ServiceExistedBeforeInstall := False;
  ServiceWasRunningBeforeInstall := False;
  ServiceStoppedForUpgrade := False;
  PreInstallServiceHandled := False;
  SetupCompleted := False;
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
  DiagnosticPath: String;
  ServiceStatePath: String;
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
      DiagnosticPath := EnterpriseDataDir + '\logs\setup-server.log';
      ServiceExistedBeforeInstall := RegKeyExists(HKLM,
        'SYSTEM\CurrentControlSet\Services\HRMCentralService');

      { This runs before Inno checks/replaces installed files. The frozen
        preflight helper stops the proven alpha.4 service and verifies SCM state. }
      if ServiceExistedBeforeInstall and (not PreInstallServiceHandled) then
      begin
        ServiceStatePath := ExpandConstant('{tmp}\service-stop-state.json');
        DeleteFile(ServiceStatePath);
        ServiceWasRunningBeforeInstall := True;
        ServiceStoppedForUpgrade := True;
        ResultCode := -1;
        LogSetupStage('START', 'service-stop-before-copy', ResultCode);
        Started := Exec(PreflightExe,
          '--data-dir "' + EnterpriseDataDir +
          '" --stop-windows-service HRMCentralService --service-stop-timeout 30' +
          ' --service-state-file "' + ServiceStatePath +
          '" --diagnostic-log "' + DiagnosticPath + '"',
          '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
        if (not Started) or (ResultCode <> 0) then
        begin
          LogSetupStage('FAIL', 'service-stop-before-copy', ResultCode);
          LogProtectedDiagnostics;
          ProvisionFailed := True;
          Result := 'توقف ایمن سرویس پیش از جایگزینی فایل‌ها شکست خورد (کد ' +
            IntToStr(ResultCode) + ').';
        end
        else if not LoadStringFromLockedFile(ServiceStatePath, ServiceStateContent) then
        begin
          LogSetupStage('FAIL', 'service-stop-state-validation', -1);
          LogProtectedDiagnostics;
          ProvisionFailed := True;
          Result := 'وضعیت توقف سرویس قابل اعتبارسنجی نیست؛ نصب برای حفاظت از فایل‌ها متوقف شد.';
        end
        else
        begin
          if Pos('"exists": false', Lowercase(String(ServiceStateContent))) > 0 then
            ServiceExistedBeforeInstall := False;
          ServiceWasRunningBeforeInstall :=
            Pos('"was_running": true', Lowercase(String(ServiceStateContent))) > 0;
          ServiceStoppedForUpgrade := ServiceWasRunningBeforeInstall;
          PreInstallServiceHandled := True;
          LogSetupStage('PASS', 'service-stop-before-copy', 0);
        end;
      end
      else if not ServiceExistedBeforeInstall then
        PreInstallServiceHandled := True;

      if Result = '' then
      begin
        ResultCode := -1;
        LogSetupStage('START', 'server-preflight', ResultCode);
        Started := Exec(PreflightExe,
          '--data-dir "' + EnterpriseDataDir + '" --seed "' + ExpandConstant('{tmp}\hrm-seed.sqlite') +
          '" --init-only --diagnostic-log "' + DiagnosticPath + '"',
          '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
        if (not Started) or (ResultCode <> 0) then
        begin
          LogSetupStage('FAIL', 'server-preflight', ResultCode);
          LogProtectedDiagnostics;
          ProvisionFailed := True;
          Result := 'پیش‌آزمون سرور مرکزی شکست خورد (کد ' + IntToStr(ResultCode) + ').' + #13#10 +
            'گزارش: ' + DiagnosticPath + #13#10 +
            'نصب متوقف شد و موفق اعلام نمی‌شود.';
        end
        else
          LogSetupStage('PASS', 'server-preflight', ResultCode);
      end;
    except
      LogSetupStage('EXCEPTION', 'server-preflight', -1);
      LogProtectedDiagnostics;
      ProvisionFailed := True;
      Result := 'اجرای پیش‌آزمون بسته مستقل ممکن نشد: ' + GetExceptionMessage;
    end;

    if Result <> '' then
    begin
      RestoreOriginalServiceIfNeeded;
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
    SetupCompleted := True;
end;

procedure DeinitializeSetup;
begin
  if not SetupCompleted then
    RestoreOriginalServiceIfNeeded;
end;
