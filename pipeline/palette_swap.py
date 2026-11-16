"""Make a shiny sprite the way Showdown's are made: the finished normal sprite, recoloured.

Run:  python3 palette_swap.py NORMAL.json SHINY.json normal.gif shiny.gif [--scale 4]

Every pixel keeps its part and shade index; only the colour changes, from the normal config's
palette to the shiny config's (make_shiny.py writes SHINY.json). So the shiny has exactly the
normal sprite's shapes, lines and motion. Fails if the normal sprite has a colour outside its
palette or two normal colours would map onto one shiny colour.
"""
import json
import sys
from pathlib import Path

import numpy as np

import sprite_style as ss

args = sys.argv[1:]
norm_cfg = json.loads(Path(args[0]).read_text())
shiny_cfg = json.loads(Path(args[1]).read_text())
src, out_path = args[2], args[3]

a, b = ss.palette(norm_cfg), ss.palette(shiny_cfg)
assert len(a) == len(b), "palettes differ in size"
cmap = {tuple(x): tuple(y) for x, y in zip(a, b)}
assert len(set(cmap.values())) == len(cmap), "two normal colours map to one shiny colour"

sprites = []
for f in ss.gif_frames(src):
    s = f.copy()
    on = s[..., 3] > 0
    seen = {tuple(c) for c in s[on][:, :3]}
    missing = seen - set(cmap)
    assert not missing, f"colours not in the normal palette: {sorted(missing)}"
    for x, y in cmap.items():
        s[on & np.all(f[..., :3] == x, axis=-1), :3] = y
    sprites.append(s)
ss.save_gifs(shiny_cfg, sprites, out_path, args[args.index("--scale") + 1] if "--scale" in args else None)
