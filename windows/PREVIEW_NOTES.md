**[Download {{ASSET}}](https://github.com/yzm824/LabCellpose/releases/download/{{TAG}}/{{ASSET}})** (1.6 GB) · 64-bit Windows 10 or 11 · Intel or AMD processor

A preview of LabCellpose 3.0 for Windows. It is the same app as [3.0 for Mac](https://github.com/yzm824/LabCellpose/releases/tag/v3.0): the same pages, the same Cellpose version and model, the same measurements.

**Nobody has used this build on a Windows PC yet.** It was built and tested by scripts on a Windows Server machine. Please try it on a few images first, and tell me what goes wrong.

## Install

1. Unzip the download close to the top of a drive, for example into `C:\LabCellpose`. The folder holds about 34,000 files, some with long names: Windows cannot unpack them into a deeply nested folder, and unpacking takes a while.
2. Open the `LabCellpose` folder and start `LabCellpose.exe`.
3. If Windows says "Windows protected your PC" (the app is not code-signed), choose **More info**, then **Run anyway**.

`USER_GUIDE.txt` in the folder describes every step of the app.

## Good to know

- **Speed.** This build finds cells on the processor only; it does not use a graphics card. A 768-pixel image took about 25 seconds on a two-core test machine and about 3 seconds on a fast laptop processor (Apple M4 Pro). Larger images take longer in proportion to their area.
- **Results.** For program-generated test images, the masks and tables were identical, byte for byte, to those of the Mac app. This has not been checked for real images.
- **For non-commercial research**, like the Mac app: the Cellpose authors state that all Cellpose models are trained on data licensed CC-BY-NC.

## What was checked, and what was not

Checked by a script that drives the app on the build machine: importing a folder, the test segmentation, Stop, an analysis, the review, saving the table as CSV, reopening saved results, and quitting.

Not checked by anyone yet: dragging files onto the window, the open and save dialogs, desktop PCs with Windows 10 or 11, high-resolution screens, and how long unpacking takes.

The `.sha256` asset holds the checksum of the ZIP. Source: branch [`windows`](https://github.com/yzm824/LabCellpose/tree/windows), commit {{COMMIT}}. Third-party notices are in `payload\THIRD_PARTY_NOTICES.md` inside the folder.
