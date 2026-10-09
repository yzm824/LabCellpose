import AppKit
import WebKit
import Darwin

// Saved results are external input. Check the opened descriptors, not a path
// that could resolve differently between validation and reading.
func readResultJSON(_ folder: URL, _ name: String) throws -> [String: Any]? {
    let unsafe = NSError(domain: "LabCellpose", code: 1, userInfo: [NSLocalizedDescriptionKey:
        "Result metadata must be a regular file, not a link, and no larger than 128 MiB."])
    let root = open(folder.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW)
    guard root >= 0 else { throw unsafe }
    defer { close(root) }
    let fd = openat(root, name, O_RDONLY | O_NOFOLLOW | O_NONBLOCK)
    guard fd >= 0 else { throw unsafe }
    let handle = FileHandle(fileDescriptor: fd, closeOnDealloc: true)
    defer { try? handle.close() }
    var info = stat()
    let limit = 128 << 20
    guard fstat(fd, &info) == 0, (info.st_mode & S_IFMT) == S_IFREG,
          info.st_size >= 0, info.st_size <= limit else { throw unsafe }
    var data = Data()
    while data.count <= limit {
        guard let chunk = try handle.read(upToCount: min(1 << 20, limit + 1 - data.count)), !chunk.isEmpty else { break }
        data.append(chunk)
    }
    guard data.count <= limit else { throw unsafe }
    return try JSONSerialization.jsonObject(with: data) as? [String: Any]
}
import UniformTypeIdentifiers

/// Splits backend output into lines. Each byte is searched once; v1.3 rescanned the whole buffer for every
/// pipe chunk, which blocked the main thread for minutes on very large single-line events.
struct LineBuffer {
    private var data = Data()
    private var scanned = 0
    mutating func append(_ chunk: Data) -> [Data] {
        data.append(chunk)
        var lines: [Data] = []
        var start = 0
        var from = scanned
        while let newline = data.withUnsafeBytes({ (raw: UnsafeRawBufferPointer) -> Int? in
            guard from < raw.count, let base = raw.baseAddress, let hit = memchr(base + from, 10, raw.count - from) else { return nil }
            return base.distance(to: UnsafeRawPointer(hit))
        }) {
            lines.append(data.subdata(in: (data.startIndex + start)..<(data.startIndex + newline)))
            start = newline + 1; from = start
        }
        if start > 0 { data.removeSubrange(data.startIndex..<(data.startIndex + start)) }
        scanned = data.count
        return lines
    }
    mutating func reset() { data = Data(); scanned = 0 }
}

/// A backend task is finished only when it has exited AND its output has been read to the end,
/// so the final events always reach the page before 'idle'.
final class TaskEnd {
    var outputClosed = false
    var exitCode: Int32?
    var reported = false
}

/// Route trackpad magnification into image-space navigation, not whole-page zoom.
final class ResultWebView: WKWebView {
    override func magnify(with event: NSEvent) {
        let point = convert(event.locationInWindow, from: nil)
        let y = isFlipped ? point.y : bounds.height - point.y
        let factor = max(0.05, 1 + event.magnification)
        evaluateJavaScript("window.labNativeMagnify?.(\(factor), \(point.x), \(y))", completionHandler: nil)
    }
}

