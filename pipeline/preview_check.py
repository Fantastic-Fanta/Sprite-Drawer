"""Quick look at a motion before a full run: draw the given rendered frames on their own and
report, per frame, the per-frame rules (thick lines, 2-px diagonals, open outline, teeth) and the
smallest gap between two parts (e.g. crown and petal: a 1-px gap opening and closing is the usual
cause of pops). Seconds, not minutes; time-based checks (flicker, pops) still need the full loop.

Run:  python3 preview_check.py CONFIG.json FRAMES_DIR PART_A PART_B [--png out.png]
FRAMES_DIR holds render_parallel.py output for some frames (--frames ...).
"""
import json
import sys

import numpy as np
from PIL import Image

import check_loop as cl
import compare
import sprite_style as ss

args = sys.argv[1:]
cfg = json.load(open(args[0])); fdir, pa, pb = args[1], args[2], args[3]
passes = ss.load_passes(fdir)
names = sorted(p.name for p in __import__("pathlib").Path(fdir).glob("color_*.png"))
box, size = ss.framing(passes, cfg["style"]["height"], anchor=[0])
info = compare.colour_info(cfg)
LINE = [cl.hexrgb(cfg["palette"]["outline"])] + [cl.colour_ref(cfg, r) for r in cfg["style"].get("dark_line_colours", [])]
imgs = []
for name, p in zip(names, passes):
    f = ss.prepare(cfg, *p, box, size)
    s = ss.stylize(cfg, f)
    s = ss.clean_lines(cfg, ss.smooth_silhouette(cfg, ss.repair(cfg, s)), corners=True)
    l = (s[..., 3] > 0) & np.any([np.all(s[..., :3] == c, -1) for c in LINE], 0)
    z = np.zeros(l.shape, bool)
    P, _ = compare.describe(s, info)
    a, b = P == pa, P == pb
    # smallest Chebyshev distance between the two parts' pixels
    gap = 99
    if a.any() and b.any():
        ya, xa = np.nonzero(a); yb, xb = np.nonzero(b)
        A = np.stack([ya, xa], 1)[:, None]; B = np.stack([yb, xb], 1)[None]
        gap = int(np.abs(A - B).max(-1).min())
    print(f"{name}: thick {cl.line_blocks(s, l)}  diag {cl.stairs(s, l, cl.separators(cfg, s, l, z))}  "
          f"open {cl.open_outline(cfg, s, l, z)}  teeth {cl.teeth(cfg, s)}  closest {pa}-{pb} {gap} px")
    imgs.append(s)
if "--png" in args:
    K = 3; h, w = imgs[0].shape[:2]
    o = Image.new("RGBA", (len(imgs) * (w * K + 6), h * K), (110, 110, 120, 255))
    for i, s in enumerate(imgs):
        o.alpha_composite(Image.fromarray(s).resize((w * K, h * K), Image.Resampling.NEAREST), (i * (w * K + 6), 0))
    o.save(args[args.index("--png") + 1])
