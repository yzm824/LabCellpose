# Third-party components (Windows package)

LabCellpose's own code is released under the BSD 3-Clause License (`LICENSE.txt` beside `LabCellpose.exe`; source: https://github.com/yzm824/LabCellpose). The components below belong to their own authors and keep their own licenses. LabCellpose is an independent project and is not affiliated with or endorsed by any of them.

This package redistributes an unmodified standalone Python runtime and unmodified Python packages installed from their official Windows wheels. Python's license is in `licenses/PYTHON_LICENSE.txt`; the license notices of the packages are kept in `runtime\Lib\site-packages\*.dist-info` and in the package folders. `DEPENDENCIES.json` records every distribution with its version and the location of its license files; `requirements.lock.txt` lists the same versions and is an inventory, not an installation instruction. The versions of Cellpose and of the libraries it computes with are the same as in the macOS app.

## Cellpose and the model

Cellpose: Howard Hughes Medical Institute and its authors, BSD-3-Clause. The accompanying license is retained in `licenses/CELLPOSE_AND_MODEL_LICENSE.txt` and the Cellpose distribution metadata. Source: https://github.com/MouseLand/cellpose

Bundled checkpoint: `cpsam_v2`, from https://huggingface.co/mouseland/cellpose-sam (model repository declares BSD-3-Clause). SHA256: `0f1cc3f7ecdd8a037a57c6c48d9d8921391be4cbce3fa9f13c3e3a2e1253c667`. No model fine-tuning was performed.

The Cellpose authors state that all Cellpose models are trained on data licensed CC-BY-NC. Use the bundled model for non-commercial research, and ask the Cellpose authors before any commercial use.

The Cellpose authors ask users to cite: Pachitariu, M., Rariden, M., & Stringer, C. (2025). Cellpose-SAM: superhuman generalization for cellular segmentation. bioRxiv. https://www.biorxiv.org/content/10.1101/2025.04.28.651001v1

## LGPL components and the GCC runtime

These are unmodified upstream binaries. Each is a separate file under `runtime\Lib\site-packages\` that can be replaced by a rebuilt version, and its source code is available at the address given. Paths below are relative to that folder.

- `fastremap` 1.20.0, LGPL-3.0. Source: https://github.com/seung-lab/fastremap . License: `fastremap-1.20.0.dist-info\licenses\LICENSE`.
- `fill_voids` 2.1.2, LGPL-3.0-or-later. Source: https://github.com/seung-lab/fill_voids . Licenses (GNU LGPL and GNU GPL, version 3): `fill_voids-2.1.2.dist-info\licenses\COPYING.LESSER` and `COPYING`.
- `opencv-python-headless` 5.0.0.93. OpenCV itself is Apache-2.0. Its official Windows wheel carries one FFmpeg library, `cv2\opencv_videoio_ffmpeg500_64.dll`. That build reports its license as LGPL version 2.1 or later and was configured without the GPL parts; the wheel's notice, `cv2\LICENSE-3RD-PARTY.txt`, contains the text of the LGPL 2.1. LabCellpose reads and writes TIFF images and calls none of the video functions; the library is present only because it is part of the OpenCV wheel. Wheel and build scripts: https://github.com/opencv/opencv-python . FFmpeg source: https://ffmpeg.org .
- `numpy` 2.5.3 and `scipy` 1.18.1 each carry OpenBLAS (BSD-3-Clause) in `numpy.libs\` and `scipy.libs\`. The GCC runtime libraries are linked into those files (GPL-3.0-or-later with the GCC Runtime Library Exception). The notices and the exception text are in `numpy-2.5.3.dist-info\licenses\LICENSE.txt` and `scipy-1.18.1.dist-info\LICENSE.txt`.

## Python runtime

The standalone CPython runtime (https://github.com/astral-sh/python-build-standalone) includes its standard-library license and original binaries. It also contains OpenSSL 3, SQLite, libffi, Tcl/Tk 8.6 and the libraries built into its extension modules (among them bzip2, XZ, zlib, expat and mpdecimal), and the Microsoft Visual C++ runtime files `vcruntime140.dll` and `vcruntime140_1.dll` (numpy and pandas carry `msvcp140` as well). The license texts of these libraries are not yet included in this package as separate files; they are published by python-build-standalone and by the upstream projects.

## The window

`LabCellpose.exe` shows its pages with Microsoft Edge WebView2. `Microsoft.Web.WebView2.Core.dll`, `Microsoft.Web.WebView2.WinForms.dll` and `WebView2Loader.dll` beside it are the unmodified WebView2 SDK files from Microsoft (BSD-style license, in `licenses/WEBVIEW2_LICENSE.txt`). The WebView2 Runtime itself is part of Windows and is not included. It is a web browser component maintained by Microsoft and may contact Microsoft on its own, for example to update itself; LabCellpose sends it only local pages, and the analysis uses no network.

The package requires no runtime integration with any AI-assistant product. Upstream compiled binaries may retain build-machine paths as debug metadata or unused search paths; these are not application configuration.

Do not remove the dependency license notices when redistributing this folder. This research bundle makes no claim of endorsement by upstream authors.
