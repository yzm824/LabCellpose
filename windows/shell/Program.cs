// The Windows shell of LabCellpose: one window with two web views, the counterpart of desktop/Main.swift.
//
//   Set up         resources\interface.html, loaded from the app folder; it talks to the shell through the "lab" bridge.
//   Review, Export the report served by "launcher.py view" on 127.0.0.1; its host page has the "labReview" bridge.
//
// The pages are the same files as on macOS. They call window.webkit.messageHandlers.<name>.postMessage, so each view
// gets a few lines of script that define that object on top of WebView2's own message channel.
// The engine runs as separate processes of the bundled Python: a worker per task (inspect, preview, run), one process
// that keeps the model loaded for trial segmentations, and the viewer server. Windows cannot send SIGINT or SIGTERM,
// so a task and the viewer are stopped by writing "stop" to their standard input (--control-stdin).

using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;
using Microsoft.Win32;

namespace LabCellpose
{
    static class Program
    {
        [STAThread]
        static void Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
#if SELFTEST
            Application.ThreadException += (sender, e) => MainWindow.Trace("EXCEPTION " + e.Exception);
#else
            Application.ThreadException += (sender, e) =>
                MessageBox.Show(e.Exception.Message, "LabCellpose", MessageBoxButtons.OK, MessageBoxIcon.Error);
#endif
            Application.Run(new MainWindow(args));
        }
    }

    /// JSON as dictionaries, lists and plain values. Large engine events never pass through here: they are handed to
    /// the page as the text the engine wrote.
    static class Json
    {
        static JavaScriptSerializer Serializer() { return new JavaScriptSerializer { MaxJsonLength = int.MaxValue, RecursionLimit = 256 }; }
        public static string Write(object value) { return Serializer().Serialize(value); }
        public static Dictionary<string, object> ReadObject(string text)
        {
            try { return Serializer().DeserializeObject(text) as Dictionary<string, object>; }
            catch (Exception) { return null; }
        }
        public static string Str(IDictionary<string, object> d, string key)
        {
            object value;
            return d != null && d.TryGetValue(key, out value) ? value as string : null;
        }
        public static Dictionary<string, object> Dict(IDictionary<string, object> d, string key)
        {
            object value;
            return d != null && d.TryGetValue(key, out value) ? value as Dictionary<string, object> : null;
        }
        public static IList List(IDictionary<string, object> d, string key)
        {
            object value;
            return d != null && d.TryGetValue(key, out value) ? value as IList : null;
        }
        public static int? Int(IDictionary<string, object> d, string key)
        {
            object value;
            if (d == null || !d.TryGetValue(key, out value) || value == null || value is bool || value is string) return null;
            try
            {
                var number = Convert.ToDouble(value);
                return number == Math.Floor(number) && Math.Abs(number) < int.MaxValue ? (int?)Convert.ToInt32(number) : null;
            }
            catch (Exception) { return null; }
        }
        public static bool True(IDictionary<string, object> d, string key)
        {
            object value;
            return d != null && d.TryGetValue(key, out value) && value is bool && (bool)value;
        }
    }

    /// Child processes end with the app, however it ends.
    sealed class Job
    {
        [StructLayout(LayoutKind.Sequential)]
        struct BasicLimits
        {
            public long PerProcessUserTimeLimit, PerJobUserTimeLimit;
            public uint LimitFlags;
            public UIntPtr MinimumWorkingSetSize, MaximumWorkingSetSize;
            public uint ActiveProcessLimit;
            public UIntPtr Affinity;
            public uint PriorityClass, SchedulingClass;
        }
        [StructLayout(LayoutKind.Sequential)]
        struct IoCounters { public ulong ReadOperations, WriteOperations, OtherOperations, ReadTransfer, WriteTransfer, OtherTransfer; }
        [StructLayout(LayoutKind.Sequential)]
        struct ExtendedLimits
        {
            public BasicLimits Basic;
            public IoCounters Io;
            public UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed;
        }
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        static extern IntPtr CreateJobObjectW(IntPtr attributes, string name);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool SetInformationJobObject(IntPtr job, int infoClass, ref ExtendedLimits info, uint length);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);

        readonly IntPtr handle;
        public Job()
        {
            handle = CreateJobObjectW(IntPtr.Zero, null);
            if (handle == IntPtr.Zero) return;
            var limits = new ExtendedLimits();
            limits.Basic.LimitFlags = 0x2000;   // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            SetInformationJobObject(handle, 9, ref limits, (uint)Marshal.SizeOf(typeof(ExtendedLimits)));
        }
        public void Add(Process process)
        {
            try { if (handle != IntPtr.Zero) AssignProcessToJobObject(handle, process.Handle); }
            catch (Exception) { }
        }
    }

    /// The system's folder picker. (.NET Framework's own FolderBrowserDialog is the small tree view of Windows XP.)
    static class FolderPicker
    {
        [ComImport, Guid("DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7")]
        class FileOpenDialog { }

        [ComImport, Guid("42f85136-db7e-439c-85f1-e4075d135fc8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        interface IFileOpenDialog
        {
            [PreserveSig] int Show(IntPtr parent);
            void SetFileTypes(uint count, IntPtr types);
            void SetFileTypeIndex(uint index);
            void GetFileTypeIndex(out uint index);
            void Advise(IntPtr events, out uint cookie);
            void Unadvise(uint cookie);
            void SetOptions(uint options);
            void GetOptions(out uint options);
            void SetDefaultFolder(IShellItem item);
            void SetFolder(IShellItem item);
            void GetFolder(out IShellItem item);
            void GetCurrentSelection(out IShellItem item);
            void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string name);
            void GetFileName([MarshalAs(UnmanagedType.LPWStr)] out string name);
            void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string title);
            void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string text);
            void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string label);
            void GetResult(out IShellItem item);
            void AddPlace(IShellItem item, int place);
            void SetDefaultExtension([MarshalAs(UnmanagedType.LPWStr)] string extension);
            void Close(int result);
            void SetClientGuid(ref Guid guid);
            void ClearClientData();
            void SetFilter(IntPtr filter);
            void GetResults(out IntPtr items);
            void GetSelectedItems(out IntPtr items);
        }

        [ComImport, Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        interface IShellItem
        {
            void BindToHandler(IntPtr context, ref Guid handler, ref Guid id, out IntPtr result);
            void GetParent(out IShellItem parent);
            void GetDisplayName(uint form, [MarshalAs(UnmanagedType.LPWStr)] out string name);
            void GetAttributes(uint mask, out uint attributes);
            void Compare(IShellItem other, uint hint, out int order);
        }

#if SELFTEST
        /// The scripted check cannot answer a dialog, but it can make one, set it up as Show does and let it go.
        public static string Probe()
        {
            var dialog = (IFileOpenDialog)new FileOpenDialog();
            try
            {
                uint options;
                dialog.GetOptions(out options);
                dialog.SetOptions(options | 0x20 | 0x40);
                dialog.SetTitle("Probe");
                dialog.SetOkButtonLabel("Choose");
                uint after;
                dialog.GetOptions(out after);
                return (after & 0x20) != 0 ? "ok" : "the folder option was not kept";
            }
            finally { Marshal.FinalReleaseComObject(dialog); }
        }
#endif

        public static string Show(IWin32Window owner, string title, string okLabel)
        {
            try
            {
                var dialog = (IFileOpenDialog)new FileOpenDialog();
                try
                {
                    uint options;
                    dialog.GetOptions(out options);
                    dialog.SetOptions(options | 0x20 | 0x40);   // FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM
                    dialog.SetTitle(title);
                    if (okLabel != null) dialog.SetOkButtonLabel(okLabel);
                    if (dialog.Show(owner.Handle) != 0) return null;   // cancelled
                    IShellItem item;
                    dialog.GetResult(out item);
                    string path;
                    item.GetDisplayName(0x80058000, out path);   // SIGDN_FILESYSPATH
                    return path;
                }
                finally { Marshal.FinalReleaseComObject(dialog); }
            }
            catch (Exception)
            {
                // Whatever is wrong with the modern dialog on this system, a folder can still be chosen.
                using (var fallback = new FolderBrowserDialog { Description = title, ShowNewFolderButton = true })
                    return fallback.ShowDialog(owner) == DialogResult.OK ? fallback.SelectedPath : null;
            }
        }
    }

    /// A backend task is finished only when it has exited AND its output has been read to the end,
    /// so the final events always reach the page before 'idle'.
    sealed class TaskEnd
    {
        public bool OutputClosed, ErrorClosed, Reported;
        public int? ExitCode;
    }

    sealed class MainWindow : Form
    {
        /// The colour of the bars and panels in the pages (--panel in ui.css).
        static readonly Color Chrome = Color.FromArgb(0x16, 0x19, 0x1E);
        static readonly UTF8Encoding Utf8 = new UTF8Encoding(false);
        const long ResultFileLimit = 128L << 20;
#if SELFTEST
        const string DataName = "LabCellpose-selftest";
#else
        const string DataName = "LabCellpose";
#endif

        // The setup page calls webkit.messageHandlers.lab.postMessage(message) and listens with window.receiveNative.
        // Requests for the engine are turned into text here, in the page, so the engine reads exactly what was asked.
        const string SetupBridge = @"(function(){
 if(window.top!==window||!window.chrome||!window.chrome.webview)return;
 const bridge=window.chrome.webview;
 const sorted=value=>Array.isArray(value)?value.map(sorted):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(k=>[k,sorted(value[k])])):value;
 const send=message=>{
  const out=Object.assign({},message);
  if(message&&(message.action==='run'||message.action==='trial')&&message.request&&typeof message.request==='object')out.text=JSON.stringify(Object.assign({},message.request,{action:message.action}));
  if(message&&message.action==='savePreset'&&message.value&&typeof message.value==='object')out.text=JSON.stringify(sorted(message.value),null,2);
  bridge.postMessage(out);
 };
 window.webkit={messageHandlers:{lab:{postMessage:send}}};
 bridge.addEventListener('message',event=>{if(typeof window.receiveNative==='function')window.receiveNative(event.data);});
 const files=event=>event.dataTransfer&&Array.prototype.indexOf.call(event.dataTransfer.types||[],'Files')>=0;
 window.addEventListener('dragover',event=>{if(files(event)){event.preventDefault();event.dataTransfer.dropEffect='copy';}});
 window.addEventListener('drop',event=>{
  if(!files(event))return;
  event.preventDefault();
  const dropped=event.dataTransfer.files;
  if(dropped.length===1&&bridge.postMessageWithAdditionalObjects)bridge.postMessageWithAdditionalObjects({action:'__dropped'},dropped);
 });
})();";

        // The report's host page looks for webkit.messageHandlers.labReview (see viewer_shell.html).
        const string ReviewBridge = @"(function(){
 if(window.top!==window||!window.chrome||!window.chrome.webview)return;
 window.webkit={messageHandlers:{labReview:{postMessage:message=>window.chrome.webview.postMessage(message)}}};
})();";

        readonly string resources, payload, python, interfacePath, dataFolder, settingsPath;
        readonly Job job = new Job();
        string session;
        WebView2 web;          // Set up
        WebView2 resultWeb;    // Review and Export
        Dictionary<string, object> settings = new Dictionary<string, object>();
        bool setupReady, revealWhenReady, cancelled, viewerUsesFallbackPort, quitting;
        string pendingOpen, pendingStep, displayedResultFolder, viewerFolder, lastResult, lastWorkspace, taskName = "";
        Uri viewerUri;
        Process worker, viewer, tester;
        int trialsPending, downloads, viewerRequest;

        public MainWindow(string[] args)
        {
            var folder = AppDomain.CurrentDomain.BaseDirectory;
            resources = Path.Combine(folder, "resources");
            payload = Path.Combine(folder, "payload");
            python = Path.Combine(payload, "runtime", "python.exe");
            interfacePath = Path.GetFullPath(Path.Combine(resources, "interface.html"));
            dataFolder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), DataName);
            settingsPath = Path.Combine(dataFolder, "settings.json");
            if (args.Length > 0 && (File.Exists(args[0]) || Directory.Exists(args[0]))) pendingOpen = Path.GetFullPath(args[0]);

            Text = "LabCellpose";
            BackColor = Chrome;
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch (Exception) { }
            StartPosition = FormStartPosition.CenterScreen;
            var scale = DeviceDpi / 96f;
            MinimumSize = new Size((int)(1040 * scale), (int)(680 * scale));
            var area = Screen.FromPoint(Cursor.Position).WorkingArea;
            ClientSize = new Size(Math.Min((int)(1380 * scale), area.Width - 40), Math.Min((int)(880 * scale), area.Height - 60));

            web = new WebView2 { Dock = DockStyle.Fill, DefaultBackgroundColor = Chrome, AllowExternalDrop = true };
            resultWeb = new WebView2 { Dock = DockStyle.Fill, DefaultBackgroundColor = Chrome, AllowExternalDrop = false };
            Controls.Add(resultWeb);
            Controls.Add(web);
            web.BringToFront();
        }

        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            // One dark surface from the title bar down, as on macOS. Older systems ignore what they do not know.
            try
            {
                int dark = 1, caption = Chrome.R | (Chrome.G << 8) | (Chrome.B << 16);
                DwmSetWindowAttribute(Handle, 20, ref dark, 4);      // DWMWA_USE_IMMERSIVE_DARK_MODE
                DwmSetWindowAttribute(Handle, 35, ref caption, 4);   // DWMWA_CAPTION_COLOR (Windows 11)
            }
            catch (Exception) { }
        }

        [DllImport("dwmapi.dll")]
        static extern int DwmSetWindowAttribute(IntPtr window, int attribute, ref int value, int size);

        protected override async void OnLoad(EventArgs e)
        {
            base.OnLoad(e);
            try { await Start(); }
            catch (Exception error)
            {
                Alert("LabCellpose could not start", error.Message);
                quitting = true; Close();
            }
        }

        async Task Start()
        {
            if (!File.Exists(python) || !File.Exists(interfacePath))
                throw new Exception("The app folder is incomplete. Unzip the whole LabCellpose folder again and start LabCellpose.exe from inside it.");
            string browser = null;
            try { browser = CoreWebView2Environment.GetAvailableBrowserVersionString(); } catch (Exception) { }
            if (string.IsNullOrEmpty(browser))
                throw new Exception("LabCellpose shows its pages with Microsoft Edge WebView2, which this computer does not have.\n\n" +
                    "Install the \"Evergreen\" WebView2 Runtime from developer.microsoft.com/microsoft-edge/webview2 and start LabCellpose again.");
            Directory.CreateDirectory(dataFolder);
            LoadSettings();
            RestoreWindow();
            session = Path.Combine(Path.GetTempPath(), "LabCellpose-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(session);

            var environment = await CoreWebView2Environment.CreateAsync(null, Path.Combine(dataFolder, "WebView2"), new CoreWebView2EnvironmentOptions());
            await web.EnsureCoreWebView2Async(environment);
            await resultWeb.EnsureCoreWebView2Async(environment);
            resultWeb.Visible = false;
            foreach (var view in new[] { web, resultWeb })
            {
                var s = view.CoreWebView2.Settings;
                s.AreDefaultContextMenusEnabled = false;   // "Refresh" or "Back" would throw away the page's state
                s.AreDevToolsEnabled = false;
                s.IsStatusBarEnabled = false;
                s.IsZoomControlEnabled = false;            // Ctrl-wheel and pinch zoom the image, not the page
                s.IsPinchZoomEnabled = false;
                s.IsSwipeNavigationEnabled = false;
                s.AreBrowserAcceleratorKeysEnabled = false;
                s.IsPasswordAutosaveEnabled = false;
                s.IsGeneralAutofillEnabled = false;
                s.IsReputationCheckingRequired = false;    // the pages are local; nothing is looked up
                view.CoreWebView2.NewWindowRequested += (sender, e) => e.Handled = true;
                view.CoreWebView2.PermissionRequested += (sender, e) => e.State = CoreWebView2PermissionState.Deny;
                view.KeyDown += StepShortcut;
            }

            await web.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(SetupBridge);
            web.CoreWebView2.WebMessageReceived += SetupMessage;
            web.CoreWebView2.NavigationStarting += (sender, e) => { if (!IsSetupPage(e.Uri)) e.Cancel = true; };
            web.CoreWebView2.FrameNavigationStarting += (sender, e) => e.Cancel = true;
            web.CoreWebView2.NavigationCompleted += (sender, e) => UpdateAppearance();

            await resultWeb.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(ReviewBridge);
            resultWeb.CoreWebView2.WebMessageReceived += ReviewMessage;
            resultWeb.CoreWebView2.NavigationStarting += (sender, e) => { if (!IsResultResource(e.Uri) && e.Uri != "about:blank") e.Cancel = true; };
            resultWeb.CoreWebView2.FrameNavigationStarting += (sender, e) => { if (!IsResultOrigin(e.Uri) && !e.Uri.StartsWith("about:", StringComparison.Ordinal)) e.Cancel = true; };
            resultWeb.CoreWebView2.NavigationCompleted += ReviewLoaded;
            resultWeb.CoreWebView2.DownloadStarting += DownloadStarting;
#if SELFTEST
            resultWeb.CoreWebView2.FrameCreated += (sender, e) => reportFrame = e.Frame;
#endif
            web.CoreWebView2.Navigate(new Uri(interfacePath).AbsoluteUri);
#if SELFTEST
            RunSelfTest();
#endif
        }

        // ---- small helpers -------------------------------------------------------------------------------------------

        /// For the scripted check only: what the shell did, in a file. Calls to this are left out of the released app.
        [Conditional("SELFTEST")]
        public static void Trace(string text)
        {
#if SELFTEST
            var file = Environment.GetEnvironmentVariable("LABCELLPOSE_SELFTEST_LOG");
            if (string.IsNullOrEmpty(file)) return;
            try { lock (Utf8) File.AppendAllText(file, DateTime.Now.ToString("HH:mm:ss.fff") + " " + (text.Length > 300 ? text.Substring(0, 300) + "… (" + text.Length + " characters)" : text) + "\r\n", Utf8); }
            catch (Exception) { }
#endif
        }

        void Alert(string title, string message)
        {
            MessageBox.Show(this, message, title, MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }

        /// Run on the window's thread; engine output arrives on other threads.
        void Post(Action action)
        {
            try { if (IsHandleCreated && !IsDisposed) BeginInvoke(action); }
            catch (Exception) { }
        }

        void After(int milliseconds, Action action)
        {
            var timer = new Timer { Interval = milliseconds };
            timer.Tick += (sender, e) => { timer.Stop(); timer.Dispose(); if (!IsDisposed) action(); };
            timer.Start();
        }

        static Dictionary<string, object> Event(string name, params object[] pairs)
        {
            var value = new Dictionary<string, object> { { "event", name } };
            for (var i = 0; i + 1 < pairs.Length; i += 2) value[(string)pairs[i]] = pairs[i + 1];
            return value;
        }

        void Send(Dictionary<string, object> values) { SendText(Json.Write(values)); }

        /// Hand one JSON object to the setup page. WebView2 parses it; text that is not JSON is refused, never run.
        bool SendText(string json)
        {
            try { web.CoreWebView2.PostWebMessageAsJson(json); return true; }
            catch (Exception) { return false; }
        }

        void SendError(string message) { Send(Event("error", "message", message)); }

        static bool SamePath(string a, string b)
        {
            return a != null && b != null && string.Equals(a.TrimEnd('\\'), b.TrimEnd('\\'), StringComparison.OrdinalIgnoreCase);
        }

        bool IsSetupPage(string address)
        {
            Uri uri;
            if (!Uri.TryCreate(address, UriKind.Absolute, out uri) || !uri.IsFile) return false;
            try { return SamePath(Path.GetFullPath(uri.LocalPath), interfacePath); }
            catch (Exception) { return false; }
        }

        bool IsResultOrigin(string address)
        {
            Uri uri;
            return viewerUri != null && Uri.TryCreate(address, UriKind.Absolute, out uri)
                && uri.Scheme == "http" && uri.Host == "127.0.0.1" && uri.Port == viewerUri.Port;
        }

        bool IsResultResource(string address)
        {
            if (address == null) return false;
            return IsResultOrigin(address) || (address.StartsWith("blob:", StringComparison.Ordinal) && IsResultOrigin(address.Substring(5)));
        }

        // ---- settings: what macOS keeps in UserDefaults ----------------------------------------------------------------

        void LoadSettings()
        {
            try
            {
                if (File.Exists(settingsPath)) settings = Json.ReadObject(File.ReadAllText(settingsPath, Utf8)) ?? new Dictionary<string, object>();
            }
            catch (Exception) { settings = new Dictionary<string, object>(); }
        }

        void SaveSettings()
        {
            try
            {
                var temporary = settingsPath + ".tmp";
                File.WriteAllText(temporary, Json.Write(settings), Utf8);
                if (File.Exists(settingsPath)) File.Replace(temporary, settingsPath, null); else File.Move(temporary, settingsPath);
            }
            catch (Exception) { }
        }

        void RestoreWindow()
        {
            var saved = Json.Dict(settings, "window");
            int? x = Json.Int(saved, "x"), y = Json.Int(saved, "y"), w = Json.Int(saved, "width"), h = Json.Int(saved, "height");
            if (x == null || y == null || w == null || h == null) return;
            var bounds = new Rectangle(x.Value, y.Value, Math.Max(w.Value, MinimumSize.Width), Math.Max(h.Value, MinimumSize.Height));
            if (!Screen.AllScreens.Any(screen => screen.WorkingArea.IntersectsWith(bounds))) return;
            StartPosition = FormStartPosition.Manual;
            Bounds = bounds;
            if (Json.True(saved, "maximized")) WindowState = FormWindowState.Maximized;
        }

        void RememberWindow()
        {
            var bounds = WindowState == FormWindowState.Normal ? Bounds : RestoreBounds;
            settings["window"] = new Dictionary<string, object> { { "x", bounds.X }, { "y", bounds.Y }, { "width", bounds.Width }, { "height", bounds.Height },
                { "maximized", WindowState == FormWindowState.Maximized } };
        }

        /// Recent analyses for the start page: completed runs that still exist.
        List<Dictionary<string, object>> Recents()
        {
            var list = new List<Dictionary<string, object>>();
            foreach (var item in Json.List(settings, "recentResults") ?? new object[0])
            {
                var entry = item as Dictionary<string, object>;
                var path = Json.Str(entry, "path");
                if (path != null && File.Exists(Path.Combine(path, "index.html"))) list.Add(entry);
            }
            return list;
        }

        void Remember(string result)
        {
            var entry = new Dictionary<string, object> { { "path", result }, { "date", DateTime.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'") } };
            try
            {
                var config = ReadResultJson(result, "config.json");
                if (config != null) { entry["title"] = Json.Str(config, "title") ?? ""; entry["images"] = (Json.List(config, "fields") ?? new object[0]).Count; }
            }
            catch (Exception) { }
            try
            {
                var objects = Json.Int(ReadResultJson(result, "validation.json"), "objects");
                if (objects != null) entry["objects"] = objects.Value;
            }
            catch (Exception) { }
            var list = new List<object> { entry };
            list.AddRange(Recents().Where(r => !SamePath(Json.Str(r, "path"), result)));
            settings["recentResults"] = list.Take(12).ToList();
            SaveSettings();
            Send(Event("recents", "recents", Recents()));
        }

        /// Settings last used for each kind of image (channel count and names), offered again for matching images.
        Dictionary<string, object> SetupMemory()
        {
            var memory = new Dictionary<string, object>();
            foreach (var item in Json.List(settings, "setupMemory") ?? new object[0])
            {
                var entry = item as Dictionary<string, object>;
                var signature = Json.Str(entry, "signature");
                var value = Json.Dict(entry, "value");
                if (signature != null && value != null) memory[signature] = value;
            }
            return memory;
        }

        void RememberSetup(string signature, Dictionary<string, object> value)
        {
            if (signature.Length > 2000 || Json.Int(value, "appPresetVersion") != 1 || Json.Write(value).Length >= 200000) return;
            var list = new List<object> { new Dictionary<string, object> { { "signature", signature }, { "value", value } } };
            foreach (var item in Json.List(settings, "setupMemory") ?? new object[0])
                if (Json.Str(item as Dictionary<string, object>, "signature") != signature) list.Add(item);
            settings["setupMemory"] = list.Take(20).ToList();
            SaveSettings();
        }

        // ---- saved results are external input ----------------------------------------------------------------------------

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        struct FindData
        {
            public uint Attributes;
            public System.Runtime.InteropServices.ComTypes.FILETIME Created, Accessed, Written;
            public uint SizeHigh, SizeLow, Reserved0, Reserved1;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)] public string Name;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 14)] public string ShortName;
        }
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        static extern IntPtr FindFirstFileW(string name, out FindData data);
        [DllImport("kernel32.dll")]
        static extern bool FindClose(IntPtr handle);

        /// A symbolic link or a junction. Other reparse points are not links: files in a cloud-synced folder carry one.
        static bool IsLink(string path)
        {
            FindData data;
            var handle = FindFirstFileW(path.TrimEnd('\\'), out data);
            if (handle == new IntPtr(-1)) return false;
            FindClose(handle);
            return (data.Attributes & 0x400) != 0 && (data.Reserved0 == 0xA000000C || data.Reserved0 == 0xA0000003);
        }

        /// A JSON file of a result folder: a regular file, not a link, no larger than 128 MiB. Null when it does not exist.
        static Dictionary<string, object> ReadResultJson(string folder, string name)
        {
            var unsafeFile = new Exception("Result metadata must be a regular file, not a link, and no larger than 128 MiB.");
            if (!Directory.Exists(folder) || IsLink(folder)) throw unsafeFile;
            var path = Path.Combine(folder, name);
            if (!File.Exists(path)) return null;
            if (IsLink(path) || new FileInfo(path).Length > ResultFileLimit) throw unsafeFile;
            var value = Json.ReadObject(File.ReadAllText(path, Utf8));
            if (value == null) throw new Exception(name + " cannot be read.");
            return value;
        }

        // ---- messages from the setup page ----------------------------------------------------------------------------------

        void SetupMessage(object sender, CoreWebView2WebMessageReceivedEventArgs e)
        {
            if (!IsSetupPage(e.Source)) { Trace("message from an unexpected page: " + e.Source); return; }
            var body = Json.ReadObject(e.WebMessageAsJson);
            Trace("page " + e.WebMessageAsJson);
            var action = Json.Str(body, "action");
            if (action == null) return;
            switch (action)
            {
                case "ready":
                    setupReady = true;
                    Send(Event("ready", "output", Json.Str(settings, "outputFolder") ?? "", "version", AppVersion(),
                        "recents", Recents(), "memory", SetupMemory()));
                    if (pendingOpen != null) { var path = pendingOpen; pendingOpen = null; Open(path); }
                    break;
                case "__dropped":
                    foreach (var item in e.AdditionalObjects ?? new object[0])
                    {
                        var file = item as CoreWebView2File;
                        if (file != null && !string.IsNullOrEmpty(file.Path)) { var path = file.Path; Post(() => Open(path)); break; }
                    }
                    break;
                case "trial":
                    if (Json.Dict(body, "request") != null && Json.Str(body, "text") != null) Trial(Json.Dict(body, "request"), Json.Str(body, "text"));
                    break;
                case "remember":
                    if (Json.Str(body, "signature") != null && Json.Dict(body, "value") != null) RememberSetup(Json.Str(body, "signature"), Json.Dict(body, "value"));
                    break;
                case "openRecent":
                    // Only a folder this app listed itself can be opened this way.
                    var recent = Json.Str(body, "path");
                    if (worker == null && recent != null && Recents().Any(r => Json.Str(r, "path") == recent)) OpenResults(recent);
                    break;
                case "choose":
                    var role = Json.Str(body, "role");
                    if (worker == null && role != null && new[] { "input", "output", "preset", "result" }.Contains(role)) Post(() => Choose(role));
                    break;
                case "inspect":
                    if (Json.Str(body, "input") != null)
                        StartTask("inspect", Json.Write(new Dictionary<string, object> { { "action", "inspect" }, { "input", Json.Str(body, "input") },
                            { "inventory", Path.Combine(session, "inventory-" + Guid.NewGuid().ToString("N") + ".json") } }));
                    break;
                case "preview":
                    if (Json.Str(body, "inventory") != null && Json.Int(body, "index") != null)
                        StartTask("preview", Json.Write(new Dictionary<string, object> { { "action", "preview" }, { "inventory", Json.Str(body, "inventory") }, { "index", Json.Int(body, "index").Value } }));
                    break;
                case "run":
                    if (Json.Dict(body, "request") != null && Json.Str(body, "text") != null) StartTask("run", Json.Str(body, "text"));
                    break;
                case "cancel":
                    if (Running(worker))
                    {
                        cancelled = true;
                        WriteLine(worker, "stop");
                        Send(Event("log", "message", "Stopping analysis; partial results will be kept."));
                    }
                    break;
                case "openResult":
                    if (lastResult != null) { pendingStep = Json.Str(body, "step") == "export" ? "export" : "review"; ShowResults(lastResult); }
                    break;
                case "openFolder":
                    if (lastWorkspace != null) ShowFolder(lastWorkspace);
                    break;
                case "savePreset":
                    var text = Json.Str(body, "text");
                    if (text != null) Post(() => SavePreset(text));
                    break;
            }
        }

        static string AppVersion()
        {
            var version = typeof(MainWindow).Assembly.GetName().Version;
            return version.Major + "." + version.Minor;
        }

        void Choose(string role)
        {
            if (role == "input")
            {
                // macOS chooses a file or a folder in one panel; Windows has a dialog for each.
                var menu = new ContextMenuStrip();
                menu.Items.Add("Choose a folder of images…", null, (sender, e) => Post(() => Chosen("input", FolderPicker.Show(this, "Choose a folder of TIFF images", "Choose"))));
                menu.Items.Add("Choose a TIFF or ZIP file…", null, (sender, e) => Post(() =>
                {
                    using (var dialog = new OpenFileDialog { Title = "Choose a TIFF or ZIP file", Filter = "TIFF images and ZIP archives|*.tif;*.tiff;*.zip|All files|*.*", CheckFileExists = true })
                        Chosen("input", dialog.ShowDialog(this) == DialogResult.OK ? dialog.FileName : null);
                }));
                menu.Closed += (sender, e) => Post(menu.Dispose);
                menu.Show(Cursor.Position);
            }
            else if (role == "output") Chosen("output", FolderPicker.Show(this, "Choose a result folder", "Save results here"));
            else if (role == "result")
            {
                var folder = FolderPicker.Show(this, "Open a saved LabCellpose result folder", "Open");
                if (folder != null) OpenResults(folder);
            }
            else
            {
                using (var dialog = new OpenFileDialog { Title = "Load analysis preset", Filter = "LabCellpose presets (*.json)|*.json|All files|*.*", CheckFileExists = true })
                {
                    if (dialog.ShowDialog(this) != DialogResult.OK) return;
                    try
                    {
                        if (new FileInfo(dialog.FileName).Length >= 1000000) throw new Exception("Invalid settings file");
                        var text = File.ReadAllText(dialog.FileName, Utf8);
                        if (Json.Int(Json.ReadObject(text), "appPresetVersion") != 1) throw new Exception("Invalid settings file");
                        // The file's own text goes to the page, so nothing in it is rounded or reordered on the way.
                        if (!SendText("{\"event\":\"preset\",\"value\":" + text + "}")) throw new Exception("Invalid settings file");
                    }
                    catch (Exception error) { SendError("Cannot load settings: " + error.Message); }
                }
            }
        }

        void Chosen(string role, string path)
        {
            if (path == null) return;
            Send(Event("chosen", "role", role, "path", path));
            if (role == "output") { settings["outputFolder"] = path; SaveSettings(); }
        }

        void SavePreset(string text)
        {
            using (var dialog = new SaveFileDialog { Title = "Save analysis preset", FileName = "LabCellpose-preset.json", Filter = "LabCellpose presets (*.json)|*.json", OverwritePrompt = true })
            {
                if (dialog.ShowDialog(this) != DialogResult.OK) return;
                try { File.WriteAllText(dialog.FileName, text, Utf8); Send(Event("log", "message", "Settings saved to " + dialog.FileName)); }
                catch (Exception error) { SendError(error.Message); }
            }
        }

        static void ShowFolder(string folder)
        {
            try { if (Directory.Exists(folder)) Process.Start(new ProcessStartInfo { FileName = folder, UseShellExecute = true }); }
            catch (Exception) { }
        }

        /// A file or folder dropped on the window or opened with the app: saved results open for review, anything else is image input.
        void Open(string path)
        {
            if (!setupReady) { pendingOpen = path; return; }
            if (worker != null) { SendError("Wait for the current task to finish, then open the files again."); return; }
            var isFolder = Directory.Exists(path);
            if (!isFolder && !File.Exists(path)) return;
            if (isFolder && (File.Exists(Path.Combine(path, "run_manifest.json")) || File.Exists(Path.Combine(path, "results", "run_manifest.json")))) OpenResults(path);
            else { ShowSetup(); Send(Event("chosen", "role", "input", "path", path)); }
        }

        /// Open a completed run (its folder or the results folder inside it) for review.
        void OpenResults(string path)
        {
            try
            {
                var folder = path;
                if (!File.Exists(Path.Combine(folder, "index.html"))) folder = Path.Combine(path, "results");
                var manifest = ReadResultJson(folder, "run_manifest.json");
                var checks = ReadResultJson(folder, "validation.json");
                if (Json.Str(manifest, "status") != "complete" || !Json.True(checks, "passed") || !File.Exists(Path.Combine(folder, "index.html")))
                    throw new Exception("This folder is not a completed LabCellpose run");
                lastResult = folder; lastWorkspace = Path.GetDirectoryName(folder);
                Send(Event("finished", "result", folder, "objects", Json.Int(checks, "objects") ?? 0, "rows", Json.Int(checks, "measurement_rows") ?? 0, "opened", true));
                Remember(folder);
                ShowResults(folder);
            }
            catch (Exception error) { SendError("Cannot open this result folder: " + error.Message); }
        }

        // ---- the bundled Python -----------------------------------------------------------------------------------------

        static string Quote(string argument)
        {
            if (argument.Length > 0 && argument.IndexOfAny(new[] { ' ', '\t', '"' }) < 0) return argument;
            var text = new StringBuilder("\"");
            var backslashes = 0;
            foreach (var c in argument)
            {
                if (c == '\\') { backslashes++; continue; }
                if (c == '"') { text.Append('\\', backslashes * 2 + 1).Append('"'); backslashes = 0; continue; }
                text.Append('\\', backslashes).Append(c); backslashes = 0;
            }
            return text.Append('\\', backslashes * 2).Append('"').ToString();
        }

        Process Python(params string[] arguments)
        {
            var info = new ProcessStartInfo(python)
            {
                Arguments = string.Join(" ", new[] { "-I", "-B", "-X", "utf8", "-u" }.Concat(arguments).Select(Quote)),
                WorkingDirectory = session,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardInput = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                StandardOutputEncoding = Utf8,
                StandardErrorEncoding = Utf8,
            };
            foreach (var key in info.Environment.Keys.ToList())
                if (key.StartsWith("PYTHON", StringComparison.OrdinalIgnoreCase)) info.Environment.Remove(key);
            // Only Windows itself on the search path: libraries of another Python or Conda installation must not be picked up.
            var windows = Environment.GetFolderPath(Environment.SpecialFolder.Windows);
            info.Environment["PATH"] = Path.Combine(windows, "System32") + ";" + windows;
            info.Environment["HF_HUB_OFFLINE"] = "1";
            info.Environment["MPLBACKEND"] = "Agg";
            info.Environment["MPLCONFIGDIR"] = Path.Combine(session, "matplotlib");
            info.Environment["CELLPOSE_LOCAL_MODELS_PATH"] = Path.Combine(payload, "models");
            return new Process { StartInfo = info, EnableRaisingEvents = true };
        }

        void Launch(Process process)
        {
            process.Start();
            Trace("START " + process.Id + " " + process.StartInfo.Arguments);
            job.Add(process);
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();
        }

        static bool Running(Process process)
        {
            try { return process != null && !process.HasExited; }
            catch (Exception) { return false; }
        }

        static void WriteLine(Process process, string line)
        {
            var bytes = Utf8.GetBytes(line + "\n");
            var stream = process.StandardInput.BaseStream;
            stream.Write(bytes, 0, bytes.Length);
            stream.Flush();
        }

        // ---- worker tasks: inspect, preview, run ---------------------------------------------------------------------------

        void StartTask(string name, string request)
        {
            if (worker != null) { SendError("A task is already running."); return; }
            taskName = name;
            if (name == "run") StopTester();   // a run needs the memory the loaded trial model holds
            try
            {
                var file = Path.Combine(session, "request-" + Guid.NewGuid().ToString("N") + ".json");
                File.WriteAllText(file, request, Utf8);
                var process = Python(Path.Combine(resources, "desktop_backend.py"), "--payload", payload, "--request", file, "--control-stdin");
                var end = new TaskEnd();
                process.OutputDataReceived += (sender, e) => Post(() => { Trace("worker out " + (e.Data ?? "<end>")); if (e.Data == null) { end.OutputClosed = true; Finish(process, end); } else Consume(e.Data); });
                process.ErrorDataReceived += (sender, e) => Post(() => { Trace("worker err " + (e.Data ?? "<end>")); if (e.Data == null) { end.ErrorClosed = true; Finish(process, end); } else Consume(e.Data); });
                process.Exited += (sender, e) => Post(() =>
                {
                    try { end.ExitCode = process.ExitCode; } catch (Exception) { end.ExitCode = -1; }
                    Trace("worker exit " + end.ExitCode);
                    Finish(process, end);
                    // Output normally closes at exit; do not wait forever if a descendant kept the pipe open.
                    After(2000, () => { end.OutputClosed = end.ErrorClosed = true; Finish(process, end); });
                });
                worker = process; cancelled = false;
                Launch(process);
                Send(Event("busy", "task", taskName));
            }
            catch (Exception error)
            {
                worker = null;
                SendError("Could not start the bundled runtime: " + error.Message);
                Send(Event("idle", "task", taskName, "code", -1, "cancelled", false));
            }
        }

        void Finish(Process process, TaskEnd end)
        {
            if (!end.OutputClosed || !end.ErrorClosed || end.ExitCode == null || end.Reported) return;
            end.Reported = true;
            if (worker == process) worker = null;
            Send(Event("idle", "task", taskName, "code", end.ExitCode.Value, "cancelled", cancelled));
            if (quitting) Close();
        }

        static readonly Regex EventName = new Regex("^\\{\"event\":\\s*\"([A-Za-z_]+)\"", RegexOptions.Compiled);

        /// One line of a worker's output. Events are JSON objects that begin with their name; anything else is a log line.
        void Consume(string line)
        {
            line = line.TrimEnd('\r');
            if (line.Length == 0) return;
            var name = line[0] == '{' && line[line.Length - 1] == '}' ? EventName.Match(line, 0, Math.Min(line.Length, 96)) : Match.Empty;
            if (!name.Success) { Send(Event("log", "message", line)); return; }
            var kind = name.Groups[1].Value;
            if (kind == "workspace" || kind == "finished")
            {
                var value = Json.ReadObject(line);
                if (kind == "workspace") lastWorkspace = Json.Str(value, "path") ?? lastWorkspace;
                else lastResult = Json.Str(value, "result") ?? lastResult;
            }
            if (!SendText(line)) { Send(Event("log", "message", line)); return; }
            if (kind == "finished" && lastResult != null) { Remember(lastResult); pendingStep = "review"; ShowResults(lastResult); }
        }

        // ---- trial segmentations: one process that keeps the model loaded between tests -----------------------------------

        void Trial(Dictionary<string, object> request, string text)
        {
            object token;
            request.TryGetValue("token", out token);
            if (worker != null) { Send(Event("trial_error", "token", token, "message", "Wait for the current task to finish.")); return; }
            if (!Running(tester)) StartTester();
            try
            {
                if (tester == null) throw new Exception("The bundled runtime could not start");
                WriteLine(tester, text);
                trialsPending++;
            }
            catch (Exception error)
            {
                StopTester();
                Send(Event("trial_error", "token", token, "message", "The test could not start: " + error.Message));
            }
        }

        void StartTester()
        {
            var process = Python(Path.Combine(resources, "desktop_backend.py"), "--payload", payload, "--serve");
            trialsPending = 0;
            process.OutputDataReceived += (sender, e) => Post(() =>
            {
                Trace("tester out " + (e.Data ?? "<end>"));
                if (tester != process || e.Data == null) return;
                var line = e.Data.TrimEnd('\r');
                var name = line.Length > 1 && line[0] == '{' ? EventName.Match(line, 0, Math.Min(line.Length, 96)) : Match.Empty;
                if (!name.Success || (name.Groups[1].Value != "trial" && name.Groups[1].Value != "trial_error")) return;
                trialsPending = Math.Max(0, trialsPending - 1);
                SendText(line);
            });
            process.ErrorDataReceived += (sender, e) => Trace("tester err " + (e.Data ?? "<end>"));   // library warnings; the page hears about failures as events
            process.Exited += (sender, e) => Post(() =>
            {
                if (tester != process) return;
                // It exits by itself after a while without tests; only a test that was waiting needs to hear about it.
                var waiting = trialsPending > 0;
                tester = null; trialsPending = 0;
                if (waiting) Send(Event("trial_error", "message", "The test stopped unexpectedly. Try again."));
            });
            try { Launch(process); tester = process; }
            catch (Exception) { tester = null; }
        }

        void StopTester()
        {
            var process = tester;
            tester = null; trialsPending = 0;
            try { if (Running(process)) process.Kill(); } catch (Exception) { }
        }

        // ---- Review and Export ---------------------------------------------------------------------------------------------

        void ShowResults(string folder, bool useRandomPort = false)
        {
            if (viewerFolder == folder && viewerUri != null && Running(viewer)) { PresentResults(viewerUri); return; }
            try { resultWeb.CoreWebView2.Stop(); } catch (Exception) { }
            displayedResultFolder = null;
            var old = viewer;
            viewer = null; viewerUri = null; viewerFolder = folder; viewerUsesFallbackPort = useRandomPort;
            var request = ++viewerRequest;
            // The earlier viewer has to let go of the port before the next one asks for it.
            StopViewer(old, () => { if (request == viewerRequest && !quitting) StartViewer(folder, useRandomPort); });
        }

        void StopViewer(Process old, Action then)
        {
            if (!Running(old)) { if (then != null) then(); return; }
            try { WriteLine(old, "stop"); old.StandardInput.Close(); } catch (Exception) { }
            Task.Run(() =>
            {
                try { if (!old.WaitForExit(2500)) { old.Kill(); old.WaitForExit(1500); } } catch (Exception) { }
                if (then != null) Post(then);
            });
        }

        void StartViewer(string folder, bool useRandomPort)
        {
            var stored = Json.Int(settings, "viewerPort") ?? 0;
            var port = useRandomPort ? 0 : (stored > 0 ? stored : 8765);
            var process = Python(Path.Combine(payload, "app", "launcher.py"), "view", "--run", folder, "--port", port.ToString(), "--no-open", "--control-stdin");
            process.OutputDataReceived += (sender, e) => Post(() =>
            {
                Trace("viewer out " + (e.Data ?? "<end>"));
                if (viewer != process || e.Data == null) return;
                var value = e.Data.StartsWith("{", StringComparison.Ordinal) ? Json.ReadObject(e.Data) : null;
                var address = Json.Str(value, "viewer");
                Uri uri;
                if (address == null || !Uri.TryCreate(address, UriKind.Absolute, out uri)) return;
                viewerUri = uri;
                // Remember only the preferred port; a temporary fallback must not move later sessions.
                if (!viewerUsesFallbackPort) { settings["viewerPort"] = uri.Port; SaveSettings(); }
                PresentResults(uri);
                Send(Event("viewer", "url", address));
            });
            process.ErrorDataReceived += (sender, e) => Trace("viewer err " + (e.Data ?? "<end>"));
            process.Exited += (sender, e) => Post(() =>
            {
                Trace("viewer exit");
                if (viewer != process) return;
                int code;
                try { code = process.ExitCode; } catch (Exception) { code = -1; }
                if (code == 0 || viewerUri != null) return;
                if (!useRandomPort) ShowResults(folder, true);
                else SendError("Results were saved, but their local viewer could not start. Open the result folder to inspect the output.");
            });
            viewer = process;
            try { Launch(process); }
            catch (Exception error) { viewer = null; SendError(error.Message); }
        }

        void PresentResults(Uri uri)
        {
            if (!IsResultOrigin(uri.AbsoluteUri)) return;
            if (resultWeb.Source == null || resultWeb.Source.AbsoluteUri != uri.AbsoluteUri || displayedResultFolder != viewerFolder)
            {
                // The view that is showing stays until the new page says it is ready (or shortly after it has loaded),
                // so the window goes from one finished page to the next and never shows an empty one.
                resultWeb.CoreWebView2.Navigate(uri.AbsoluteUri);
                displayedResultFolder = null;
                revealWhenReady = true;
            }
            else { ApplyPendingStep(); ShowReview(); }
        }

        void ReviewLoaded(object sender, CoreWebView2NavigationCompletedEventArgs e)
        {
            if (e.IsSuccess)
            {
                if (viewerUri != null && resultWeb.Source != null && resultWeb.Source.AbsoluteUri == viewerUri.AbsoluteUri)
                {
                    displayedResultFolder = viewerFolder; ApplyPendingStep();
                    // The page normally reports 'ready' within a moment of loading; do not wait for it for long.
                    After(1500, RevealReview);
                }
                UpdateAppearance();
            }
            else if (e.WebErrorStatus != CoreWebView2WebErrorStatus.OperationCanceled && viewerUri != null)
            {
                displayedResultFolder = null; revealWhenReady = false;
                ShowSetup();
                SendError("The results could not be shown. Open saved results to retry. (" + e.WebErrorStatus + ")");
            }
        }

        void ReviewMessage(object sender, CoreWebView2WebMessageReceivedEventArgs e)
        {
            // The review page can only switch back to the setup view, show its own result folder, or say that it has drawn itself.
            if (!IsResultOrigin(e.Source)) return;
            var action = Json.Str(Json.ReadObject(e.WebMessageAsJson), "action");
            if (action == "showSetup") ShowSetup();
            else if (action == "showFolder") { if (viewerFolder != null) ShowFolder(viewerFolder); }
            else if (action == "ready") { ApplyPendingStep(); RevealReview(); }
        }

        void RevealReview()
        {
            if (!revealWhenReady) return;
            revealWhenReady = false;
            ShowReview();
        }

        /// Review or Export, as asked for when the results were opened; applied once the page can take it.
        void ApplyPendingStep()
        {
            if (pendingStep == null) return;
            var step = pendingStep == "export" ? "export" : "review";
            pendingStep = null;
            try { resultWeb.CoreWebView2.ExecuteScriptAsync("window.labShowStep&&window.labShowStep('" + step + "')"); } catch (Exception) { }
        }

        void ShowReview()
        {
            resultWeb.Visible = true;
            resultWeb.BringToFront();
            web.Visible = false;
            var name = viewerFolder == null ? "" : Path.GetFileName(Path.GetDirectoryName(viewerFolder.TrimEnd('\\')) ?? "");
            Text = string.IsNullOrEmpty(name) ? "LabCellpose" : "LabCellpose — " + name;
            resultWeb.Focus();
        }

        void ShowSetup()
        {
            revealWhenReady = false;
            web.Visible = true;
            web.BringToFront();
            resultWeb.Visible = false;
            Text = "LabCellpose";
            web.Focus();
        }

        /// Ctrl-1, -2 and -3 go to Set up, Review and Export (the View menu of the macOS app).
        void StepShortcut(object sender, KeyEventArgs e)
        {
            if (!e.Control || e.Alt || e.Shift) return;
            if (e.KeyCode == Keys.D1) ShowSetup();
            else if ((e.KeyCode == Keys.D2 || e.KeyCode == Keys.D3) && lastResult != null && worker == null)
            {
                pendingStep = e.KeyCode == Keys.D3 ? "export" : "review";
                ShowResults(lastResult);
            }
            else return;
            e.Handled = true; e.SuppressKeyPress = true;
        }

        /// Exports of the review page are downloads; each is saved where the user says.
        void DownloadStarting(object sender, CoreWebView2DownloadStartingEventArgs e)
        {
            e.Handled = true;   // no download bar of the browser
            var operation = e.DownloadOperation;
            if (!IsResultResource(operation.Uri) || !resultWeb.Visible) { e.Cancel = true; return; }
            var suggested = Path.GetFileName(e.ResultFilePath);
            var deferral = e.GetDeferral();
            Post(() =>
            {
                try
                {
                    string destination = null;
#if SELFTEST
                    if (selfTestDownloads != null) destination = Path.Combine(selfTestDownloads, suggested);
#else
                    var extension = Path.GetExtension(suggested).TrimStart('.').ToLowerInvariant();
                    var filter = extension.Length > 0 ? extension.ToUpperInvariant() + " (*." + extension + ")|*." + extension + "|All files|*.*" : "All files|*.*";
                    using (var dialog = new SaveFileDialog { Title = "Save analysis export", FileName = suggested, Filter = filter, OverwritePrompt = true })
                        if (dialog.ShowDialog(this) == DialogResult.OK) destination = dialog.FileName;
#endif
                    if (destination == null) { e.Cancel = true; return; }
                    e.ResultFilePath = destination;
                    downloads++;
                    operation.StateChanged += (source, change) =>
                    {
                        if (operation.State == CoreWebView2DownloadState.InProgress) return;
                        downloads = Math.Max(0, downloads - 1);
                        if (operation.State == CoreWebView2DownloadState.Completed) Send(Event("log", "message", "Export saved to " + destination));
                        else if (operation.InterruptReason != CoreWebView2DownloadInterruptReason.UserCanceled) Alert("Export failed", operation.InterruptReason.ToString());
                    };
                }
                catch (Exception error) { e.Cancel = true; Alert("Unable to save export", error.Message); }
                finally { deferral.Complete(); }
            });
        }

        /// Windows' "Transparency effects" setting, for the pages' overlays.
        void UpdateAppearance()
        {
            var reduced = "false";
            try
            {
                var value = Registry.GetValue(@"HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "EnableTransparency", 1);
                if (value is int && (int)value == 0) reduced = "true";
            }
            catch (Exception) { }
            try
            {
                web.CoreWebView2.ExecuteScriptAsync("document.documentElement.dataset.reduceTransparency='" + reduced + "'");
                resultWeb.CoreWebView2.ExecuteScriptAsync("window.labSetAppearance&&window.labSetAppearance({reduceTransparency:" + reduced + "})");
            }
            catch (Exception) { }
        }

        // ---- quitting -----------------------------------------------------------------------------------------------------

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
#if !SELFTEST
            if (!quitting && e.CloseReason == CloseReason.UserClosing)
            {
                if (downloads > 0)
                {
                    Alert("Export in progress", "Wait for the current file export to finish before quitting.");
                    e.Cancel = true; return;
                }
                if (Running(worker))
                {
                    var answer = MessageBox.Show(this, "Stop the current task and quit?\n\nPartial output will be kept. Run again into a new folder when ready.",
                        "LabCellpose", MessageBoxButtons.YesNo, MessageBoxIcon.Question, MessageBoxDefaultButton.Button2);
                    if (answer != DialogResult.Yes) { e.Cancel = true; return; }
                }
            }
#endif
            if (!quitting)
            {
                // Ask the engine to stop and give it a moment to tidy up; whatever is left ends with the app.
                quitting = true;
                RememberWindow(); SaveSettings();
                e.Cancel = true;
                Hide();
                StopTester();
                var task = worker; var server = viewer;
                try { if (Running(task)) { cancelled = true; WriteLine(task, "stop"); } } catch (Exception) { }
                try { if (Running(server)) { WriteLine(server, "stop"); server.StandardInput.Close(); } } catch (Exception) { }
                Task.Run(() =>
                {
                    try { if (Running(server)) server.WaitForExit(2500); } catch (Exception) { }
                    try { if (Running(task)) task.WaitForExit(3000); } catch (Exception) { }
                    Post(Close);
                });
                return;
            }
            // The session folder holds only this launch's requests and inventories. A process that has just been
            // ended may hold it for a moment longer.
            for (var attempt = 0; attempt < 15 && session != null && Directory.Exists(session); attempt++)
            {
                try { Directory.Delete(session, true); }
                catch (Exception) { System.Threading.Thread.Sleep(100); }
            }
            base.OnFormClosing(e);
        }

