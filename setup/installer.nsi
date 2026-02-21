Unicode true

; =================================================================
; PMUsage Installer -- NSIS Script
;
; Creates a standard Windows installer:
;   - Choose install location (default: Program Files\PMUsage)
;   - Start Menu + Desktop shortcuts
;   - Optional autostart with Windows
;   - Uninstaller in Add/Remove Programs
; =================================================================

!include "MUI2.nsh"
!include "FileFunc.nsh"

; -- App Info -----------------------------------------------------
!define APP_NAME "PMUsage"
!define APP_PUBLISHER "UVuruna"
!define APP_EXE "PMUsage.exe"
!define APP_VERSION "1.1.390"
!define APP_DESCRIPTION "Real-time CPU and Memory usage monitor"

; Registry key for uninstall info
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"

; -- Paths (passed from build.py via /D flags) --------------------
; DIST_DIR -- PyInstaller output (dist\PMUsage\)
; SETUP_DIR -- setup folder (for icon reference)

; -- General Settings ---------------------------------------------
Name "${APP_NAME}"
OutFile "${DIST_DIR}\${APP_NAME}_Setup.exe"
InstallDir "$PROGRAMFILES\${APP_NAME}"
InstallDirRegKey HKLM "${UNINST_KEY}" "InstallLocation"
RequestExecutionLevel admin
SetCompressor /SOLID lzma

; -- Icon ---------------------------------------------------------
!define MUI_ICON "${PROJECT_DIR}\assets\icon.ico"
!define MUI_UNICON "${PROJECT_DIR}\assets\icon.ico"

; -- Interface Settings -------------------------------------------
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Welcome to ${APP_NAME} Setup"
!define MUI_WELCOMEPAGE_TEXT "This wizard will install ${APP_NAME} on your computer.$\r$\n$\r$\n${APP_DESCRIPTION}$\r$\n$\r$\nClick Next to continue."
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Launch ${APP_NAME}"

; -- Pages --------------------------------------------------------
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; Uninstaller pages
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; -- Language -----------------------------------------------------
!insertmacro MUI_LANGUAGE "English"

; =================================================================
; INSTALLER SECTIONS
; =================================================================

Section "!${APP_NAME} (required)" SecMain
    SectionIn RO  ; Cannot be deselected

    ; Copy application files
    SetOutPath "$INSTDIR"
    File /r "${DIST_DIR}\${APP_NAME}\*.*"

    ; Start Menu shortcuts
    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\icon.ico"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

    ; Write uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; Write registry keys for Add/Remove Programs
    WriteRegStr HKLM "${UNINST_KEY}" "DisplayName" "${APP_NAME} - ${APP_DESCRIPTION}"
    WriteRegStr HKLM "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\icon.ico"
    WriteRegStr HKLM "${UNINST_KEY}" "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
    WriteRegStr HKLM "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "${UNINST_KEY}" "Publisher" "${APP_PUBLISHER}"
    WriteRegStr HKLM "${UNINST_KEY}" "DisplayVersion" "${APP_VERSION}"
    WriteRegDWORD HKLM "${UNINST_KEY}" "NoModify" 1
    WriteRegDWORD HKLM "${UNINST_KEY}" "NoRepair" 1

    ; Calculate installed size
    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKLM "${UNINST_KEY}" "EstimatedSize" $0
SectionEnd

Section "Desktop Shortcut" SecDesktop
    CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\icon.ico"
SectionEnd

Section "Start with Windows" SecAutostart
    ; Use registry Run key for autostart (no admin needed at runtime)
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${APP_NAME}" "$\"$INSTDIR\${APP_EXE}$\""
SectionEnd

; -- Section Descriptions -----------------------------------------
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SecMain} "Install ${APP_NAME} core files (required)."
    !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "Create a shortcut on your Desktop."
    !insertmacro MUI_DESCRIPTION_TEXT ${SecAutostart} "Automatically start ${APP_NAME} when Windows starts."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; =================================================================
; UNINSTALLER
; =================================================================

Section "Uninstall"
    ; Remove autostart registry key
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${APP_NAME}"

    ; Remove shortcuts
    Delete "$DESKTOP\${APP_NAME}.lnk"
    RMDir /r "$SMPROGRAMS\${APP_NAME}"

    ; Remove program files
    RMDir /r "$INSTDIR"

    ; Remove registry keys
    DeleteRegKey HKLM "${UNINST_KEY}"
SectionEnd
