"""Draw the LabCellpose app icon and build AppIcon.icns.

    python3 make_icon.py svg                      write AppIcon.svg and AppIcon-small.svg (vector sources, pure Python)
    python3 make_icon.py icns LARGE.png SMALL.png build AppIcon.icns and AppIcon-source.png from renders of the two SVGs

The icon shows what the app does: one fluorescent cell on the dark image stage, traced by the yellow outline that marks
the selected cell in Review, with two dimmer neighbours. AppIcon-small.svg is the same mark without the neighbours and
with a heavier outline; it is used for the 16 and 32 point sizes, where fine detail would only blur.

The SVGs are rendered to PNG (2048 px, transparent) with a browser engine - for 3.0,
packaging/macos_app/validation_v3.0/wkshot --transparent - and this script resamples them into the icon set.
Requires Pillow for the icns step; iconutil is part of macOS.
"""
from pathlib import Path
import math, subprocess, sys, tempfile

HERE = Path(__file__).resolve().parent
SIZE = 1024


def squircle(cx, cy, half, n=5.0, steps=180):
    """A superellipse: the continuous-corner tile of macOS icons."""
    points = []
    for i in range(steps):
        t = 2 * math.pi * i / steps
        c, s = math.cos(t), math.sin(t)
        points.append((cx + half * math.copysign(abs(c) ** (2 / n), c), cy + half * math.copysign(abs(s) ** (2 / n), s)))
    return 'M' + 'L'.join(f'{x:.1f},{y:.1f}' for x, y in points) + 'Z'


def blob(cx, cy, base, terms, rotate, grow=0.0, steps=96):
    """A smooth closed cell outline from a few harmonics; grow moves every point outward along its normal."""
    def radius(t): return base * (1 + sum(a * math.cos(k * (t - p)) for k, a, p in terms))
    def point(t):
        r = radius(t); return r * math.cos(t), r * math.sin(t)
    raw = []
    for i in range(steps):
        t = 2 * math.pi * i / steps
        x, y = point(t)
        if grow:
            (x0, y0), (x1, y1) = point(t - 1e-3), point(t + 1e-3)
            dx, dy = x1 - x0, y1 - y0; length = math.hypot(dx, dy)
            x, y = x + grow * dy / length, y - grow * dx / length
        a = math.radians(rotate)
        raw.append((cx + x * math.cos(a) - y * math.sin(a), cy + x * math.sin(a) + y * math.cos(a)))
    # Catmull-Rom through the points, written as cubic Beziers.
    path = [f'M{raw[0][0]:.1f},{raw[0][1]:.1f}']
    for i in range(steps):
        p0, p1, p2, p3 = raw[i - 1], raw[i], raw[(i + 1) % steps], raw[(i + 2) % steps]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6); c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        path.append(f'C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}')
    return ''.join(path) + 'Z'


CELL = dict(terms=[(1, .13, .25), (2, .25, 0.0), (3, .045, .55)], rotate=-40)


