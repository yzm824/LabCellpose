# LabCellpose 1.2

**Developed by Zhenmo Yu · Powered by Cellpose**

A local Apple Silicon Mac application for 2D cell segmentation, fluorescence
measurements, and manual quality control. No Claude, Codex, Terminal, separate
Python installation, or cloud inference service is required to use the app.

## Download and use

Download [LabCellpose 1.2 for Apple Silicon Mac](https://github.com/yzm824/LabCellpose/releases/download/v1.2/LabCellpose-1.2-mac-arm64.zip)
from the [LabCellpose 1.2 release](https://github.com/yzm824/LabCellpose/releases/tag/v1.2).
The release also provides a SHA-256 checksum for the app ZIP.
This private repository and its downloads require authorized GitHub access.
Use the app ZIP listed under Assets; GitHub's automatic Source code ZIP contains
source files only and does not include the runtime or model.

1. Extract the ZIP and double-click `LabCellpose.app`.
2. Choose a TIFF, ZIP, or image folder, starting with one representative field.
3. Browse FOVs and enlarge channel previews. Confirm channel names/order; choose one or more independent segmentation channels and fluorescence
   channels to measure. Save settings to reuse a matching experiment setup.
4. Choose a results folder and click **Run analysis**.
5. Inspect the interactive results. Exclude unwanted candidates, then select
   **Download included CSV**. Save the QC decisions JSON to preserve your review.

The app generates and displays the interactive report in its own result window.
CSV and QC JSON exports use native save dialogs; QC JSON can be loaded in the app.
Keep the app open while viewing results; **Open saved results** reopens a completed run without inference.
See [the full user guide](docs/USER_GUIDE.txt) for methods and operating details.

## Input and scientific scope

- Registered 2D grayscale TIFF channel pages, uint8 or uint16; TIFF/ZIP/folder input.
- Variable channel counts, explicit channel roles, and reusable settings.
- Whole-cell candidate masks, background-corrected intensity, geometric inner-edge
  and interior measurements, channel switching, and manual exclusions.
- Nuclei/Golgi/plasma-membrane identity is not inferred from bright spots.
- Native CZI/ND2/LIF, RGB composites, and 3D/time-series analysis are not supported
  by this release. Separate channel files need registration/stack preparation.
- Mean intensity uses original pixels. Display contrast does not change the
  measurements. Background and cell boundaries must be reviewed for each assay.

Each run gets a new output folder. The original CSV retains all candidates; only
**Download included CSV** applies review exclusions. A stopped run retains partial
output and can be retried in a fresh folder.

## Changes in 1.2

- Analysis results open inside the app, including saved runs. Use **Analysis setup**
  to return to setup; exports and QC imports use native file dialogs.

- Removed the redundant **Select first FOV** button; FOV preview/navigation and
  checkbox batch selection are unchanged.
- **Analysis presets** is collapsed by default. **Load preset** and **Save preset**
  reuse channel assignments and parameters without saving image selections or
  output paths. Reconfirm channel assignments after loading.
- Desktop setup, review controls, intensity readout, and export controls use the
  same white and pale neutral palette with slate and mauve accents. Raw images remain
  grayscale. ROI colors and the displayed legend are consistent.
- Cellpose, model weights, measurement formulas, and existing result files are
  unchanged. The prior 1.1 batch validation remains the computational baseline.

## Changes in 1.1

- Selecting a FOV updates the channel preview. File-name buttons and Previous/Next
  controls browse without changing batch inclusion. Click a channel to enlarge it.
- Multiple segmentation inputs are evaluated independently; the results selector
  switches object populations. IDs are not matched between populations.
- A selected background mask supplies one shared background estimate per FOV.
- Original image names appear in the viewer; terminology is standardized.
- Image import automatically checks file structure. **Re-scan image files** repeats
  that check after source files change; it does not segment images.

## Compatibility and validation

Build target: Apple Silicon ARM64, macOS 14 or later. Tested on one Apple Silicon
Mac running macOS 27.0.1. Other physical Macs and older macOS versions are not yet
verified. This is a research pilot, not a validated turnkey assay.

The native workflow was exercised with one Ryu five-channel field: 4 candidate
cells and 36 measurement rows. Manual exclusion removed all 9 rows belonging to
one candidate, leaving 27 rows with unchanged included measurements. Cancellation
and reopening saved results were checked. Configuration tests covered multiple
channel counts; these tests do not establish accuracy for all cell types/stains.

Version 1.2 passed 14 contract tests and native preset save/load, integrated-report
opening, filtered CSV export, and QC JSON save/import checks. A new Burak Image 12
C4 analysis produced 230 candidates and 2,070 measurement rows; its mask hash and
all measurements matched the corresponding v1.1 baseline. The v1.1 baseline
covered 10 Burak FOVs across four segmentation inputs. These checks establish
execution and numerical compatibility, not expert biological validation or
compatibility with every Mac.

The downloadable app has an **ad-hoc local signature**, not an Apple Developer ID
signature or notarization. A downloaded copy may be blocked by macOS. Developer
credit is an authorship label, not Apple identity verification. Do not disable
system-wide security protections to run the app.

## Source layout and pinned runtime

- `desktop/`: Swift AppKit/WKWebView shell, setup interface, Python desktop adapter,
  and configuration tests.
- `engine/`: versioned analysis/measurement/viewer source, templates,
  dependency lock, method description, and third-party notices.
- `macos/`: app metadata and icon.
- `docs/`: usage guide.

The full Python runtime and model live in the Release app at
`Contents/Resources/payload/`. They are deliberately distributed as a Release
asset instead of Git objects. The engine's own `FILE_HASHES.json` is included there
for integrity checks. The source checkout alone is not a standalone installation.

Pinned engine: Cellpose **4.2.1.1**, **cpsam_v2**, Python **3.12.14**. App and analysis-package version: **1.2**. The model, dependency versions, and
anchor-mask-mad-v1 numerical measurement method are unchanged.

Raw experiment images, analysis output, credentials, and machine-specific user
settings are not part of this repository or its app distribution. Cellpose and
other dependencies retain their original authorship and licenses; see
[third-party notices](engine/THIRD_PARTY_NOTICES.md).
