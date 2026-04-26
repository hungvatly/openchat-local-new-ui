// OpenChatLocal.swift — Native macOS App
// Starts FastAPI server, then shows the UI in a WKWebView.
// Build: ./build_app.sh

import Cocoa
import WebKit
import Carbon
import LocalAuthentication

// ── Entry Point ───────────────────────────────────────────────────────────────

let _app  = NSApplication.shared
let _del  = AppDelegate()
_app.delegate = _del
_app.run()

// ── Helper for FourCharCode
func UTGetOSTypeFromString(_ string: String) -> OSType {
    var result: OSType = 0
    if let data = string.data(using: .macOSRoman) {
        for (i, byte) in data.enumerated() where i < 4 {
            result = (result << 8) | OSType(byte)
        }
    }
    return result
}

// ── Native Draggable Overlay ─────────────────────────────────────────────

class DraggableView: NSView {
    override func hitTest(_ point: NSPoint) -> NSView? {
        // Force the view to catch clicks even if it's completely transparent
        let localPoint = self.convert(point, from: self.superview)
        return self.bounds.contains(localPoint) ? self : nil
    }

    override func mouseDown(with event: NSEvent) {
        self.window?.performDrag(with: event)
    }
}

// ── App Delegate ──────────────────────────────────────────────────────────────

final class AppDelegate: NSObject, NSApplicationDelegate, WKScriptMessageHandler, WKUIDelegate {

    private var mainWindow: NSWindow?
    private var webView: WKWebView?
    private var serverProcess: Process?
    private var statusItem: NSStatusItem?
    private var loadingWC: LoadingWindowController?
    private var hotKeyRef: EventHotKeyRef?

    private let port = 8000

    // ── Paths ──────────────────────────────────────────────────────────────

    private lazy var projectDir: String = {
        let home = NSHomeDirectory()
        // 1. Embedded inside the .app bundle (Resources/app/)
        if let res = Bundle.main.resourcePath {
            let candidate = res + "/app"
            if FileManager.default.fileExists(atPath: candidate + "/main.py") {
                return candidate
            }
        }
        // 2. Same directory as the .app
        let appParent = (Bundle.main.bundlePath as NSString).deletingLastPathComponent
        let sibling = appParent + "/openchat-local"
        if FileManager.default.fileExists(atPath: sibling + "/main.py") { return sibling }

        // 3. Known development paths
        for p in [
            home + "/Documents/Antigravity/openchat-local",
            home + "/Documents/openchat-local",
        ] {
            if FileManager.default.fileExists(atPath: p + "/main.py") { return p }
        }
        return home + "/Documents/Antigravity/openchat-local"
    }()

