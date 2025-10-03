!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"
!include "EnvVarUpdate.nsh"

Name "FaceFusion"
OutFile "FaceFusionSetup.exe"

InstallDir "$PROGRAMFILES64\FaceFusion"
InstallDirRegKey HKLM "Software\FaceFusion" "InstallDir"

RequestExecutionLevel admin

Var CondaRoot
Var CondaEnvName
Var CondaPrefix
Var MinicondaInstaller

!define WM_SETTINGCHANGE 0x1A
!define MinicondaUrl "https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe"

Page directory
Page instfiles

UninstPage uninstConfirm
UninstPage instfiles

Function .onInit
    StrCpy $CondaEnvName "facefusion"
    ${If} ${RunningX64}
        StrCpy $InstDir "$PROGRAMFILES64\FaceFusion"
    ${Else}
        StrCpy $InstDir "$PROGRAMFILES\FaceFusion"
    ${EndIf}
    StrCpy $CondaRoot "$LOCALAPPDATA\FaceFusion\Miniconda3"
    StrCpy $CondaPrefix "$CondaRoot\envs\$CondaEnvName"
FunctionEnd

Section "FaceFusion" SEC_FACEFUSION
    SetShellVarContext all
    SetOutPath "$INSTDIR"

    File /r "facefusion\*"
    File "facefusion.py"
    File "requirements.txt"
    File "facefusion.ico"
    IfFileExists "$INSTDIR\desktop_installer.py" 0 +2
    File "desktop_installer.py"
    IfFileExists "$INSTDIR\build_facefusion_installer.py" 0 +2
    File "build_facefusion_installer.py"

    WriteRegStr HKLM "Software\FaceFusion" "InstallDir" "$INSTDIR"

    Call EnsureMiniconda
    Call EnsureCondaEnvironment
    Call InstallPythonDependencies
    Call WriteEnvironmentVariables
    Call CreateShortcuts
    Call BroadcastEnvironmentChange

    WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
    SetShellVarContext all

    ReadRegStr $0 HKLM "Software\FaceFusion" "CondaPrefix"
    ${If} $0 == ""
        StrCpy $0 "$CondaPrefix"
    ${EndIf}

    ${EnvVarUpdate} $1 "PATH" "R" "HKLM" "$0"
    ${EnvVarUpdate} $1 "PATH" "R" "HKLM" "$0\\Scripts"
    ${EnvVarUpdate} $1 "PATH" "R" "HKLM" "$0\\Library\\bin"

    DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "FACEFUSION_HOME"
    DeleteRegValue HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "FACEFUSION_CONDA_PREFIX"
    DeleteRegValue HKLM "Software\FaceFusion" "InstallDir"
    DeleteRegValue HKLM "Software\FaceFusion" "CondaPrefix"

    Delete "$SMPROGRAMS\FaceFusion\FaceFusion.lnk"
    Delete "$SMPROGRAMS\FaceFusion\FaceFusion (Terminal).lnk"
    Delete "$SMPROGRAMS\FaceFusion\Uninstall.lnk"
    RMDir "$SMPROGRAMS\FaceFusion"

    Delete "$INSTDIR\Uninstall.exe"
    RMDir /r "$INSTDIR"

    IfFileExists "$CondaRoot" 0 +2
    RMDir /r "$CondaRoot"

    Call BroadcastEnvironmentChange
SectionEnd

Function EnsureMiniconda
    IfFileExists "$CondaRoot\\Scripts\\conda.exe" Done

    DetailPrint "下载 Miniconda..."
    StrCpy $MinicondaInstaller "$TEMP\\Miniconda3-latest-Windows-x86_64.exe"
    nsExec::ExecToLog 'powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri \"${MinicondaUrl}\" -OutFile \"$MinicondaInstaller\""'
    Pop $0
    ${If} $0 != 0
        MessageBox MB_ICONSTOP "Miniconda 下载失败 (退出代码 $0)。"
        Abort
    ${EndIf}

    DetailPrint "安装 Miniconda..."
    nsExec::ExecToLog '"$MinicondaInstaller" /InstallationType=JustMe /RegisterPython=0 /AddToPath=0 /S /D=$CondaRoot'
    Pop $0
    ${If} $0 != 0
        MessageBox MB_ICONSTOP "Miniconda 安装失败 (退出代码 $0)。"
        Abort
    ${EndIf}

    Delete "$MinicondaInstaller"

