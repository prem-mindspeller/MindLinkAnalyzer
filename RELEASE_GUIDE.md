# MindLink Analyzer — Release Guide

## Overview

MindLink Analyzer supports multiple EEG headsets, each maintained in its own branch. When you're ready to ship a new version, a single `git tag` command triggers a fully automated build and release pipeline — no manual uploads, no sending files over Google Drive.

Clients receive a permanent download link at **releases.mindspeller.com** that always shows the latest version for each headset.

---

## Repository Structure

| Repository | Visibility | Purpose |
|---|---|---|
| `prem-mindspeller/MindLinkAnalyzer` | Private | All source code |
| `Mindspeller/MindLink-Releases` | Public | Built installers + download page |

The source code never becomes public. Only the compiled `.exe` files are pushed to the public repo.

---

## Branch → Headset Mapping

| Branch | Headset | Tag Pattern |
|---|---|---|
| `feature/neuroprofile-traceability-v7` | MindLink Single Channel | `v1.2.0-mindlink` |
| `mindrove-integration` | MindRove 4-Channel | `v2.1.0-mindrove` |

Each branch has its own independent release pipeline. Releasing one headset never affects the other.

---

## What Happens When You Release

```
You push a tag
      │
      ▼
GitHub Actions picks it up (private repo)
      │
      ├── 1. Checks out the correct branch for that headset
      ├── 2. Builds the Python backend (PyInstaller → .exe)
      ├── 3. Bundles it inside the Electron app (electron-builder)
      ├── 4. Publishes the installer to Mindspeller/MindLink-Releases
      │         └── Creates a GitHub Release with:
      │               ├── Mindlink Analyzer Setup x.x.x.exe   ← installer
      │               ├── Mindlink Analyzer Setup x.x.x.exe.blockmap
      │               └── latest.yml                          ← auto-updater manifest
      │
      └── 5. Updates releases.mindspeller.com
                └── Reads version files for both headsets
                └── Regenerates download page with correct version per headset
```

After a client installs the app, it **automatically checks for updates** every 4 hours and prompts the user to restart when a new version is available. They never need a new download link.

---

## How to Release — Step by Step

### Before your first release
Make sure you're on the correct branch for the headset you're releasing.

---

### Releasing the MindLink Single Channel app

```bash
# 1. Make sure you're on the right branch
git checkout feature/neuroprofile-traceability-v7

# 2. Make your code changes and commit them as usual
git add .
git commit -m "feat: your change description"
git push origin feature/neuroprofile-traceability-v7

# 3. Tag the release (replace 1.2.0 with the new version number)
git tag v1.2.0-mindlink
git push origin v1.2.0-mindlink
```

That's it. The CI pipeline does everything else.

---

### Releasing the MindRove 4-Channel app

```bash
# 1. Make sure you're on the right branch
git checkout mindrove-integration

# 2. Make your code changes and commit them as usual
git add .
git commit -m "feat: your change description"
git push origin mindrove-integration

# 3. Tag the release (replace 2.1.0 with the new version number)
git tag v2.1.0-mindrove
git push origin v2.1.0-mindrove
```

---

### Versioning convention

Use standard semantic versioning: `vMAJOR.MINOR.PATCH-headset`

| Change type | Example | When to use |
|---|---|---|
| Patch | `v1.2.1-mindlink` | Bug fixes |
| Minor | `v1.3.0-mindlink` | New features, backward compatible |
| Major | `v2.0.0-mindlink` | Breaking changes or major overhaul |

Both headsets version independently — the MindLink app can be on `v1.3.0` while MindRove is on `v2.1.0`.

---

### Fixing a bad release (rollback)

If you need to undo a tag:

```bash
# Delete the tag locally and remotely
git tag -d v1.2.0-mindlink
git push origin :refs/tags/v1.2.0-mindlink

# Fix your code, commit, then re-tag
git tag v1.2.0-mindlink
git push origin v1.2.0-mindlink
```

---

## Monitoring a Release

1. Go to: `https://github.com/prem-mindspeller/MindLinkAnalyzer/actions`
2. Find the run triggered by your tag
3. Watch the steps — the full build takes **~5–10 minutes**
4. If it fails, the error message will appear in the failing step — paste it in the dev chat for help

When it succeeds:
- Release appears at: `https://github.com/Mindspeller/MindLink-Releases/releases`
- Download page updates at: `https://releases.mindspeller.com`

---

## The Download Page (releases.mindspeller.com)

The page shows two download cards — one per headset. Each card:
- Shows the headset image
- Shows the current released version number
- Links directly to the installer on GitHub Releases
- Shows "Coming Soon" if that headset has never been released

The page is regenerated automatically on every release by the `generate-page.ps1` script in `Mindspeller/MindLink-Releases`. You never need to edit it manually.

---

## Sharing with Clients

Send clients this one permanent link. It never changes:

```
https://releases.mindspeller.com
```

They download the installer for their headset, run it once, and from then on the app updates itself silently in the background.

---

## Adding a New Headset in the Future

1. Create a new branch from the most relevant existing branch
2. Add a new entry to `.github/workflows/` (copy `release-mindlink.yml` as a template, change the branch name, tag pattern, and product name)
3. Add a `newheadset-version.txt` file to `Mindspeller/MindLink-Releases`
4. Update `generate-page.ps1` to read the new version file and add a new card to the HTML
5. Cherry-pick the workflow files to the new branch

---

## Key Files Reference

| File | Location | Purpose |
|---|---|---|
| `release-singlechannel.yml` | `MindLinkAnalyzer/.github/workflows/` | CI pipeline for MindLink single channel |
| `release-mindrove.yml` | `MindLinkAnalyzer/.github/workflows/` | CI pipeline for MindRove 4-channel |
| `MindLinkBackend.spec` | `MindLinkAnalyzer/newBackend/` | PyInstaller build config for Python backend |
| `package.json` | `MindLinkAnalyzer/ElectronFrontEnd/` | Electron build config + publish settings |
| `main.js` | `MindLinkAnalyzer/ElectronFrontEnd/` | Auto-updater logic |
| `generate-page.ps1` | `MindLink-Releases/` | Regenerates the download page HTML |
| `mindlink-version.txt` | `MindLink-Releases/` | Tracks current MindLink release version |
| `mindrove-version.txt` | `MindLink-Releases/` | Tracks current MindRove release version |
