# LabCellpose 3.0 — build 300

A redesign of the whole app. Cellpose 4.2.1.1, cpsam_v2, the pinned runtime with its precompiled
bytecode and all measurement formulas are unchanged; masks, background masks, measurements.csv,
field_summary.csv and fields.csv are byte-identical to 2.1.

Interface
- Set up, Review and Export are steps of one window (bar at the top; View menu, Command-1, -2, -3)
  instead of a setup window and a separate result window. Every step has the same three panes:
  images on the left, the image in the middle, settings or measurements on the right.
- One dark interface for every step, built from one shared stylesheet, so image contrast is judged
  against the same surround everywhere. Standard macOS title bar. Solid overlays with Reduce
  Transparency; no animation between steps with Reduce Motion.
- New app icon: a fluorescent cell traced by the outline that marks the selected cell in Review.

Set up
- Drop a folder, a ZIP or a TIFF on the window or on the app icon. Recent analyses are listed on the
  start page and reopen with one click.
- Channel roles in plain words: Find cells (Cellpose outlines the cells in this channel) and Measure.
  Show one channel or combine several in colour (Shift-click).
- Cell size can be measured on the image by dragging a line across a cell.
- Test on this image runs Cellpose on the image in the preview only and draws the outlines, with the
  number of cells and their typical width, so the cell size and thresholds can be settled before the
  whole batch is analysed. The model stays loaded between tests. A test saves nothing.
- Names, roles and settings are remembered for images with the same channels and filled in next time;
  Start from the defaults undoes it. Presets remain, under More settings.
- Progress in plain words: Finding cells… 3 of 8 images · Apple GPU.

Review
- Cells: every cell of the image, or of all images, as a small picture below the image. Order them
  flagged first, by number, by size or by brightness. Flags mark cells that touch the image edge, are
  much smaller or larger than the others or contain saturated pixels; they are hints, and nothing is
  excluded automatically.
- Keyboard: arrows move between cells, X excludes or restores, Z undoes, Return marks the image as
  reviewed and goes to the next one, [ and ] change image, 1-9 show a channel, ? lists every shortcut.
- Several cells at once: Shift-click, Command-click or Shift-drag a box on the image, then X.
- Reviewed images get a tick, and a bar shows how far the review is. The marks are saved with the
  decisions; 1.4, 2.0 and 2.1 open such a review with every decision but do not show the marks, and
  a review changed in one of them comes back without the marks.
- Blind review hides file names and conditions and shows the images in a fixed shuffled order.
- Plot of every included cell by condition (image folder); click a dot to go to that cell.
- Several channels can be shown merged in colour. Display settings never enter a measurement.

Export
- The tables are cards: Everything, Key values, One row per cell, By condition, Custom. The first
  rows are shown exactly as they will be saved, with the number of rows and columns and the file name.
- By condition is new: one column per image folder and one row per cell, for a column table in Prism.
- Everything is the same file as All columns in 2.1, byte for byte.

Compatibility
- Reviews made with 1.4, 2.0 or 2.1 open in 3.0 with every decision; a review continued in 3.0 still
  opens in those versions. Results saved by any version since 1.2 reopen without analysing again and
  keep their review identity.
- The app keeps, on this Mac only, the list of recent analyses, the remembered settings, the last
  save location and the window size.

Validation: 54 Python and 64 JavaScript tests pass; doctor --verify-all (32,880 files) and
self-test --inference pass. Masks, background masks and CSV files are byte-identical to 2.1 (Ryu
8 fields; Burak 3 fields x 2 segmentation inputs). The real macOS shell was driven by a script in an
invisible window (15 checks: start page, import of a ZIP, test segmentation, an analysis of two
images, Review and Export in the same window, saving a decision, reopening saved results, recent
analyses). Every state of the three steps was rendered in WebKit from the built app and inspected.
Results saved by 0.3.0, 1.2 and 2.1 reopen with the same review identity; a review saved by 3.0 opens
in 1.4, 2.0 and 2.1 and comes back. See packaging/macos_app/validation_v3.0.

Not verified by automation: the native open and save panels, drag and drop from Finder onto the
window or the app icon, and the look of the title bar; these were not exercised by a person for this
build either. Tested on one Apple Silicon Mac (macOS 27.2.1).

Local ad-hoc signature only; no Apple Developer ID signing or notarization.

# LabCellpose 2.1 — build 210

Review-workflow release following lab feedback. Cellpose 4.2.1.1, cpsam_v2, the pinned runtime with
its precompiled bytecode and all measurement formulas are unchanged; masks, background masks,
measurements.csv, field_summary.csv and fields.csv are byte-identical to 2.0.

