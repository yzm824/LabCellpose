# Third-party components

LabCellpose's own code is released under the BSD 3-Clause License (`LICENSE` in the source repository, https://github.com/yzm824/LabCellpose). The components below belong to their own authors and keep their own licenses. LabCellpose is an independent project and is not affiliated with or endorsed by any of them.

This distribution redistributes the unmodified Python runtime and installed scientific-library payloads from the validated analysis environment. Python's license is in `licenses/PYTHON_LICENSE.txt`; installed package license notices are retained in their `runtime/lib/python3.12/site-packages/*dist-info` directories and accompanying package data. `DEPENDENCIES.json` records the exact distributions and license-file locations; `requirements.lock.txt` is an inventory, not an installation instruction.

## Cellpose and the model

Cellpose: Howard Hughes Medical Institute and its authors, BSD-3-Clause. The accompanying license is retained in `licenses/CELLPOSE_AND_MODEL_LICENSE.txt` and the Cellpose distribution metadata. Source: https://github.com/MouseLand/cellpose

Bundled checkpoint: `cpsam_v2`, from https://huggingface.co/mouseland/cellpose-sam (model repository declares BSD-3-Clause). SHA256: `0f1cc3f7ecdd8a037a57c6c48d9d8921391be4cbce3fa9f13c3e3a2e1253c667`. No model fine-tuning was performed.

The Cellpose authors state that all Cellpose models are trained on data licensed CC-BY-NC. Use the bundled model for non-commercial research, and ask the Cellpose authors before any commercial use.

The Cellpose authors ask users to cite: Pachitariu, M., Rariden, M., & Stringer, C. (2025). Cellpose-SAM: superhuman generalization for cellular segmentation. bioRxiv. https://www.biorxiv.org/content/10.1101/2025.04.28.651001v1

## LGPL and GPL components

These are unmodified upstream binaries. Each is a separate file under `runtime/lib/python3.12/site-packages/` that can be replaced by a rebuilt version, and its source code is available at the address given. Paths below are relative to that folder.

- `fastremap` 1.20.0, LGPL-3.0. Source: https://github.com/seung-lab/fastremap . License: `fastremap-1.20.0.dist-info/licenses/LICENSE`.
- `fill_voids` 2.1.2, LGPL-3.0-or-later. Source: https://github.com/seung-lab/fill_voids . Licenses (GNU LGPL and GNU GPL, version 3): `fill_voids-2.1.2.dist-info/licenses/COPYING.LESSER` and `COPYING`.
- `opencv-python-headless` 5.0.0.93. OpenCV itself is Apache-2.0. Its official macOS wheel also carries FFmpeg and the libraries FFmpeg was built with, in `cv2/.dylibs/`. That FFmpeg build was configured with `--enable-gpl --enable-version3` and reports its license as GPL version 3 or later. It includes the GPL libraries x264, x265, vid.stab and Rubber Band, and LGPL libraries such as GnuTLS, Nettle, libbluray and LAME. The wheel's own notice, `cv2/LICENSE-3RD-PARTY.txt`, describes the FFmpeg binaries as LGPL-2.1 and does not mention the GPL parts. The text of the GNU GPL version 3 is in `fill_voids-2.1.2.dist-info/licenses/COPYING`. LabCellpose reads and writes TIFF images and calls none of the video functions; these libraries are present only because the OpenCV module loads them. Wheel and build scripts: https://github.com/opencv/opencv-python . Library sources: https://ffmpeg.org , https://www.videolan.org/developers/x264.html , https://www.x265.org , https://github.com/georgmartius/vid.stab , https://breakfastquay.com/rubberband/ .
- `scipy` 1.18.1 carries the GCC runtime libraries `libgfortran`, `libquadmath` and `libgcc_s` in `scipy/.dylibs/` (GPL-3.0-or-later with the GCC Runtime Library Exception). The notices and the exception text are in `scipy-1.18.1.dist-info/LICENSE.txt`.

## Python runtime

The standalone CPython runtime includes its standard-library license and original binaries; Python standalone distribution information: https://github.com/astral-sh/python-build-standalone . The runtime also contains Tcl/Tk 9.0 and libraries built into the interpreter, among them OpenSSL 3.5, SQLite, libffi, XZ, bzip2, expat and mpdecimal. Their license texts are not yet included in this bundle as separate files; they are published by python-build-standalone and by the upstream projects.

The package requires no runtime integration with any AI-assistant product. Upstream compiled binaries may retain build-machine paths as debug metadata or unused search paths; these are not application configuration.

Do not remove the dependency license notices when redistributing this folder. This research bundle makes no claim of endorsement by upstream authors.
