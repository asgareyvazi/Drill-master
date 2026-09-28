; DrillMaster Windows installer. Build through packaging/build_windows.ps1.
; User data is intentionally outside {app}, so upgrades and uninstall do not
; delete the SQLite database, logs, mapping memory, or backups.

#ifndef AppVersion
#error AppVersion must be supplied by packaging/build_windows.ps1
#endif
#ifndef SourceDir
#define SourceDir "..\dist\DrillMaster"
#endif
#ifndef OutputDir
#define OutputDir "..\release"
#endif

[Setup]
AppId=DrillMaster
AppName=DrillMaster
AppVersion={#AppVersion}
AppPublisher=DrillMaster
AppPublisherURL=
DefaultDirName={autopf}\DrillMaster
DefaultGroupName=DrillMaster
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=DrillMaster-{#AppVersion}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=DrillMaster
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\DrillMaster"; Filename: "{app}\DrillMaster.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\DrillMaster"; Filename: "{app}\DrillMaster.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\DrillMaster.exe"; Description: "Launch DrillMaster"; Flags: nowait postinstall skipifsilent
