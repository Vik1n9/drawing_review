; Fire Review 消防審圖輔助系統 —— Windows 安裝程式（Inno Setup 6）
;
; 建置：
;   python3 tools/make_release.py --version v1.2.0 --out dist --stage-only
;   ISCC /DMyVersion=v1.2.0 /DStageDir=..\dist\FireReview-v1.2.0 packaging\fire-review.iss
;
; ## 設計原則：安裝程式薄，升級邏輯在 Python
;
; 本檔的 Pascal Script 只做三件事：偵測 Python、決定檔案先落在哪裡、
; 呼叫 tools\update_guard.py。逐檔「保留使用者版本／另存 .上游新版」的判斷
; 一律在 Python 端——那份邏輯有 tests/test_update_guard_install.py 把關，
; 而 Pascal Script 沒有任何測試。同一份邏輯寫兩次，遲早會漂移成兩種行為。
;
; ## 為什麼不裝進 Program Files
;
; 這個系統會往自己的資料夾寫東西（output/ 交付物、governance/ 裁示紀錄、
; input/ 案件圖面）。Program Files 需要管理員權限，而且 Windows 的 VirtualStore
; 重導向會讓使用者在檔案總管裡找不到自己的產出。預設放「文件」底下，
; PrivilegesRequired=lowest，全程不需要管理員。

#ifndef MyVersion
  #define MyVersion "v0.0.0"
#endif
#ifndef StageDir
  #define StageDir "..\dist\FireReview-" + MyVersion
#endif

#define MyAppName "Fire Review 消防審圖輔助系統"
#define MyAppShortName "FireReview"
#define MyManifest "安裝清單.json"
#define MyWelcome "安裝完成-請把這段貼給你的AI.txt"
#define MyStagingDir ".更新暫存"