    private lazy var pythonPath: String = {
        let home = NSHomeDirectory()
        let candidates = [
            projectDir + "/.venv/bin/python3",
            home + "/Documents/openchat-local/venv/bin/python3",
            home + "/opt/venv/bin/python3",
            "/usr/local/bin/python3",
            "/opt/homebrew/bin/python3",
        ]
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0) }
               ?? "/usr/bin/python3"
    }()

    // ── Lifecycle ──────────────────────────────────────────────────────────

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        setupMainMenu()      // Full menu bar — enables Cmd+C/V/Z etc.
        setupStatusBarMenu() // Status bar icon
        registerGlobalShortcut()
        
        DispatchQueue.global(qos: .userInitiated).async { self.bootSequence() }
    }

    private func registerGlobalShortcut() {
        var hotKeyID = EventHotKeyID()
        hotKeyID.signature = UTGetOSTypeFromString("OPEN")
        hotKeyID.id = UInt32(1)

        var eventType = EventTypeSpec()
        eventType.eventClass = OSType(kEventClassKeyboard)
        eventType.eventKind = OSType(kEventHotKeyPressed)

        InstallEventHandler(GetApplicationEventTarget(), { (nextHandler, theEvent, userData) -> OSStatus in
            var hkCom = EventHotKeyID()
            GetEventParameter(theEvent, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID), nil, MemoryLayout<EventHotKeyID>.size, nil, &hkCom)
            if hkCom.id == 1 {
                DispatchQueue.main.async {
                    if let appDel = NSApp.delegate as? AppDelegate {
                        appDel.bringToFront()
                    }
                }
            }
            return noErr
        }, 1, &eventType, nil, nil)

        // kVK_Space is 49, optionKey is 2048
        RegisterEventHotKey(UInt32(49), UInt32(2048), hotKeyID, GetApplicationEventTarget(), 0, &hotKeyRef)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationWillTerminate(_ notification: Notification) {
        serverProcess?.terminate()
    }

    // ── Main Menu Bar (enables Cmd+C/V/X/Z/A etc.) ─────────────────────────

    private func setupMainMenu() {
        let mainMenu = NSMenu(title: "MainMenu")

        // ── Apple Menu ──
        let appItem = NSMenuItem()
        mainMenu.addItem(appItem)
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "About OpenChat Local",
                        action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)),
                        keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Hide OpenChat Local",
                        action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(withTitle: "Quit OpenChat Local",
                        action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu

        // ── Edit Menu (gives WKWebView Cut/Copy/Paste/Undo/Redo) ──
        let editItem = NSMenuItem()
        mainMenu.addItem(editItem)
        let editMenu = NSMenu(title: "Edit")
        editMenu.addItem(withTitle: "Undo",  action: Selector(("undo:")),  keyEquivalent: "z")
        editMenu.addItem(withTitle: "Redo",  action: Selector(("redo:")),  keyEquivalent: "Z")
        editMenu.addItem(.separator())
        editMenu.addItem(withTitle: "Cut",        action: #selector(NSText.cut(_:)),        keyEquivalent: "x")
        editMenu.addItem(withTitle: "Copy",       action: #selector(NSText.copy(_:)),       keyEquivalent: "c")
        editMenu.addItem(withTitle: "Paste",      action: #selector(NSText.paste(_:)),      keyEquivalent: "v")
        editMenu.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editMenu.addItem(.separator())
        let findItem = editMenu.addItem(withTitle: "Find", action: nil, keyEquivalent: "")
        let findMenu = NSMenu(title: "Find")
        findMenu.addItem(withTitle: "Find…",          action: #selector(NSResponder.performTextFinderAction(_:)), keyEquivalent: "f")
        findMenu.addItem(withTitle: "Find Next",       action: #selector(NSResponder.performTextFinderAction(_:)), keyEquivalent: "g")
        findItem.submenu = findMenu
        editItem.submenu = editMenu

        // ── Window Menu ──
        let winItem = NSMenuItem()
        mainMenu.addItem(winItem)
        let winMenu = NSMenu(title: "Window")
        winMenu.addItem(withTitle: "Minimize", action: #selector(NSWindow.miniaturize(_:)), keyEquivalent: "m")
        winMenu.addItem(withTitle: "Zoom",     action: #selector(NSWindow.zoom(_:)),        keyEquivalent: "")
        winMenu.addItem(.separator())
        winMenu.addItem(withTitle: "Bring All to Front", action: #selector(NSApplication.arrangeInFront(_:)), keyEquivalent: "")
        winItem.submenu = winMenu
        NSApp.windowsMenu = winMenu

        NSApp.mainMenu = mainMenu
    }

    // ── Status Bar Menu ────────────────────────────────────────────────────

    private func setupStatusBarMenu() {
        let menu = NSMenu()
        menu.addItem(withTitle: "Show OpenChat", action: #selector(bringToFront), keyEquivalent: "")
        menu.addItem(.separator())
        menu.addItem(withTitle: "Show Logs", action: #selector(showLogs), keyEquivalent: "")
        menu.addItem(.separator())
        menu.addItem(withTitle: "Quit OpenChat", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let btn = statusItem?.button {
            btn.image = NSImage(systemSymbolName: "diamond.fill", accessibilityDescription: "OpenChat")
            btn.image?.size = NSSize(width: 14, height: 14)
            btn.imageScaling = .scaleProportionallyDown
        }
        statusItem?.menu = menu
    }

    @objc private func bringToFront() {
        mainWindow?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc private func showLogs() {
        let logPath = NSHomeDirectory() + "/Library/Logs/OpenChatLocal.log"
        NSWorkspace.shared.open(URL(fileURLWithPath: logPath))
    }

    // ── Loading Window ─────────────────────────────────────────────────────

    private func showLoadingWindow() {
        DispatchQueue.main.async {
            let wc = LoadingWindowController()
            wc.showWindow(nil)
            self.loadingWC = wc
            NSApp.activate(ignoringOtherApps: true)
        }
    }

    private func setStatus(_ msg: String) {
        DispatchQueue.main.async { self.loadingWC?.updateStatus(msg) }
    }

    private func setDetail(_ msg: String) {
        DispatchQueue.main.async { self.loadingWC?.updateDetail(msg) }
    }

    // ── Boot Sequence ──────────────────────────────────────────────────────

    private func bootSequence() {
        startPythonServer()
        waitForServer(timeout: 60) { ok in
            DispatchQueue.main.async {
                self.loadingWC?.close()
                self.loadingWC = nil
                if ok {
                    self.showMainWindow()
                } else {
                    self.showErrorAlert()
                }
            }
        }
    }

    // ── Python Server ──────────────────────────────────────────────────────

    private func startPythonServer() {
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: pythonPath)
        // Run uvicorn directly (no reload in app mode)
        proc.arguments = ["-m", "uvicorn", "main:app",
                          "--host", "127.0.0.1",
                          "--port", "\(port)",
                          "--log-level", "warning"]
        proc.currentDirectoryURL = URL(fileURLWithPath: projectDir)
        proc.environment = enrichedEnv()
        redirectOutput(proc, tag: "server")
        try? proc.run()
        serverProcess = proc
    }

    // ── Health Wait ────────────────────────────────────────────────────────

    private func waitForServer(timeout: Int, completion: @escaping (Bool) -> Void) {
        let url = URL(string: "http://127.0.0.1:\(port)/api/health")!
        var attempt = 0
        func check() {
            guard attempt < timeout else { completion(false); return }
            attempt += 1
            let task = URLSession.shared.dataTask(with: url) { _, res, _ in
                if (res as? HTTPURLResponse)?.statusCode == 200 {
                    completion(true)
                } else {
                    Thread.sleep(forTimeInterval: 1)
                    check()
                }
            }
            task.resume()
        }
        check()
    }

    // ── Main Window ────────────────────────────────────────────────────────

    private func showMainWindow() {
        let screen = NSScreen.main?.frame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let w = min(1280.0, screen.width  * 0.88)
        let h = min(860.0,  screen.height * 0.88)
        let x = (screen.width  - w) / 2
        let y = (screen.height - h) / 2

        let cfg = WKWebViewConfiguration()
        cfg.preferences.setValue(true, forKey: "developerExtrasEnabled")
        // Allow media capture without prompting each time
        if #available(macOS 12.0, *) {
            cfg.defaultWebpagePreferences.allowsContentJavaScript = true
        }
        cfg.userContentController.add(self, name: "nativeApp")
        let wv = WKWebView(frame: .zero, configuration: cfg)
        wv.uiDelegate = self   // Required for media permission delegate method
        wv.load(URLRequest(url: URL(string: "http://127.0.0.1:\(port)")!))
        webView = wv

        let win = NSWindow(
            contentRect: NSRect(x: x, y: y, width: w, height: h),
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        // Dark window — no NSVisualEffectView, no transparent background.
        // This avoids triggering macOS Screen Recording permission.
        // The web UI handles its own glass effects via CSS backdrop-filter.
        win.isOpaque = true
        win.backgroundColor = NSColor(calibratedRed: 0.039, green: 0.039, blue: 0.043, alpha: 1)
        win.titlebarAppearsTransparent = true
        win.titleVisibility = .hidden
        win.isMovableByWindowBackground = true

        if let contentView = win.contentView {
            wv.frame = contentView.bounds
            wv.autoresizingMask = [.width, .height]
            // DO NOT set drawsBackground=false — it triggers Screen Recording permission
            contentView.addSubview(wv)

            // Add native draggable titlebar overlay (x: 80 leaves room for macOS traffic lights)
            let dragView = DraggableView(frame: NSRect(x: 80, y: contentView.bounds.height - 32, width: contentView.bounds.width - 80, height: 32))
            dragView.autoresizingMask = [.width, .minYMargin]
            contentView.addSubview(dragView)
        }
        
        win.minSize = NSSize(width: 720, height: 520)
        win.setFrameAutosaveName("MainWindow")
        win.makeKeyAndOrderFront(nil)
        mainWindow = win
        NSApp.activate(ignoringOtherApps: true)
    }

    // ── Script Message Handler ─────────────────────────────────────────────


    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.name == "nativeApp",
              let body = message.body as? [String: Any],
              let action = body["action"] as? String else { return }
        
        if action == "dragWindow" {
            if let event = NSApp.currentEvent {
                self.mainWindow?.performDrag(with: event)
            }
            return
        }

        
        let callbackId = body["callbackId"] as? String ?? ""
        
        func respond(payload: String) {
            guard !callbackId.isEmpty else { return }
            let js = "window._nativeCallback('\(callbackId)', \(payload));"
            DispatchQueue.main.async {
                self.webView?.evaluateJavaScript(js, completionHandler: nil)
            }
        }
        
        if action == "touch_id" {
            let context = LAContext()
            var error: NSError?
            if context.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: &error) {
                let reason = body["reason"] as? String ?? "Authenticate for Private Session"
                context.evaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, localizedReason: reason) { success, authError in
                    respond(payload: "{\"success\": \(success)}")
                }
            } else {
                respond(payload: "{\"success\": false, \"error\": \"Biometrics unavailable\"}")
            }
        }
        else if action == "browse_folder" {
            DispatchQueue.main.async {
                let panel = NSOpenPanel()
                panel.canChooseFiles = false
                panel.canChooseDirectories = true
                panel.allowsMultipleSelection = false
                if panel.runModal() == .OK, let url = panel.url {
                    respond(payload: "{\"path\": \"\(url.path)\"}")
                } else {
                    respond(payload: "{\"path\": null}")
                }
            }
        }
    }

    // ── WKUIDelegate — auto-grant mic/camera (permission already given via system prompt) ──

    @available(macOS 12.0, *)
    func webView(_ webView: WKWebView,
                 requestMediaCapturePermissionFor origin: WKSecurityOrigin,
                 initiatedByFrame frame: WKFrameInfo,
                 type: WKMediaCaptureType,
                 decisionHandler: @escaping (WKPermissionDecision) -> Void) {
        decisionHandler(.grant)
    }

    // ── WKUIDelegate — native file picker for <input type="file"> ──────────
    // WKWebView SILENTLY ignores file inputs unless this delegate is implemented.

    func webView(_ webView: WKWebView,
                 runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo,
                 completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.canChooseFiles         = true
        panel.canChooseDirectories   = false
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.allowedContentTypes    = [] // allow all — web page accept= filter handles restriction
        panel.message  = "Choose file(s) to upload"
        panel.prompt   = "Upload"

        panel.begin { response in
            if response == .OK {
                completionHandler(panel.urls)
            } else {
                completionHandler(nil)
            }
        }
    }

    // ── Error Alert ────────────────────────────────────────────────────────

    private func showErrorAlert() {
        let alert = NSAlert()
        alert.messageText = "Server failed to start"
        alert.informativeText = "Check ~/Library/Logs/OpenChatLocal.log for details.\n\nMake sure the Python venv and dependencies are installed."
        alert.alertStyle = .critical
        alert.addButton(withTitle: "Show Logs")
        alert.addButton(withTitle: "Quit")
        if alert.runModal() == .alertFirstButtonReturn {
            showLogs()
        }
        NSApp.terminate(nil)
    }

    // ── Helpers ────────────────────────────────────────────────────────────

    private func isPortOpen(_ port: Int) -> Bool {
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/bin/sh")
        proc.arguments = ["-c", "curl -s http://127.0.0.1:\(port) > /dev/null 2>&1"]
        try? proc.run()
        proc.waitUntilExit()
        return proc.terminationStatus == 0
    }

    private func enrichedEnv() -> [String: String] {
        var env = ProcessInfo.processInfo.environment
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        // Add Homebrew to PATH if not already there
        let extraPaths = "/opt/homebrew/bin:/usr/local/bin"
        env["PATH"] = extraPaths + ":" + (env["PATH"] ?? "/usr/bin:/bin")
        return env
    }

    private func redirectOutput(_ proc: Process, tag: String) {
        let logPath = NSHomeDirectory() + "/Library/Logs/OpenChatLocal.log"
        FileManager.default.createFile(atPath: logPath, contents: nil)
        if let fh = FileHandle(forWritingAtPath: logPath) {
            fh.seekToEndOfFile()
            proc.standardOutput = fh
            proc.standardError  = fh
        }
    }
}

// ── Loading Window ────────────────────────────────────────────────────────────

final class LoadingWindowController: NSWindowController {

    private var spinner: NSProgressIndicator!

    convenience init() {
        // Transparent borderless window setup
        let win = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 340, height: 110),
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        win.isOpaque = false
        win.backgroundColor = .clear // Transparent window background
        win.hasShadow = false
        win.center()
        win.level = .floating
        self.init(window: win)
        buildUI()
    }

    private func buildUI() {
        guard let cv = window?.contentView else { return }

        // Glow container (drawn inside the transparent window bounds to allow shadow bleed)
        let bgView = NSView()
        bgView.wantsLayer = true
        bgView.layer?.backgroundColor = NSColor(calibratedRed: 0.05, green: 0.05, blue: 0.05, alpha: 1.0).cgColor
        bgView.layer?.cornerRadius = 18
        bgView.layer?.borderWidth = 1
        bgView.layer?.borderColor = NSColor(calibratedRed: 0.2, green: 0.4, blue: 0.8, alpha: 0.6).cgColor // Subtle blue glow
        
        // Custom neon glow via shadow
        bgView.layer?.shadowColor = NSColor.systemBlue.cgColor
        bgView.layer?.shadowOpacity = 0.8
        bgView.layer?.shadowRadius = 16
        bgView.layer?.shadowOffset = .zero
        bgView.translatesAutoresizingMaskIntoConstraints = false
        cv.addSubview(bgView)

        // App name
        let name = NSTextField(labelWithString: "OpenChat Local")
        name.font = NSFont.systemFont(ofSize: 22, weight: .regular)
        name.textColor = NSColor(calibratedRed: 0.95, green: 0.95, blue: 0.95, alpha: 1)
        name.alignment = .center
        name.translatesAutoresizingMaskIntoConstraints = false
        bgView.addSubview(name)

        NSLayoutConstraint.activate([
            // Pad 20px on all sides to give room for the shadow glow without getting clipped
            bgView.leadingAnchor.constraint(equalTo: cv.leadingAnchor, constant: 20),
            bgView.trailingAnchor.constraint(equalTo: cv.trailingAnchor, constant: -20),
            bgView.topAnchor.constraint(equalTo: cv.topAnchor, constant: 20),
            bgView.bottomAnchor.constraint(equalTo: cv.bottomAnchor, constant: -20),

            // Perfectly center the text
            name.centerXAnchor.constraint(equalTo: bgView.centerXAnchor),
            name.centerYAnchor.constraint(equalTo: bgView.centerYAnchor)
        ])
    }

    // No-ops — kept so existing call sites don't crash
    func updateStatus(_ msg: String) {}
    func updateDetail(_ msg: String) {}
}

