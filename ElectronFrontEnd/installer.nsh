!macro customInit
  ; Check if any version is already installed
  ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "DisplayVersion"
  ${If} $0 != ""
    ; Skip if same version
    StrCmp $0 "${VERSION}" done

    ReadRegStr $R1 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "InstallLocation"
    MessageBox MB_YESNO|MB_ICONINFORMATION \
      "Mindlink Analyzer v$0 is already installed on this computer.$\n$\nThis installer is for v${VERSION}, which may be an older version. Running it could downgrade your app.$\n$\nClick Yes to launch the installed v$0 instead, or No to cancel." \
      IDNO abort_install
    ExecShell "open" "$R1\$(^Name).exe"
    Quit
    abort_install:
    Quit
    done:
  ${EndIf}
!macroend
