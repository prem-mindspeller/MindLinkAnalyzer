!include "VersionCompare.nsh"

!macro customInit
  ; If a newer version is already installed, offer to launch it instead
  ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "DisplayVersion"
  ${If} $0 != ""
    ${VersionCompare} $0 ${VERSION} $R0
    ${If} $R0 == 1
      ; $0 = installed version (newer), ${VERSION} = this installer version (older)
      ReadRegStr $R1 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "InstallLocation"
      MessageBox MB_YESNO|MB_ICONINFORMATION \
        "$(^Name) v$0 is already installed on this computer.$\n$\nThis installer is for the older v${VERSION}. Installing it will downgrade your app.$\n$\nClick Yes to launch the installed v$0 instead, or No to cancel." \
        IDNO abort_old_install
      ExecShell "open" "$R1\$(^Name).exe"
      Quit
      abort_old_install:
      Quit
    ${EndIf}
  ${EndIf}
!macroend
