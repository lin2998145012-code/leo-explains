"""Cut Leo out of the white background and build expression variants.

Outputs (in assets/):
  leo.png        transparent character
  leo_blink.png  eyes closed (for blinking)
  leo_happy.png  ^ ^ eyes (for the ending)
"""
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "leo.webp"
OUT = ROOT / "assets"

im = Image.open(SRC).convert("RGB")
a = np.asarray(im).astype(np.int16)
h, w, _ = a.shape

# Background = near-white pixels connected to the border (flood fill),
# so white details inside the outline (zipper, eye highlights) survive.
bright = (a.min(axis=2) > 232) & ((a.max(axis=2) - a.min(axis=2)) < 14)
bg = np.zeros((h, w), bool)
q = deque()
for x in range(w):
    for y in (0, h - 1):
        if bright[y, x] and not bg[y, x]:
            bg[y, x] = True; q.append((y, x))
for y in range(h):
    for x in (0, w - 1):
        if bright[y, x] and not bg[y, x]:
            bg[y, x] = True; q.append((y, x))
while q:
    y, x = q.popleft()
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        ny, nx = y + dy, x + dx
        if 0 <= ny < h and 0 <= nx < w and bright[ny, nx] and not bg[ny, nx]:
            bg[ny, nx] = True; q.append((ny, nx))

# White gaps enclosed between hair strands or between the legs are background
# too: small bright blobs entirely above the hairline or below the hem.
HAIRLINE, HEM = 320, 1000
seen = bg.copy()
for sy in list(range(HAIRLINE)) + list(range(HEM, h)):
    for sx in range(w):
        if not bright[sy, sx] or seen[sy, sx]:
            continue
        blob = [(sy, sx)]; seen[sy, sx] = True; i = 0
        while i < len(blob):
            y, x = blob[i]; i += 1
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and bright[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True; blob.append((ny, nx))
        ys = [y for y, _ in blob]
        if len(blob) < 8000 and (max(ys) < HAIRLINE or min(ys) > HEM):
            for y, x in blob:
                bg[y, x] = True

# Drop the soft grey ground shadow under the feet; the video draws its own.
grey = (a.min(axis=2) > 196) & ((a.max(axis=2) - a.min(axis=2)) < 16)
bg[1040:, :] |= grey[1040:, :]

alpha = Image.fromarray(np.where(bg, 0, 255).astype(np.uint8))
alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
rgba = im.copy(); rgba.putalpha(alpha)
bbox = rgba.getbbox()
pad = 8
bbox = (bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad)
print("bbox", bbox, file=sys.stderr)

SKIN = tuple(int(c) for c in np.median(a[420:440, 600:640].reshape(-1, 3), axis=0))
INK = (24, 22, 22)

# Eye regions in source pixels: (cover box, lid line y)
EYES = [((438, 452, 556, 541), 500), ((646, 434, 758, 528), 484)]


def variant(kind):
    v = rgba.copy()
    d = ImageDraw.Draw(v)
    for (x0, y0, x1, y1), ly in EYES:
        d.rounded_rectangle((x0, y0, x1, y1), radius=26, fill=SKIN + (255,))
        if kind == "blink":
            d.arc((x0 + 6, ly - 26, x1 - 6, ly + 22), 15, 165, fill=INK, width=9)
        else:  # happy: upside-down arcs  ^ ^
            d.arc((x0 + 14, ly - 12, x1 - 14, ly + 52), 200, 340, fill=INK, width=10)
    return v


rgba.crop(bbox).save(OUT / "leo.png")
variant("blink").crop(bbox).save(OUT / "leo_blink.png")
variant("happy").crop(bbox).save(OUT / "leo_happy.png")
print("skin", SKIN, file=sys.stderr)