#if SELFTEST
        // Compiled only for the scripted check on the build machine, never into the released app. The build follows a
        // script: it opens files, runs JavaScript in a view, reports which view is showing and saves what a view displays.
        CoreWebView2Frame reportFrame;
        string selfTestDownloads;

        async void RunSelfTest()
        {
            var path = Environment.GetEnvironmentVariable("LABCELLPOSE_SELFTEST");
            if (path == null || !File.Exists(path)) return;
            var script = Json.ReadObject(File.ReadAllText(path, Utf8));
            var steps = Json.List(script, "steps");
            var output = Json.Str(script, "out");
            selfTestDownloads = Json.Str(script, "downloads");
            var results = new List<object>();
            Action save = () => { try { File.WriteAllText(output, Json.Write(results), Utf8); } catch (Exception) { } };
            for (var index = 0; index < steps.Count; index++)
            {
                var step = steps[index] as Dictionary<string, object>;
                object value = null;
                try
                {
                    var view = Json.Str(step, "view") == "review" ? resultWeb : web;
                    if (step.ContainsKey("wait")) await Task.Delay((int)(Convert.ToDouble(step["wait"]) * 1000));
                    else if (step.ContainsKey("open")) Open(Json.Str(step, "open"));
                    else if (step.ContainsKey("js")) value = await Evaluate(view, Json.Str(step, "js"), Json.True(step, "frame"));
                    else if (step.ContainsKey("snapshot"))
                    {
                        using (var stream = File.Create(Json.Str(step, "snapshot")))
                            await view.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, stream);
                        value = true;
                    }
                    else if (step.ContainsKey("screen"))
                    {
                        // The window as it is on the screen, title bar included (a page capture shows the page only).
                        Activate(); await Task.Delay(400);
                        using (var image = new Bitmap(Bounds.Width, Bounds.Height))
                        {
                            using (var graphics = Graphics.FromImage(image)) graphics.CopyFromScreen(Bounds.Location, Point.Empty, Bounds.Size);
                            image.Save(Json.Str(step, "screen"), System.Drawing.Imaging.ImageFormat.Png);
                        }
                        value = new Dictionary<string, object> { { "width", Bounds.Width }, { "height", Bounds.Height }, { "dpi", DeviceDpi } };
                    }
                    else if (step.ContainsKey("probe")) value = FolderPicker.Probe();
                    else if (step.ContainsKey("state"))
                        value = new Dictionary<string, object> { { "setupVisible", web.Visible }, { "reviewVisible", resultWeb.Visible }, { "title", Text },
                            { "busy", worker != null }, { "tester", Running(tester) }, { "viewer", Running(viewer) }, { "lastResult", lastResult ?? "" }, { "recents", Recents().Count },
                            { "downloads", downloads } };
                    else if (step.ContainsKey("quit")) { results.Add(new Dictionary<string, object> { { "step", index }, { "result", null } }); save(); Close(); return; }
                    else value = "unknown step";
                }
                catch (Exception error) { value = "ERROR: " + error.Message; }
                results.Add(new Dictionary<string, object> { { "step", index }, { "result", value } });
                save();
            }
        }

        /// The value a script body returns. In the page it may await; in the report's frame it must not.
        async Task<object> Evaluate(WebView2 view, string body, bool frame)
        {
            if (frame)
            {
                if (reportFrame == null) return "no frame";
                var json = await reportFrame.ExecuteScriptAsync("(function(){" + body + "\n})()");
                return Json.ReadObject("{\"value\":" + json + "}")?["value"];
            }
            var parameters = Json.Write(new Dictionary<string, object> { { "expression", "(async()=>{" + body + "\n})()" }, { "awaitPromise", true }, { "returnByValue", true } });
            var reply = Json.ReadObject(await view.CoreWebView2.CallDevToolsProtocolMethodAsync("Runtime.evaluate", parameters));
            var details = Json.Dict(reply, "exceptionDetails");
            if (details != null) return "ERROR: " + (Json.Str(Json.Dict(details, "exception"), "description") ?? Json.Str(details, "text") ?? "script failed");
            object value;
            var result = Json.Dict(reply, "result");
            return result != null && result.TryGetValue("value", out value) ? value : null;
        }
#endif
    }
}