- Setup page: Select all and Deselect all are separate buttons next to the FOV list (2.0 had one
  button that switched between Select all and Clear selection). Each is unavailable when it would
  change nothing.
- Results: the manual exclusion controls moved to the top of the measurement panel, directly below
  the background estimator, so Exclude selected object no longer needs scrolling. Click-to-exclude
  and Undo last change sit beside it instead of inside a collapsed section.
- Results: Exclude all in this FOV and Restore all in this FOV act on every object of the current
  segmentation input in the current field as one undoable step; earlier exclusions keep their
  reason and time. To keep only a few cells: exclude all, turn Click-to-exclude on, then click the
  cells to keep.
- QC decisions saved by 2.1, including whole-FOV steps, still open in 1.4 and 2.0.

Validation: 52 Python and 56 JavaScript tests; doctor --verify-all (32,876 files) and self-test
--inference on the packaged app and on a copy extracted from the ZIP; byte-identical outputs against
2.0 for Ryu (8 fields) and Burak (3 fields × 2 inputs); both new controls exercised in WKWebView and
in a browser walkthrough with Ryu's data. See packaging/macos_app/validation_v2.1.

Local ad-hoc signature only; no Apple Developer ID signing or notarization.

# LabCellpose 2.0 — build 200

Usability and speed release, following a full researcher walkthrough of the app and feedback
from the lab. Cellpose 4.2.1.1, cpsam_v2, the pinned runtime and all measurement formulas are
unchanged; masks, measurements.csv and field_summary.csv are byte-identical to 1.4.

- Export contents: the included CSV can hold all columns (as in 1.4, the default), key values
  (whole ROI raw mean, background estimator, background used, corrected mean, image file name,
  image folder and channel name) or a custom choice of regions, measurement channels and
  columns, as one row per measurement or one row per object. QC exclusions and the background
  estimator apply to every layout; the report validates every request again. Exports with
  non-ASCII names start with a UTF-8 BOM for Excel. Files are named after the analysis title.
- fields.csv in each new result folder maps field IDs (CSV rows, mask file names) to image
  name, folder, source file, archive member and mask files, with spreadsheet-safe text.
- Folder imports name images by their path inside the folder (CA/Image 1.tif, DN/Image 1.tif).
- Speed: runtime bytecode is precompiled (hash-checked .pyc covered by FILE_HASHES.json) and
  matplotlib is not loaded for analysis, avoiding a ~10 s macOS font scan per app session.
  Time to the first segmentation fell from 18 s to 4.5 s; an 8-field run from 38 s to 23 s.
- Setup page: every FOV is selected after import (Clear selection to pilot one); ticking FOVs
  no longer loads previews or is blocked by a loading preview; the Run button lists what is
  missing; progress shows tasks done with a determinate bar; plain-word unsupported-file
  reasons; correct singular/plural counts; version badge read from the app bundle; reopened
  results are labelled as saved results.
- Backend: progress events replace raw JSON lines; warnings and tracebacks go to analysis.log
  only; analysis errors name that log; SIGINT is always handled, so Stop works even when the
  launching process ignored SIGINT.

Validation: 52 Python and 54 JavaScript tests; doctor --verify-all (32,876 files) and
self-test --inference; byte-identical masks and CSVs against 1.4 for Ryu (8 fields) and Burak
(3 fields × 2 inputs); saved 0.3.0, 1.2 and 1.4 results reopen with unchanged QC identity;
export contents checked in WKWebView. See packaging/macos_app/validation_v2.0.

Local ad-hoc signature only; no Apple Developer ID signing or notarization.

# LabCellpose 1.4 — build 140

Reliability release from the 2026-10-08 code review, stress and adversarial audit.
Cellpose 4.2.1.1, cpsam_v2, the pinned runtime and all measurement formulas are unchanged.

- Accepted batches can always be reviewed. Previews are sized to a review budget before
  inference; a run whose interactive review would exceed 128 MiB stops early with a clear
  message (completed masks are kept). New results store a slimmer review payload (raw
  values only; the inner-band outline is rebuilt from the whole and interior outlines).
  Older oversized saved results reopen with smaller previews when that is enough, with
  their QC identity unchanged. Clear messages replace "not a regular file" for size limits.
- One corrupt TIFF (e.g. zero tile size) no longer aborts a whole import; every per-file
  decoding error is isolated. Metadata sidecars and inputs must be regular files, so a
  FIFO can no longer hang inspection. Field errors during a run name the file.
- Review decisions are saved in qc_review_state.json in the result folder (token-protected,
  revision-checked, atomic, never following links; damaged or replaced files are backed up).
  Browser storage is a mirror and fallback, so its ~5 MiB shared quota and port changes no
  longer drop decisions; 1.3 browser decisions migrate on first open. Re-importing a QC JSON
  no longer duplicates history. Another window cannot silently replace unsaved decisions,
  and conflict warnings stay visible.
