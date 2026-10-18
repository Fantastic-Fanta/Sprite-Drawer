"""Learn the game's lighting from the reference frame, as a matcap.

Run:  python3 learn_matcap.py CONFIG.json FRAME0_DIR [--size 9] [--out matcap.json]
Writes CONFIG.json style.matcap (and optionally a standalone matcap.json for reuse with other
Pokémon: X/Y uses the same battle lighting for every Pokémon).

A matcap maps a surface's facing direction (camera-space normal x, y) to a brightness.
We learn it by pairing pixels: stylize frame 0, line it up with the reference (same offset
compare.py uses), and for every pixel where both sprites show the same part, record
(our normal there, the reference's shade rank there, scaled to 0..1 within the part).
Averaging those per direction bin gives the reference's lighting, including things one
light can't do (the back-edge rim light, dark under-chin). Empty bins are filled from
their neighbours. sprite_style.py then uses matcap(normal) instead of normal·light, and
the per-part thresholds are re-matched to the reference's shade mix as usual.
"""
import json
import sys
from pathlib import Path

import numpy as np

import compare
import sprite_style as ss

args = sys.argv[1:]
cfg_path = Path(args[0])
cfg = json.loads(cfg_path.read_text())
N = int(args[args.index("--size") + 1]) if "--size" in args else 9
ref = compare.load(cfg_path.parent / cfg["reference"])
passes = ss.load_passes(args[1], only_first=True)
box, size = ss.framing(passes, cfg["style"]["height"])
f = ss.prepare(cfg, *passes[0], box, size)

# stylize, then crop exactly like compare.load does, carrying the normals along
rgba = ss.stylize(cfg, f)
pad = (rgba.shape[0] - f["solid"].shape[0]) // 2
n_canvas = np.zeros((*rgba.shape[:2], 3)); n_canvas[pad:pad + f["n"].shape[0], pad:pad + f["n"].shape[1]] = f["n"]
ys, xs = np.nonzero(rgba[..., 3] > 0)
y0, x0 = ys.min(), xs.min()
ours = rgba[y0:ys.max() + 1, x0:xs.max() + 1]
n_ours = n_canvas[y0:ys.max() + 1, x0:xs.max() + 1]

res = compare.score(cfg, ref, ours)
PR, RR, PO, RO, union, both, part_ok, same_part, H, W = res["_grids"]
# find our offset inside the comparison canvas: compare places ours at (4+dy, 8+dx)
(iou, dy, dx), _, _ = compare.align(*(compare.describe(a, compare.colour_info(cfg))[0] for a in (ref, ours)))
N_C = np.zeros((H, W, 3)); N_C[4 + dy:4 + dy + ours.shape[0], 8 + dx:8 + dx + ours.shape[1]] = n_ours
# pixels in our cast shadow are left out: the cast-shadow pass explains their darkness, and
# counting them would teach the matcap that those facing directions are dark
CAST = np.zeros((H, W), bool)
if f.get("cast") is not None:
    c_canvas = np.zeros(rgba.shape[:2]); c_canvas[pad:pad + f["cast"].shape[0], pad:pad + f["cast"].shape[1]] = f["cast"]
    CAST[4 + dy:4 + dy + ours.shape[0], 8 + dx:8 + dx + ours.shape[1]] = c_canvas[y0:ys.max() + 1, x0:xs.max() + 1] >= 0.5

samples = []
for name, shades in cfg["palette"]["parts"].items():
    first = cfg["style"]["first_shade"].get(name, 0)
    top = len(shades) - 1
    if top <= first:
        continue
    m = same_part & (PR == name) & (RR >= first) & ~CAST
    v = (RR[m] - first) / (top - first)
    samples.append(np.column_stack([N_C[m][:, 0], N_C[m][:, 1], v]))
S = np.vstack(samples)
print(f"{len(S)} paired pixels (silhouette IoU {iou:.3f})")

# bin by normal x, y in [-1, 1]
ix = np.clip(((S[:, 0] + 1) / 2 * N).astype(int), 0, N - 1)
iy = np.clip(((S[:, 1] + 1) / 2 * N).astype(int), 0, N - 1)
total = np.zeros((N, N)); count = np.zeros((N, N))
np.add.at(total, (iy, ix), S[:, 2]); np.add.at(count, (iy, ix), 1)
mc = np.where(count >= 3, total / np.maximum(count, 1), np.nan)
known = ~np.isnan(mc)
while np.isnan(mc).any():                      # fill empty bins from known neighbours
    filled = mc.copy()
    for y, x in zip(*np.nonzero(np.isnan(mc))):
        nb = mc[max(0, y - 1):y + 2, max(0, x - 1):x + 2]
        if (~np.isnan(nb)).any():
            filled[y, x] = np.nanmean(nb)
    mc = filled
# light smoothing so single noisy bins don't dominate
sm = mc.copy()
for y in range(N):
    for x in range(N):
        nb = mc[max(0, y - 1):y + 2, max(0, x - 1):x + 2]
        sm[y, x] = 0.5 * mc[y, x] + 0.5 * nb.mean()

print("matcap (rows: normal y from down to up; cols: normal x from left to right; 0 dark .. 1 light)")
for y in range(N - 1, -1, -1):
    print("  " + " ".join(f"{v:4.2f}" if known[y, x] else f"({v:3.2f})"[:5] for x, v in enumerate(sm[y])))

matcap = {"size": N, "values": [[round(float(v), 4) for v in row] for row in sm],
          "learned_from": cfg.get("reference_source", cfg["reference"]), "samples": int(len(S))}
cfg = json.loads(cfg_path.read_text())
cfg["style"]["matcap"] = matcap
cfg.setdefault("log", []).append({"step": "learn_matcap", "samples": int(len(S)), "size": N})
cfg_path.write_text(json.dumps(cfg, indent=2))
if "--out" in args:
    Path(args[args.index("--out") + 1]).write_text(json.dumps(matcap, indent=2))
print(f"updated {cfg_path}")
