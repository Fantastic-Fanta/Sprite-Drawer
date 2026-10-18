"""Seam maps: the lines a sprite artist traces on armour (plate edges, segment grooves), painted in
texture space so they can be rendered on the model (render.seams) and drawn as inner lines.

Run:  python3 -I make_seams.py MODEL_DIR TEXTURE_NAME [--width W] [--groove G] [--out NAME]
                                [--islands ID_OFFSET]
      e.g. make_seams.py MegaGolisopod "pm0867_51_00_body_a_alb (Composite).png" --islands 0
Writes "<texture> (seams).png" next to it: white where a line belongs, black elsewhere.
--islands K also writes "<texture> (islands).png": every UV island (= one armour plate / segment)
in its own colour, ids K+1, K+2, ... (give each texture of a model its own range, e.g. 0 and 256),
coded as base-8 levels of 36 per channel (id = 64 r + 8 g + b, levels r, g, b = value / 36), black =
no island. Rendered as the "islands" texture pass, it tells which plate each sprite pixel shows
(style.plate_shading).
* island borders: every UV island is a separate piece of the model (an armour plate, a segment),
  so a band `W` texels wide inside each island's edge marks where two pieces meet
* grooves: the normal map (same name with _nrm) bends sharply along modelled grooves and bevels;
  texels whose tangent-space normal tilts more than `G` (0..1, length of the x/y part) are seams
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

args = sys.argv[1:]
d = Path(args[0]); name = args[1]
W = int(args[args.index("--width") + 1]) if "--width" in args else 4
G = float(args[args.index("--groove") + 1]) if "--groove" in args else 0.45
alb = np.array(Image.open(d / name).convert("RGBA")).astype(float)
inside = (alb[..., 3] > 127) & (alb[..., :3].max(-1) > 8)      # islands on a black / clear background
H, Wd = inside.shape


def shift(m, dy, dx, fill):
    out = np.full_like(m, fill)
    ys, yd = (slice(dy, None), slice(None, -dy or None)) if dy >= 0 else (slice(None, dy), slice(-dy, None))
    xs, xd = (slice(dx, None), slice(None, -dx or None)) if dx >= 0 else (slice(None, dx), slice(-dx, None))
    out[ys, xs] = m[yd, xd]
    return out


out_m = ~inside
grown = out_m.copy()
for i in range(W):                                   # outside grown W texels into the islands
    g = grown.copy()
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)) + (((1, 1), (-1, -1), (1, -1), (-1, 1)) if i % 2 else ()):
        g |= shift(grown, dy, dx, True)
    grown = g
border = inside & grown

seam = border
nrm_path = d / name.replace("_alb (Composite)", "_nrm")
if nrm_path.exists() and G < 1:
    n = np.array(Image.open(nrm_path).convert("RGB").resize((Wd, H), Image.Resampling.BILINEAR)).astype(float) / 255 * 2 - 1
    tilt = np.hypot(n[..., 0], n[..., 1])
    seam = seam | (inside & (tilt > G))
out_name = args[args.index("--out") + 1] if "--out" in args else name.replace(".png", " (seams).png")
Image.fromarray((seam * 255).astype(np.uint8)).convert("RGB").save(d / out_name)
print(f"{out_name}: {inside.mean():.2f} of the texture is islands, seams {seam.sum() / max(inside.sum(), 1):.3f} of them "
      f"(borders {border.sum() / max(inside.sum(), 1):.3f})")

if "--islands" in args:
    K = int(args[args.index("--islands") + 1])
    ids = np.zeros((H, Wd), np.int32); n = 0
    for y0, x0 in zip(*np.nonzero(inside)):
        if ids[y0, x0]:
            continue
        n += 1; ids[y0, x0] = K + n; st = [(y0, x0)]
        while st:
            y, x = st.pop()
            for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= yy < H and 0 <= xx < Wd and inside[yy, xx] and not ids[yy, xx]:
                    ids[yy, xx] = K + n; st.append((yy, xx))
    assert K + n < 512, f"{K + n} ids: more than the 511 the colour code holds"
    rgb = np.stack([(ids // 64) % 8, (ids // 8) % 8, ids % 8], -1) * 36
    rgb[ids == 0] = 0
    isl_name = name.replace(".png", " (islands).png")
    Image.fromarray(rgb.astype(np.uint8)).save(d / isl_name)
    print(f"{isl_name}: {n} islands, ids {K + 1}..{K + n}")
