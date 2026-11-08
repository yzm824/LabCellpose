# LabCellpose 2.1

**Developed by Zhenmo Yu · Powered by Cellpose**

A local Apple Silicon Mac application for 2D cell segmentation, fluorescence
measurements, and manual quality control. No Claude, Codex, Terminal, separate
Python installation, or cloud inference service is required to use the app.

## Download and use

The current release is v2.1 (build 210): Deselect all for FOVs and quicker manual review (exclusion
controls at the top of the measurement panel; exclude or restore a whole FOV in one step). Download
[LabCellpose 2.1 for Apple Silicon Mac](https://github.com/yzm824/LabCellpose/releases/download/v2.1/LabCellpose-2.1-mac-arm64.zip)
from the [LabCellpose 2.1 release](https://github.com/yzm824/LabCellpose/releases/tag/v2.1).
The release also provides a SHA-256 checksum for the app ZIP.
This private repository and its downloads require authorized GitHub access.
Use the app ZIP listed under Assets; GitHub's automatic Source code ZIP contains
source files only and does not include the runtime or model.

1. Extract the ZIP and double-click `LabCellpose.app`.
2. Choose a TIFF, ZIP, or image folder. Every FOV is selected; use **Deselect all** and tick one field to pilot first.
3. Browse FOVs and enlarge channel previews. Confirm channel names/order; choose one or more independent segmentation channels and fluorescence
   channels to measure. Save settings to reuse a matching experiment setup.
4. Choose a results folder and click **Run analysis** (the line below it says what is still missing).
5. Inspect the interactive results. Exclude unwanted candidates with the controls under the background
   estimator (click-to-exclude, or **Exclude all in this FOV** and then click the few objects to keep), choose **Contents** (all columns,
   key values, or your own regions, channels and columns; one row per measurement or per object),
   then select **Download included CSV**. Save the QC decisions JSON to preserve your review.

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

## Changes in 2.1

- **Deselect all.** The FOV list has separate *Select all* and *Deselect all* buttons, so you can
  clear the selection and tick only the fields you need.
- **Quicker manual review.** The exclusion controls sit at the top of the measurement panel, right
  below the background estimator, with *Click-to-exclude* and *Undo* beside *Exclude selected object*.
  *Exclude all in this FOV* and *Restore all in this FOV* act on every object of the current
  segmentation input in one undoable step: to keep only a few cells, exclude all, turn
  *Click-to-exclude* on and click the cells to keep. Reviews saved by 2.1 still open in 1.4 and 2.0.
- Measurements are unchanged: masks and CSV files are byte-identical to 2.0.

## Changes in 2.0

- **Export contents.** Choose what the included CSV holds: *All columns* (as before), *Key values*
  (whole ROI raw mean, background used with its estimator, corrected mean, image and channel
  names) or a custom selection of regions, measurement channels and columns. Choose one row per
  measurement or one row per object (channels and regions side by side). Image file name and
  folder (e.g. the condition folder) can be added; files are named after the analysis title.
- **Readable result folders.** `fields.csv` maps each field ID used in the CSV files and mask
  names to its image, folder and source. Folder imports name images by their path in the folder,
  so equally named files in different condition folders stay distinguishable.
- **Faster.** The first analysis after opening the app starts about 13 s sooner (precompiled
  runtime bytecode; Cellpose no longer loads its plotting library, whose macOS font scan took
  ~10 s). An 8-field run fell from 38 s to 23 s. Import and result opening are faster too.
- **Clearer workflow.** Imports select every FOV; ticking FOVs no longer triggers or waits for
  previews. The Run button explains what is missing, progress shows tasks done, the Activity
  panel shows readable lines without warnings or tracebacks, Stop responds promptly, problems are
  stated in plain words, the version is read from the app, and reopened results are labelled.
- Measurement formulas, Cellpose 4.2.1.1, cpsam_v2 and the pinned runtime are unchanged; masks,
  measurements.csv and field_summary.csv are byte-identical to 1.4 for the same inputs.

## Changes in 1.4

- Every batch the app accepts can be reviewed: previews are sized to a review budget before
  inference, runs that would exceed the 128 MiB review limit stop early with a clear message,
  and older oversized results reopen with smaller previews when possible (QC identity kept).
- One corrupt TIFF or a special file next to the images no longer stops the whole import.
- Review decisions are saved with the results in `qc_review_state.json` (browser storage is a
  mirror), so storage quota, port changes and a second window no longer drop decisions.
- The result viewer and analysis stop cleanly if the app exits unexpectedly; very large
  messages no longer freeze the window; temporary reports are removed.
- Very small cell diameters that would enlarge images beyond 8192 px for Cellpose are refused
  with the smallest workable value. Stricter report CSP and localhost server hardening.
- Measurement formulas, Cellpose 4.2.1.1, cpsam_v2 and the pinned runtime are unchanged.

## Changes in 1.3

- Reject unsafe legacy report execution, symlink assets, and unrelated localhost
  paths; current structured results reopen interactively with the same QC identity.
- Isolate corrupt TIFFs, bound image/archive/batch allocations before decoding,
  and bind inspected images plus metadata to subsequent use with SHA-256.
- Clear stale setup state on re-scan. Restore damaged QC from a valid import or
  explicit backed-up reset; reject edits beyond review limits atomically.
- Neutralize spreadsheet formulas in review CSV text while retaining signed
  numeric intensities. Model weights and measurement formulas are unchanged.
- Select Median (default) or Mean for background subtraction. Both are recorded
  from the same background mask. Per-channel choices apply across all FOVs and
  update readouts, summaries, ratios, and included CSV exports; QC JSON preserves
  the choices. Older saved runs without background means remain median-only.
- App/package version 1.3, build 131. See the user guide for capacity limits and
  the safe handling of legacy HTML-only reports.

## Changes in 1.2.2

- Image-only trackpad pinch zoom, drag/two-finger pan, fit/object navigation,
  zoom buttons, and keyboard alternatives. Channel changes preserve the viewport.
- Clear separation of display, segmentation, and measurement channels; an object
  inspector, per-FOV table, and persistent export bar organize the results. Images
  keep their source aspect ratio, with a wider two-column measurement panel.
- Native Liquid Glass navigation on macOS 26+, with an opaque accessibility and
  older-system fallback. Images and measurements stay on stable opaque surfaces.
- New glass-style app icon. New image previews preserve up to 1,600 pixels.
- Saved runs with viewer_data.json open in the current interface without changing
  source results or their QC identity. Legacy embedded-only reports are preserved.
- Model weights, masks, measurement formulas, and v1.2.1 fixes remain unchanged.

## Changes in 1.2.1

- CSV and QC JSON exports are generated on request and matched to the current QC
  revision and export scope. Changes cancel pending exports; invalid responses
  show an error rather than leaving an older CSV available.
- Opening results uses a fresh URL and disables HTTP caching, including when an
  older run replaces a newer run on the same local port. Failed navigation can retry.
- Missing optional Leica acquisition values remain unknown. Invalid numeric
  metadata is reported per file without aborting the complete input inventory.
- The shared TIFF reader rejects explicit Z/time stacks for both the app and CLI.
- The model, segmentation parameters, and intensity formulas are unchanged.
  Existing self-contained report files retain their original viewer code.

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
Mac running macOS 27.0.1 and 27.2. Other physical Macs and older macOS versions are not yet
verified. This is a research pilot, not a validated turnkey assay.

The native workflow was exercised with one Ryu five-channel field: 4 candidate
cells and 36 measurement rows. Manual exclusion removed all 9 rows belonging to
one candidate, leaving 27 rows with unchanged included measurements. Cancellation
and reopening saved results were checked. Configuration tests covered multiple
channel counts; these tests do not establish accuracy for all cell types/stains.

Version 2.1 validation exercised Deselect all and the whole-FOV exclusion controls with Ryu's data,
in the browser harness and in WKWebView. Masks, background masks and CSV files are byte-identical
to 2.0 (Ryu 8 fields; Burak 3 fields × 2 segmentation inputs). 52 Python and 56 JavaScript tests
pass; `doctor --verify-all` (32,876 files) and `self-test --inference` pass.

Version 2.0 validation walked through the whole workflow as a researcher (import of Ryu's
eight-field, five-channel ZIP; channel naming, presets, run, stop, review, QC, export, reopening
saved 0.3.0/1.2/1.4 results), using the real setup page and backend in a browser harness that
stands in for the native window (native clicks were not automated). For the same inputs,
masks, background masks, measurements.csv and field_summary.csv are byte-identical to 1.4
(Ryu 8 fields; Burak 3 fields × 2 segmentation inputs); saved results keep their QC identity.
Export contents were checked in WKWebView. 52 Python and 54 JavaScript tests pass;
`doctor --verify-all` (32,876 files) and `self-test --inference` pass.

Version 1.4 validation re-ran the 2026-10-08 audit against the new build: the 32-field,
three-input Burak batch that 1.3 could not reopen now completes with 768 px previews and a
98 MiB review that opens in about 1.4 s; masks, measurements.csv and field_summary.csv are
byte-identical to 1.3 for the same inputs; 1.3-era results reopen with unchanged QC identity.
A zero-tile-size TIFF, FIFO sidecars, a full browser storage quota, an app crash during review
or analysis, and a 163 MB backend message no longer stop imports, lose decisions, leave
processes running or freeze the window. 49 Python and 39 JavaScript tests pass.

Version 1.3 validation includes corrupt TIFF/ZIP isolation, predecode and aggregate
budgets, same-stat pixel/metadata replacements, legacy-script and symlink rejection,
QC recovery/concurrency/limits, spreadsheet-safe text, and stale setup invalidation.
Ten Burak fields pass inspection. Fresh CPU inference of Image 12 reproduces all
230 masks and 2,070 measurements byte-for-byte against the 1.2.1 baseline. Native
CSV export retains 2,061 unchanged rows after excluding object 1; reset restores
2,070 rows and preserves a downloadable backup. Cancellation, clean retry, duplicate
output protection, offline runtime integrity and the clean app signature are checked.

Version 1.2.2 passed 22 Python and 15 JavaScript regression tests. Square and
rectangular preview checks preserve source pixels and aspect ratios; existing
CSV line endings and QC identity are retained when refreshing a saved report.
The user confirmed image pinch zoom with the physical trackpad on this Mac.

Version 1.2.1 passed 21 Python contract tests and seven JavaScript QC/export
tests, including an export exceeding 50 million characters. All ten Burak FOVs
passed input inspection. A fresh CPU run of Image 12 matched the v1.2 mask and
all 2,070 measurement rows. Native CSV export removed exactly nine rows for one
excluded object and preserved the other 2,061 rows; QC JSON save/import passed.

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

Pinned engine: Cellpose **4.2.1.1**, **cpsam_v2**, Python **3.12.14**. App and analysis-package version: **2.1**. The model, dependency versions, and
anchor-mask-mad-v1 numerical measurement method are unchanged.

Raw experiment images, analysis output, credentials, and machine-specific user
settings are not part of this repository or its app distribution. Cellpose and
other dependencies retain their original authorship and licenses; see
[third-party notices](engine/THIRD_PARTY_NOTICES.md).