final class GlassToolbar: NSView {
    private let stack: NSStackView
    private var surface: NSView?
    init(views: [NSView]) {
        stack = NSStackView(views: views); stack.spacing = 12
        super.init(frame: .zero)
        NSWorkspace.shared.notificationCenter.addObserver(self, selector: #selector(rebuild), name: NSWorkspace.accessibilityDisplayOptionsDidChangeNotification, object: nil)
        rebuild()
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
    override var intrinsicContentSize: NSSize { NSSize(width: stack.fittingSize.width + 28, height: 48) }
    deinit { NSWorkspace.shared.notificationCenter.removeObserver(self) }
    @objc private func rebuild() {
        stack.removeFromSuperview(); surface?.removeFromSuperview()
        let holder = NSView(); holder.addSubview(stack)
        stack.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: holder.leadingAnchor, constant: 14),
            stack.trailingAnchor.constraint(equalTo: holder.trailingAnchor, constant: -14),
            stack.topAnchor.constraint(equalTo: holder.topAnchor, constant: 10),
            stack.bottomAnchor.constraint(equalTo: holder.bottomAnchor, constant: -10)
        ])
        let backdrop: NSView
        if #available(macOS 26.0, *), !NSWorkspace.shared.accessibilityDisplayShouldReduceTransparency {
            let glass = NSGlassEffectView(); glass.style = .regular; glass.cornerRadius = 22
            if #available(macOS 27.0, *) { glass.effectIsInteractive = true }
            glass.contentView = holder; backdrop = glass
        } else {
            let plain = NSView(); plain.wantsLayer = true
            plain.layer?.backgroundColor = NSColor.windowBackgroundColor.cgColor
            plain.layer?.cornerRadius = 18
            plain.addSubview(holder); holder.translatesAutoresizingMaskIntoConstraints = false
            NSLayoutConstraint.activate([holder.leadingAnchor.constraint(equalTo: plain.leadingAnchor), holder.trailingAnchor.constraint(equalTo: plain.trailingAnchor), holder.topAnchor.constraint(equalTo: plain.topAnchor), holder.bottomAnchor.constraint(equalTo: plain.bottomAnchor)])
            backdrop = plain
        }
        addSubview(backdrop); backdrop.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([backdrop.leadingAnchor.constraint(equalTo: leadingAnchor), backdrop.trailingAnchor.constraint(equalTo: trailingAnchor), backdrop.topAnchor.constraint(equalTo: topAnchor), backdrop.bottomAnchor.constraint(equalTo: bottomAnchor)])
        surface = backdrop
    }
}

