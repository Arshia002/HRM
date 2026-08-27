#ifndef ProjectRoot
  #error ProjectRoot is required
#endif
#ifndef DistDir
  #error DistDir is required
#endif
#ifndef SeedPath
  #error SeedPath is required
#endif
#ifndef AppVersion
  #error AppVersion is required
#endif

[Setup]
AppId={{4F82A3C7-1D55-4B80-9F21-6B3D4E7A1600}
AppName=HRM
AppVersion={#AppVersion}
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
Source: "{#SeedPath}"; DestName: "hrm-seed.sqlite"; Components: server; Flags: dontcopy noencryption
Source: "{#DistDir}\HRM.exe"; DestDir: "{app}\Client"; Components: client; Flags: ignoreversion
Source: "{#DistDir}\HRMServer.exe"; DestDir: "{app}\Server"; Components: server; Flags: ignoreversion
Source: "{#DistDir}\HRMService.exe"; DestDir: "{app}\Server"; Components: server; Flags: ignoreversion
Source: "{#ProjectRoot}\docs\راهنمای-استقرار.md"; DestDir: "{app}\Docs"; Flags: ignoreversion
Source: "{#ProjectRoot}\docs\چک‌لیست-تست-Windows.md"; DestDir: "{app}\Docs"; Flags: ignoreversion
Source: "{#ProjectRoot}\tools\collect-diagnostics.cmd"; DestDir: "{app}\Tools"; Flags: ignoreversion
Source: "{#ProjectRoot}\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\HRM"; Filename: "{app}\Client\HRM.exe"; Parameters: "--server {code:GetServerUrl}"; WorkingDir: "{app}\Client"; Components: client
Name: "{group}\HRM"; Filename: "{app}\Client\HRM.exe"; Parameters: "--server {code:GetServerUrl}"; Components: client
Name: "{group}\راهنمای استقرار"; Filename: "{app}\Docs\راهنمای-استقرار.md"
Name: "{group}\چک‌لیست تست Windows"; Filename: "{app}\Docs\چک‌لیست-تست-Windows.md"
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
  OwnerPage: TInputQueryWizardPage;
  ServiceExistedBeforeInstall: Boolean;
  ProvisionFailed: Boolean;

function GetInitialUsername(Param: String): String; forward;
function GetInitialDisplayName(Param: String): String; forward;

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

procedure RecoverServerAfterFailure;
begin
  if ServiceExistedBeforeInstall then
    RunIgnored(ExpandConstant('{app}\Server\HRMService.exe'), '--wait 30 start')
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
  { The seed is extracted only into Setup's protected temporary directory.
    It must never remain in Program Files after provisioning. }
  SeedPath := ExpandConstant('{tmp}\hrm-seed.sqlite');
  DiagnosticPath := DataDir + '\logs\setup-server.log';
  ServiceExistedBeforeInstall := RegKeyExists(HKLM,
    'SYSTEM\CurrentControlSet\Services\HRMCentralService');

  if ServiceExistedBeforeInstall then
    RunIgnored(ServiceExe, '--wait 30 stop');

  RunRequired(ServerExe,
    '--data-dir "' + DataDir + '" --seed "' + SeedPath +
    '" --initial-user "' + GetInitialUsername('') +
    '" --initial-display-name "' + GetInitialDisplayName('') +
    '" --init-only --diagnostic-log "' + DiagnosticPath + '"',
    'ساخت و اعتبارسنجی دیتابیس جدید');

  if ServiceExistedBeforeInstall then
  begin
    RunRequired(ServiceExe, '--startup auto update', 'به‌روزرسانی Windows Service')
  end
  else
    RunRequired(ServiceExe, '--startup auto install', 'نصب Windows Service');

  RunRequired(ExpandConstant('{sys}\sc.exe'),
    'config HRMCentralService obj= "NT SERVICE\HRMCentralService" password= ""',
    'اعمال حساب مجازی کم‌اختیار برای سرویس');
  RunRequired(ExpandConstant('{sys}\sc.exe'),
    'sidtype HRMCentralService unrestricted',
    'فعال‌سازی Service SID اختصاصی');
  RunRequired(ExpandConstant('{sys}\icacls.exe'),
    '"' + DataDir + '" /grant:r *S-1-5-32-544:(OI)(CI)F ' +
    '"NT SERVICE\HRMCentralService:(OI)(CI)M" /T',
    'اعمال دسترسی صریح Service SID');

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
    '"' + DataDir + '" /inheritance:r /T',
    'حذف ارث‌بری ACL پس از اثبات دسترسی سرویس');
  RunRequired(ExpandConstant('{sys}\icacls.exe'),
    '"' + DataDir + '" /verify /T',
    'اعتبارسنجی نهایی ACL');
  RunRequired(ServerExe,
    '--data-dir "' + DataDir + '" --health-check https://127.0.0.1:8765 --health-timeout 30' +
    ' --diagnostic-log "' + DiagnosticPath + '"',
    'آزمون نهایی TLS و سرویس پس از سخت‌سازی ACL');
end;

procedure InitializeWizard;
begin
  ProvisionFailed := False;
  ServerPage := CreateInputQueryPage(wpSelectComponents,
    'اتصال به سرور مرکزی',
    'آدرس سرویس مرکزی را مشخص کنید.',
    'در نصب کامل مقدار محلی مناسب است. در رایانه مدیر، IP سرور اداره را وارد کنید.');
  ServerPage.Add('آدرس (نمونه: https://192.168.1.10:8765):', False);
  ServerPage.Values[0] := 'https://127.0.0.1:8765';
  OwnerPage := CreateInputQueryPage(ServerPage.ID,
    'مدیر اولیه سامانه',
    'حساب مالک اولیه را مشخص کنید.',
    'رمز یک‌بارمصرف به‌صورت تصادفی ساخته می‌شود و پس از نخستین ورود باید تغییر کند.');
  OwnerPage.Add('نام کاربری:', False);
  OwnerPage.Add('نام نمایشی:', False);
  OwnerPage.Values[0] := 'owner';
  OwnerPage.Values[1] := 'مدیر سامانه';
end;

function GetServerUrl(Param: String): String;
begin
  Result := Trim(ServerPage.Values[0]);
  if Result = '' then
    Result := 'https://127.0.0.1:8765';
end;

function GetInitialUsername(Param: String): String;
begin
  Result := Trim(OwnerPage.Values[0]);
  if Result = '' then
    Result := 'owner';
end;

function GetInitialDisplayName(Param: String): String;
begin
  Result := Trim(OwnerPage.Values[1]);
  if Result = '' then
    Result := 'مدیر سامانه';
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  PreflightExe: String;
  DiagnosticPath: String;
  ResultCode: Integer;
  Started: Boolean;
begin
  if WizardIsComponentSelected('client') and (Trim(ServerPage.Values[0]) = '') then
    Result := 'آدرس سرور مرکزی الزامی است.'
  else
    Result := '';
  if (Result = '') and WizardIsComponentSelected('server') and
     ((Trim(OwnerPage.Values[0]) = '') or (Trim(OwnerPage.Values[1]) = '')) then
    Result := 'نام کاربری و نام نمایشی مدیر اولیه الزامی است.';
  if (Result = '') and WizardIsComponentSelected('server') and
     ((Pos('"', OwnerPage.Values[0]) > 0) or (Pos('"', OwnerPage.Values[1]) > 0)) then
    Result := 'استفاده از علامت نقل‌قول در مشخصات مدیر مجاز نیست.';
  if (Result = '') and WizardIsComponentSelected('server') then
  begin
    try
      LogSetupStage('START', 'server-preflight', -1);
      ExtractTemporaryFile('HRMServerPreflight.exe');
      ExtractTemporaryFile('hrm-seed.sqlite');
      PreflightExe := ExpandConstant('{tmp}\HRMServerPreflight.exe');
      DiagnosticPath := EnterpriseDataDir + '\logs\setup-server.log';
      ResultCode := -1;
      Started := Exec(PreflightExe,
        '--data-dir "' + EnterpriseDataDir + '" --seed "' + ExpandConstant('{tmp}\hrm-seed.sqlite') +
        '" --initial-user "' + GetInitialUsername('') +
        '" --initial-display-name "' + GetInitialDisplayName('') +
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
    except
      LogSetupStage('EXCEPTION', 'server-preflight', -1);
      LogProtectedDiagnostics;
      ProvisionFailed := True;
      Result := 'اجرای پیش‌آزمون بسته مستقل ممکن نشد: ' + GetExceptionMessage;
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
          'نام کاربری: ' + GetInitialUsername(''), mbInformation, MB_OK, IDOK)
      else
        SuppressibleMsgBox('سرور مرکزی با موفقیت نصب، به‌روزرسانی و آزمون شد.', mbInformation, MB_OK, IDOK);
    end;
  end;
end;