- The result viewer stops when the app exits unexpectedly and removes its temporary report
  when stopped; the analysis worker records an unexpected app exit or SIGTERM as stopped.
  A fallback viewer port is no longer remembered.
- Large backend messages no longer freeze the window (linear line splitting); only the first
  channel group carries previews in the import event, others load on demand. A failed task
  start no longer leaves the setup page busy; task completion waits for all output.
- Cell diameters that would enlarge an image beyond 8192 x 8192 px for Cellpose are refused
  before running, with the smallest workable diameter. CLI configs accept only known Cellpose
  parameters and IDs that start with a letter or digit and are not browser reserved names.
- Report templating inserts each part exactly once, so labels such as "__APP__" cannot break
  the export controls. Strict CSP in the report files (no third-party script origins or eval),
  frame-ancestors/X-Frame-Options, 30 s idle timeout and no per-request logging on localhost.

Validation: 49 Python and 39 JavaScript tests (including new regression tests for every
audit finding; the new tests fail on 1.3). See packaging/macos_app/validation_v1.4.

Local ad-hoc signature only; no Apple Developer ID signing or notarization.

# LabCellpose 1.3 — build 131

Adds selectable background Median (default) and Mean without re-segmentation.
Both statistics are recorded from the same sampled region. The result selector
applies to one measurement channel across all FOVs and segmentation inputs;
readouts, field summaries, exploratory ratios and the included CSV update together.
CSV exports identify the estimator, selected value, mean and median. Review JSON
saves the choices with exclusions and supports undo and reload. The original run
CSV keeps its initial settings. Older runs lacking means remain median-only.

The method selector does not establish that the sampled region is clean; inspect
the background overlay. Raw intensities, masks and saturation counts are unchanged.

## LabCellpose 1.3 — build 130

Repairs eight categories from the adversarial/stress audit: unsafe legacy report
execution and symlink access; corrupt TIFF batch aborts; damaged QC recovery;
stale setup after failed re-scan; missing resource limits; stat-only source
confirmation; non-atomic QC history/size/revision bounds; and formula-like CSV text.

App/package 1.3, build 130. Cellpose 4.2.1.1, cpsam_v2, pinned dependencies,
original-pixel measurement formulas, image navigation and manual review remain.
Structured saved runs keep their original files and QC identity. HTML-only legacy
reports open a safe notice with a CSV download instead of executing supplied code.
Large inputs may need splitting according to the documented capacity limits.

# LabCellpose 1.2.2

Image navigation and a compact, proportionate result workspace.

- Trackpad pinch zooms the image, with bounded drag/two-finger panning and
  fit/object/keyboard controls. Changing channels preserves the viewport;
  changing FOV resets it. Dragging does not accidentally exclude a cell.
- The image frame follows the original image aspect ratio. Square microscopy
  fields use a square viewport; a wider two-column inspector keeps measurements
  and manual exclusion controls together. Display, segmentation, and measurement
  selectors remain prominent. Contrast controls sit next to the image.
- Previous/Next browse FOVs within the same run; the selector jumps directly to
  a FOV. With only one FOV the arrows are hidden and the selector is read-only.
- Light native Liquid Glass navigation on macOS 26+, matched to light setup,
  channel, and export controls. Images and numeric data retain opaque surfaces.
  Older macOS and Reduce Transparency use opaque fallbacks.
- New multi-resolution glass-style icon. This is a static ICNS asset, not a
  layered Icon Composer asset.
- New display previews preserve up to 1,600 pixels on the longest side.
  Existing saved previews retain their original resolution; measurements still
  use the original pixels and zoom is relative to the fitted image.
- Saved runs with viewer_data.json open with the current presentation, rendered
  temporarily without altering source outputs. Preserve exact CSV line endings
  when rebuilding the QC identity so existing saved exclusions still match.
  Legacy reports without viewer_data.json retain their original interface.
- App version/build: 1.2.2 / 122. Cellpose 4.2.1.1, cpsam_v2, quantitative methods,
  model weights, and the v1.2.1 maintenance fixes remain unchanged.

Validation: 22 Python and 15 JavaScript tests passed. Preview checks cover square
and rectangular inputs, resolution limits, and original-pixel immutability.
The user confirmed two-finger pinch on the physical Mac trackpad works normally.
Native review restored the prior QC exclusions and exported 2,061 rows identical
to the v1.2.1 included CSV. Original saved-run checksums remained unchanged.
Packaging integrity is recorded with the build.
These are technical UI and compatibility checks, not biological validation.

