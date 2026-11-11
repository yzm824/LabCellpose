# LabCellpose

A Mac app for cell segmentation and fluorescence measurement with
[Cellpose](https://github.com/MouseLand/cellpose). No Python setup, no Terminal, no cloud:
everything runs on your Mac.

**[Download LabCellpose 3.0](https://github.com/yzm824/LabCellpose/releases/download/v3.0/LabCellpose-3.0-mac-arm64.zip)**
(1.5 GB) · Apple Silicon · macOS 14 or later ·
[all releases](https://github.com/yzm824/LabCellpose/releases)

## Install

1. Download the ZIP above and unzip it.
2. Move `LabCellpose.app` to Applications (or any local folder) and open it.
3. If macOS says it cannot verify the app (it is not notarized by Apple), open
   **System Settings › Privacy & Security** and click **Open Anyway**.

To update, download the new version and replace the old app. Results, settings and review
decisions are kept.

## Use

One window, three steps:

1. **Set up.** Drop a folder, a ZIP or a TIFF on the window. Say which channel shows the cells
   and which channels to measure, test the outlines on one image, then click **Analyze**.
2. **Review.** Step through the cells and press **X** to exclude the ones you do not want.
   Every decision is saved with the results.
3. **Export.** Pick a table (everything, key values, one row per cell, or by condition for
   Prism) and save it as CSV.

Details are in the [user guide](docs/USER_GUIDE.txt); changes in each version are in the
[release notes](docs/RELEASE_NOTES.md).

## Good to know

- **Input:** registered 2D grayscale TIFF, 8 or 16 bit, one page per channel. CZI, ND2, LIF,
  RGB images, z-stacks and time series are not supported.
- **Measurements** use the original pixel values; display contrast never changes them.
- **Check the outlines.** Segmentation is automatic, and cell boundaries and background need a
  look for each assay. This is a research tool, not a validated assay.
- Tested on a single Apple Silicon Mac so far (macOS 27).

## Source

| Folder | Contents |
| --- | --- |
| `desktop/` | macOS shell (Swift, WKWebView), the Set up page and its Python backend |
| `engine/` | analysis, measurement, and the Review and Export pages |
| `macos/` | app metadata and icon |
| `docs/` | user guide and release notes |

The Python runtime and the Cellpose model (Cellpose 4.2.1.1, `cpsam_v2`, Python 3.12) ship inside
the release app, not in this repository, so a source checkout does not run on its own.

## Credits

Developed by Zhenmo Yu. Segmentation by [Cellpose](https://github.com/MouseLand/cellpose);
Cellpose and the other dependencies keep their own authorship and licenses, listed in the
[third-party notices](engine/THIRD_PARTY_NOTICES.md).
