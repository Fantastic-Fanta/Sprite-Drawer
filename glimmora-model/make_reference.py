"""Showdown has no real Mega Glimmora sprite yet: sprites/ani/glimmora-mega.gif is a single
still, an anti-aliased render (239 colours, soft dark rim). This snaps it to a Showdown-style
palette so the pipeline has a crisp reference to fit the pose to and check against:
  * silhouette edge pixels (touching the outside) and very dark interior pixels -> outline
  * every other pixel -> nearest palette shade (all parts; optionally limited by hue per part,
    config "reference_hue_parts")
Run:  python3 -I make_reference.py CONFIG.json STILL.png OUT.png
"""
import json, sys
import numpy as np
from PIL import Image

cfg = json.load(open(sys.argv[1]))
m = np.array(Image.open(sys.argv[2]).convert("RGBA")).astype(int)
hexrgb = lambda h: tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
pal = [(p, i, hexrgb(h)) for p, shades in cfg["palette"]["parts"].items() for i, h in enumerate(shades)]
cols = np.array([c for _, _, c in pal])
solid = m[..., 3] > 127
P = np.pad(~solid, 1, constant_values=True)
edge = solid & (P[:-2, 1:-1] | P[2:, 1:-1] | P[1:-1, :-2] | P[1:-1, 2:])
dark = solid & (m[..., :3].max(-1) < cfg.get("reference_dark_below", 60))
out = np.zeros_like(m)
d2 = ((m[..., None, :3] - cols[None, None]) ** 2).sum(-1).astype(float)
# optional "reference_hue_parts": {part: [hue_min, hue_max]}: a pixel may only snap to such a part
# if its own hue is in range (Glimmora: the crown's slate-lilac separators and the grey-blue spike
# are close in RGB but not in hue)
hue_parts = cfg.get("reference_hue_parts", {})
if hue_parts:
    import colorsys
    hue = np.zeros(m.shape[:2]); sat = np.zeros(m.shape[:2])
    for y, x in zip(*np.nonzero(m[..., 3] > 127)):
        hue[y, x], sat[y, x], _ = colorsys.rgb_to_hsv(*(m[y, x, :3] / 255))
    for k, (p, _, _) in enumerate(pal):
        if p in hue_parts:
            lo, hi, *s = hue_parts[p]          # optional saturation range: [hue_lo, hue_hi, sat_lo, sat_hi]
            ok = (hue >= lo) & (hue < hi)
            if s:
                ok &= (sat >= s[0]) & (sat < s[1])
            d2[..., k] = np.where(ok, d2[..., k], np.inf)
idx = np.argmin(d2, -1)
out[..., :3] = cols[idx]
out[..., 3] = np.where(solid, 255, 0)
out[edge | dark, :3] = hexrgb(cfg["palette"]["outline"])


def thin(mask):
    """Zhang-Suen thinning to 1-px lines"""
    m = np.pad(mask.copy(), 1)
    while True:
        changed = False
        for step in (0, 1):
            P = [np.roll(np.roll(m, -dy, 0), -dx, 1) for dy, dx in
                 ((-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1))]
            B = sum(p.astype(int) for p in P)
            A = sum(((~P[i]) & P[(i + 1) % 8]).astype(int) for i in range(8))
            c1 = (P[0] & P[2] & P[4]) if step == 0 else (P[0] & P[2] & P[6])
            c2 = (P[2] & P[4] & P[6]) if step == 0 else (P[0] & P[4] & P[6])
            rm = m & (B >= 2) & (B <= 6) & (A == 1) & ~c1 & ~c2
            if rm.any():
                m &= ~rm; changed = True
        if not changed:
            return m[1:-1, 1:-1]


# "reference_thin": {"part:i": "part:j"}: a line colour thinned to 1 px like the sprite's own
# lines (the still's soft dark bands snap 2-3 px wide; Showdown draws 1-px lines); the removed
# pixels take colour part:j
for src, dst in cfg.get("reference_thin", {}).items():
    p_, i_ = src.split(":"); q_, j_ = dst.split(":")
    c_src = hexrgb(cfg["palette"]["parts"][p_][int(i_)]); c_dst = hexrgb(cfg["palette"]["parts"][q_][int(j_)])
    msk = solid & np.all(out[..., :3] == c_src, -1)
    keep = thin(msk)
    out[msk & ~keep, :3] = c_dst
out[~solid] = 0
Image.fromarray(out.astype(np.uint8)).save(sys.argv[3])
print("colours used:", len({tuple(c) for c in out[solid][:, :3]}), "outline px:", int((edge | dark).sum()))
