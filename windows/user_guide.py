"""The Windows user guide: docs/USER_GUIDE.txt with the passages that only hold for the macOS app replaced.

    python windows/user_guide.py [OUTPUT]

One guide is written by hand; this keeps the Windows copy in step with it. Every replacement must match exactly once,
so a change to the guide that touches one of these passages stops the build until the list below is updated.
"""
from pathlib import Path
import sys

SOURCE = Path(__file__).resolve().parent.parent / 'docs/USER_GUIDE.txt'

REPLACEMENTS = [
    ("LabCellpose 3.0 — Apple Silicon Mac app\n",
     "LabCellpose 3.0 — Windows app (64-bit, runs on the processor)\n"),
    ("Keep the .app intact. You may move it to Applications or another local folder.\n",
     "Unzip the whole LabCellpose folder and start LabCellpose.exe inside it. Keep the folder\n"
     "intact; you may move it as a whole. Unzip it close to the top of a drive (for example\n"
     "C:\\LabCellpose): it holds about 34,000 files, some with long names, and Windows cannot\n"
     "unpack them into a deeply nested folder.\n"
     "The first time, Windows may say \"Windows protected your PC\" because the app is not\n"
     "code-signed: choose More info, then Run anyway.\n"),
    ("go to it (also View menu, Command-1, -2, -3). Review and Export become available when an\n",
     "go to it (also Ctrl-1, -2, -3). Review and Export become available when an\n"),
    ("- Drop a folder, a ZIP or a TIFF on the window (or on the app icon), or click Choose\n",
     "- Drop a folder, a ZIP or a TIFF on the window (or on LabCellpose.exe), or click Choose\n"),
    ("  channels in colour. Pinch to zoom, drag to pan.\n",
     "  channels in colour. Hold Ctrl and scroll (or pinch on a touchpad) to zoom, drag to pan.\n"),
    ("- Several cells at once. Shift-click or Command-click cells, or Shift-drag a box on the\n",
     "- Several cells at once. Shift-click or Ctrl-click cells, or Shift-drag a box on the\n"),
    ("- The folder button at the top right shows the result folder in Finder.\n",
     "- The folder button at the top right shows the result folder in File Explorer.\n"),
    ("Apple Silicon (ARM64), macOS 14 or later is the build target. Tested on one Apple Silicon\n"
     "Mac running macOS 27.0.1, 27.2 and 27.2.1; other Macs and macOS releases are not yet tested.\n"
     "This is a research pilot, not a validated turnkey assay or an App Store release.\n"
     "The app has a local ad-hoc signature, not Apple Developer ID notarization.\n"
     "A downloaded copy may be blocked by macOS. Do not disable system-wide security;\n"
     "have a trusted developer review/sign/notarize it for broader distribution.\n",
     "64-bit Windows 10 or 11 on an Intel or AMD processor is the build target. The pages are\n"
     "shown with Microsoft Edge WebView2, which Windows 11 includes and Windows 10 normally has.\n"
     "This build was made and tested by scripts on a Windows Server 2022 machine; it has not yet\n"
     "been used by a person on a Windows PC.\n"
     "This is a research pilot, not a validated turnkey assay or a Store release.\n"
     "The app is not code-signed. Do not disable system-wide security to run it.\n"
     "\n"
     "Speed. This build finds cells on the processor (CPU) only, not on a graphics card. A\n"
     "768-pixel image took about 30 seconds on a two-core test machine and about 3 seconds on a\n"
     "fast ten-core processor; larger images take longer in proportion to their area.\n"),
    ("runtime and Cellpose model, needed for offline execution. The app keeps, on this Mac\n"
     "only, the list of recent analyses, the settings remembered per image type, the last save\n"
     "location and the window size.\n",
     "runtime and Cellpose model, needed for offline execution. The app keeps, on this computer\n"
     "only (in %LOCALAPPDATA%\\LabCellpose), the list of recent analyses, the settings remembered\n"
     "per image type, the last save location and the window position.\n"),
    ("The original-pixel intensity calculations, the model weights and the bundled runtime are\n"
     "unchanged since 2.1: for the same images and settings, the masks and measurement files of\n"
     "a 3.0 analysis are identical to those of 2.1.\n"
     "Methods, version locks, license notices and version-specific checksums are\n"
     "inside LabCellpose.app/Contents/Resources/payload/. Third-party licenses remain\n"
     "with the corresponding components.\n",
     "The calculations, the model weights and the versions of Cellpose and its libraries are the\n"
     "same as in the macOS app. For program-generated test images the masks and measurement\n"
     "files of this build were identical, byte for byte, to those of the macOS app; this has not\n"
     "been checked for laboratory images or for every processor.\n"
     "Methods, version locks, license notices and version-specific checksums are\n"
     "inside the payload folder. Third-party licenses remain with the corresponding components.\n"),
    ("surround everywhere. With Reduce Transparency switched on in macOS, overlays are solid;\n"
     "with Reduce Motion, changes between steps are not animated. The app icon is a static\n"
     "multi-resolution ICNS asset.\n",
     "surround everywhere. With Transparency effects switched off in Windows, overlays are solid.\n"),
    ("guarantee sufficient memory for every image or model operation on every Mac.\n",
     "guarantee sufficient memory for every image or model operation on every computer.\n"),
    ("server, a running analysis and a running test stop by themselves. A failed GPU run is\n"
     "reported, not silently repeated: choose CPU under More settings and start again.\n",
     "server, a running analysis and a running test stop by themselves.\n"),
]


def windows_guide():
    data = SOURCE.read_bytes()
    if b'\r\n' in data: raise SystemExit('docs/USER_GUIDE.txt has CRLF line endings')
    text = data.decode('utf-8')
    for old, new in REPLACEMENTS:
        if text.count(old) != 1: raise SystemExit('The user guide no longer contains exactly once: ' + old.splitlines()[0])
        text = text.replace(old, new)
    for word in ('macOS', 'Mac ', 'Apple', 'Finder', 'Command-', '.app', 'notariz'):
        left = [line for line in text.splitlines() if word in line and 'macOS app' not in line]
        if left: raise SystemExit(f'The Windows guide still says {word!r}: {left[0]}')
    return text


if __name__ == '__main__':
    guide = windows_guide()
    if len(sys.argv) > 1: Path(sys.argv[1]).write_bytes(guide.replace('\n', '\r\n').encode('utf-8'))
    else: sys.stdout.write(guide)
