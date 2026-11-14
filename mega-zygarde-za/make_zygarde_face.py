"""Record the true shapes of Mega Zygarde's face features for paint_zygarde.py: the two eyes,
the white diamond, the hexagon on the forehead, the dark face mask and the beak below it, as surface positions (rest-pass values) read off the
full-size render of frame 0. A sprite pixel then shows a feature if its surface position is one
of these, so each feature keeps its real outline and size at any sprite height and in every frame.

Run (from pipeline/):  PYTHONPATH=. python3 ../mega-zygarde-za/make_zygarde_face.py FRAMES_DIR [OUT.json]
writes zygarde_face.json next to this script (or OUT.json). FRAMES_DIR is a render with the
config's pose (a head turn changes which part of the face plate shows).
"""
import json
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

import sprite_style as ss

HERE = Path(__file__).resolve().parent
cfg = json.loads((HERE / "zygarde_front.json").read_text())
paths = ss.frame_paths(sys.argv[1])
info = ss.pmap(ss.color_info, [(p,) for p in paths])
box, size = ss.framing(None, 210, anchor=[0], boxes=[b for b, _ in info])
col = np.array(Image.open(paths[0]).convert("RGBA").crop(box)).astype(int)
rest = np.array(Image.open(paths[0].with_name(paths[0].name.replace("color_", "rest_"))).convert("RGBA").crop(box)).astype(int)
k = col.shape[1] / size[0]                      # render px per sprite px at height 210

# the face: a window round the white diamond (in frame 0 at height 210 it sits near sprite y 114,
# x 165, wherever the head is turned)
wy, wx = np.nonzero((col[..., 0] > 200) & (col[..., 1] > 200) & (col[..., 2] > 200) & (col[..., 3] > 200))
near = (np.abs(wy / k - 114) < 16) & (np.abs(wx / k - 165) < 16)
cy, cx = wy[near].mean() / k, wx[near].mean() / k
y0, y1, x0, x1 = [int(v * k) for v in (cy - 16, cy + 12, cx - 14, cx + 14)]
c, rs = col[y0:y1, x0:x1], rest[y0:y1, x0:x1]
r, g, b, a = (c[..., i] for i in range(4))
white = (r > 200) & (g > 200) & (b > 200) & (a > 200)
pale = (r > 170) & (g > 170) & (b < 170) & (a > 200) & ~white
dark = (r < 90) & (g < 90) & (b < 90) & (a > 200)

dia = np.zeros_like(white)
ys, xs = zip(*max(ss.components(white), key=len)); dia[ys, xs] = True
dia_y = np.mean(ys)
# the pale patches: the crown's two large base panels, a hexagon on the forehead above the
# diamond, and the two eyes below it, one either side
comps = sorted(ss.components(pale), key=len, reverse=True)[2:]
eyes = np.zeros_like(pale)
hexa = np.zeros_like(pale)
for comp in comps:
    ys, xs = zip(*comp)
    if len(comp) < 0.1 * k * k:                 # specks under ~0.1 sprite px
        continue
    (eyes if np.mean(ys) > dia_y else hexa)[ys, xs] = True
# the mask: the dark face plate round the diamond and eyes (within ~4 sprite px of them)
feat = eyes | dia | hexa
near = feat.copy()
for _ in range(int(4 * k)):
    near = near | ss.shift(near, 1, 0, False) | ss.shift(near, -1, 0, False) | ss.shift(near, 0, 1, False) | ss.shift(near, 0, -1, False)
mask = dark & near & ~feat

# the beak: the collar's central lobe pointing down below the red gem's plate (the collar is one
# surface, so it's grown from a seed below the gem over surface facing the same way)
red = (col[..., 0] > 120) & (col[..., 0] > col[..., 1] + 80) & (col[..., 0] > col[..., 2] + 60) & (col[..., 3] > 200)
ry, rx = np.nonzero(red)
near_g = (np.abs(ry / k - (cy + 13)) < 10) & (np.abs(rx / k - cx) < 12)
beak_full = np.zeros(col.shape[:2], bool)
if near_g.any():
    data = np.array(Image.open(paths[0].with_name(paths[0].name.replace("color_", "data_"))).convert("RGBA").crop(box)).astype(int)
    dep, nrm = data[..., 2], data[..., :2] / 255.0 * 2 - 1
    darkf = (col[..., 0] < 100) & (col[..., 1] < 100) & (col[..., 2] < 100) & (col[..., 3] > 200) & (np.abs(col[..., 0] - col[..., 1]) < 25)
    gy, gx = ry[near_g].mean(), rx[near_g].mean()
    # two seeds: the lobe's slab and its tip face different ways, so each is grown on its own
    for oy, ox in ((8.5, -3.8), (18.3, -0.5)):
        seed = (int(gy + oy * k), int(gx + ox * k))
        if not darkf[seed]:
            continue
        n0 = nrm[seed]
        grown = np.zeros_like(beak_full)
        grown[seed] = True
        q = deque([seed])
        while q:
            y, x = q.popleft()
            for dy_, dx_ in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                yy, xx = y + dy_, x + dx_
                if (0 <= yy < col.shape[0] and 0 <= xx < col.shape[1] and not grown[yy, xx] and darkf[yy, xx]
                        and abs(dep[yy, xx] - dep[y, x]) <= 1 and np.abs(nrm[yy, xx] - n0).max() < 0.35):
                    grown[yy, xx] = True
                    q.append((yy, xx))
        beak_full |= grown

pack = lambda m: sorted({tuple(v) for v in rs[m & (rs[..., 3] > 0)][:, :3].tolist()})
packf = lambda m: sorted({tuple(v) for v in rest[m & (rest[..., 3] > 0)][:, :3].tolist()})
out = {"eyes": pack(eyes), "diamond": pack(dia), "hex": pack(hexa), "mask": pack(mask), "beak": packf(beak_full),
       "note": "rest-pass values of frame 0's face features, read off the full-size render"}
(Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "zygarde_face.json").write_text(json.dumps(out))
print({key: len(v) for key, v in out.items() if key != "note"}, "render px: eyes", int(eyes.sum()), "diamond", int(dia.sum()), "hex", int(hexa.sum()), "mask", int(mask.sum()), "beak", int(beak_full.sum()))
