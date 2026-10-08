"""Generated wonder art -> the wonder sprite of civ.WONDER (b_sf_wonder_x1.sld), fitted to the 5x5-tile footprint.

    python make_wonder.py                         # assets/gen/wonder.* -> build/graphics/b_sf_wonder_x1.sld
    python make_wonder.py --src my_wonder.png --out build

The stock wonders sit on their canvas with the footprint's centre at the hotspot; a 5x5-tile
diamond is 480 x 240 px at 1x, so the plaza's left/right corners go to hotspot +/- 240 and its
bottom corner to hotspot + 120. Blue banners -> player colour (same hue mask as the units).
Check the fit in build/previews/wonder_fit.png (1/3 scale, the footprint diamond in red).
"""
import argparse
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import civ as C
import sld
from aoe2paths import DEFAULT_BUILD, asset
from make_sprites import player_mask

W, H, HX, HY = 1300, 1500, 650, 900


def cutout(im, thresh=236):
    a = np.array(im.convert("RGBA"))
    h, w = a.shape[:2]
    bg = np.zeros((h, w), bool)
    light = a[..., :3].min(-1) >= thresh
    q = deque([(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for y in range(h) for x in (0, w - 1)])
    while q:
        x, y = q.popleft()
        if bg[y, x] or not light[y, x]:
            continue
        bg[y, x] = True
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and not bg[ny, nx]:
                q.append((nx, ny))
    a[bg, 3] = 0
    return a


def main(src, out):
    a = cutout(Image.open(src))
    ys, xs = np.nonzero(a[..., 3])
    bottom = ys.max()
    lower = a[..., 3][int(bottom * 0.72):]          # the plaza: widest part near the bottom
    lx = np.nonzero(lower.any(0))[0]
    left, right = lx.min(), lx.max()
    scale = 500 / (right - left)
    im = Image.fromarray(a).resize((int(a.shape[1] * scale), int(a.shape[0] * scale)), Image.LANCZOS)
    b = np.array(im)
    b[..., 3] = np.where(b[..., 3] >= 128, 255, 0)
    canvas = np.zeros((H, W, 4), np.uint8)
    ox = int(HX - (left + right) / 2 * scale)
    oy = int(HY + 122 - bottom * scale)
    y0, x0 = max(0, oy), max(0, ox)
    sub = b[y0 - oy:y0 - oy + H - y0, x0 - ox:x0 - ox + W - x0]
    canvas[y0:y0 + sub.shape[0], x0:x0 + sub.shape[1]] = sub
    m = player_mask(canvas[..., :3], canvas[..., 3], sat_lo=0.5, val_lo=0.35)  # banners only, not bluish shade
    rgb = canvas[..., :3].astype(np.float32)
    lum = (0.3 * rgb[..., 0] + 0.59 * rgb[..., 1] + 0.11 * rgb[..., 2])[..., None]
    k = (m / 255.0)[..., None]
    canvas[..., :3] = (rgb * (1 - k) + np.clip(lum * 1.15, 0, 255) * k).astype(np.uint8)
    graphics, previews = out / "graphics", out / "previews"
    graphics.mkdir(parents=True, exist_ok=True)
    previews.mkdir(parents=True, exist_ok=True)
    path = graphics / f"{C.WONDER['sprite']}_x1.sld"
    sld.write(path, [dict(rgba=canvas, hotspot=(HX, HY), player=m)])
    prev = Image.new("RGBA", (W, H), (80, 120, 60, 255))
    prev.alpha_composite(Image.fromarray(canvas))
    # draw the footprint diamond for checking
    dr = ImageDraw.Draw(prev)
    dr.polygon([(HX - 240, HY), (HX, HY - 120), (HX + 240, HY), (HX, HY + 120)], outline=(255, 0, 0, 255))
    prev.resize((W // 3, H // 3)).save(previews / "wonder_fit.png")
    print("wrote", path, "- scale", round(scale, 3), "player px", int((m > 30).sum()), "top y", int(np.nonzero(canvas[..., 3])[0].min()))
    print("fit preview", previews / "wonder_fit.png")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", help="the wonder art on a white background (default: assets/gen/<civ.WONDER art>.*)")
    ap.add_argument("--out", default=str(DEFAULT_BUILD), help="build folder: writes <out>/graphics and <out>/previews")
    a = ap.parse_args()
    if not C.WONDER:
        ap.error("civ.WONDER is None: the civ keeps the stock wonder")
    main(Path(a.src) if a.src else asset(C.WONDER["art"]), Path(a.out))
