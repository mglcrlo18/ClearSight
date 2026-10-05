import Cocoa
import WebKit

class CustomWebView: WKWebView {
    override var acceptsFirstResponder: Bool {
        return true
    }
}

class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKDownloadDelegate, WKUIDelegate {
    var window: NSWindow!
    var webView: CustomWebView!

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        setupMainMenu()

        // Set native macOS Dock icon from official brand logo mark
        let iconPaths = [
            Bundle.main.path(forResource: "app_icon", ofType: "png"),
            "app_icon.png",
            "static/app_icon.png"
        ].compactMap { $0 }
        for path in iconPaths {
            if FileManager.default.fileExists(atPath: path), let img = NSImage(contentsOfFile: path) {
                NSApp.applicationIconImage = img
                break
            }
        }

        let screenRect = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 920)
        let windowWidth: CGFloat = min(1440, screenRect.width * 0.94)
        let windowHeight: CGFloat = min(920, screenRect.height * 0.92)

        let rect = NSRect(
            x: (screenRect.width - windowWidth) / 2,
            y: (screenRect.height - windowHeight) / 2,
            width: windowWidth,
            height: windowHeight
        )

        window = NSWindow(
            contentRect: rect,
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        window.title = "ClearSight - Native Survey Tabulation"
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .visible
        window.center()
        window.delegate = self

        let config = WKWebViewConfiguration()
        webView = CustomWebView(frame: window.contentView!.bounds, configuration: config)
        webView.navigationDelegate = self
        webView.uiDelegate = self  // <-- Connect WKUIDelegate (CS-101)
        webView.autoresizingMask = [.width, .height]
        window.contentView?.addSubview(webView)

        // Read dynamic port if configured or discover via .clearsight_port
        let envPort = ProcessInfo.processInfo.environment["CLEARSIGHT_PORT"]
        let filePort: String? = {
            if let dir = Bundle.main.resourcePath {
                let candidate = (dir as NSString).appendingPathComponent(".clearsight_port")
                if let str = try? String(contentsOfFile: candidate, encoding: .utf8) {
                    return str.trimmingCharacters(in: .whitespacesAndNewlines)
                }
            }
            if let str = try? String(contentsOfFile: ".clearsight_port", encoding: .utf8) {
                return str.trimmingCharacters(in: .whitespacesAndNewlines)
            }
            return nil
        }()
        let portStr = envPort ?? filePort ?? "8540"
        let port = Int(portStr) ?? 8540

        if let url = URL(string: "http://127.0.0.1:\(port)") {
            webView.load(URLRequest(url: url))
        }

        window.makeKeyAndOrderFront(nil)
        window.makeFirstResponder(webView)
        NSApp.activate(ignoringOtherApps: true)
    }

    // MARK: - Native WebKit Download Handling
    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        if let mimeType = navigationResponse.response.mimeType, mimeType.contains("spreadsheetml") || mimeType.contains("octet-stream") || mimeType.contains("pdf") {
            if #available(macOS 11.3, *) {
                decisionHandler(.download)
                return
            }
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        download.delegate = self
    }

    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
        download.delegate = self
    }

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        let downloadsDirectory = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first!
        var destinationURL = downloadsDirectory.appendingPathComponent(suggestedFilename)
        var counter = 1
        let baseName = (suggestedFilename as NSString).deletingPathExtension
        let ext = (suggestedFilename as NSString).pathExtension
        while FileManager.default.fileExists(atPath: destinationURL.path) {
            let newName = "\(baseName)_\(counter).\(ext)"
            destinationURL = downloadsDirectory.appendingPathComponent(newName)
            counter += 1
        }
        completionHandler(destinationURL)
    }

    func downloadDidFinish(_ download: WKDownload) {
        let downloadsDirectory = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first!
        let fileURL = downloadsDirectory.appendingPathComponent("ClearSight_Agency_Banner_Book.xlsx")
        if FileManager.default.fileExists(atPath: fileURL.path) {
            NSWorkspace.shared.activateFileViewerSelecting([fileURL])
        }
    }

    // MARK: - Native WebKit Open Panel (File Picker) Handling (CS-101 / CS-103)
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let openPanel = NSOpenPanel()
        openPanel.canChooseFiles = true
        openPanel.canChooseDirectories = false
        openPanel.allowsMultipleSelection = parameters.allowsMultipleSelection
        openPanel.allowedFileTypes = ["json", "xlsx", "xls", "csv"]
        openPanel.beginSheetModal(for: self.window) { response in
            if response == .OK {
                completionHandler(openPanel.urls)
            } else {
                completionHandler(nil)
            }
        }
    }

    func setupMainMenu() {
        let mainMenu = NSMenu()

        // ClearSight Application Menu
        let appMenuItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "About ClearSight", action: nil, keyEquivalent: "")
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(withTitle: "Quit ClearSight", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appMenuItem.submenu = appMenu
        mainMenu.addItem(appMenuItem)

        // Edit Menu
        let editMenuItem = NSMenuItem()
        let editMenu = NSMenu(title: "Edit")
        editMenu.addItem(withTitle: "Undo", action: Selector(("undo:")), keyEquivalent: "z")
        editMenu.addItem(withTitle: "Redo", action: Selector(("redo:")), keyEquivalent: "Z")
        editMenu.addItem(NSMenuItem.separator())
        editMenu.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        editMenu.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editMenu.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        editMenu.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editMenuItem.submenu = editMenu
        mainMenu.addItem(editMenuItem)

        NSApp.mainMenu = mainMenu
    }

    func killServerProcess() {
        let envPid = ProcessInfo.processInfo.environment["CLEARSIGHT_SERVER_PID"]
        let filePid: String? = {
            if let dir = Bundle.main.resourcePath {
                let candidate = (dir as NSString).appendingPathComponent(".clearsight_server.pid")
                if let str = try? String(contentsOfFile: candidate, encoding: .utf8) {
                    return str.trimmingCharacters(in: .whitespacesAndNewlines)
                }
            }
            if let str = try? String(contentsOfFile: ".clearsight_server.pid", encoding: .utf8) {
                return str.trimmingCharacters(in: .whitespacesAndNewlines)
            }
            return nil
        }()

        if let pidStr = envPid ?? filePid, let pid = Int32(pidStr), pid > 1 {
            // Verify PID is running before sending SIGTERM (CS-101 / zero-orphan lifecycle)
            if kill(pid, 0) == 0 {
                kill(pid, SIGTERM)
            }
            try? FileManager.default.removeItem(atPath: ".clearsight_server.pid")
            try? FileManager.default.removeItem(atPath: ".clearsight_port")
        }
    }

    func windowWillClose(_ notification: Notification) {
        killServerProcess()
        NSApp.terminate(nil)
    }

    func applicationWillTerminate(_ notification: Notification) {
        killServerProcess()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
