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

/// The setup and review views. Trackpad magnification zooms the image under the pointer instead of the whole page,
/// and a file or folder dropped on the setup view becomes the images to analyse.
final class StageWebView: WKWebView {
    var onDrop: ((URL) -> Void)?
    override func magnify(with event: NSEvent) {
        let point = convert(event.locationInWindow, from: nil)
        let y = isFlipped ? point.y : bounds.height - point.y
        let factor = max(0.05, 1 + event.magnification)
        evaluateJavaScript("window.labNativeMagnify?.(\(factor), \(point.x), \(y))", completionHandler: nil)
    }
    private func droppedFile(_ sender: NSDraggingInfo) -> URL? {
        guard onDrop != nil else { return nil }
        let urls = sender.draggingPasteboard.readObjects(forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true]) as? [URL]
        return urls?.count == 1 ? urls?.first : nil
    }
    override func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation { droppedFile(sender) != nil ? .copy : [] }
    override func draggingUpdated(_ sender: NSDraggingInfo) -> NSDragOperation { droppedFile(sender) != nil ? .copy : [] }
    override func prepareForDragOperation(_ sender: NSDraggingInfo) -> Bool { droppedFile(sender) != nil }
    override func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
        guard let url = droppedFile(sender) else { return false }
        onDrop?(url); return true
    }
}

