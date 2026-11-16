"""python3 gpu/classify_diffs.py CONFIG.json PUBLISHED.gif PROTOTYPE.gif: what kind of change each differing pixel is"""
import sys
from collections import Counter
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
from build import load
from compare_gifs import frames
import sprite_style as ss

cfg = load(Path(sys.argv[1]).resolve())
out = ss.hexrgb(cfg["palette"]["outline"])
ramp = {}
for p, sh in cfg["palette"]["parts"].items():
    for i, h in enumerate(sh):
        ramp.setdefault(ss.hexrgb(h), (p, i))
c = Counter()
for a, b in zip(frames(sys.argv[2]), frames(sys.argv[3])):
    for y, x in np.argwhere(((a[..., 3] > 0) != (b[..., 3] > 0)) | ((a[..., :3] != b[..., :3]).any(-1) & (a[..., 3] > 0))):
        if (a[y, x, 3] > 0) != (b[y, x, 3] > 0):
            c["silhouette (pixel added/removed)"] += 1; continue
        pa, pb = tuple(a[y, x, :3]), tuple(b[y, x, :3])
        if out in (pa, pb):
            c["outline added/removed"] += 1
        elif ramp[pa][0] == ramp[pb][0] and abs(ramp[pa][1] - ramp[pb][1]) == 1:
            c["fill: one shade step (band border)"] += 1
        else:
            c["fill: other colour (part / 2+ steps)"] += 1
n = sum(c.values())
for k, v in c.most_common():
    print(f"{k}: {v} ({100 * v / n:.0f}%)")
print("total", n, "over", len(frames(sys.argv[2])), "frames")