final class Application: NSObject, NSApplicationDelegate, WKScriptMessageHandler, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate, NSWindowDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var resultWindow: NSWindow?
    var resultWeb: WKWebView?
    var displayedResultFolder: String?
    var downloads: [ObjectIdentifier: (download: WKDownload, destination: URL, temporary: URL)] = [:]
    var worker: Process?
    var viewer: Process?
    var viewerURL: URL?
    var viewerFolder: String?
    var lastResult: String?
    var lastWorkspace: String?
    var workerLines = LineBuffer()
    var viewerLines = LineBuffer()
    var viewerUsesFallbackPort = false
    var taskName = ""
    var cancelled = false
    var session: URL!
    let resources = Bundle.main.resourceURL!
    var payload: URL { resources.appendingPathComponent("payload") }

    func applicationDidFinishLaunching(_ notification: Notification) {
        do {
            session = FileManager.default.temporaryDirectory.appendingPathComponent("LabCellpose-" + UUID().uuidString)
            try FileManager.default.createDirectory(at: session, withIntermediateDirectories: true)
        } catch { alert("Unable to create a working folder", error.localizedDescription); NSApp.terminate(nil); return }
        let controller = WKUserContentController()
        controller.add(self, name: "lab")
        let config = WKWebViewConfiguration()
        config.userContentController = controller
        web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = self
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1140, height: 830),
            styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "LabCellpose"
        window.titlebarAppearsTransparent = true
        window.appearance = NSAppearance(named: .aqua)
        window.isReleasedWhenClosed = false
        window.minSize = NSSize(width: 850, height: 620)
        window.contentView = web
        window.delegate = self
        window.center()
        window.makeKeyAndOrderFront(nil)
        let menu = NSMenu()
        let applicationMenu = NSMenuItem()
        menu.addItem(applicationMenu)
        let items = NSMenu()
        items.addItem(withTitle: "About LabCellpose", action: #selector(about), keyEquivalent: "")
        items.addItem(.separator())
        items.addItem(withTitle: "Quit LabCellpose", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        applicationMenu.submenu = items
        let edit = NSMenuItem(title: "Edit", action: nil, keyEquivalent: "")
        let editing = NSMenu(title: "Edit")
        editing.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editing.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        editing.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        edit.submenu = editing; menu.addItem(edit); NSApp.mainMenu = menu
        web.loadFileURL(resources.appendingPathComponent("interface.html"), allowingReadAccessTo: resources)
        NSWorkspace.shared.notificationCenter.addObserver(self, selector: #selector(updateAccessibilityAppearance), name: NSWorkspace.accessibilityDisplayOptionsDidChangeNotification, object: nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc func about() {
        alert("LabCellpose 1.4", "Developed by Zhenmo Yu\nCell segmentation and quantitative fluorescence analysis.\nCellpose 4.2.1.1 · cpsam_v2\nLocal processing; no external AI service required.\nFor research use. Review segmentation and background before interpretation.")
    }

    func alert(_ title: String, _ message: String) {
        let box = NSAlert(); box.messageText = title; box.informativeText = message; box.runModal()
    }

    func send(_ values: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: values, options: [.fragmentsAllowed]),
              let json = String(data: data, encoding: .utf8) else { return }
        web.evaluateJavaScript("window.receiveNative(\(json))", completionHandler: nil)
    }

    func choose(_ role: String) {
        let panel = NSOpenPanel()
        // macOS 27 updates file/directory flags when allowedContentTypes changes.
        panel.allowedContentTypes = role == "preset" ? [.json] : []
        panel.canChooseDirectories = role != "preset"
        panel.canChooseFiles = role == "input" || role == "preset"
        panel.allowsMultipleSelection = false
        panel.prompt = role == "output" ? "Save results here" : "Choose"
        panel.title = role == "input" ? "Choose a TIFF, ZIP, or image folder" : (role == "output" ? "Choose a result folder" : (role == "result" ? "Open a saved LabCellpose result folder" : "Load analysis preset"))
        panel.beginSheetModal(for: window) { [weak self] response in
          guard let self = self else { return }
          if response == .OK, let url = panel.url {
            if role == "result" {
                do {
                    var folder = url
                    if !FileManager.default.fileExists(atPath: folder.appendingPathComponent("index.html").path) { folder = url.appendingPathComponent("results") }
                    let manifest = try readResultJSON(folder, "run_manifest.json")
                    let checks = try readResultJSON(folder, "validation.json")
                    guard manifest?["status"] as? String == "complete", checks?["passed"] as? Bool == true,
                          FileManager.default.fileExists(atPath: folder.appendingPathComponent("index.html").path) else { throw NSError(domain: "This folder is not a completed LabCellpose run", code: 1) }
                    lastResult = folder.path; lastWorkspace = folder.deletingLastPathComponent().path
                    send(["event": "finished", "result": folder.path, "objects": checks?["objects"] ?? 0, "rows": checks?["measurement_rows"] ?? 0])
                    showResults(folder.path)
                } catch { send(["event": "error", "message": "Cannot open this result folder: " + error.localizedDescription]) }
            } else if role == "preset" {
                do {
                    let data = try Data(contentsOf: url)
                    guard data.count < 1_000_000,
                          let value = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                          value["appPresetVersion"] as? Int == 1 else { throw NSError(domain: "Invalid settings file", code: 1) }
                    send(["event": "preset", "value": value])
                } catch { send(["event": "error", "message": "Cannot load settings: \(error.localizedDescription)"]) }
            } else {
                send(["event": "chosen", "role": role, "path": url.path])
                if role == "output" { UserDefaults.standard.set(url.path, forKey: "outputFolder") }
            }
          }
        }
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.frameInfo.isMainFrame, message.webView === web,
              message.frameInfo.request.url?.standardizedFileURL == resources.appendingPathComponent("interface.html").standardizedFileURL,
              let body = message.body as? [String: Any], let action = body["action"] as? String else { return }
        switch action {
        case "ready":
            send(["event": "ready", "output": UserDefaults.standard.string(forKey: "outputFolder") ?? ""])
        case "choose":
            if worker == nil, let role = body["role"] as? String, ["input", "output", "preset", "result"].contains(role) { choose(role) }
        case "inspect":
            guard let input = body["input"] as? String else { return }
            let inventory = session.appendingPathComponent("inventory-" + UUID().uuidString + ".json")
            start(["action": "inspect", "input": input, "inventory": inventory.path])
        case "preview":
            if let inventory = body["inventory"] as? String, let index = body["index"] as? Int {
                start(["action": "preview", "inventory": inventory, "index": index])
            }
        case "run":
            if var request = body["request"] as? [String: Any] { request["action"] = "run"; start(request) }
        case "cancel":
            if let process = worker, process.isRunning {
                cancelled = true; process.interrupt()
                send(["event": "log", "message": "Stopping analysis; partial results will be kept."])
                DispatchQueue.main.asyncAfter(deadline: .now() + 6) { [weak self, weak process] in
                    if let p = process, self?.worker === p, p.isRunning { p.terminate() }
                }
            }
        case "openResult":
            if let folder = lastResult { showResults(folder) }
        case "openFolder":
            if let folder = lastWorkspace { NSWorkspace.shared.open(URL(fileURLWithPath: folder)) }
        case "savePreset":
            if let preset = body["value"] as? [String: Any] {
                let panel = NSSavePanel(); panel.nameFieldStringValue = "LabCellpose-preset.json"
                panel.beginSheetModal(for: window) { [weak self] response in
                  guard let self = self else { return }
                  if response == .OK, let url = panel.url {
                    do { try JSONSerialization.data(withJSONObject: preset, options: [.prettyPrinted, .sortedKeys]).write(to: url, options: .atomic)
                        send(["event": "log", "message": "Settings saved to " + url.path])
                    } catch { send(["event": "error", "message": error.localizedDescription]) }
                  }
                }
            }
        default: break
        }
    }

    func python(_ arguments: [String]) -> Process {
        let process = Process()
        process.executableURL = payload.appendingPathComponent("runtime/bin/python3.12")
        process.arguments = ["-I", "-B", "-X", "utf8", "-u"] + arguments
        process.currentDirectoryURL = session
        var env = ProcessInfo.processInfo.environment
        for key in Array(env.keys) where key.hasPrefix("PYTHON") || key.hasPrefix("DYLD_") { env.removeValue(forKey: key) }
        env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
        env["HF_HUB_OFFLINE"] = "1"; env["MPLBACKEND"] = "Agg"
        env["MPLCONFIGDIR"] = session.appendingPathComponent("matplotlib").path
        env["CELLPOSE_LOCAL_MODELS_PATH"] = payload.appendingPathComponent("models").path
        process.environment = env
        return process
    }

    func start(_ request: [String: Any]) {
        guard worker == nil else { send(["event": "error", "message": "A task is already running."]); return }
        taskName = request["action"] as? String ?? "task"
        do {
            let file = session.appendingPathComponent("request-" + UUID().uuidString + ".json")
            try JSONSerialization.data(withJSONObject: request).write(to: file, options: .atomic)
            let process = python([resources.appendingPathComponent("desktop_backend.py").path, "--payload", payload.path, "--request", file.path])
            let output = Pipe(); process.standardOutput = output; process.standardError = output
            workerLines.reset(); worker = process; cancelled = false
            let end = TaskEnd()
            output.fileHandleForReading.readabilityHandler = { [weak self] handle in
                let data = handle.availableData
                if data.isEmpty {
                    handle.readabilityHandler = nil
                    DispatchQueue.main.async { end.outputClosed = true; self?.finish(process, end) }
                    return
                }
                DispatchQueue.main.async { self?.consume(data, viewer: false) }
            }
            process.terminationHandler = { [weak self] process in
                DispatchQueue.main.async {
                    end.exitCode = process.terminationStatus; self?.finish(process, end)
                    // Output normally closes at exit; do not wait forever if a descendant kept the pipe open.
                    DispatchQueue.main.asyncAfter(deadline: .now() + 2) { end.outputClosed = true; self?.finish(process, end) }
                }
            }
            try process.run()
            send(["event": "busy", "task": taskName])
        } catch {
            worker = nil; send(["event": "error", "message": "Could not start the bundled runtime: " + error.localizedDescription])
            send(["event": "idle", "task": taskName, "code": -1, "cancelled": false])
        }
    }

    func finish(_ process: Process, _ end: TaskEnd) {
        guard end.outputClosed, let code = end.exitCode, !end.reported else { return }
        end.reported = true
        if worker === process { worker = nil }
        send(["event": "idle", "task": taskName, "code": code, "cancelled": cancelled])
    }

    func consume(_ data: Data, viewer isViewer: Bool) {
        let lines = isViewer ? viewerLines.append(data) : workerLines.append(data)
        for line in lines {
            guard let value = try? JSONSerialization.jsonObject(with: line) as? [String: Any] else {
                if !isViewer, let text = String(data: line, encoding: .utf8), !text.isEmpty { send(["event": "log", "message": text]) }
                continue
            }
            if isViewer {
                if let address = value["viewer"] as? String, let url = URL(string: address) {
                    viewerURL = url
                    // Remember only the preferred port; a temporary fallback must not move later sessions.
                    if !viewerUsesFallbackPort { UserDefaults.standard.set(url.port ?? 8765, forKey: "viewerPort") }
                    presentResults(url); send(["event": "viewer", "url": address])
                }
            } else {
                if value["event"] as? String == "workspace" { lastWorkspace = value["path"] as? String }
                if value["event"] as? String == "finished", let result = value["result"] as? String { lastResult = result }
                send(value["event"] == nil ? ["event": "log", "message": String(data: line, encoding: .utf8) ?? ""] : value)
                if value["event"] as? String == "finished", let result = lastResult { showResults(result) }
            }
        }
    }

    func showResults(_ folder: String, useRandomPort: Bool = false) {
        if resultWindow?.attachedSheet != nil {
            resultWindow?.makeKeyAndOrderFront(nil)
            send(["event": "error", "message": "Finish the current result save/import dialog, then open the results again."])
            return
        }
        if viewerFolder == folder, let url = viewerURL, viewer?.isRunning == true { presentResults(url); return }
        resultWeb?.stopLoading()
        displayedResultFolder = nil
        if viewer?.isRunning == true { viewer?.terminate() }
        viewerURL = nil; viewerFolder = folder; viewerLines.reset(); viewerUsesFallbackPort = useRandomPort
        let stored = UserDefaults.standard.integer(forKey: "viewerPort")
        let port = useRandomPort ? 0 : (stored > 0 ? stored : 8765)
        let process = python([payload.appendingPathComponent("app/launcher.py").path, "view", "--run", folder, "--port", String(port), "--no-open"])
        let output = Pipe(); process.standardOutput = output; process.standardError = output
        output.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if data.isEmpty { handle.readabilityHandler = nil; return }
            DispatchQueue.main.async {
                guard let self = self, self.viewer === process else { return }
                self.consume(data, viewer: true)
            }
        }
        process.terminationHandler = { [weak self] process in
            DispatchQueue.main.async {
                guard let self = self, self.viewer === process else { return }
                if process.terminationStatus != 0 && self.viewerURL == nil {
                    if !useRandomPort { self.showResults(folder, useRandomPort: true) }
                    else { self.send(["event": "error", "message": "Results were saved, but their local viewer could not start. Open the result folder to inspect the output."]) }
                }
            }
        }
        viewer = process
        do { try process.run() } catch { send(["event": "error", "message": error.localizedDescription]) }
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if webView === resultWeb {
            let url = navigationAction.request.url
            if navigationAction.shouldPerformDownload {
                decisionHandler(isResultResource(url) ? .download : .cancel)
            } else if isResultOrigin(url) || (navigationAction.targetFrame?.isMainFrame == false && url?.scheme == "about") {
                decisionHandler(.allow)
            } else { decisionHandler(.cancel) }
            return
        }
        let expected = resources.appendingPathComponent("interface.html").standardizedFileURL
        decisionHandler(navigationAction.request.url?.standardizedFileURL == expected ? .allow : .cancel)
    }

    func isResultOrigin(_ url: URL?) -> Bool {
        guard let url = url, let origin = viewerURL else { return false }
        return url.scheme == "http" && url.host == "127.0.0.1" && url.port == origin.port
    }

    func isResultResource(_ url: URL?) -> Bool {
        guard let url = url else { return false }
        if isResultOrigin(url) { return true }
        return url.scheme == "blob" && isResultOrigin(URL(string: String(url.absoluteString.dropFirst(5))))
    }

    func presentResults(_ url: URL) {
        guard isResultOrigin(url) else { return }
        if resultWindow == nil {
            // The report has no native script bridge. Keep the existing sandboxed iframe.
            let config = WKWebViewConfiguration()
            let report = ResultWebView(frame: .zero, configuration: config)
            report.allowsMagnification = false
            report.navigationDelegate = self; report.uiDelegate = self
            let reportWindow = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1250, height: 900),
                styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
            reportWindow.title = "LabCellpose — Analysis Results"
            reportWindow.titlebarAppearsTransparent = true
            reportWindow.appearance = NSAppearance(named: .aqua)
            reportWindow.minSize = NSSize(width: 850, height: 620)
            reportWindow.isReleasedWhenClosed = false
            let setup = NSButton(title: "Analysis setup", target: self, action: #selector(showSetup))
            let folder = NSButton(title: "Show result folder", target: self, action: #selector(showResultFiles))
            setup.image = NSImage(systemSymbolName: "slider.horizontal.3", accessibilityDescription: nil); setup.imagePosition = .imageLeading
            folder.image = NSImage(systemSymbolName: "folder", accessibilityDescription: nil); folder.imagePosition = .imageLeading
            let label = NSTextField(labelWithString: "Local analysis · Original-pixel measurements")
            label.textColor = .secondaryLabelColor; label.font = .systemFont(ofSize: 12)
            let bar = GlassToolbar(views: [setup, folder])
            let content = NSVisualEffectView(); content.material = .underWindowBackground
            content.blendingMode = .behindWindow; content.state = .active
            reportWindow.contentView = content
            content.addSubview(bar); content.addSubview(label); content.addSubview(report)
            bar.translatesAutoresizingMaskIntoConstraints = false; label.translatesAutoresizingMaskIntoConstraints = false; report.translatesAutoresizingMaskIntoConstraints = false
            NSLayoutConstraint.activate([
                bar.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 18),
                bar.topAnchor.constraint(equalTo: content.topAnchor, constant: 8),
                bar.trailingAnchor.constraint(lessThanOrEqualTo: content.trailingAnchor, constant: -18),
                bar.heightAnchor.constraint(equalToConstant: 48),
                label.leadingAnchor.constraint(equalTo: bar.trailingAnchor, constant: 18),
                label.centerYAnchor.constraint(equalTo: bar.centerYAnchor),
                label.trailingAnchor.constraint(lessThanOrEqualTo: content.trailingAnchor, constant: -18),
                report.topAnchor.constraint(equalTo: bar.bottomAnchor, constant: 10),
                report.leadingAnchor.constraint(equalTo: content.leadingAnchor),
                report.trailingAnchor.constraint(equalTo: content.trailingAnchor),
                report.bottomAnchor.constraint(equalTo: content.bottomAnchor)
            ])
            resultWeb = report; resultWindow = reportWindow; reportWindow.center()
        }
        if resultWeb?.url != url || displayedResultFolder != viewerFolder {
            resultWeb?.load(URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData))
            displayedResultFolder = nil
        }
        resultWindow?.subtitle = URL(fileURLWithPath: viewerFolder ?? "").deletingLastPathComponent().lastPathComponent
        resultWindow?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc func showSetup() { window.makeKeyAndOrderFront(nil) }
    @objc func showResultFiles() {
        if let folder = viewerFolder { NSWorkspace.shared.open(URL(fileURLWithPath: folder)) }
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        if webView === resultWeb && !navigationResponse.canShowMIMEType {
            decisionHandler(isResultResource(navigationResponse.response.url) ? .download : .cancel)
        } else { decisionHandler(.allow) }
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) { download.delegate = self }
    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) { download.delegate = self }

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        guard isResultResource(response.url), let reportWindow = resultWindow else { completionHandler(nil); return }
        let panel = NSSavePanel()
        panel.title = "Save analysis export"
        panel.nameFieldStringValue = URL(fileURLWithPath: suggestedFilename).lastPathComponent
        panel.beginSheetModal(for: reportWindow) { [weak self] answer in
            guard let self = self, answer == .OK, let destination = panel.url else { completionHandler(nil); return }
            // WebKit requires a new file. Stage first, then atomically save to the user's chosen destination.
            let temporary = self.session.appendingPathComponent("export-" + UUID().uuidString)
            self.downloads[ObjectIdentifier(download)] = (download, destination, temporary)
            completionHandler(temporary)
        }
    }

    func downloadDidFinish(_ download: WKDownload) {
        guard let item = downloads.removeValue(forKey: ObjectIdentifier(download)) else { return }
        do {
            try Data(contentsOf: item.temporary).write(to: item.destination, options: .atomic)
            try? FileManager.default.removeItem(at: item.temporary)
            send(["event": "log", "message": "Export saved to " + item.destination.path])
        } catch { alert("Unable to save export", error.localizedDescription) }
    }

    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        if let item = downloads.removeValue(forKey: ObjectIdentifier(download)) { try? FileManager.default.removeItem(at: item.temporary) }
        if (error as NSError).code != NSURLErrorCancelled { alert("Export failed", error.localizedDescription) }
    }

    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        guard webView === resultWeb, frame.isMainFrame, isResultOrigin(frame.request.url), let reportWindow = resultWindow else { completionHandler(nil); return }
        let panel = NSOpenPanel(); panel.title = "Load QC decisions"
        panel.allowedContentTypes = [.json]; panel.canChooseFiles = true
        panel.canChooseDirectories = false; panel.allowsMultipleSelection = false
        panel.beginSheetModal(for: reportWindow) { answer in completionHandler(answer == .OK ? panel.urls : nil) }
    }

    @objc func updateAccessibilityAppearance() {
        let reduced = NSWorkspace.shared.accessibilityDisplayShouldReduceTransparency ? "true" : "false"
        web?.evaluateJavaScript("document.documentElement.dataset.reduceTransparency = '\(reduced)'", completionHandler: nil)
        resultWeb?.evaluateJavaScript("window.labSetAppearance?.({reduceTransparency:\(reduced)})", completionHandler: nil)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        if webView === resultWeb && webView.url == viewerURL { displayedResultFolder = viewerFolder }
        updateAccessibilityAppearance()
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        reportNavigationFailure(webView, error: error)
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        reportNavigationFailure(webView, error: error)
    }

    func reportNavigationFailure(_ webView: WKWebView, error: Error) {
        if webView === resultWeb && (error as NSError).code != NSURLErrorCancelled {
            displayedResultFolder = nil
            send(["event": "error", "message": "The result window could not load. Open saved results to retry. " + error.localizedDescription])
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if !downloads.isEmpty {
            alert("Export in progress", "Wait for the current file export to finish before quitting.")
            return .terminateCancel
        }
        if worker?.isRunning == true {
            let box = NSAlert(); box.messageText = "Stop the current task and quit?"
            box.informativeText = "Partial output will be kept. Run again into a new folder when ready."
            box.addButton(withTitle: "Keep running"); box.addButton(withTitle: "Stop and quit")
            if box.runModal() == .alertFirstButtonReturn { return .terminateCancel }
            worker?.interrupt()
            if worker?.isRunning == true { worker?.terminate() }
        }
        if viewer?.isRunning == true { viewer?.terminate() }
        return .terminateNow
    }
}

let application = NSApplication.shared
let delegate = Application()
application.delegate = delegate
application.setActivationPolicy(.regular)
application.run()
