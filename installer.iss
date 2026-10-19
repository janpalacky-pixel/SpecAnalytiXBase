#define MyAppName "SpecAnalytiXBase"
#define MyAppExeName "SpecAnalytiXBase.exe"
#define MyAppFolder "SpecAnalytiXBase"
#define MyAppVersion "1.5.0"
#define MyAppPublisher "Institute of Biophysics of the Czech Academy of Sciences"
#define MyAppURL "https://www.ibp.cz/en/research/departments/biophysics-of-nucleic-acids/research-profile"
#define MyOutputDir "installer"
#define MyWizardImage "installer_assets\wizardimage.bmp"
#define MySetupIcon "installer_assets\setupicon.ico"

[Setup]
AppId={{8a84bbec-d963-4f73-9840-8c4f5549a1ea}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppFolder}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputBaseFilename=Setup_for_{#MyAppName}_ver_{#MyAppVersion}
OutputDir={#MyOutputDir}
WizardImageFile={#MyWizardImage}
SetupIconFile={#MySetupIcon}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
LicenseFile=installer_assets\license.txt
PrivilegesRequired=admin
ShowLanguageDialog=auto
UsePreviousTasks=no
; Tell Windows (Explorer) that file associations changed, see [Registry]
ChangesAssociations=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "czech"; MessagesFile: "compiler:Languages\Czech.isl"

[InstallDelete]
; An upgrade installs into the same folder as the previous version, and Inno Setup
; never removes files it is not installing this time. Libraries that an older build
; shipped but this one doesn't (e.g. a leftover _internal\pyarrow folder from 1.3.0)
; would otherwise stay on sys.path and break imports at startup. Clear the whole
; bundled-library folder before the new files are copied.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\{#MyAppFolder}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\{#MyAppFolder}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "installer_assets\license.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "installer_assets\readme.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Create start menu shortcut
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
; Create uninstaller shortcut (commented out by default)
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
; Create desktop shortcut - using autodesktop for better compatibility
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "assocsnapx"; Description: "{cm:AssocSnapx}"; GroupDescription: "{cm:AssocGroup}"
Name: "readme"; Description: "{cm:ReadmeTaskDescription}"; Flags: unchecked

[Registry]
; Double-click on a snapshot (.snapx) opens it in SpecAnalytiXBase (task
; "assocsnapx", on by default). main.py opens the files it is given.
Root: HKA; Subkey: "Software\Classes\.snapx"; ValueType: string; ValueName: ""; ValueData: "SpecAnalytiXBase.snapx"; Flags: uninsdeletevalue; Tasks: assocsnapx
Root: HKA; Subkey: "Software\Classes\.snapx\OpenWithProgids"; ValueType: string; ValueName: "SpecAnalytiXBase.snapx"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocsnapx
Root: HKA; Subkey: "Software\Classes\SpecAnalytiXBase.snapx"; ValueType: string; ValueName: ""; ValueData: "SpecAnalytiXBase snapshot"; Flags: uninsdeletekey; Tasks: assocsnapx
Root: HKA; Subkey: "Software\Classes\SpecAnalytiXBase.snapx\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: assocsnapx
Root: HKA; Subkey: "Software\Classes\SpecAnalytiXBase.snapx\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: assocsnapx
; "Open with -> SpecAnalytiXBase" for the data formats it reads (without
; taking over their default program).
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExeName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExeName}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExeName}\SupportedTypes"; ValueType: string; ValueName: ".snapx"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExeName}\SupportedTypes"; ValueType: string; ValueName: ".spc"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExeName}\SupportedTypes"; ValueType: string; ValueName: ".spe"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExeName}\SupportedTypes"; ValueType: string; ValueName: ".jws"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExeName}\SupportedTypes"; ValueType: string; ValueName: ".jwb"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExeName}\SupportedTypes"; ValueType: string; ValueName: ".mat"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExeName}\SupportedTypes"; ValueType: string; ValueName: ".txt"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExeName}\SupportedTypes"; ValueType: string; ValueName: ".csv"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExeName}\SupportedTypes"; ValueType: string; ValueName: ".dat"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExeName}\SupportedTypes"; ValueType: string; ValueName: ".xlsx"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#MyAppExeName}\SupportedTypes"; ValueType: string; ValueName: ".xls"; ValueData: ""

[Run]
; Launch application after install (with proper ampersand handling)
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
; Show readme file after installation only if the "readme" task is selected
Filename: "notepad.exe"; Parameters: "{app}\readme.txt"; Flags: shellexec skipifsilent; Check: WizardIsTaskSelected('readme')

[CustomMessages]
english.ReadmeTaskDescription=View README after install
czech.ReadmeTaskDescription=Zobrazit README po instalaci
english.AssocGroup=File types:
czech.AssocGroup=Typy souboru:
english.AssocSnapx=Open snapshots (.snapx) with SpecAnalytiXBase by double-click
czech.AssocSnapx=Otevirat snapshoty (.snapx) dvojklikem v SpecAnalytiXBase

; Existing translation
czech.LaunchProgram=Spustit aplikaci %1
