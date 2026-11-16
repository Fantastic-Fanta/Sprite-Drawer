"""python3 make_gif.py CONFIG.json FRAMES_DIR out.gif [--scale 4] [--first-only out.png]
python3 make_gif.py --shiny NORMAL.json SHINY.json normal.gif shiny.gif [--scale 4]
--shiny recolours the finished normal GIF palette to palette. Exit 1 if the model touches the render edge.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import sprite_style as ss

args = sys.argv[1:]
scale = args[args.index("--scale") + 1] if "--scale" in args else None

if args[0] == "--shiny":
    norm_cfg, shiny_cfg = (json.loads(Path(p).read_text()) for p in args[1:3])
    a, b = ss.palette(norm_cfg), ss.palette(shiny_cfg)
    assert len(a) == len(b), "palettes differ in size"
    cmap = {tuple(x): tuple(y) for x, y in zip(a, b)}
    assert len(set(cmap.values())) == len(cmap), "two normal colours map to one shiny colour"
    sprites = []
    for f in ss.gif_frames(args[3]):
        s = f.copy()
        on = s[..., 3] > 0
        missing = {tuple(c) for c in s[on][:, :3]} - set(cmap)
        assert not missing, f"colours not in the normal palette: {sorted(missing)}"
        for x, y in cmap.items():
            s[on & np.all(f[..., :3] == x, axis=-1), :3] = y
        sprites.append(s)
    ss.save_gifs(shiny_cfg, sprites, args[4], scale)
    sys.exit(0)

cfg_path = Path(args[0])
cfg = json.loads(cfg_path.read_text())
frames_dir, out_path = args[1], args[2]
first_only = args[args.index("--first-only") + 1] if "--first-only" in args else None

paths = ss.frame_paths(frames_dir)
info = ss.pmap(ss.color_info, [(p,) for p in paths])      # each frame's box, and whether it's cut off
# the model must fit inside the render: a frame touching the render's edge is cut off (a wing
# ending in a straight edge) - fixed by a wider render (render.width / height with the FOV
# widened to match)
clipped = [k for k, (_, cut) in enumerate(info) if cut]
if clipped:
    print(f"  FAIL  render_clipped   {len(clipped)} frames touch the render edge (first: {clipped[:5]})")
# pixel grid: style.frame_anchor "first" = frame 0's own grid, grown by whole sprite px to fit the
# loop - so changing the motion can't resample frame 0; otherwise with fast_frames, the slow
# frames' grid; otherwise the whole loop's box
fast = {i for a, b in cfg["style"].get("fast_frames", []) for i in range(a, b + 1)}
anchor = None
if cfg["style"].get("frame_anchor") == "first":
    anchor = [0]
elif fast:
    anchor = [i for i in range(len(paths)) if i not in fast]
box, size = ss.framing(cfg["style"]["height"], [b for b, _ in info], anchor=anchor)

# style.mirror: flip the finished sprite left-right. For a model whose face only shows from the side
# that points it right (Absol Z's hair covers its face from the other side): the camera keeps the
# side the art shows, and the sprite still faces left like the others.
mirror = (lambda ss_: [s[:, ::-1].copy() for s in ss_]) if cfg["style"].get("mirror") else (lambda ss_: ss_)

if first_only:
    Image.fromarray(mirror(ss.loop(cfg, paths[:1], box, size))[0]).save(first_only)
    print(f"wrote {first_only}")
    sys.exit(0)

ss.save_gifs(cfg, mirror(ss.loop(cfg, paths, box, size)), out_path, scale)
sys.exit(1 if clipped else 0)
