Write-Host "Building BrainCompanion App with PyInstaller..." -ForegroundColor Green

# Clean up previous builds
if (Test-Path ".\dist") {
    Write-Host "Cleaning previous dist folder..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force ".\dist"
}
if (Test-Path ".\build") {
    Write-Host "Cleaning previous build folder..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force ".\build"
}

# Create version info for the executable
$version_info = @"
# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(1, 0, 0, 0),
    prodvers=(1, 0, 0, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
    ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'MindSpeller'),
        StringStruct(u'FileDescription', u'BrainLink Companion App'),
        StringStruct(u'FileVersion', u'1.2.0'),
        StringStruct(u'InternalName', u'BrainCompanion'),
        StringStruct(u'LegalCopyright', u'Copyright (c) 2025 MindSpeller'),
        StringStruct(u'OriginalFilename', u'BrainCompanion.exe'),
        StringStruct(u'ProductName', u'BrainLink Companion'),
        StringStruct(u'ProductVersion', u'1.2.0')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"@

# Write version info to a file
$version_info | Out-File -FilePath ".\file_version_info.txt" -Encoding utf8

# Create a pre-launch script to handle security warnings
$launcher_script = @"
import sys
import os
from PySide6.QtWidgets import QApplication, QMessageBox
import ctypes

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def main():
    # Check for unblock flag file
    flag_file = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'app_trusted.flag')
    
    if not os.path.exists(flag_file) and not is_admin():
        # Create flag file to avoid showing this message every time
        try:
            with open(flag_file, 'w') as f:
                f.write('trusted')
        except:
            pass
            
        app = QApplication(sys.argv)
        QMessageBox.information(
            None,
            "BrainLink Companion Security Notice",
            "This application needs to connect to the internet to function properly.\n\n"
            "If you experience connection issues, you may need to:\n"
            "1. Run as administrator\n"
            "2. Add an exception in your firewall\n"
            "3. Temporarily disable your antivirus\n\n"
            "Please see the TroubleshootingGuide.md file for detailed instructions."
        )
        
    # Continue with the main application
    from BrainCompanion import main
    main()

if __name__ == "__main__":
    main()
"@

# Write launcher script to a file
$launcher_script | Out-File -FilePath ".\launcher.py" -Encoding utf8

# Run PyInstaller with all required options and launcher script
pyinstaller --noconfirm --onefile --windowed `
    --add-data "assets;assets" `
    --add-data "BrainLinkParser;BrainLinkParser" `
    --add-data "TroubleshootingGuide.md;." `
    --icon="assets\favicon.ico" `
    --name="BrainCompanion" `
    --version-file="file_version_info.txt" `
    --uac-admin `
    launcher.py

# Check if build was successful
if (Test-Path ".\dist\BrainCompanion.exe") {
    Write-Host "Build successful! Executable created at: .\dist\BrainCompanion.exe" -ForegroundColor Green
    
    # Create a simple batch file to run as admin (alternative method)
    $batch_content = @"
@echo off
echo Starting BrainLink Companion with administrative privileges...
powershell -Command "Start-Process '.\BrainCompanion.exe' -Verb RunAs"
"@
    $batch_content | Out-File -FilePath ".\dist\RunAsAdmin.bat" -Encoding ascii
    
    # Copy the troubleshooting guide
    Copy-Item -Path ".\TroubleshootingGuide.md" -Destination ".\dist\" -Force
    
    Write-Host "Added RunAsAdmin.bat to help run with administrator privileges" -ForegroundColor Green
    Write-Host "Added TroubleshootingGuide.md to help users resolve security issues" -ForegroundColor Green
} else {
    Write-Host "Build failed! Executable not found." -ForegroundColor Red
}

# Clean up temporary files
Remove-Item -Path ".\file_version_info.txt" -Force -ErrorAction SilentlyContinue
Remove-Item -Path ".\launcher.py" -Force -ErrorAction SilentlyContinue

Write-Host "Done. Press Enter to exit..." -ForegroundColor Cyan
Read-Host
