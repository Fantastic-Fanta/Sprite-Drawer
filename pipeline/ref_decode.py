"""Rebuild a Showdown reference frame from the compact text the browser exports
("W,H;palette;run-length;hash", see SPRITE_PIPELINE.md) and check its hash.
Run:  python3 -I ref_decode.py IN.txt OUT.png
"""
import sys
import numpy as np
from PIL import Image

txt = open(sys.argv[1]).read().strip()
size, pal, runs, h = txt.split(";")
W, H = map(int, size.split(","))
pal = [tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) for c in pal.split(",")]
seq = []
for tok in runs.split():
    v, n = tok.split(".")
    seq += [int(v, 36)] * int(n, 36)
assert len(seq) == W * H, (len(seq), W * H)
hh = 0
for v in seq:
    hh = (hh * 31 + v) & 0xFFFFFFFF
assert hh == int(h), "hash mismatch"
a = np.zeros((H * W, 4), np.uint8)
for i, v in enumerate(seq):
    if v:
        a[i, :3] = pal[v - 1]; a[i, 3] = 255
Image.fromarray(a.reshape(H, W, 4)).save(sys.argv[2])
print("ok", W, H, len(pal), "colours")