final class Application: NSObject, NSApplicationDelegate, NSMenuItemValidation, WKScriptMessageHandler, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate, NSWindowDelegate {
    var window: NSWindow!
    var content: NSView!
    var web: StageWebView!          // Set up
    var resultWeb: StageWebView?    // Review and Export; created when results are first shown
    var displayedResultFolder: String?
    var pendingStep: String?        // the step to show once the review page has loaded
    var revealWhenReady = false     // the review view replaces the setup view once its page has drawn itself
    var swapToken = 0
    var pendingOpen: URL?           // a file opened with the app before the setup page was ready
    var setupReady = false
    var downloads: [ObjectIdentifier: (download: WKDownload, destination: URL, temporary: URL)] = [:]
    var worker: Process?
    var viewer: Process?
    // Trial segmentations: one process that keeps the model loaded between tests of the setup page.
    var tester: Process?
    var testerInput: FileHandle?
    var testerLines = LineBuffer()
    var trialsPending = 0
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
        signal(SIGPIPE, SIG_IGN)   // writing to a trial process that has just exited must fail, not end the app
        do {
            session = FileManager.default.temporaryDirectory.appendingPathComponent("LabCellpose-" + UUID().uuidString)
            try FileManager.default.createDirectory(at: session, withIntermediateDirectories: true)
        } catch { alert("Unable to create a working folder", error.localizedDescription); NSApp.terminate(nil); return }
        let controller = WKUserContentController()
        controller.add(self, name: "lab")
        let config = WKWebViewConfiguration()
        config.userContentController = controller
        web = StageWebView(frame: .zero, configuration: config)
        web.allowsMagnification = false
        web.navigationDelegate = self
        web.underPageBackgroundColor = chrome
        web.onDrop = { [weak self] url in self?.open(url) }
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1380, height: 880),
            styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "LabCellpose"
        // One dark surface from the title bar down: the bar of each page continues the title bar's colour.
        window.titlebarAppearsTransparent = true
        window.appearance = NSAppearance(named: .darkAqua)
        window.backgroundColor = chrome
        window.isReleasedWhenClosed = false
        window.minSize = NSSize(width: 1040, height: 680)
        content = NSView()
        content.wantsLayer = true
        window.contentView = content
        pin(web)
        window.delegate = self
        if !window.setFrameUsingName("LabCellposeMain") { window.center() }
        window.setFrameAutosaveName("LabCellposeMain")
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
        edit.submenu = editing; menu.addItem(edit)
        let view = NSMenuItem(title: "View", action: nil, keyEquivalent: "")
        let steps = NSMenu(title: "View")
        steps.addItem(withTitle: "Set Up", action: #selector(showSetup), keyEquivalent: "1")
        steps.addItem(withTitle: "Review", action: #selector(menuReview), keyEquivalent: "2")
        steps.addItem(withTitle: "Export", action: #selector(menuExport), keyEquivalent: "3")
        view.submenu = steps; menu.addItem(view); NSApp.mainMenu = menu
        web.loadFileURL(resources.appendingPathComponent("interface.html"), allowingReadAccessTo: resources)
        NSWorkspace.shared.notificationCenter.addObserver(self, selector: #selector(updateAccessibilityAppearance), name: NSWorkspace.accessibilityDisplayOptionsDidChangeNotification, object: nil)
        activate()
#if SELFTEST
        window.alphaValue = 0; window.ignoresMouseEvents = true   // the scripted check never shows a window or takes the focus
        runSelfTest()
#endif
    }

    func activate() {
#if !SELFTEST
        NSApp.activate(ignoringOtherApps: true)
#endif
    }

    /// The colour of the bars and panels in the pages (--panel in ui.css).
    let chrome = NSColor(srgbRed: 0x16 / 255.0, green: 0x19 / 255.0, blue: 0x1E / 255.0, alpha: 1)

    /// Both views fill the window; only one is visible at a time.
    func pin(_ view: NSView) {
        content.addSubview(view); view.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([view.topAnchor.constraint(equalTo: content.topAnchor), view.bottomAnchor.constraint(equalTo: content.bottomAnchor),
            view.leadingAnchor.constraint(equalTo: content.leadingAnchor), view.trailingAnchor.constraint(equalTo: content.trailingAnchor)])
    }

    func validateMenuItem(_ item: NSMenuItem) -> Bool {
        if item.action == #selector(menuReview) || item.action == #selector(menuExport) { return lastResult != nil && worker == nil }
        return true
    }

    @objc func menuReview() { if let folder = lastResult { pendingStep = "review"; showResults(folder) } }
    @objc func menuExport() { if let folder = lastResult { pendingStep = "export"; showResults(folder) } }

    /// A file or folder dropped on the window or opened with the app: saved results open for review, anything else is image input.
    func open(_ url: URL) {
        guard setupReady else { pendingOpen = url; return }
        guard worker == nil else { send(["event": "error", "message": "Wait for the current task to finish, then open the files again."]); return }
        var isFolder: ObjCBool = false
        guard FileManager.default.fileExists(atPath: url.path, isDirectory: &isFolder) else { return }
        let results = url.appendingPathComponent("results")
        if isFolder.boolValue, [url, results].contains(where: { FileManager.default.fileExists(atPath: $0.appendingPathComponent("run_manifest.json").path) }) { openResults(url) }
        else { showSetup(); send(["event": "chosen", "role": "input", "path": url.path]) }
    }

    func application(_ application: NSApplication, open urls: [URL]) { if let url = urls.first { open(url) } }

    @objc func about() {
        alert("LabCellpose \(appVersion)", "Developed by Zhenmo Yu\nCell segmentation and quantitative fluorescence analysis.\nCellpose 4.2.1.1 · cpsam_v2\nLocal processing; no external AI service required.\nFor research use. Review segmentation and background before interpretation.")
    }

    var appVersion: String { Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "" }

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
                openResults(url)
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

    /// Open a completed run (its folder or the results folder inside it) for review.
    func openResults(_ url: URL) {
        do {
            var folder = url
            if !FileManager.default.fileExists(atPath: folder.appendingPathComponent("index.html").path) { folder = url.appendingPathComponent("results") }
            let manifest = try readResultJSON(folder, "run_manifest.json")
            let checks = try readResultJSON(folder, "validation.json")
            guard manifest?["status"] as? String == "complete", checks?["passed"] as? Bool == true,
                  FileManager.default.fileExists(atPath: folder.appendingPathComponent("index.html").path) else { throw NSError(domain: "This folder is not a completed LabCellpose run", code: 1) }
            lastResult = folder.path; lastWorkspace = folder.deletingLastPathComponent().path
            send(["event": "finished", "result": folder.path, "objects": checks?["objects"] ?? 0, "rows": checks?["measurement_rows"] ?? 0, "opened": true])
            remember(result: folder.path)
            showResults(folder.path)
        } catch { send(["event": "error", "message": "Cannot open this result folder: " + error.localizedDescription]) }
    }

    /// Recent analyses for the start page: title, size and date of completed runs that still exist.
    var recents: [[String: Any]] {
        let stored = UserDefaults.standard.array(forKey: "recentResults") as? [[String: Any]] ?? []
        return stored.filter { entry in
            guard let path = entry["path"] as? String else { return false }
            return FileManager.default.fileExists(atPath: URL(fileURLWithPath: path).appendingPathComponent("index.html").path)
        }
    }

    func remember(result path: String) {
        let folder = URL(fileURLWithPath: path)
        var entry: [String: Any] = ["path": path, "date": ISO8601DateFormatter().string(from: Date())]
        if let config = try? readResultJSON(folder, "config.json") {
            entry["title"] = config["title"] as? String ?? ""
            entry["images"] = (config["fields"] as? [Any])?.count ?? 0
        }
        if let checks = try? readResultJSON(folder, "validation.json"), let objects = checks["objects"] as? Int { entry["objects"] = objects }
        let list = [entry] + recents.filter { $0["path"] as? String != path }
        UserDefaults.standard.set(Array(list.prefix(12)), forKey: "recentResults")
        send(["event": "recents", "recents": recents])
    }

    /// Settings last used for each acquisition protocol (channel count and names), offered again for matching images.
    var setupMemory: [String: Any] {
        var memory: [String: Any] = [:]
        for item in UserDefaults.standard.array(forKey: "setupMemory") as? [[String: Any]] ?? [] {
            if let signature = item["signature"] as? String, let value = item["value"] as? [String: Any] { memory[signature] = value }
        }
        return memory
    }

    func rememberSetup(_ signature: String, _ value: [String: Any]) {
        guard signature.count <= 2000, value["appPresetVersion"] as? Int == 1,
              let data = try? JSONSerialization.data(withJSONObject: value), data.count < 200_000 else { return }
        let stored = UserDefaults.standard.array(forKey: "setupMemory") as? [[String: Any]] ?? []
        let list = [["signature": signature, "value": value]] + stored.filter { $0["signature"] as? String != signature }
        UserDefaults.standard.set(Array(list.prefix(20)), forKey: "setupMemory")
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.frameInfo.isMainFrame, let body = message.body as? [String: Any], let action = body["action"] as? String else { return }
        if message.name == "labReview" {
            // The review page can only switch back to the setup view, show its own result folder, or say that it has drawn itself.
            guard message.webView === resultWeb, isResultOrigin(message.frameInfo.request.url) else { return }
            if action == "showSetup" { showSetup() } else if action == "showFolder" { showResultFiles() } else if action == "ready" { applyPendingStep(); revealReview() }
            return
        }
        guard message.name == "lab", message.webView === web,
              message.frameInfo.request.url?.standardizedFileURL == resources.appendingPathComponent("interface.html").standardizedFileURL else { return }
        switch action {
        case "ready":
            setupReady = true
            send(["event": "ready", "output": UserDefaults.standard.string(forKey: "outputFolder") ?? "", "version": appVersion, "recents": recents, "memory": setupMemory])
            if let url = pendingOpen { pendingOpen = nil; open(url) }
        case "trial":
            if let request = body["request"] as? [String: Any] { trial(request) }
        case "remember":
            if let signature = body["signature"] as? String, let value = body["value"] as? [String: Any] { rememberSetup(signature, value) }
        case "openRecent":
            // Only a folder this app listed itself can be opened this way.
            if worker == nil, let path = body["path"] as? String, recents.contains(where: { $0["path"] as? String == path }) { openResults(URL(fileURLWithPath: path)) }
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
            if let folder = lastResult { pendingStep = body["step"] as? String == "export" ? "export" : "review"; showResults(folder) }
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
        if taskName == "run" { stopTester() }   // a run needs the memory the loaded trial model holds
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

    func trial(_ request: [String: Any]) {
        let token = request["token"] ?? NSNull()
        guard worker == nil else { send(["event": "trial_error", "token": token, "message": "Wait for the current task to finish."]); return }
        var body = request; body["action"] = "trial"
        guard let data = try? JSONSerialization.data(withJSONObject: body) else { return }
        if tester?.isRunning != true { startTester() }
        do {
            guard let input = testerInput else { throw NSError(domain: "The bundled runtime could not start", code: 1) }
            try input.write(contentsOf: data + Data([10])); trialsPending += 1
        } catch {
            stopTester(); send(["event": "trial_error", "token": token, "message": "The test could not start: " + error.localizedDescription])
        }
    }

    func startTester() {
        let process = python([resources.appendingPathComponent("desktop_backend.py").path, "--payload", payload.path, "--serve"])
        let input = Pipe(), output = Pipe()
        process.standardInput = input; process.standardOutput = output; process.standardError = FileHandle.nullDevice
        testerLines.reset(); trialsPending = 0
        output.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if data.isEmpty { handle.readabilityHandler = nil; return }
            DispatchQueue.main.async {
                guard let self = self, self.tester === process else { return }
                for line in self.testerLines.append(data) {
                    guard let value = try? JSONSerialization.jsonObject(with: line) as? [String: Any],
                          let event = value["event"] as? String, event == "trial" || event == "trial_error" else { continue }
                    self.trialsPending = max(0, self.trialsPending - 1); self.send(value)
                }
            }
        }
        process.terminationHandler = { [weak self] process in
            DispatchQueue.main.async {
                guard let self = self, self.tester === process else { return }
                // It exits by itself after a while without tests; only a test that was waiting needs to hear about it.
                let waiting = self.trialsPending > 0
                self.tester = nil; self.testerInput = nil; self.trialsPending = 0
                if waiting { self.send(["event": "trial_error", "message": "The test stopped unexpectedly. Try again."]) }
            }
        }
        do { try process.run(); tester = process; testerInput = input.fileHandleForWriting } catch { tester = nil; testerInput = nil }
    }

    func stopTester() {
        let process = tester
        tester = nil; testerInput = nil; trialsPending = 0
        if process?.isRunning == true { process?.terminate() }
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
                if value["event"] as? String == "finished", let result = lastResult { remember(result: result); pendingStep = "review"; showResults(result) }
            }
        }
    }

    func showResults(_ folder: String, useRandomPort: Bool = false) {
        if resultWeb?.isHidden == false, window.attachedSheet != nil {
            send(["event": "error", "message": "Finish the current save or load dialog, then open the results again."])
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
#if SELFTEST
            if let frame = navigationAction.targetFrame, !frame.isMainFrame { selfTestReportFrame = frame }
#endif
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
        if resultWeb == nil {
            // The report runs in a sandboxed frame; its host page gets a bridge with two harmless actions only.
            let controller = WKUserContentController()
            controller.add(self, name: "labReview")
            let config = WKWebViewConfiguration()
            config.userContentController = controller
            let report = StageWebView(frame: .zero, configuration: config)
            report.allowsMagnification = false
            report.navigationDelegate = self; report.uiDelegate = self
            report.underPageBackgroundColor = chrome
            report.isHidden = true
            pin(report); resultWeb = report
        }
        if resultWeb?.url != url || displayedResultFolder != viewerFolder {
            // The view that is showing stays until the new page says it is ready (or shortly after it has loaded),
            // so the window goes from one finished page to the next and never shows an empty one.
            resultWeb?.load(URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData))
            displayedResultFolder = nil
            revealWhenReady = true
        } else { applyPendingStep(); showReview() }
    }

    func revealReview() {
        guard revealWhenReady else { return }
        revealWhenReady = false
        showReview()
    }

    /// Show one of the two views with a short cross-fade. Their bars and panes are in the same places, so only the
    /// contents appear to change. The review view lies above the setup view: it fades in over it, or out to uncover it.
    func swap(to shown: NSView, from other: NSView?) {
        swapToken += 1
        let token = swapToken
        guard let other = other, other !== shown, !other.isHidden, !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion else {
            shown.alphaValue = 1; shown.isHidden = false
            if let other = other, other !== shown { other.isHidden = true; other.alphaValue = 1 }
            return
        }
        let fadingIn = shown === resultWeb
        if fadingIn && shown.isHidden { shown.alphaValue = 0 }
        shown.isHidden = false
        NSAnimationContext.runAnimationGroup({ context in
            context.duration = 0.16
            (fadingIn ? shown : other).animator().alphaValue = fadingIn ? 1 : 0
        }, completionHandler: { [weak self] in
            guard let self = self, token == self.swapToken else { return }
            other.isHidden = true; other.alphaValue = 1; shown.alphaValue = 1
        })
    }

    /// Review or Export, as asked for when the results were opened; applied once the page can take it.
    func applyPendingStep() {
        guard let step = pendingStep else { return }
        pendingStep = nil
        resultWeb?.evaluateJavaScript("window.labShowStep?.('\(step == "export" ? "export" : "review")')", completionHandler: nil)
    }

    func showReview() {
        guard let report = resultWeb else { return }
        swap(to: report, from: web)
        window.subtitle = URL(fileURLWithPath: viewerFolder ?? "").deletingLastPathComponent().lastPathComponent
        window.makeKeyAndOrderFront(nil); window.makeFirstResponder(report)
        activate()
    }

    @objc func showSetup() {
        if window.attachedSheet != nil { return }
        revealWhenReady = false
        swap(to: web, from: resultWeb)
        window.subtitle = ""
        window.makeKeyAndOrderFront(nil); window.makeFirstResponder(web)
    }

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
        guard isResultResource(response.url), resultWeb?.isHidden == false else { completionHandler(nil); return }
        let panel = NSSavePanel()
        panel.title = "Save analysis export"
        panel.nameFieldStringValue = URL(fileURLWithPath: suggestedFilename).lastPathComponent
        panel.beginSheetModal(for: window) { [weak self] answer in
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
        guard webView === resultWeb, frame.isMainFrame, isResultOrigin(frame.request.url), resultWeb?.isHidden == false else { completionHandler(nil); return }
        let panel = NSOpenPanel(); panel.title = "Load a review file"
        panel.allowedContentTypes = [.json]; panel.canChooseFiles = true
        panel.canChooseDirectories = false; panel.allowsMultipleSelection = false
        panel.beginSheetModal(for: window) { answer in completionHandler(answer == .OK ? panel.urls : nil) }
    }

    @objc func updateAccessibilityAppearance() {
        let reduced = NSWorkspace.shared.accessibilityDisplayShouldReduceTransparency ? "true" : "false"
        web?.evaluateJavaScript("document.documentElement.dataset.reduceTransparency = '\(reduced)'", completionHandler: nil)
        resultWeb?.evaluateJavaScript("window.labSetAppearance?.({reduceTransparency:\(reduced)})", completionHandler: nil)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        if webView === resultWeb && webView.url == viewerURL {
            displayedResultFolder = viewerFolder; applyPendingStep()
            // The page normally reports 'ready' within a moment of loading; do not wait for it for long.
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in self?.revealReview() }
        }
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
            displayedResultFolder = nil; revealWhenReady = false
            showSetup()
            send(["event": "error", "message": "The results could not be shown. Open saved results to retry. " + error.localizedDescription])
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationWillTerminate(_ notification: Notification) {
        // The session folder holds only this launch's requests, inventories and staged exports.
        if let session = session { try? FileManager.default.removeItem(at: session) }
    }

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
        stopTester()
        return .terminateNow
    }
}