Local ad-hoc signature only; no Apple Developer ID signing or notarization.

---

# LabCellpose 1.2.1

Maintenance fixes for review exports, result loading, and input validation.

- Generate only the requested CSV or QC JSON at export time. Remove the old
  50-million-character rejection path; match replies to request, QC revision,
  and segmentation scope. Discard stale replies after QC/scope changes.
- Serve result pages and CSVs with Cache-Control: no-store and ignore conditional
  cache validators. Each viewer session has a fresh URL while preserving the
  localhost origin used for QC storage. Failed report loading can be retried.
- Missing optional Leica exposure, wavelength, saturation, and pixel-spacing
  values remain unknown. Invalid numeric metadata has a per-file diagnostic;
  one malformed sidecar no longer terminates inspection of the whole batch.
- The shared TIFF reader rejects explicit Z/time stacks in both app and CLI paths.
- App version/build: 1.2.1 / 121. Cellpose 4.2.1.1, cpsam_v2, dependencies,
  segmentation parameters, and quantitative measurement methods are unchanged.

Existing result folders are preserved. Report-cache fixes apply when the new app
opens saved runs; the export changes apply to newly generated report pages.

Validation: 21 Python and seven JavaScript regression tests; ten-FOV input
inspection; one fresh CPU inference (230 objects / 2,070 rows) with identical
mask and measurements versus v1.2. Native CSV export and QC JSON save/import
passed; one exclusion removed nine rows, leaving 2,061 unchanged measurements.
Switching from the new report to an older report in the native window kept
the same local port and displayed the correct run.
These are technical checks, not biological validation.

Local ad-hoc signature only;
no Apple Developer ID signing or notarization.

---

# LabCellpose 1.2

Simplified setup, an integrated result window, and a restrained neutral interface.

- Results open inside the app, including Open saved results. Analysis setup
  returns to the main window. CSV/QC exports and QC imports use native dialogs.
  The report retains its sandboxed iframe and has no native command bridge.
- Removed Select first FOV. Preview navigation and batch selection remain.
- Moved Load/Save preset into the collapsed Analysis presets section. Presets
  retain channel labels/roles, segmentation inputs, background settings, model
  parameters, processing device, and analysis title. They do not save image
  selection or output paths. Loading still requires channel confirmation.
- Applied a white canvas and pale neutral cards with #22223B, #4A4E69,
  and #9A8C98 accents to desktop setup and newly generated result viewers. Grayscale image pixels are unchanged.
- Selected ROIs are white; excluded outlines are mauve and dashed;
  sampled background is mauve. Legends and labels describe the new colors.
- App version/build: 1.2 / 120. Cellpose 4.2.1.1, cpsam_v2, dependencies,
  segmentation logic, and quantitative measurement methods remain unchanged.

Earlier result folders and v1.0/v1.1 applications are preserved. Existing viewers
retain their original appearance; new runs use the v1.2 templates. The v1.1
10-FOV, four-input dataset is reused for viewer checks without rerunning inference.

Validation: 14 contract tests; native preset save/load, integrated result opening,
filtered CSV export, and QC JSON save/import. A new single-FOV C4 GUI run produced
230 candidates and 2,070 measurement rows, identical to the corresponding v1.1
mask and measurements. These are technical checks, not expert biological validation.

Local ad-hoc signature only; no Apple Developer ID signing or notarization.
Other physical Macs have not yet been tested.

---

# LabCellpose 1.1

Batch preview and independent multichannel segmentation. Selecting a FOV updates
the channel previews; file-name/Previous/Next controls browse without changing
batch inclusion. Each channel can be enlarged. Select one or more segmentation
inputs, including all channels if useful, and switch their masks in the results.
Object identities and QC exclusions remain separate for each segmentation input.

A single explicitly selected segmentation mask and fluorescence reference define
the background region for each FOV. This background is shared by all segmentation
inputs so switching masks does not silently change the correction method.

Image import checks file structure and metadata automatically. Re-scan image files
is only needed when input files change. It does not perform segmentation.

Viewer FOV names now use original image names. Professional terms replace the
prototype/skill labels. Existing v1.0 configurations and results remain readable.

Cellpose 4.2.1.1, cpsam_v2, and numerical measurement formulas are unchanged.
Ad-hoc signature only; no Apple Developer ID signing or notarization.

Validation: 14 contract tests; 10 Burak FOVs × 4 inputs (40 segmentations,
29,736 measurement rows) with full raw-pixel recomputation. The C4 masks and
measurements exactly matched v1.0. Native GUI preview/enlargement and a two-FOV
four-input run passed. Export tests verified that a C2 object exclusion did not
exclude C4 objects. These checks are not biological accuracy or cross-Mac validation.
