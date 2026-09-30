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
