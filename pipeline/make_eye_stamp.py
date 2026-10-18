"""Cut the eye out of the reference frame as a pixel stamp, so every frame gets the same crisp eye.

Run:  python3 make_eye_stamp.py CONFIG.json X0 Y0 X1 Y1
(X0..X1, Y0..Y1 inclusive: a box around the eye in the reference frame, in pixels)

Inside the box, a pixel belongs to the eye if its colour is the outline colour, a shade of the
part the eye whites use (parts.eye.light, e.g. shell), the eye highlight, or a shade listed in
parts.eye.stamp_extra (e.g. the dark lid-line blue). Skin pixels are left out, so the stamp sits
on top of our own shading. The anchor is the centroid of the stamp's outline-colour pixels
(pupil + lid); sprite_style.py places the stamp so that anchor lands on the 3D model's eye
centre each frame. Writes parts.eye.stamp in CONFIG.json.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

cfg_path = Path(sys.argv[1])
x0, y0, x1, y1 = map(int, sys.argv[2:6])
cfg = json.loads(cfg_path.read_text())
eye = cfg["parts"]["eye"]
a = np.array(Image.open(cfg_path.parent / cfg["reference"]).convert("RGBA"))

refs = {cfg["palette"]["outline"]: "outline"}
white_part = eye["light"].split(":")[0]
for i, h in enumerate(cfg["palette"]["parts"][white_part]):
    refs.setdefault(h, f"{white_part}:{i}")
for r in [eye.get("highlight", "cream:-1")] + eye.get("stamp_extra", []):
    p, i = r.split(":")
    refs.setdefault(cfg["palette"]["parts"][p][int(i)], f"{p}:{int(i) % len(cfg['palette']['parts'][p])}")

pixels, dark = [], []
for y in range(y0, y1 + 1):
    row = ""
    for x in range(x0, x1 + 1):
        h = "#%02x%02x%02x" % tuple(int(v) for v in a[y, x, :3])
        if a[y, x, 3] and h in refs:
            pixels.append([x, y, refs[h]])
            row += "o" if refs[h] == "outline" else "#"
            if refs[h] == "outline":
                dark.append((x, y))
        else:
            row += "."
    print(row)
ax, ay = float(np.mean([p[0] for p in dark])), float(np.mean([p[1] for p in dark]))
cfg["parts"]["eye"]["stamp"] = {
    "box": [x0, y0, x1, y1], "anchor": [round(ax, 2), round(ay, 2)],
    "pixels": [[round(x - ax, 2), round(y - ay, 2), r] for x, y, r in pixels],
    "note": "eye cut from the reference by make_eye_stamp.py; [dx, dy, colour] relative to the anchor",
}
cfg_path.write_text(json.dumps(cfg, indent=2))
print(f"{len(pixels)} eye pixels, anchor ({ax:.2f}, {ay:.2f}) -> {cfg_path}")
