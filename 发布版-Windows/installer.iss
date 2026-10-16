[Setup]
AppId={{9C661805-363A-4250-BC6B-1BD4E1229F70}
AppName=Clipline
AppVersion=1.0.5
AppPublisher=Clipline
DefaultDirName={localappdata}\Programs\Clipline
DefaultGroupName=Clipline
PrivilegesRequired=lowest
MinVersion=10.0.17763
ArchitecturesAllowed=x64compatible
OutputDir=交付
OutputBaseFilename=Clipline-安装包
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\app_icon.ico
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\Clipline.exe

[Files]
Source: "dist_clipline\Clipline\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "交付\Clipline-产品介绍与使用手册.pdf"; DestDir: "{app}"; DestName: "使用手册.pdf"; Flags: ignoreversion
Source: "licenses\LGPL-3.0-only.txt"; DestDir: "{app}\licenses"; Flags: ignoreversion
Source: "第三方许可说明.txt"; DestDir: "{app}\licenses"; Flags: ignoreversion

[Icons]
Name: "{group}\Clipline"; Filename: "{app}\Clipline.exe"
Name: "{group}\使用手册"; Filename: "{app}\使用手册.pdf"
Name: "{group}\卸载 Clipline"; Filename: "{uninstallexe}"
