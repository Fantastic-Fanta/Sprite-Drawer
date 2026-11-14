"""Paint-over sprites: a per-Pokemon paint script draws every frame (shading, lines, colours: the
art decisions), and the drawing of the key frames is carried through the loop, so it sticks to
the body instead of being re-decided each frame.

Used by make_gif.py when the config has style.paint_over:
  {"script": "paint_zygarde.py",     paint script, next to the config
   "keys": [0, 32],                  key frames (default: frame 0 and the middle of the loop)
   "search": 4, "tol": 4,            surface matching through the rest pass (transport_shading_frame)
   "blink_spans": [1, 2, 3]}         pixels that change for this many frames and return are held

The paint script is run once per frame as  python3 SCRIPT FRAME.pkl OUT.png OUT.npz: the pickle
holds the prepared frame (solid, n, depth, part, fixed, fixed_rgb, eye_area, rest), the PNG is
the painted frame with a 2 px margin, the npz holds its line mask ("line", without the margin).

Every frame but the first key:
  - lines: the key's lines carried onto the frame, thickened by 1 px and thinned back to their
    centre (a continuous stroke; the frame's own lines switch on and off from frame to frame)
  - fill: the first key's painted pixel showing the same spot of the surface, else the next
    key's, else the frame's own paint; carried strays (3 of 4 neighbours agree) evened
Then blinks over the loop are held, and the GIF is written with one exact palette for every frame
(the GIF writer's per-frame quantizing merges near-identical tones differently each frame).
"""
import pickle
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

import sprite_style as ss

HERE = Path(__file__).resolve().parent
KEYS = ("solid", "n", "depth", "part", "fixed", "fixed_rgb", "eye_area", "rest")


def _dilate(m):
    o = m.copy()
    for dy, dx in ss.NB8:
        o |= ss.shift(m, dy, dx, False)
    return o


