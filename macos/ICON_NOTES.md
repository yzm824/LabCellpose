# LabCellpose 3.0 icon

The icon shows what the app does: one fluorescent cell on the dark image stage, traced by the yellow outline that
marks the selected cell in Review, with two dimmer neighbours at the edges of the tile.

- `AppIcon.svg` is the vector source; `AppIcon-small.svg` is the same mark without the neighbours and with a heavier
  outline, used for the 16 and 32 point sizes, where fine detail would only blur.
- `make_icon.py svg` writes both SVGs (pure Python: the tile is a superellipse, the cell a few harmonics).
- `make_icon.py icns LARGE.png SMALL.png` resamples 2048 px transparent renders of the two SVGs into `AppIcon.icns`
  (16 to 1024 px) and `AppIcon-source.png` (1024 px). For 3.0 the renders were made with WebKit:
  `packaging/macos_app/validation_v3.0/wkshot --transparent`.

It is a static multi-resolution ICNS asset drawn for this app, not an Icon Composer layered icon with system-generated
appearance variants. Versions 1.2.2 to 2.1 used a generated glass-style image.