#if SELFTEST
// Compiled only for packaging/macos_app/validation_v3.0/native_check.py, never into the released app. macOS does not let
// an unattended script click in the app or capture its window, so this build follows a script instead: it opens files,
// runs JavaScript in a view, reports which view is showing and saves what a view displays.
var selfTestReportFrame: WKFrameInfo?
extension Application {
    func runSelfTest() {
        guard let path = ProcessInfo.processInfo.environment["LABCELLPOSE_SELFTEST"],
              let data = try? Data(contentsOf: URL(fileURLWithPath: path)),
              let script = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let steps = script["steps"] as? [[String: Any]], let out = script["out"] as? String else { return }
        var results: [[String: Any]] = []
        func save() {
            let safe = JSONSerialization.isValidJSONObject(results) ? results : results.map { ["step": $0["step"] ?? -1, "result": String(describing: $0["result"] ?? "")] }
            try? JSONSerialization.data(withJSONObject: safe, options: [.prettyPrinted, .sortedKeys]).write(to: URL(fileURLWithPath: out), options: .atomic)
        }
        func run(_ index: Int) {
            guard index < steps.count else { save(); return }
            let step = steps[index]
            let next: (Any?) -> Void = { value in results.append(["step": index, "result": value ?? NSNull()]); save(); run(index + 1) }
            let view: WKWebView? = step["view"] as? String == "review" ? self.resultWeb : self.web
            if let seconds = step["wait"] as? Double { DispatchQueue.main.asyncAfter(deadline: .now() + seconds) { next(nil) } }
            else if let file = step["open"] as? String { self.open(URL(fileURLWithPath: file)); next(nil) }
            else if let body = step["js"] as? String {
                guard let view = view else { next("no view"); return }
                view.callAsyncJavaScript(body, arguments: [:], in: step["frame"] as? Bool == true ? selfTestReportFrame : nil, in: .page) { result in
                    switch result {
                    case .success(let value): next(value)
                    case .failure(let error): next("ERROR: \(error)")
                    }
                }
            } else if let file = step["snapshot"] as? String {
                guard let view = view else { next("no view"); return }
                view.takeSnapshot(with: nil) { image, _ in
                    if let tiff = image?.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff), let png = rep.representation(using: .png, properties: [:]) {
                        try? png.write(to: URL(fileURLWithPath: file))
                    }
                    next(image != nil)
                }
            } else if step["state"] != nil {
                next(["setupVisible": !self.web.isHidden, "reviewVisible": self.resultWeb?.isHidden == false, "title": self.window.title, "subtitle": self.window.subtitle,
                      "busy": self.worker != nil, "tester": self.tester?.isRunning == true, "lastResult": self.lastResult ?? "", "recents": self.recents.count])
            } else if step["quit"] != nil { save(); NSApp.terminate(nil) }
            else { next("unknown step") }
        }
        run(0)
    }
}
#endif

let application = NSApplication.shared
let delegate = Application()
application.delegate = delegate
#if SELFTEST
application.setActivationPolicy(.accessory)
#else
application.setActivationPolicy(.regular)
#endif
application.run()
