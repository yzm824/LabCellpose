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

## How to use

One window takes an analysis through three steps.

**1. Set up**

- Drop a folder, a ZIP or a TIFF on the window, or click **Choose images**. Images in
  sub-folders are grouped by folder, and each folder counts as a condition.
- Name the channels and give each a role: **Find cells** (Cellpose outlines the cells in this
  channel) or **Measure** (its intensity is measured inside the outlines).
- Enter the width of a typical cell in pixels, or click **Measure on image** and drag a line
  across one cell.
- Click **Test on this image** to see the outlines on one image. Adjust and test again until
  they look right.
- Choose where to save and click **Analyze**. Every analysis gets a new folder; nothing is
  overwritten.

**2. Review**

- Step through the cells with the arrow keys. **X** excludes or restores a cell, **Z** undoes,
  and **Return** marks the image as reviewed and goes to the next one.
- The strip below the image shows every cell. Cells that touch the image edge, are much
  smaller or larger than the rest, or contain saturated pixels are flagged for a closer look;
  nothing is excluded automatically.
- The panel on the right shows the measurements of the selected cell and a plot of all cells
  by condition. **Blind review** hides file names and conditions.
- Every decision is saved with the results at once.

**3. Export**

- Pick a table: **Everything**, **Key values**, **One row per cell**, **By condition** (one
  column per folder, for Prism) or **Custom**.
- Check the preview and click **Save table as CSV**. Excluded cells are left out.

**Open results** reopens a finished analysis later, with its review, without analysing again.
The [user guide](docs/USER_GUIDE.txt) has the details, including what each number means.

## Good to know

- **Input:** registered 2D grayscale TIFF, 8 or 16 bit, one page per channel. CZI, ND2, LIF,
  RGB images, z-stacks and time series are not supported.
- **Measurements** use the original pixel values; display contrast never changes them. The
  corrected mean is the mean inside the outline minus the background of that image and channel.
- **Check the outlines.** Segmentation is automatic, and cell boundaries and background need a
  look for each assay. This is a research tool, not a validated assay.
- Tested on a single Apple Silicon Mac so far (macOS 27).

## Version history

| Version | Released | What changed |
| --- | --- | --- |
| [3.0](https://github.com/yzm824/LabCellpose/releases/tag/v3.0) | Nov&nbsp;2026 | Redesigned: Set up, Review and Export are three steps of one dark window. Test the segmentation on one image first, review with a cell gallery and the keyboard, blind review, *By condition* table for Prism, new icon. |
| [2.1](https://github.com/yzm824/LabCellpose/releases/tag/v2.1) | Nov&nbsp;2026 | *Deselect all* for the image list; exclusion controls at the top of the panel; exclude or restore every cell of an image in one step. |
| [2.0](https://github.com/yzm824/LabCellpose/releases/tag/v2.0) | Oct&nbsp;2026 | Choose what the exported CSV contains (all columns, key values or your own selection; one row per measurement or per cell). Result folders list image names in `fields.csv`. The first analysis starts about 13 s sooner. |
| [1.4](https://github.com/yzm824/LabCellpose/releases/tag/v1.4) | Oct&nbsp;2026 | Large batches can always be reviewed; review decisions are saved in the result folder; one damaged TIFF no longer stops an import. |
| [1.3](https://github.com/yzm824/LabCellpose/releases/tag/v1.3) | Sep&nbsp;2026 | Median or mean background, chosen per channel; safer handling of damaged files and old reports. |
| [1.2](https://github.com/yzm824/LabCellpose/releases/tag/v1.2)&nbsp;–&nbsp;1.2.2 | Sep&nbsp;2026 | Results open inside the app; presets; pinch to zoom and drag to pan; cell inspector and per-image table. |
| 1.1 | Sep&nbsp;2026 | Channel preview for every image; several channels can be segmented, each with its own set of cells; one shared background per image. |
| [1.0](https://github.com/yzm824/LabCellpose/releases/tag/v1.0) | Sep&nbsp;2026 | First release: Cellpose segmentation, fluorescence measurement and manual exclusion in a local Mac app. |

Segmentation (Cellpose 4.2.1.1, `cpsam_v2`) and the measurement formulas are the same in every
version; 1.4 to 3.0 were checked to give byte-identical masks and tables for the same images
and settings. Full notes are in [RELEASE_NOTES.md](docs/RELEASE_NOTES.md).

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
