#define BridgeRoot AddBackslash(SourcePath) + ".."
#define BridgeExecutable BridgeRoot + "\build\publish\Almdina.ScannerBridge.exe"
#define BridgeVersion GetVersionNumbersString(BridgeExecutable)

[Setup]
AppId={{BE953535-3ED0-4B50-A5EB-324F1BC69236}
AppName=Almdina Scanner Bridge
AppVerName=Almdina Scanner Bridge {#BridgeVersion}
AppVersion={#BridgeVersion}
AppPublisher=Almdina ERP
AppPublisherURL=https://almadina-2.horizontechco.com
AppSupportURL=https://almadina-2.horizontechco.com
DefaultDirName={localappdata}\Programs\Almdina Scanner Bridge
DefaultGroupName=Almdina Scanner Bridge
DisableProgramGroupPage=yes
DisableWelcomePage=yes
DisableDirPage=yes
DisableReadyPage=yes
AllowCancelDuringInstall=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#BridgeRoot}\build\installer
OutputBaseFilename=AlmdinaScannerBridgeSetup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupIconFile={#BridgeRoot}\assets\AlmdinaScannerBridge.ico
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
UninstallDisplayName=Almdina Scanner Bridge
VersionInfoCompany=Almdina ERP
VersionInfoDescription=Almdina Scanner Bridge Installer
VersionInfoProductName=Almdina Scanner Bridge
VersionInfoProductVersion={#BridgeVersion}
VersionInfoVersion={#BridgeVersion}

[Files]
Source: "{#BridgeExecutable}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\تشغيل برنامج سكانر المدينة"; Filename: "{app}\Almdina.ScannerBridge.exe"; IconFilename: "{app}\Almdina.ScannerBridge.exe"
Name: "{group}\إزالة برنامج سكانر المدينة"; Filename: "{uninstallexe}"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "AlmdinaScannerBridge"; ValueData: """{app}\Almdina.ScannerBridge.exe"" --background"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\Almdina.ScannerBridge.exe"; Parameters: "--installed"; Description: "تشغيل برنامج سكانر المدينة الآن"; Flags: nowait postinstall skipifsilent
Filename: "{app}\Almdina.ScannerBridge.exe"; Parameters: "--background"; Flags: nowait runhidden skipifnotsilent

[UninstallRun]
Filename: "{app}\Almdina.ScannerBridge.exe"; Parameters: "--shutdown"; Flags: runhidden waituntilterminated skipifdoesntexist

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ExistingBridge: String;
  ResultCode: Integer;
begin
  ExistingBridge := ExpandConstant('{localappdata}\Programs\Almdina Scanner Bridge\Almdina.ScannerBridge.exe');
  if FileExists(ExistingBridge) then
  begin
    Exec(ExistingBridge, '--shutdown', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(500);
  end;
  Result := '';
end;
