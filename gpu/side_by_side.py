"""python3 gpu/side_by_side.py PUBLISHED.gif PROTOTYPE.gif OUT.png [frames...]: rows = frames;
columns = published, prototype, differences (red) at 1x, then the same at 4x"""
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageSequence

pub, gpu, out = sys.argv[1:4]
picks = [int(f) for f in sys.argv[4:]] or [0, 40, 80, 120]
load = lambda p: [np.array(f.convert("RGBA")) for f in ImageSequence.Iterator(Image.open(p))]
A, B = load(pub), load(gpu)
bg = np.array([236, 236, 240, 255], np.uint8)


def flat(s):
    o = np.tile(bg, s.shape[:2] + (1,))
    o[s[..., 3] > 0] = s[s[..., 3] > 0]
    return o


def diff(a, b):
    d = ((a[..., 3] > 0) != (b[..., 3] > 0)) | ((a[..., 3] > 0) & (b[..., 3] > 0) & (a[..., :3] != b[..., :3]).any(-1))
    g = flat(a).astype(float)
    g[..., :3] = g[..., :3].mean(-1, keepdims=True) * 0.35 + 165
    g[d] = [230, 20, 40, 255]
    return g.astype(np.uint8), int(d.sum())


rows, gap = [], 8
for f in picks:
    dimg, n = diff(A[f], B[f])
    small = [flat(A[f]), flat(B[f]), dimg]
    big = [np.repeat(np.repeat(x, 4, 0), 4, 1) for x in small]
    h = big[0].shape[0]
    pad = lambda x: np.pad(x, ((0, h - x.shape[0]), (0, gap), (0, 0)), constant_values=255)
    rows.append((np.concatenate([pad(x) for x in small + big], 1), f, n))
W = rows[0][0].shape[1]
img = Image.new("RGBA", (W, sum(r.shape[0] + 24 for r, _, _ in rows)), "white")
d, y = ImageDraw.Draw(img), 0
for r, f, n in rows:
    d.text((4, y + 6), f"frame {f}: published | prototype | {n} px differ   (then the same at 4x)", fill="black")
    img.paste(Image.fromarray(r), (0, y + 24))
    y += r.shape[0] + 24
img.convert("RGB").save(out)
print(out, img.size)
