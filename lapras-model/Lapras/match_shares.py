"""Set shade thresholds so each part's shades cover target shares on frame 0 - for sprites with
no reference to match (tune_style.py matches a reference's mix instead).

Run:  python3 match_shares.py CONFIG.json FRAME0_DIR
Uses style.target_shares {part: [darkest .. lightest]} (or style.target_shares_default), counted
over the part's fill shades (from style.first_shade on).
"""
import json
import sys
from pathlib import Path

import numpy as np

import sprite_style as ss

cfg_path = Path(sys.argv[1]); cfg = json.loads(cfg_path.read_text())
passes = ss.load_passes(sys.argv[2], only_first=True)
box, size = ss.framing(passes, cfg["style"]["height"])
f = ss.prepare(cfg, *passes[0], box, size)
light = ss.lighting(cfg["style"], f)
st = cfg["style"]
for name, shades in cfg["palette"]["parts"].items():
    first = st["first_shade"].get(name, 0)
    n = len(shades) - first
    target = np.array(st.get("target_shares", {}).get(name, st.get("target_shares_default", [1] * n))[:n], float)
    vals = light[f["solid"] & (f["part"] == name)]
    if len(vals) < 10 or n < 2:
        continue
    cum = np.cumsum(target / target.sum())[:-1]
    st["thresholds"][name] = [round(float(q), 4) for q in np.quantile(vals, cum)]
    print(name, "px", len(vals), "thresholds", st["thresholds"][name])
cfg_path.write_text(json.dumps(cfg, indent=2))
