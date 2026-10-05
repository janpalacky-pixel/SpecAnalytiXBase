#define MyAppName "SpecAnalytiXBase"
#define MyAppExeName "SpecAnalytiXBase.exe"
#define MyAppFolder "SpecAnalytiXBase"
#define MyAppVersion "1.4.2"
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
Name: "readme"; Description: "{cm:ReadmeTaskDescription}"; Flags: unchecked

[Run]
; Launch application after install (with proper ampersand handling)
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
; Show readme file after installation only if the "readme" task is selected
Filename: "notepad.exe"; Parameters: "{app}\readme.txt"; Flags: shellexec skipifsilent; Check: WizardIsTaskSelected('readme')

[CustomMessages]
english.ReadmeTaskDescription=View README after install
czech.ReadmeTaskDescription=Zobrazit README po instalaci

; Existing translation
czech.LaunchProgram=Spustit aplikaci %1