[Setup]
AppId={{8F3C1B72-5A94-4E1D-9C0F-FIRE00REVIEW}
AppName={#MyAppName}
AppVersion={#MyVersion}
AppVerName={#MyAppName} {#MyVersion}
DefaultDirName={userdocs}\{#MyAppShortName}
DefaultGroupName={#MyAppShortName}
DisableProgramGroupPage=yes
DisableDirPage=no
AllowNoIcons=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename={#MyAppShortName}-{#MyVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName}
; 反安裝只移除上游檔案；使用者的成果不在此列（見 [UninstallDelete] 的說明）
Uninstallable=yes

[Languages]
Name: "chinesetraditional"; MessagesFile: "compiler:Default.isl"

[Files]
; DestDir 走 {code:GetTargetDir}：全新安裝直接落地，升級先落在暫存區，
; 之後交給 update_guard.py install 逐檔判定。
Source: "{#StageDir}\*"; DestDir: "{code:GetTargetDir}"; \
    Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\開場診斷"; Filename: "{app}\開場診斷.bat"; WorkingDir: "{app}"
Name: "{group}\安裝資料夾"; Filename: "{app}"
Name: "{userdesktop}\{#MyAppShortName} 開場診斷"; Filename: "{app}\開場診斷.bat"; \
    WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "在桌面建立「開場診斷」捷徑"; \
    GroupDescription: "附加工作："; Flags: unchecked

[Run]
Filename: "{app}\{#MyWelcome}"; Description: "開啟「怎麼交給 AI」說明"; \
    Flags: postinstall shellexec skipifsilent nowait
Filename: "{app}"; Description: "開啟安裝資料夾"; \
    Flags: postinstall shellexec skipifsilent nowait unchecked

[UninstallDelete]
; 反安裝時清掉暫存區，但**不碰**使用者的成果目錄。
; 使用者的圖面與裁示紀錄不是安裝程式放的，也就不該由安裝程式刪。
Type: filesandordirs; Name: "{app}\{#MyStagingDir}"

[Code]
var
  PythonCmd: String;       { 偵測到的 Python 啟動命令，空字串代表沒裝 }
  IsUpgrade: Boolean;      { 目標資料夾已經有安裝清單 }
  PythonPage: TOutputMsgWizardPage;
  UpgradePage: TOutputMsgWizardPage;

function GetTargetDir(Param: String): String;
begin
  { 升級時先把新版落在暫存區，別直接蓋掉使用者改過的檔案 }
  if IsUpgrade then
    Result := ExpandConstant('{app}\{#MyStagingDir}')
  else
    Result := ExpandConstant('{app}');
end;

function TryPython(const Cmd, Args: String): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec(ExpandConstant('{cmd}'), '/C ' + Cmd + ' ' + Args + ' >nul 2>nul',
                 '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

function DetectPython(): String;
begin
  { py 啟動器優先——Windows 上它比 PATH 裡的 python 可靠 }
  if TryPython('py -3', '--version') then
    Result := 'py -3'
  else if TryPython('python', '--version') then
    Result := 'python'
  else
    Result := '';
end;

procedure InitializeWizard();
begin
  PythonPage := CreateOutputMsgPage(wpWelcome,
    '需要 Python', '這個系統靠 Python 執行法規計算',
    '偵測不到 Python。' + #13#10#13#10 +
    '安裝可以照常進行，檔案會先就位；但在你安裝 Python 之前，' +
    '審圖工具跑不起來。' + #13#10#13#10 +
    '請到 https://www.python.org/downloads/ 下載安裝，' +
    '安裝時務必勾選「Add python.exe to PATH」。' + #13#10#13#10 +
    '裝好之後，雙擊安裝資料夾裡的「開場診斷.bat」即可開始。');

  UpgradePage := CreateOutputMsgPage(wpSelectDir,
    '偵測到既有安裝', '你的成果不會被蓋掉',
    '這個資料夾已經裝過 Fire Review。' + #13#10#13#10 +
    '接下來會：' + #13#10 +
    '  1. 把你的成果備份到這個資料夾的外面' + #13#10 +
    '  2. 你**沒有改過**的檔案，直接更新成新版' + #13#10 +
    '  3. 你**改過**的檔案，保留你的版本；' +
    '上游新版另存成「.上游新版」讓你自己比對' + #13#10 +
    '  4. 你自己新增的案件圖面、實務見解，完全不動' + #13#10#13#10 +
    '裝完會產生一份「更新報告-日期.txt」，逐檔告訴你發生了什麼事。');
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if PageID = PythonPage.ID then
    Result := (PythonCmd <> '');
  if PageID = UpgradePage.ID then
    Result := not IsUpgrade;
end;

function InitializeSetup(): Boolean;
begin
  PythonCmd := DetectPython();
  Result := True;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  { 目錄選完才知道是不是升級——使用者可以在精靈裡改安裝位置 }
  if CurPageID = wpSelectDir then
    IsUpgrade := FileExists(ExpandConstant('{app}\{#MyManifest}'));
end;

procedure FillWelcomeFile();
var
  Path, Text: String;
begin
  Path := ExpandConstant('{app}\{#MyWelcome}');
  if not LoadStringFromFile(Path, Text) then
    Exit;
  StringChangeEx(Text, '{{INSTALL_DIR}}', ExpandConstant('{app}'), True);
  SaveStringToFile(Path, Text, False);
end;

procedure RunUpgrade();
var
  ResultCode: Integer;
  Staging, Command: String;
begin
  Staging := ExpandConstant('{app}\{#MyStagingDir}');
  if PythonCmd = '' then
  begin
    { Python 沒裝就無法逐檔判定。**寧可什麼都不覆蓋**，也不要盲目蓋掉成果——
      新版原封不動留在暫存區，等使用者裝好 Python 再跑一次即可。 }
    MsgBox('偵測不到 Python，無法安全地完成升級。' + #13#10#13#10 +
           '你原本的檔案完全沒有被更動。新版放在：' + #13#10 +
           Staging + #13#10#13#10 +
           '請先安裝 Python（記得勾選 Add python.exe to PATH），' +
           '再雙擊「開場診斷.bat」，或重新執行這個安裝程式。',
           mbInformation, MB_OK);
    Exit;
  end;

  { 用**新版**的 update_guard.py 執行升級：邏輯修正才吃得到 }
  Command := '/C cd /d "' + ExpandConstant('{app}') + '" && ' +
             PythonCmd + ' "' + Staging + '\tools\update_guard.py" ' +
             '--root "' + ExpandConstant('{app}') + '" ' +
             'install --from "' + Staging + '" --by 安裝程式';
  if not Exec(ExpandConstant('{cmd}'), Command, '', SW_HIDE,
              ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
  begin
    MsgBox('升級過程發生問題，你原本的檔案沒有被覆蓋。' + #13#10#13#10 +
           '新版放在：' + #13#10 + Staging + #13#10#13#10 +
           '請雙擊「開場診斷.bat」看看狀態，或把這段訊息告訴你的 AI。',
           mbError, MB_OK);
    Exit;
  end;
  DelTree(Staging, True, True, True);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if IsUpgrade then
      RunUpgrade();
    FillWelcomeFile();
  end;
end;
