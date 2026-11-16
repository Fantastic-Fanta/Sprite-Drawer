"""Turn render_sprite.py output into a pixel sprite GIF (sprite_style.py's look).

Run:  python3 make_gif.py CONFIG.json FRAMES_DIR out.gif [--scale 4] [--first-only out.png]

--scale N also writes out_Nx.gif, enlarged with hard pixel edges.
--first-only writes just frame 0 as a PNG (quick checks).
Exit code 1 if a frame touches the render's edge (the model is cut off).
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import sprite_style as ss

args = sys.argv[1:]
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

sprites = mirror(ss.loop(cfg, paths, box, size))
ss.save_gif(cfg, sprites, out_path)
h, w = sprites[0].shape[:2]
print(f"wrote {out_path}: {len(sprites)} frames, {w}x{h}")

if "--scale" in args:
    k = int(args[args.index("--scale") + 1])
    big = [np.array(Image.fromarray(s).resize((s.shape[1] * k, s.shape[0] * k), Image.Resampling.NEAREST))
           for s in sprites]
    big_path = str(Path(out_path).with_name(Path(out_path).stem + f"_{k}x.gif"))
    ss.save_gif(cfg, big, big_path)
    print(f"wrote {big_path}")
sys.exit(1 if clipped else 0)
