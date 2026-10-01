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
