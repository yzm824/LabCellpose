import AppKit
import WebKit

final class Application: NSObject, NSApplicationDelegate, WKScriptMessageHandler, WKNavigationDelegate, NSWindowDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var worker: Process?
    var viewer: Process?
    var viewerURL: URL?
    var viewerFolder: String?
    var lastResult: String?
    var lastWorkspace: String?
    var workerBuffer = Data()
    var viewerBuffer = Data()
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
        NSApp.activate(ignoringOtherApps: true)
    }

    @objc func about() {
        alert("LabCellpose 1.0", "Developed by Zhenmo Yu\nLocal cell segmentation and fluorescence measurements.\nCellpose 4.2.1.1 · cpsam_v2\nNo Claude, Codex, account or network service required.\nResearch pilot; review masks and background before interpreting results.")
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
        panel.canChooseDirectories = role != "preset"
        panel.canChooseFiles = role == "input" || role == "preset"
        panel.allowsMultipleSelection = false
        panel.prompt = role == "output" ? "Save results here" : "Choose"
        panel.title = role == "input" ? "Choose a TIFF, ZIP, or image folder" : (role == "output" ? "Choose a result folder" : (role == "result" ? "Open a saved LabCellpose result folder" : "Load experiment settings"))
        if panel.runModal() == .OK, let url = panel.url {
            if role == "result" {
                do {
                    var folder = url
                    if !FileManager.default.fileExists(atPath: folder.appendingPathComponent("index.html").path) { folder = url.appendingPathComponent("results") }
                    let manifest = try JSONSerialization.jsonObject(with: Data(contentsOf: folder.appendingPathComponent("run_manifest.json"))) as? [String: Any]
                    let checks = try JSONSerialization.jsonObject(with: Data(contentsOf: folder.appendingPathComponent("validation.json"))) as? [String: Any]
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
                let panel = NSSavePanel(); panel.nameFieldStringValue = "LabCellpose-settings.json"
                if panel.runModal() == .OK, let url = panel.url {
                    do { try JSONSerialization.data(withJSONObject: preset, options: [.prettyPrinted, .sortedKeys]).write(to: url, options: .atomic)
                        send(["event": "log", "message": "Settings saved to " + url.path])
                    } catch { send(["event": "error", "message": error.localizedDescription]) }
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
        do {
            let file = session.appendingPathComponent("request-" + UUID().uuidString + ".json")
            try JSONSerialization.data(withJSONObject: request).write(to: file, options: .atomic)
            let process = python([resources.appendingPathComponent("desktop_backend.py").path, "--payload", payload.path, "--request", file.path])
            let output = Pipe(); process.standardOutput = output; process.standardError = output
            workerBuffer = Data(); worker = process; cancelled = false
            taskName = request["action"] as? String ?? "task"
            output.fileHandleForReading.readabilityHandler = { [weak self] handle in
                let data = handle.availableData
                if data.isEmpty { handle.readabilityHandler = nil; return }
                DispatchQueue.main.async { self?.consume(data, viewer: false) }
            }
            process.terminationHandler = { [weak self] process in
                DispatchQueue.main.async {
                    guard let self = self else { return }
                    self.worker = nil
                    self.send(["event": "idle", "task": self.taskName, "code": process.terminationStatus, "cancelled": self.cancelled])
                }
            }
            try process.run()
            send(["event": "busy", "task": taskName])
        } catch {
            worker = nil; send(["event": "error", "message": "Could not start the bundled runtime: " + error.localizedDescription])
        }
    }

    func consume(_ data: Data, viewer isViewer: Bool) {
        if isViewer { viewerBuffer.append(data) } else { workerBuffer.append(data) }
        var buffer = isViewer ? viewerBuffer : workerBuffer
        while let newline = buffer.firstIndex(of: 10) {
            let line = buffer.subdata(in: 0..<newline)
            buffer.removeSubrange(0...newline)
            guard let value = try? JSONSerialization.jsonObject(with: line) as? [String: Any] else {
                if !isViewer, let text = String(data: line, encoding: .utf8), !text.isEmpty { send(["event": "log", "message": text]) }
                continue
            }
            if isViewer {
                if let address = value["viewer"] as? String, let url = URL(string: address) {
                    viewerURL = url; UserDefaults.standard.set(url.port ?? 8765, forKey: "viewerPort")
                    NSWorkspace.shared.open(url); send(["event": "viewer", "url": address])
                }
            } else {
                if value["event"] as? String == "workspace" { lastWorkspace = value["path"] as? String }
                if value["event"] as? String == "finished", let result = value["result"] as? String { lastResult = result }
                send(value["event"] == nil ? ["event": "log", "message": String(data: line, encoding: .utf8) ?? ""] : value)
                if value["event"] as? String == "finished", let result = lastResult { showResults(result) }
            }
        }
        if isViewer { viewerBuffer = buffer } else { workerBuffer = buffer }
    }

    func showResults(_ folder: String, useRandomPort: Bool = false) {
        if viewerFolder == folder, let url = viewerURL, viewer?.isRunning == true { NSWorkspace.shared.open(url); return }
        if viewer?.isRunning == true { viewer?.terminate() }
        viewerURL = nil; viewerFolder = folder; viewerBuffer = Data()
        let stored = UserDefaults.standard.integer(forKey: "viewerPort")
        let port = useRandomPort ? 0 : (stored > 0 ? stored : 8765)
        let process = python([payload.appendingPathComponent("app/launcher.py").path, "view", "--run", folder, "--port", String(port), "--no-open"])
        let output = Pipe(); process.standardOutput = output; process.standardError = output
        output.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if data.isEmpty { handle.readabilityHandler = nil; return }
            DispatchQueue.main.async { self?.consume(data, viewer: true) }
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
        let expected = resources.appendingPathComponent("interface.html").standardizedFileURL
        decisionHandler(navigationAction.request.url?.standardizedFileURL == expected ? .allow : .cancel)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
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