Done:
    WriteRegStr HKLM "Software\FaceFusion" "CondaPrefix" "$CondaPrefix"
FunctionEnd

Function EnsureCondaEnvironment
    IfFileExists "$CondaPrefix" 0 CreateEnv
    IfFileExists "$CondaPrefix\\python.exe" EnvReady CreateEnv

CreateEnv:
    DetailPrint "创建 FaceFusion Conda 环境..."
    nsExec::ExecToLog '"$CondaRoot\\condabin\\conda.bat" env remove -y -n $CondaEnvName'
    Pop $0

    nsExec::ExecToLog '"$CondaRoot\\condabin\\conda.bat" create -y -n $CondaEnvName python=3.10'
    Pop $0
    ${If} $0 != 0
        MessageBox MB_ICONSTOP "创建 Conda 环境失败 (退出代码 $0)。"
        Abort
    ${EndIf}

EnvReady:
    Return
FunctionEnd

Function InstallPythonDependencies
    DetailPrint "安装 Python 依赖..."
    nsExec::ExecToLog '"$CondaRoot\\condabin\\conda.bat" run -n $CondaEnvName python -m pip install --upgrade pip'
    Pop $0
    ${If} $0 != 0
        MessageBox MB_ICONSTOP "更新 pip 失败 (退出代码 $0)。"
        Abort
    ${EndIf}

    nsExec::ExecToLog '"$CondaRoot\\condabin\\conda.bat" run -n $CondaEnvName python -m pip install -r "$INSTDIR\\requirements.txt"'
    Pop $0
    ${If} $0 != 0
        MessageBox MB_ICONSTOP "安装依赖失败 (退出代码 $0)。"
        Abort
    ${EndIf}
FunctionEnd

Function WriteEnvironmentVariables
    DetailPrint "写入环境变量..."
    WriteRegStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "FACEFUSION_HOME" "$INSTDIR"
    WriteRegStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "FACEFUSION_CONDA_PREFIX" "$CondaPrefix"

    ${EnvVarUpdate} $0 "PATH" "A" "HKLM" "$CondaPrefix"
    ${EnvVarUpdate} $0 "PATH" "A" "HKLM" "$CondaPrefix\\Scripts"
    ${EnvVarUpdate} $0 "PATH" "A" "HKLM" "$CondaPrefix\\Library\\bin"
FunctionEnd

Function CreateShortcuts
    CreateDirectory "$SMPROGRAMS\FaceFusion"
    CreateShortCut "$SMPROGRAMS\FaceFusion\FaceFusion.lnk" "cmd.exe" '/c ""$CondaRoot\\condabin\\conda.bat" run -n $CondaEnvName python "$INSTDIR\\facefusion.py" run"' "$INSTDIR\\facefusion.ico"
    CreateShortCut "$SMPROGRAMS\FaceFusion\FaceFusion (Terminal).lnk" "cmd.exe" '/k ""$CondaRoot\\condabin\\conda.bat" activate $CondaEnvName"' "$INSTDIR\\facefusion.ico"
    CreateShortCut "$SMPROGRAMS\FaceFusion\Uninstall.lnk" "$INSTDIR\\Uninstall.exe"
FunctionEnd

Function BroadcastEnvironmentChange
    System::Call 'User32::SendMessageTimeoutW(i 0xffff, i ${WM_SETTINGCHANGE}, i 0, w "Environment", i 0, i 5000, *i .r0)'
FunctionEnd
