# LabCellpose 1.0

**Developed by Zhenmo Yu · Powered by Cellpose**

A local Apple Silicon Mac application for 2D cell segmentation, fluorescence
measurements, and manual quality control. No Claude, Codex, Terminal, separate
Python installation, or cloud inference service is required to use the app.

## Download and use

Download [LabCellpose 1.0 for Apple Silicon Mac](https://github.com/yzm824/LabCellpose/releases/download/v1.0/LabCellpose-1.0-mac-arm64.zip)
from the [LabCellpose 1.0 release](https://github.com/yzm824/LabCellpose/releases/tag/v1.0).
This private repository and its downloads require authorized GitHub access.
Use the app ZIP listed under Assets; GitHub's automatic Source code ZIP contains
source files only and does not include the runtime or model.

1. Extract the ZIP and double-click `LabCellpose.app`.
2. Choose a TIFF, ZIP, or image folder, starting with one representative field.
3. Confirm channel names/order; choose one segmentation channel and fluorescence
   channels to measure. Save settings to reuse a matching experiment setup.
4. Choose a results folder and click **Run analysis**.
5. Inspect the interactive results. Exclude unwanted candidates, then select
   **Download included CSV**. Save the QC decisions JSON to preserve your review.

The app generates the interactive viewer automatically. Keep the app open while
viewing results; **Open saved results** reopens a completed run without inference.
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

## Compatibility and validation

Build target: Apple Silicon ARM64, macOS 14 or later. Tested on one Apple Silicon
Mac running macOS 27.0.1. Other physical Macs and older macOS versions are not yet
verified. This is a research pilot, not a validated turnkey assay.

The native workflow was exercised with one Ryu five-channel field: 4 candidate
cells and 36 measurement rows. Manual exclusion removed all 9 rows belonging to
one candidate, leaving 27 rows with unchanged included measurements. Cancellation
and reopening saved results were checked. Configuration tests covered multiple
channel counts; these tests do not establish accuracy for all cell types/stains.

The downloadable app has an **ad-hoc local signature**, not an Apple Developer ID
signature or notarization. A downloaded copy may be blocked by macOS. Developer
credit is an authorship label, not Apple identity verification. Do not disable
system-wide security protections to run the app.

## Source layout and pinned runtime

- `desktop/`: Swift AppKit/WKWebView shell, setup interface, Python desktop adapter,
  and configuration tests.
- `engine/`: the unchanged 0.3.0 analysis/measurement/viewer source, templates,
  dependency lock, method description, and third-party notices.
- `macos/`: app metadata and icon.
- `docs/`: usage guide.

The full Python runtime and model live in the Release app at
`Contents/Resources/payload/`. They are deliberately distributed as a Release
asset instead of Git objects. The engine's own `FILE_HASHES.json` is included there
for integrity checks. The source checkout alone is not a standalone installation.

Pinned engine: Cellpose **4.2.1.1**, **cpsam_v2**, Python **3.12.14**. App version is
**1.0**; the frozen engine's run manifests retain **0.3.0** for provenance.

Raw experiment images, analysis output, credentials, and machine-specific user
settings are not part of this repository or its app distribution. Cellpose and
other dependencies retain their original authorship and licenses; see
[third-party notices](engine/THIRD_PARTY_NOTICES.md).