def icon(small=False):
    tile = squircle(512, 512, 412)
    scale = 1.13 if small else 1.0
    cell = blob(506, 522, 192 * scale, **CELL)
    ring = blob(506, 522, 192 * scale, grow=(44 if small else 34) * scale, **CELL)
    neighbours = '' if small else f'''
  <g clip-path="url(#tile)" opacity=".9">
   <path d="{blob(178, 846, 150, [(2, .2, .4), (3, .05, 0)], 20)}" fill="url(#dim)"/>
   <path d="{blob(178, 846, 150, [(2, .2, .4), (3, .05, 0)], 20, grow=22)}" fill="none" stroke="#FFFFFF" stroke-opacity=".3" stroke-width="8"/>
   <path d="{blob(862, 196, 128, [(2, .22, 1.1), (3, .05, .3)], -10)}" fill="url(#dim)"/>
   <path d="{blob(862, 196, 128, [(2, .22, 1.1), (3, .05, .3)], -10, grow=20)}" fill="none" stroke="#FFFFFF" stroke-opacity=".3" stroke-width="8"/>
  </g>'''
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}" width="{SIZE}" height="{SIZE}">
 <defs>
  <clipPath id="tile"><path d="{tile}"/></clipPath>
  <linearGradient id="stage" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2A3157"/><stop offset=".55" stop-color="#141831"/><stop offset="1" stop-color="#0A0C19"/></linearGradient>
  <radialGradient id="halo" cx="512" cy="520" r="430" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#3BE69A" stop-opacity=".34"/><stop offset=".55" stop-color="#2BC8A0" stop-opacity=".10"/><stop offset="1" stop-color="#2BC8A0" stop-opacity="0"/></radialGradient>
  <radialGradient id="cell" cx="456" cy="462" r="340" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#DFFFEA"/><stop offset=".25" stop-color="#8FF3B7"/><stop offset=".6" stop-color="#37D588"/><stop offset="1" stop-color="#0D8A60"/></radialGradient>
  <radialGradient id="dim" cx=".42" cy=".4" r=".7"><stop offset="0" stop-color="#4FD8A4" stop-opacity=".34"/><stop offset="1" stop-color="#2AA08A" stop-opacity=".14"/></radialGradient>
  <radialGradient id="nucleus" cx=".4" cy=".38" r=".7"><stop offset="0" stop-color="#0B6B4E" stop-opacity=".5"/><stop offset="1" stop-color="#0B6B4E" stop-opacity=".2"/></radialGradient>
  <linearGradient id="rim" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF" stop-opacity=".34"/><stop offset=".3" stop-color="#FFFFFF" stop-opacity=".05"/><stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/></linearGradient>
  <filter id="shadow" x="-20%" y="-20%" width="140%" height="150%"><feDropShadow dx="0" dy="16" stdDeviation="20" flood-color="#000" flood-opacity=".38"/></filter>
  <filter id="glow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="16"/></filter>
  <filter id="soft" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="26"/></filter>
 </defs>
 <path d="{tile}" fill="url(#stage)" filter="url(#shadow)"/>
 <g clip-path="url(#tile)"><rect width="{SIZE}" height="{SIZE}" fill="url(#halo)"/></g>{neighbours}
 <path d="{ring}" fill="none" stroke="#FFD43B" stroke-width="{34 if small else 26}" stroke-opacity=".55" filter="url(#glow)"/>
 <path d="{cell}" fill="url(#cell)"/>
 <ellipse cx="556" cy="560" rx="{74 * scale:.0f}" ry="{58 * scale:.0f}" transform="rotate(-40 556 560)" fill="url(#nucleus)"/>
 <ellipse cx="440" cy="452" rx="{92 * scale:.0f}" ry="{56 * scale:.0f}" transform="rotate(-40 440 452)" fill="#FFFFFF" fill-opacity=".3" filter="url(#soft)"/>
 <path d="{ring}" fill="none" stroke="#FFD43B" stroke-width="{38 if small else 24}" stroke-linejoin="round"/>
 <path d="{tile}" fill="none" stroke="url(#rim)" stroke-width="5"/>
</svg>
'''


def write_svgs():
    (HERE / 'AppIcon.svg').write_text(icon())
    (HERE / 'AppIcon-small.svg').write_text(icon(small=True))


def build_icns(large, small):
    from PIL import Image
    big, little = Image.open(large).convert('RGBA'), Image.open(small).convert('RGBA')
    if big.size[0] != big.size[1] or big.size[0] < 1024 or little.size != big.size: raise SystemExit('Render both SVGs square, at 1024 px or more.')
    big.resize((1024, 1024), Image.Resampling.LANCZOS).save(HERE / 'AppIcon-source.png')
    with tempfile.TemporaryDirectory() as temp:
        iconset = Path(temp) / 'AppIcon.iconset'; iconset.mkdir()
        for points in (16, 32, 128, 256, 512):
            for factor in (1, 2):
                pixels = points * factor
                source = little if pixels <= 64 else big
                source.resize((pixels, pixels), Image.Resampling.LANCZOS).save(iconset / f'icon_{points}x{points}{"@2x" if factor == 2 else ""}.png')
        subprocess.run(['/usr/bin/iconutil', '-c', 'icns', str(iconset), '-o', str(HERE / 'AppIcon.icns')], check=True)


if __name__ == '__main__':
    if sys.argv[1:] == ['svg']: write_svgs()
    elif len(sys.argv) == 4 and sys.argv[1] == 'icns': build_icns(sys.argv[2], sys.argv[3])
    else: raise SystemExit(__doc__)
