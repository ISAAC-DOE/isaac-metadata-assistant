"""
Provenance script for `apps/web/public/favicon*` — regenerates the PNG/ICO
favicon fallbacks from the exact same mark as `favicon.svg`: the app's own
`.brand-tile` (`TopBar.tsx`'s `Brand()` / `chrome.css`, 30x30, rx 8, fill
`--action` #2c6ab0) plus the lucide-react `AudioWaveform` glyph (path copied
verbatim from `node_modules/lucide-react/dist/esm/icons/audio-waveform.js`,
rendered at size 17, strokeWidth 2.2 — the exact props `Brand()` passes).

WHY THIS SCRIPT EXISTS RATHER THAN A ONE-LINE `rsvg-convert favicon.svg`:
no SVG rasterizer (cairo, librsvg, ImageMagick) is installed in the
environment this was written in, and none was installed system-wide to
avoid an unreviewed machine-level dependency. This is pure Python —
`svgpathtools` to sample the path's arcs/lines, Pillow to draw and
downsample — so it needed no new system package. It is NOT invoked by the
app, the build, or CI; it is a provenance/reproducibility record for how the
committed PNG/ICO bytes were produced, to be re-run only if the mark
changes.

Usage (from repo root, in a virtualenv with `pip install pillow
svgpathtools`):

    python3 scripts/render_favicons.py
"""
from pathlib import Path

from svgpathtools import parse_path
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "apps" / "web" / "public"

# Copied verbatim from lucide-react's AudioWaveform icon node.
PATH_D = (
    "M2 13a2 2 0 0 0 2-2V7a2 2 0 0 1 4 0v13a2 2 0 0 0 4 0V4a2 2 0 0 1 4 0"
    "v13a2 2 0 0 0 4 0v-4a2 2 0 0 1 2-2"
)
BG = (0x2C, 0x6A, 0xB0, 255)  # --action, apps/web/src/styles/tokens.css
FG = (0xFF, 0xFF, 0xFF, 255)

TILE = 30.0
ICON_SIZE = 17.0
ICON_SCALE = ICON_SIZE / 24.0  # lucide's native viewBox is 24x24
ICON_INSET = (TILE - ICON_SIZE) / 2.0  # 6.5 — matches the tile's flex centering
STROKE_W_24 = 2.2  # lucide strokeWidth, in 24-unit space, as Brand() passes it

SS = 8  # supersample factor for anti-aliasing before downsampling


def render(size_px: int, out_path: Path, rect_radius_30: float, full_bleed: bool) -> Image.Image:
    big = size_px * SS
    scale = big / TILE  # px per tile-unit (tile is 30 units)

    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if full_bleed:
        # Apple touch icon convention: edge-to-edge square, no pre-rounded
        # corners and no transparency — iOS applies its own corner mask, and
        # a transparent corner would otherwise render as opaque black.
        draw.rectangle([0, 0, big, big], fill=BG)
    else:
        r = rect_radius_30 * scale
        draw.rounded_rectangle([0, 0, big - 1, big - 1], radius=r, fill=BG)

    path = parse_path(PATH_D)
    n = 600
    pts = []
    for i in range(n + 1):
        t = i / n
        c = path.point(t)
        x24, y24 = c.real, c.imag
        x = (ICON_INSET + x24 * ICON_SCALE) * scale
        y = (ICON_INSET + y24 * ICON_SCALE) * scale
        pts.append((x, y))

    stroke_w_px = STROKE_W_24 * ICON_SCALE * scale
    width_i = max(1, round(stroke_w_px))

    # Approximate a round-capped, round-jointed stroke: draw the densely
    # sampled polyline, then stamp a filled circle at every sample point so
    # corners (including the arc turns) stay smooth rather than mitered.
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        draw.line([(x0, y0), (x1, y1)], fill=FG, width=width_i)
    r = stroke_w_px / 2.0
    for x, y in pts:
        draw.ellipse([x - r, y - r, x + r, y + r], fill=FG)

    img = img.resize((size_px, size_px), Image.LANCZOS)
    img.save(out_path)
    print("wrote", out_path, img.size)
    return img


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    im16 = render(16, OUT_DIR / "_favicon-16.png", rect_radius_30=8.0, full_bleed=False)
    im32 = render(32, OUT_DIR / "favicon-32.png", rect_radius_30=8.0, full_bleed=False)
    im48 = render(48, OUT_DIR / "_favicon-48.png", rect_radius_30=8.0, full_bleed=False)
    render(180, OUT_DIR / "apple-touch-icon.png", rect_radius_30=0.0, full_bleed=True)

    # Multi-resolution .ico. Pillow's ICO writer only includes a requested
    # size if some provided image is exactly that size AND no larger than
    # the base image passed to .save() — so the base must be the largest.
    im48.save(
        OUT_DIR / "favicon.ico",
        sizes=[(16, 16), (32, 32), (48, 48)],
        append_images=[im16, im32],
    )
    print("wrote", OUT_DIR / "favicon.ico")

    # The 16px and 48px PNGs are intermediates kept only long enough to
    # build the .ico (favicon-32.png is the one linked directly from
    # index.html for the sizes="32x32" PNG fallback).
    (OUT_DIR / "_favicon-16.png").unlink()
    (OUT_DIR / "_favicon-48.png").unlink()
