# Building & Packaging Mindlink Analyzer

Complete step-by-step guide to build and package the application from source to a Windows installer `.exe`.

---

## Prerequisites

- **Python 3.11** environment (`brainlink311` conda env) with dependencies installed
- **Node.js** and **npm** installed
- **PyInstaller** installed in the Python environment
- Backend built with PyInstaller once, output in `newBackend/dist/MindlinkBackend/`

---

## Build Steps

### Step 1: Build the Python Backend (PyInstaller)

Navigate to the backend directory and compile `main.py` into a Windows executable:

```powershell
cd m:\CODEBASE\MindLinkAnalyzer\newBackend

# Activate the Python 3.11 environment
conda activate brainlink311

# Install PyInstaller if not already present
python -m pip install pyinstaller -q

# Build the executable using the spec file
pyinstaller MindLinkBackend.spec --distpath dist --workpath build --noconfirm
```

**Output:** `newBackend/dist/MindlinkBackend/MindlinkBackend.exe`

This creates a self-contained executable that includes:
- Python 3.11 runtime
- All Python dependencies (fastapi, uvicorn, numpy, scipy, pyserial)
- BrainLinkParser SDK DLL
- EEG processing code

---

### Step 2: Build the React Frontend (Webpack)

Return to the Electron frontend directory and compile the React app:

```powershell
cd m:\CODEBASE\MindLinkAnalyzer\ElectronFrontEnd

# Install Node dependencies (if not already done)
npm install

# Build the webpack bundle
npm run build
```

**Output:** 
- `ElectronFrontEnd/dist/bundle.js` — React app bundle
- `ElectronFrontEnd/dist/index.html` — HTML entry point

---

### Step 3: Package the Electron App (electron-builder)

Create the Windows installer:

```powershell
# Stay in ElectronFrontEnd directory
cd m:\CODEBASE\MindLinkAnalyzer\ElectronFrontEnd

# Set environment variables to disable code signing
$env:CSC_IDENTITY_AUTO_DISCOVERY = "false"
$env:WIN_CSC_LINK = ""

# Build and package the app into an NSIS installer
npx electron-builder --win --publish=never
```

**Output:**
- `ElectronFrontEnd/dist/Mindlink Analyzer Setup 1.0.0.exe` — **Main installer**
- `ElectronFrontEnd/dist/win-unpacked/` — Portable (unpackaged) version

---

## Complete One-Liner (for CI/Automation)

If you want to run all three steps in sequence:

```powershell
# Build backend
cd m:\CODEBASE\MindLinkAnalyzer\newBackend; `
conda activate brainlink311; `
python -m pip install pyinstaller -q; `
pyinstaller MindLinkBackend.spec --distpath dist --workpath build --noconfirm; `

# Build frontend
cd m:\CODEBASE\MindLinkAnalyzer\ElectronFrontEnd; `
npm run build; `

# Package app
$env:CSC_IDENTITY_AUTO_DISCOVERY="false"; `
$env:WIN_CSC_LINK=""; `
npx electron-builder --win --publish=never
```

---

## Finding Your Application

### Main Installer (Recommended Distribution)

```
📦 m:\CODEBASE\MindLinkAnalyzer\ElectronFrontEnd\dist\
   └── 📄 Mindlink Analyzer Setup 1.0.0.exe   ← RUN THIS TO INSTALL
```

**To run:** Double-click `Mindlink Analyzer Setup 1.0.0.exe` — it will launch the NSIS installer wizard that guides users through installation to Program Files.

---

### Portable Version (No Installation Required)

```
📦 m:\CODEBASE\MindLinkAnalyzer\ElectronFrontEnd\dist\win-unpacked\
   └── 📄 Mindlink Analyzer.exe    ← RUN THIS DIRECTLY (no installer)
```

**To run:** Double-click `Mindlink Analyzer.exe` — the app launches immediately without installation. All dependencies are bundled in the same folder.

---

## What Happens When You Run the Installer

1. **NSIS Installer Wizard** launches
2. User selects installation directory (default: `C:\Program Files\Mindlink Analyzer`)
3. Files are copied to the installation directory:
   - Electron runtime
   - React frontend (bundled as `bundle.js`)
   - Python backend (`MindlinkBackend.exe`) inside `resources/backend/`
   - All assets and locales (EN, NL)
4. Start Menu shortcut is created
5. Application is ready to launch

---

## What Happens When You Run the App

1. **Electron main process** (`main.js`) launches
2. **Python backend** is spawned as a child process (`MindlinkBackend.exe`)
   - Listens on `http://localhost:8000`
   - Provides REST API and WebSocket endpoints
3. **Electron window** opens and loads the React frontend
4. Frontend connects to the backend via WebSocket at `ws://localhost:8000/ws`
5. User sees the Mindlink Analyzer interface and can start recording EEG data

---

## File Structure After Build

```
ElectronFrontEnd/
├── dist/
│   ├── Mindlink Analyzer Setup 1.0.0.exe    ← INSTALLER
│   ├── Mindlink Analyzer Setup 1.0.0.exe.blockmap
│   ├── win-unpacked/                        ← PORTABLE
│   │   ├── Mindlink Analyzer.exe
│   │   ├── resources/
│   │   │   └── backend/
│   │   │       └── MindlinkBackend.exe      ← Python backend
│   │   └── ...
│   └── builder-effective-config.yaml
├── package.json
└── ...

newBackend/
├── dist/
│   └── MindlinkBackend/
│       ├── MindlinkBackend.exe              ← Python executable
│       ├── _internal/                       ← Runtime libs
│       │   ├── python311.dll
│       │   ├── uvicorn files
│       │   └── ...
│       └── BrainLinkParser/
│           ├── BrainLinkParser.pyd
│           └── DLLs
└── ...
```

---

## Troubleshooting

### Backend not bundled in installer

**Issue:** `resources/backend/` directory is empty in the packaged app.

**Solution:** Ensure the PyInstaller build completed successfully before running `npm run build`:
```powershell
# Verify the backend exists
Test-Path m:\CODEBASE\MindLinkAnalyzer\newBackend\dist\MindlinkBackend\MindlinkBackend.exe

# If not, rebuild it
```

### App won't start after installation

**Issue:** "Cannot find Python runtime" or backend fails to start.

**Solution:** 
- Check that `MindlinkBackend.exe` is in `C:\Program Files\Mindlink Analyzer\resources\backend\`
- Verify the Python environment had all dependencies: `fastapi`, `uvicorn[standard]`, `numpy`, `scipy`, `pyserial`
- Run `MindlinkBackend.exe` manually to check for DLL errors:
```powershell
C:\Program Files\Mindlink Analyzer\resources\backend\MindlinkBackend.exe
```

### Installer fails with "7zip extraction error"

**Issue:** Code signing cache corrupted (symlink permission error).

**Solution:**
```powershell
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\electron-builder\Cache\winCodeSign" -ErrorAction SilentlyContinue
npx electron-builder --win --publish=never
```

---

## Distribution

The installer `Mindlink Analyzer Setup 1.0.0.exe` is ready to distribute to end users. They can:
- Download it
- Run the installer
- Launch the app from Start Menu → "Mindlink Analyzer"
- No additional software required (Python, Node, etc. are bundled)

---

## Version Updates

To release a new version:

1. Increment version in `ElectronFrontEnd/package.json` (e.g., `1.0.1`)
2. Rebuild backend (Step 1)
3. Rebuild frontend (Step 2)
4. Repackage (Step 3) — the new `.exe` will have the new version number in the filename

---

**Last updated:** May 11, 2026
