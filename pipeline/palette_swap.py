"""Make a shiny sprite the way Showdown's are made: the finished normal sprite, recoloured.

Run:  python3 palette_swap.py NORMAL.json SHINY.json normal.gif shiny.gif [--scale 4] [--no-qa]

Every pixel keeps its part and shade index; only the colour changes, from the normal config's
palette to the shiny config's (make_shiny.py writes SHINY.json). So the shiny has exactly the
normal sprite's shapes, lines and motion - no re-render, no new shade-band pops - and QA runs on
it with SHINY.json's limits. Fails if the normal sprite has a colour outside its palette or two
normal colours would map onto one shiny colour.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import check_loop as cl
import sprite_style as ss

args = sys.argv[1:]
norm_cfg = json.loads(Path(args[0]).read_text())
shiny_path = Path(args[1])
shiny_cfg = json.loads(shiny_path.read_text())
src, out_path = args[2], args[3]

a, b = ss.palette(norm_cfg), ss.palette(shiny_cfg)
assert len(a) == len(b), "palettes differ in size"
cmap = {tuple(x): tuple(y) for x, y in zip(a, b)}
assert len(set(cmap.values())) == len(cmap), "two normal colours map to one shiny colour"

sprites = []
for f in cl.gif_frames(src):
    s = f.copy()
    on = s[..., 3] > 0
    seen = {tuple(c) for c in s[on][:, :3]}
    missing = seen - set(cmap)
    assert not missing, f"colours not in the normal palette: {sorted(missing)}"
    for x, y in cmap.items():
        s[on & np.all(f[..., :3] == x, axis=-1), :3] = y
    sprites.append(s)
ss.save_gif(shiny_cfg, sprites, out_path)
eyes = Path(src).with_suffix(".eyes.json")
if eyes.exists():
    Path(out_path).with_suffix(".eyes.json").write_text(eyes.read_text())
print(f"wrote {out_path}: {len(sprites)} frames recoloured")

ok = True
if "--no-qa" not in args and shiny_cfg.get("qa"):
    import qa
    values, results = qa.run(shiny_path, out_path)
    ok = qa.report(results)
    Path(out_path).with_suffix(".qa.json").write_text(json.dumps(
        {"values": values, "pass": bool(ok),
         "checks": [{"name": n, "value": v, "limit": l, "pass": bool(p)} for n, v, l, _, p in results]}, indent=2))

if "--scale" in args:
    k = int(args[args.index("--scale") + 1])
    big = [np.array(Image.fromarray(s).resize((s.shape[1] * k, s.shape[0] * k), Image.Resampling.NEAREST))
           for s in sprites]
    big_path = str(Path(out_path).with_name(Path(out_path).stem + f"_{k}x.gif"))
    ss.save_gif(shiny_cfg, big, big_path)
    print(f"wrote {big_path}")
sys.exit(0 if ok else 1)