def loop(cfg, cfg_path, paths, box, size):
    """the painted loop: one RGBA array per frame"""
    po = cfg["style"]["paint_over"]
    script = Path(cfg_path).resolve().parent / po["script"]
    search, tol = po.get("search", 4), po.get("tol", 4)
    frames = ss.pmap(ss.load_prepare, [(cfg, p, box, size) for p in paths])
    frames = [{k: f[k] for k in KEYS} for f in frames]
    # part labels stick to the surface (a turning head otherwise re-decides its colour regions
    # every frame): carried from frame 0 through the rest pass, then the carried edges evened
    if len(frames) > 2:
        frames = ss.transport_parts(frames, 0, 6, 4)
        frames = [f if i == 0 else dict(f, part=ss.smooth_parts(f["part"], f["solid"] & ~f["fixed"], 2))
                  for i, f in enumerate(frames)]
    n = len(frames)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        def paint(i):
            pickle.dump(frames[i], open(tmp / f"f{i:03d}.pkl", "wb"))
            r = subprocess.run([sys.executable, str(script), str(tmp / f"f{i:03d}.pkl"), str(tmp / f"p{i:03d}.png"),
                                str(tmp / f"d{i:03d}.npz")], capture_output=True, text=True,
                               env={"PYTHONPATH": str(HERE)})
            if r.returncode:
                raise RuntimeError(f"paint script failed on frame {i}:\n{r.stderr[-2000:]}")
            return (np.array(Image.open(tmp / f"p{i:03d}.png").convert("RGBA"))[2:-2, 2:-2],
                    np.load(tmp / f"d{i:03d}.npz")["line"])

        with ThreadPoolExecutor(6) as ex:                 # each paint is its own process
            painted = list(ex.map(paint, range(n)))

    cols = {}                                             # colours as indices, to ride the transport

    def index(img, mask):
        idx = np.full(mask.shape, -1)
        for y, x in np.argwhere(mask):
            idx[y, x] = cols.setdefault(tuple(img[y, x, :3]), len(cols))
        return idx

    K = [k for k in po.get("keys", [0, n // 2]) if k < n]
    keys = []
    for k in K:
        f, (img, ln) = frames[k], painted[k]
        keys.append({"f": {"rest": f["rest"], "solid": f["solid"], "part": f["part"]},
                     "fill_f": {"rest": f["rest"], "solid": f["solid"] & ~ln, "part": f["part"]},
                     "fill": index(img, f["solid"] & ~ln), "line": index(img, ln)})

    def carry(key, what, f, solid):
        src = key["fill_f"] if what == "fill" else key["f"]
        return ss.transport_shading_frame(src, key[what], dict(f, solid=solid),
                                          {"rank": np.full(f["solid"].shape, -1)}, search, tol)["rank"]

    out = []
    for i, f in enumerate(frames):
        img = painted[i][0].copy()
        if i != K[0]:
            # the later keys only fill what the first key never showed (a later key itself too,
            # so it doesn't pop out of the loop)
            later = [key for k, key in zip(K[1:], keys[1:]) if k != i]
            tl_col = carry(keys[0], "line", f, f["solid"])
            unmatched = f["solid"] & (carry(keys[0], "fill", f, f["solid"]) < 0) & (tl_col < 0)
            for key in later:
                t2 = carry(key, "line", f, f["solid"])
                tl_col = np.where(unmatched & (t2 >= 0), t2, tl_col)
            ln = ss.thin(_dilate((tl_col >= 0) & f["solid"]) & f["solid"])
            for comp in ss.components(ln):
                if len(comp) < 3:
                    ys, xs = zip(*comp); ln[ys, xs] = False
            near = np.full(f["solid"].shape, -1)               # a line's colour: the nearest carried one
            for dy, dx in [(0, 0)] + list(ss.NB8):
                sh = ss.shift(tl_col, dy, dx, -1)
                near = np.where((near < 0) & (sh >= 0), sh, near)
            got = carry(keys[0], "fill", f, f["solid"] & ~ln)
            for key in later:
                got = np.where(got < 0, carry(key, "fill", f, f["solid"] & ~ln), got)
            got = np.where(got < 0, index(img, f["solid"] & ~ln), got)
            for _ in range(2):                                 # carried strays: 3 of 4 neighbours agree
                nb = np.stack([ss.shift(got, dy, dx, -2) for dy, dx in ss.NB4])
                for c in np.unique(got[got >= 0]):
                    fix = ((nb == c).sum(0) >= 3) & (got != c) & (got >= 0)
                    got[fix] = c
            lut = np.zeros((len(cols), 3), np.uint8)
            for c, j in cols.items():
                lut[j] = c
            m = f["solid"] & ~ln & (got >= 0)
            img[m, :3] = lut[got[m]]
            ok = ln & (near >= 0)
            img[ok, :3] = lut[near[ok]]
        out.append(np.pad(img, ((2, 2), (2, 2), (0, 0))))
    return hold_blinks(out, po.get("blink_spans", [1, 2, 3]))


def hold_blinks(sprites, spans):
    """a pixel that differs for `span` frames and then returns to what it was takes that value
    throughout (the loop wraps); a moving edge changes once and is untouched"""
    A = np.stack(sprites).astype(np.int64)
    key = A[..., 0] * 65536 + A[..., 1] * 256 + A[..., 2] + (A[..., 3] == 0) * (1 << 25)
    n = len(key)
    for _ in range(3):
        for span in spans:
            for i in range(n):
                before, after = key[(i - 1) % n], key[(i + span) % n]
                m = before == after
                for k in range(span):
                    m &= key[(i + k) % n] != before
                for k in range(span):
                    j = (i + k) % n
                    key[j][m] = before[m]
                    A[j][m] = A[(i - 1) % n][m]
    return [a.astype(np.uint8) for a in A]


def save_gif(cfg, sprites, path):
    """one exact palette shared by every frame, built from the colours the frames use"""
    pal = sorted({tuple(c) for s in sprites for c in s[s[..., 3] > 0][:, :3].tolist()})
    if len(pal) > 255:
        raise ValueError(f"{len(pal)} colours: a GIF holds 255 plus transparency")
    pk = np.array([c[0] << 16 | c[1] << 8 | c[2] for c in pal], np.int64)      # sorted, so searchsorted
    flat = [v for c in pal for v in c] + [0, 0, 0] * (256 - len(pal))
    frames = []
    for s in sprites:
        k = s[..., 0].astype(np.int64) << 16 | s[..., 1].astype(np.int64) << 8 | s[..., 2]
        idx = np.where(s[..., 3] > 0, np.searchsorted(pk, k), 255).astype(np.uint8)
        p = Image.fromarray(idx, "P")
        p.putpalette(flat)
        frames.append(p)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=cfg["style"]["frame_ms"],
                   loop=0, transparency=255, disposal=2, optimize=False)
