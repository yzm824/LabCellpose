# Input manifest and versioned methods

All paths are relative to the configuration file unless absolute. Example schema (replace input paths and channel roles using actual evidence):

```json
{
  "schema_version": 1,
  "title": "Microscopy pilot",
  "plane_axis": "channel",
  "axis_evidence": "Researcher confirmed TIFF pages are co-registered channels",
  "notes": ["Marker identities and experimental groups are not inferred"],
  "fields": [{"id": "field-001", "path": "images.zip", "member": "experiment/Image 1.tif"}],
  "channels": [
    {"id": "C1", "page": 0, "label": "Fluorescence A", "kind": "fluorescence", "measure": true, "saturation_value": 65535},
    {"id": "C2", "page": 1, "label": "Phase contrast", "kind": "phase", "measure": false}
  ],
  "segmentation_channels": ["C2"],
  "background": {"estimator": "median", "mask_channel": "C2", "foreground_channel": "C1", "mad_multiplier": 5, "dilation_iterations": 5, "min_fraction": 0.01, "min_pixels": 100},
  "edge_width_px": 6,
  "parameters": {"diameter": 60, "flow_threshold": 0.4, "cellprob_threshold": 0, "min_size": 15, "normalize": true, "niter": null, "batch_size": 4, "do_3D": false},
  "ratios": []
}
```

Include every saved channel in page order. `page` is zero-based; IDs and labels are independent of TIFF page number. At least one segmentation and one fluorescence measurement channel are needed. An optional display-only exploratory ratio is `{"label":"B / A", "numerator":"C2", "denominator":"C1"}` where both channels are fluorescence measurements. A positive corrected denominator is required; it does not establish ratio reliability. Ratios are not exported or included in the automated numerical validation; the CSV exports the underlying intensities. `saturation_value` must come from acquisition metadata or a justified explicit setting; omission uses recognized metadata when available, while null explicitly leaves saturation unknown. Container uint16 alone does not establish the detector's clipping level.

Each field may specify `metadata_member` (XML member in the same ZIP), `metadata_path` (local XML), `exposure_seconds` keyed by channel ID, and `pixel_size_um` as `[x,y]`. The narrow Leica XML adapter accepts only saved-channel LUT order matching the first corresponding camera records, and rejects extra Z/T dimensions. It records filter/preset names and wavelengths without turning them into biological identities. Missing metadata stays unknown. Spatial co-registration must be established by the acquisition, not inferred from equal dimensions.

## Method: anchor-mask-mad-v1

For each field, combine the Cellpose mask from `background.mask_channel` with bright foreground in `background.foreground_channel` above `median + mad_multiplier × 1.4826 × MAD`. Apply the configured number of binary dilation iterations (cross-shaped connectivity). Remaining pixels define one background region. Both the mean and median in that same region are calculated separately for each channel and reused across that field's segmentation choices. `background.estimator` selects `median` (default for omitted settings) or `mean` for initial outputs. Background below either configured minimum is flagged; corrected measurements are then missing. The pixel-count thresholds are pilot QC defaults, not a biological proof of clean background. Save and inspect the actual background mask.

Corrected mean = raw ROI mean − selected field/channel background estimate. Corrected sum = raw sum − area × the selected background estimate. The CSV records `background_mean`, `background_median`, `background_estimator` and `background_value`. Results can change the estimator for a channel across all FOVs, without changing raw values or segmentation. Included CSV and on-screen summaries use review settings; the original CSV and field summary retain initial run settings. Review JSON stores per-channel choices with manual exclusions. Older results without stored means disable Mean rather than infer it from the median. Retain negative values. Switching background algorithms can change corrected values and must be identified as a method change.

Whole mask = Cellpose candidate. Inner edge = pixels with Euclidean distance from outside ≤ edge_width_px; interior = complement. Empty interiors are missing. Measurements use native raw pixels; previews alone are downsampled. Saturation counts use the explicit per-channel limit and are not repaired or discarded automatically.

Auto display uses field/channel p10 and p99.9 with the existing asinh transform. Fixed display uses common per-channel limits across the selected run's fields (minimum p10, maximum p99.9) with a linear mapping. Fixed display is not exposure/gain normalization and is run-dependent. Field summaries retain each field and its exposure; no pooled biological statistics are computed.

## Reproducibility scope

The run records the complete config, code/template hashes, input TIFF/XML hashes, model SHA256, Python/library versions, device and precision, saved label masks, numerical checks and run status. It refuses an existing output directory and never silently changes device after an inference error. Seeds and versions improve reproducibility; bitwise mask equality across CPU/MPS/CUDA is not promised. The initial compatibility target is uncompressed grayscale 2D TIFF pages in uint8/uint16; other axes/formats fail explicitly.

The frozen model is `cpsam_v2`, SHA256 `0f1cc3f7ecdd8a037a57c6c48d9d8921391be4cbce3fa9f13c3e3a2e1253c667`. Supply an existing matching weight file separately; it is not bundled. The runner rejects other checkpoints even if their own checksum is valid. Model changes require a separate validation, while channel roles and field paths remain experiment configuration.
