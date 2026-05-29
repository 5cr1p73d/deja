; deja.iss — installer Inno Setup per Déjà
; Build app:   pyinstaller --noconfirm deja.spec   (genera dist\Deja\)
; Build setup: iscc deja.iss                        (genera dist\Deja-Setup-1.0.0.exe)
; Inno Setup gratuito: https://jrsoftware.org/isdl.php

#define MyAppName "Déjà"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Scr1p73d"
#define MyAppExeName "Deja.exe"

[Setup]
AppId={{7B3F2A10-DE7A-4C2B-9A1D-DE1A0000DEJA}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Deja
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=Deja-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Avvia Déjà all'accesso a Windows"; GroupDescription: "Opzioni:"; Flags: unchecked

[Files]
; Output onedir di PyInstaller (Deja.exe + _internal\)
Source: "dist\Deja\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Disinstalla {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Autostart per l'utente corrente (opzionale)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
  ValueName: "Deja"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Avvia {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
// Alla disinstallazione, offri di eliminare anche i dati catturati.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\Deja');
    if DirExists(DataDir) then
    begin
      if MsgBox('Vuoi eliminare anche tutti i dati registrati da Déjà ' +
                '(screenshot, audio, trascrizioni, log)?' + #13#10 +
                DataDir, mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
