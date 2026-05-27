# MindLink Analyzer

A desktop EEG cognitive-assessment application built with **Electron + React** and a **Python FastAPI** backend.

The app connects to a NeuroSky/BrainLink EEG headset, guides the user through a standardised session of cognitive tasks, and seeds the resulting brain-wave report to the Mindspeller API.

---

## Project Structure

```
MindLinkAnalyzer/
├── newBackend/          # Python FastAPI backend — serial parsing, signal processing, WebSocket
└── ElectronFrontEnd/    # Electron + React frontend — UI, session flow, API integration
```

> All other files and folders at the repository root are legacy or experimental and are **not part of the active application**.

---

## Documentation

| Component | File | Description |
|---|---|---|
| Python backend | [newBackend/STARTUP.md](newBackend/STARTUP.md) | Environment setup, dependency installation, and how to start the backend server |
| Electron frontend | [ElectronFrontEnd/DOCUMENTATION.md](ElectronFrontEnd/DOCUMENTATION.md) | Full architecture reference, module guide, data-flow diagrams, and build instructions |

---

## Quick Start

Both the backend and the frontend must be running at the same time.

### 1. Start the Python backend

```powershell
cd newBackend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 2. Start the Electron frontend

```powershell
cd ElectronFrontEnd
npm install
npm run dev
```
### . Build Instruction

Step 1 — build the backend (from workspace root, using conda Python):

cd m:\CODEBASE\MindLinkAnalyzer
C:\Users\conta\anaconda3\envs\brainlink\python.exe -m PyInstaller MindLinkBackend.spec --distpath newBackend/dist

Step 2 — package the Electron app (electron-builder picks up the backend folder automatically via extraResources):

cd ElectronFrontEnd
npm run package

# Equivalent: npx electron-builder
# The Electron Builder beforePack hook runs the webpack production build and
# verifies dist/index.html and dist/bundle.js before packaging.


See the linked documentation files above for full details, troubleshooting, and build instructions.
