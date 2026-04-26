# How to Build OpenChat Local with Xcode

This guide walks you through building the `OpenChat Local.app` using Xcode instead of the CLI script. The result is a fully signed `.app` you can run, archive, and distribute.

---

## Prerequisites

| Requirement | Version |
|-------------|---------|
| macOS | 13.0 Ventura or later |
| Xcode | 15 or later |
| Python | 3.10+ (via Homebrew: `brew install python`) |

Install Xcode from the App Store, then accept the license:
```bash
sudo xcodebuild -license accept
```

---

## Step 1 — Create a New Xcode Project

1. Open **Xcode** → **File** → **New** → **Project…**
2. Choose **macOS** → **App**
3. Fill in the fields:
   - **Product Name:** `OpenChat Local`
   - **Bundle Identifier:** `com.yourname.openchat-local` (can be anything)
   - **Language:** Swift
   - **Interface:** **None** (we provide our own window)
   - **Life Cycle:** AppKit App Delegate
4. **Uncheck** "Include Tests"
5. Save the project **inside** the `openchat-local Mac/` folder (e.g., `openchat-local Mac/XcodeProj/`)

---

## Step 2 — Replace the Default Swift Files

1. In the Xcode project navigator, **delete** `AppDelegate.swift` and `main.swift` (move to Trash)
2. **Drag** `OpenChatLocal.swift` from the project root into the Xcode project navigator
3. When prompted, select **"Copy items if needed"** → add to target

Your `OpenChatLocal.swift` already contains the full `AppDelegate` and `LoadingWindowController` — it needs no modifications for Xcode.

---

## Step 3 — Configure Build Settings

### 3a. Info.plist

1. Click the project in the navigator → select the **Target** → **Info** tab
2. Set:
   | Key | Value |
   |-----|-------|
   | `CFBundleName` | `OpenChat Local` |
   | `CFBundleIdentifier` | (same as Step 1) |
   | `CFBundleVersion` | `1` |
   | `NSPrincipalClass` | `NSApplication` |
   | `NSHighResolutionCapable` | `YES` |
   | `NSAppTransportSecurity` > `NSAllowsLocalNetworking` | `YES` |

   Or simply copy the existing `OpenChatLocal.plist` as the project's `Info.plist`:
   - In Build Settings → search for **Info.plist File** → set to `../OpenChatLocal.plist`

### 3b. Deployment Target

- Build Settings → **macOS Deployment Target** → `13.0`

### 3c. App Sandbox

> [!IMPORTANT]
> The app cannot be sandboxed because it launches a subprocess (Python/uvicorn).

- **Signing & Capabilities** → remove **App Sandbox** if present (or ensure it's OFF)

---

## Step 4 — Add Python App as Bundle Resources

The Swift wrapper looks for `Resources/app/main.py` inside the bundle. We need to add all Python files as resources.

1. In Xcode, right-click on the project navigator → **Add Files to "OpenChat Local"…**
2. Select the entire **`openchat-local Mac/`** folder (the parent folder)
3. Options:
   - ✅ **Create folder references** (not groups — this keeps the directory hierarchy)
   - Target membership: **OpenChat Local**
4. In **Build Phases** → **Copy Bundle Resources**, confirm the folder appears

This embeds the Python app at:
```
OpenChat Local.app/Contents/Resources/openchat-local Mac/
```

> [!TIP]
> The Swift wrapper also searches for the folder **next to** the `.app` file, so you can skip resource embedding during development and just run the `.app` in-place from your project directory.

---

## Step 5 — Bundled Python venv (for distribution)

For a distributable app that doesn't require the user to have Python:

1. Run the bundled venv setup manually once:
   ```bash
   cd "openchat-local Mac"
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```
2. In Xcode → **Build Phases** → **Copy Bundle Resources** → add the `.venv` folder
3. The Swift wrapper will find `.venv/bin/python3` inside the Resources/app path automatically

> [!WARNING]
> The `.venv` folder is large (~500MB with llama-cpp-python). Expect the `.app` bundle to be 500MB+ before adding models. This is normal.

---

## Step 6 — Build the App

1. Select the **"My Mac"** destination in the toolbar
2. Press **⌘B** to build
3. Press **⌘R** to run

The app will launch the loading window, start the Python server, and open the chat UI in a WebView.

---

## Step 7 — Archive for Distribution

If you want to share the `.app` with others:

1. **Product** → **Archive**
2. In the Organizer window → **Distribute App**
3. Choose **Copy App** (for manual distribution, no App Store)
4. Export the `.app` file

Then zip it for sharing:
```bash
cd /path/to/export
zip -r "OpenChat Local.zip" "OpenChat Local.app"
```

---

## Troubleshooting

### "Server failed to start"
- Check `~/Library/Logs/OpenChatLocal.log` for the Python traceback
- Most common cause: missing dependencies. Run:
  ```bash
  .venv/bin/pip install -r requirements.txt
  ```

### "Python not found"
- The Swift wrapper searches for Python in this order:
  1. `Resources/app/.venv/bin/python3` (bundled venv)
  2. `~/Documents/openchat-local/venv/bin/python3`
  3. `/opt/homebrew/bin/python3`
  4. `/usr/local/bin/python3`
  5. `/usr/bin/python3`
- Install Python: `brew install python`

### Build error: "module 'Cocoa' not found"
- Make sure you selected **macOS App** (not iOS) as the platform
- Check Build Settings → **Base SDK** is set to **macOS**

### App opens but shows blank WebView
- The server may still be starting. Wait 10–20 seconds and refresh
- Check the log file for errors

---

## Quick Reference

| Action | Command |
|--------|---------|
| Build (CLI, no Xcode) | `./build_app.sh` |
| Build (Xcode) | `⌘B` |
| Run (Xcode) | `⌘R` |
| View logs | `open ~/Library/Logs/OpenChatLocal.log` |
| Install to Applications | Drag `.app` to `/Applications` |
