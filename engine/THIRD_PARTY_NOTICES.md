# Third-party components

This distribution redistributes the unmodified Python runtime and installed scientific-library payloads from the validated analysis environment. Python's license is in `licenses/PYTHON_LICENSE.txt`; installed package license notices are retained in their `runtime/lib/python3.12/site-packages/*dist-info` directories and accompanying package data. `DEPENDENCIES.json` records the exact distributions and license-file locations; `requirements.lock.txt` is an inventory, not an installation instruction.

Cellpose: Howard Hughes Medical Institute and its authors, BSD-3-Clause. The accompanying license is retained in `licenses/CELLPOSE_AND_MODEL_LICENSE.txt` and the Cellpose distribution metadata. Source: https://github.com/MouseLand/cellpose

Bundled checkpoint: `cpsam_v2`, from https://huggingface.co/mouseland/cellpose-sam (model repository declares BSD-3-Clause). SHA256: `0f1cc3f7ecdd8a037a57c6c48d9d8921391be4cbce3fa9f13c3e3a2e1253c667`. No model fine-tuning was performed.

The standalone CPython runtime includes its standard-library license and original binaries; Python standalone distribution information: https://github.com/astral-sh/python-build-standalone . The package requires no runtime integration with any AI-assistant product. Upstream compiled binaries may retain build-machine paths as debug metadata or unused search paths; these are not application configuration.

Do not remove the dependency license notices when redistributing this folder. This research bundle makes no claim of endorsement by upstream authors.
