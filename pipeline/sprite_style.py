"""The sprite look: render_sprite.py's passes -> palette pixel art.

Flat palette colours, cel bands and inverted-hull lines. The lines are wherever the hull shows
(render.hull), so where every line goes - silhouette and interior - is decided by the 3D model,
with no tracing, painting or per-Pokemon line rules.

Config (style section; every key but height / frame_ms is optional):
  "height": 86, "frame_ms": 30   sprite height in px (frame 0), GIF frame time
  "light": [x, y, z]             light direction in camera space (x right, y up, z to the viewer);
                                 default LIGHT, from the upper left like the games' sprites
  "bands": [lo, hi]              N.L below lo: one shade darker, above hi: one lighter
                                 (default: frame 0's 25th / 70th percentile, fixed for the loop)
  "flat_parts": ["red", ...]     parts that keep their texture shade (marks, gems)
  "deep_parts": {"core": [10, 30, 70, 90]}   parts shaded up to two steps: N.L percentiles of that
                                 part's own pixels in frame 0 (fixed for the loop) - below the 1st two
                                 darker, below the 2nd one darker, above the 3rd one lighter, above
                                 the 4th two lighter (shows the contours of a part with a long ramp)
  "cover": 0.35                  a sprite pixel is line where the hull covers this much of it
  "weak_cover": 0.12             ...and a 1-2 px gap in a line is filled where it covers this much
  "ring": true                   outline right outside the body where the hull left a crack
  "despeckle": 2                 fill islands of up to this many px of another shade, inside one
                                 part, take the shade around them (see despeckle); default 0 = off
  "fast_frames", "frame_anchor"  motion timing / pixel grid (make_gif.py, render_sprite.py)

Per sprite pixel, from the full-size passes (color_, id_, data_, hull_ next to each other):
  * the part is the palette part most of its render samples snap to (nearest palette shade,
    or with parts.match "albedo" nearest parts.albedo texture colour), leaving out the samples
    under the hull (they belong to the line); a sample of a material in parts.materials (id_
    pass) only snaps to the parts its group allows ("purple|red"); its colour is the mean of those samples, snapped to
    that part's shades - a pixel on a border takes one side's colour, never a blend
  * the shade moves one step down / up by the light on the mean normal of those samples
  * lines are the outline colour, never thinned or moved; bits of a part up to SLIVER px along a
    line (texture colour reaching past the edge the line follows) take the colour around them
"""
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageSequence

NB4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
NB8 = NB4 + ((1, 1), (1, -1), (-1, 1), (-1, -1))
MARGIN = 3        # sprite px around the body's box: the hull's silhouette line sits outside it
Q = 5             # bits per channel of the colour -> palette lookup
SLIVER = 3        # largest bit of a part along a line that is recoloured as a sliver (see draw)
LIGHT = (-0.15, 0.45, 0.88)
# material group colours of the id_ pass, in parts.materials group order (same list as render_sprite.py)
ID_RGB = [(1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0), (1, 0, 1), (0, 1, 1), (1, 1, 1),
          (0.5, 0, 0), (0, 0.5, 0), (0, 0, 0.5), (0.5, 0.5, 0), (0.5, 0, 0.5), (0, 0.5, 0.5)]


# --- palette ------------------------------------------------------------------

def hexrgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def palette(cfg):
    """every colour a sprite may use: the outline, then each part's shades"""
    cols = [hexrgb(cfg["palette"]["outline"])]
    for shades in cfg["palette"]["parts"].values():
        cols += [hexrgb(h) for h in shades if hexrgb(h) not in cols]
    return cols


# --- helpers --------------------------------------------------------------------

_POOL, _POOL_JOBS = None, 0


def _call(job):
    fn, args = job
    return fn(*args)


def pmap(fn, arg_list):
    """[fn(*args) for args in arg_list], spread over worker processes (SPRITE_JOBS, default all
    cores; SPRITE_JOBS=1 runs everything here). Only for per-frame steps that don't depend on
    each other's results, so the output is the same as the plain loop."""
    global _POOL, _POOL_JOBS
    jobs = int(os.environ.get("SPRITE_JOBS", os.cpu_count() or 1))
    if jobs <= 1 or len(arg_list) < 2:
        return [fn(*a) for a in arg_list]
    if _POOL is None:
        import sys
        import multiprocessing as mp
        # workers are started with "spawn" (fork isn't safe with macOS's Accelerate) and would
        # re-run the calling script (make_gif.py has no __main__ guard): hide it while they start
        main = sys.modules["__main__"]
        main_file = main.__dict__.pop("__file__", None)
        try:
            _POOL, _POOL_JOBS = mp.get_context("spawn").Pool(jobs), jobs
        finally:
            if main_file is not None:
                main.__file__ = main_file
    chunk = -(-len(arg_list) // (_POOL_JOBS * 2))
    return _POOL.map(_call, [(fn, a) for a in arg_list], chunksize=chunk)


def shift(a, dy, dx, fill):
    """a moved by (dy, dx): out[y, x] = a[y - dy, x - dx], with `fill` coming in at the border."""
    out = np.empty_like(a)
    out[...] = fill
    h, w = a.shape[:2]
    out[max(dy, 0):h + min(dy, 0), max(dx, 0):w + min(dx, 0)] = a[max(-dy, 0):h - max(dy, 0), max(-dx, 0):w - max(dx, 0)]
    return out


# --- loading and framing ----------------------------------------------------------

def frame_paths(frames_dir, only_first=False):
    """one path per frame: its colour pass (the other passes sit next to it). A folder rendered
    again in the other format (PNG / TGA) has both: the newer render counts."""
    newest = {}
    for p in Path(frames_dir).glob("color_*"):
        if p.suffix in (".png", ".tga") and (p.stem not in newest or p.stat().st_mtime > newest[p.stem].stat().st_mtime):
            newest[p.stem] = p
    paths = [newest[k] for k in sorted(newest)]
    return paths[:1] if only_first else paths


def alpha_bbox(color):
    return color.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()


def color_info(p):
    """a frame's box for framing(), and whether it touches the render's edge (cut off)"""
    color = Image.open(p).convert("RGBA")
    a = np.array(color.getchannel("A")) > 8
    return alpha_bbox(color), bool(a[0].any() or a[-1].any() or a[:, 0].any() or a[:, -1].any())


def framing(height, boxes, anchor=None):
    """One crop box for the whole loop (no jitter); scale so frame 0 is `height` px tall.
    anchor: indices of the frames that fix the pixel grid (e.g. all but a fast spin, whose
    in-between poses reach a little further); the box is then grown by whole sprite pixels to
    fit the rest, so the anchor frames sample exactly as they would on their own.
    boxes: each frame's alpha_bbox."""
    def union(bs):
        box = None
        for b in bs:
            box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
        return box
    b0 = boxes[0]
    scale = height / (b0[3] - b0[1])
    if anchor is None:
        box = union(boxes)
        return box, (round((box[2] - box[0]) * scale), round((box[3] - box[1]) * scale))
    box = list(union([boxes[i] for i in anchor])); full = union(boxes)
    size = [round((box[2] - box[0]) * scale), round((box[3] - box[1]) * scale)]
    for side, k, sgn in ((0, 0, -1), (1, 1, -1), (2, 0, 1), (3, 1, 1)):
        need = (box[side] - full[side]) * -sgn            # render px the full loop sticks out
        if need > 0:
            # whole sprite pixels to add; of the few that fit, the one whose width in render px is
            # closest to a whole number, so the anchor frames' grid barely shifts
            m0 = int(np.ceil(need * scale))
            m = min(range(m0, m0 + 4), key=lambda q: abs(q / scale - round(q / scale)))
            box[side] += sgn * round(m / scale)
            size[k] += m
    return tuple(box), tuple(size)


# --- the look ---------------------------------------------------------------------

def _setup(cfg):
    st = cfg["style"]
    parts = list(cfg["palette"]["parts"])
    shades = [np.array([hexrgb(c) for c in cfg["palette"]["parts"][p]], float) for p in parts]
    # each part's reference colours: its palette shades, or with parts.match "albedo" its one
    # texture colour (parts.albedo) - for ramps that overlap another part's (a gunmetal armour
    # nearer a slate claw shade than its own)
    pm = cfg.get("parts", {})
    alb = pm.get("albedo", {}) if pm.get("match") == "albedo" else {}
    refs = [np.array([hexrgb(alb[p])], float) if p in alb else sh for p, sh in zip(parts, shades)]
    flat = np.concatenate(refs)
    part_of = np.concatenate([[i] * len(r) for i, r in enumerate(refs)])
    # every colour (at Q bits per channel) -> the part of its nearest reference colour
    g = (np.arange(1 << Q) << (8 - Q)) + (1 << (7 - Q))
    grid = np.stack(np.meshgrid(g, g, g, indexing="ij"), -1).reshape(-1, 3).astype(float)
    d2 = ((grid[:, None] - flat[None]) ** 2).sum(-1)
    # one table per material group (parts.materials): its colours only go to the parts it allows
    # ("purple|red", "shell"); the default material, and a group naming no palette part, allow all
    pm = cfg.get("parts", {})
    groups = [pm.get("default_material")] + sorted(set(pm.get("materials", {}).values()))
    luts = []
    for gi, g in enumerate(groups):
        ok = [parts.index(n) for n in (g or "").split("|") if n in parts] if gi else []
        dd = d2 if not ok else np.where(np.isin(part_of, ok)[None], d2, np.inf)
        luts.append(part_of[dd.argmin(-1)].astype(np.int16))
    lut = np.stack(luts)
    srgb = lambda c: np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055) * 255
    id_rgb = srgb(np.array(ID_RGB[:len(groups)], float))
    light = np.array(st.get("light", LIGHT), float)
    return {"parts": parts, "shades": shades, "lut": lut, "id_rgb": id_rgb, "light": light / np.linalg.norm(light),
            "shaded": np.array([p not in st.get("flat_parts", []) for p in parts]),
            "out": np.array(hexrgb(cfg["palette"]["outline"]), np.uint8),
            "cover": st.get("cover", 0.35), "weak": st.get("weak_cover", 0.12), "ring": st.get("ring", True),
            "despeckle": int(st.get("despeckle", 0))}


def _load(p, kind, box):
    q = p.with_name(p.name.replace("color_", kind + "_"))
    return np.array(Image.open(q).convert("RGBA").crop(box))


def measure(cfg, p, box, size, S=None):
    """one frame's sprite-pixel arrays: body, part, mean colour of that part's samples, mean
    normal, hull coverage"""
    S = S or _setup(cfg)
    W, H = size
    col = _load(p, "color", box)
    dat = _load(p, "data", box)
    hul = _load(p, "hull", box)
    h, w = col.shape[:2]
    # sprite pixel of every render pixel (the same box -> size mapping as a BOX resize)
    sy = np.minimum((np.arange(h) * H) // h, H - 1)
    sx = np.minimum((np.arange(w) * W) // w, W - 1)
    cell = (sy[:, None] * W + sx[None, :]).ravel()
    n = W * H
    total = np.bincount(cell, minlength=n).astype(float)
    opaque = col[..., 3].ravel() > 127
    rgb = col[..., :3].reshape(-1, 3)
    P = len(S["parts"])
    q = rgb.astype(np.int32) >> (8 - Q)
    # each sample's material group (id_ pass, rendered when parts.materials maps any material)
    grp = 0
    if len(S["lut"]) > 1:
        ida = _load(p, "id", box)
        key = ida[..., :3].reshape(-1, 3).astype(np.int32) @ np.array([1 << 16, 1 << 8, 1])
        u, inv = np.unique(key, return_inverse=True)
        urgb = np.stack([u >> 16, (u >> 8) & 255, u & 255], -1).astype(float)
        grp = ((urgb[:, None] - S["id_rgb"][None]) ** 2).sum(-1).argmin(-1)[inv.ravel()]
        grp = np.where(ida[..., 3].ravel() > 127, grp, 0)
    part = S["lut"][grp, (q[:, 0] << 2 * Q) | (q[:, 1] << Q) | q[:, 2]]
    hull_px = hul[..., 3].ravel() > 127
    body_cnt = np.bincount(cell[opaque], minlength=n)
    # the part: majority of the body samples the hull doesn't cover (what's under a line belongs
    # to the line - counting it lets the far side's colour leak to the near side of the line);
    # a pixel the hull covers completely counts all its samples
    use = opaque & ~hull_px
    use |= opaque & (np.bincount(cell[use], minlength=n) == 0)[cell]
    counts = np.bincount(cell[use] * P + part[use], minlength=n * P).reshape(n, P)
    best = counts.argmax(-1)
    # the winning part's samples: their mean colour and mean normal
    win = use.copy()
    win[use] = part[use] == best[cell[use]]
    c = cell[win]
    k = np.maximum(np.bincount(c, minlength=n), 1)[:, None]
    mean_rgb = np.stack([np.bincount(c, rgb[win, i].astype(float), n) for i in range(3)], -1) / k
    nrm = dat[..., :2].reshape(-1, 2)[win].astype(float) / 255 * 2 - 1
    mean_n = np.stack([np.bincount(c, nrm[:, i], n) for i in range(2)], -1) / k
    hull_cov = np.bincount(cell, hull_px, n) / np.maximum(total, 1)
    rs = lambda a: a.reshape(H, W, *a.shape[1:])
    return {"body": rs(body_cnt / np.maximum(total, 1)) >= 0.5, "part": rs(best), "rgb": rs(mean_rgb),
            "n": rs(mean_n), "hull": rs(hull_cov)}


def _ndl(S, nxy):
    nz = np.sqrt(np.clip(1 - (nxy ** 2).sum(-1), 0, 1))
    L = S["light"]
    return nxy[..., 0] * L[0] + nxy[..., 1] * L[1] + nz * L[2]


def draw(cfg, m, bands, S=None, deep=None):
    """one frame's RGBA sprite from measure()'s arrays; deep: {part index: 4 N.L thresholds}
    (style.deep_parts, measured on frame 0 by loop())"""
    S = S or _setup(cfg)
    body, part = m["body"], m["part"]
    H, W = body.shape
    out = np.zeros((H, W, 4), np.uint8)
    ndl = _ndl(S, m["n"])
    step = np.where(ndl > bands[1], 1, np.where(ndl < bands[0], -1, 0))
    for i, sh in enumerate(S["shades"]):
        sel = body & (part == i)
        if not sel.any():
            continue
        j = ((m["rgb"][sel][:, None] - sh[None]) ** 2).sum(-1).argmin(-1)
        if deep and i in deep:
            b, v = deep[i], ndl[sel]
            j = np.clip(j + (v > b[2]).astype(int) + (v > b[3]) - (v < b[1]) - (v < b[0]), 0, len(sh) - 1)
        elif S["shaded"][i]:
            j = np.clip(j + step[sel], 0, len(sh) - 1)
        out[sel, :3] = sh[j]
    out[body, 3] = 255
    # lines: where the hull covers enough of the pixel; plus gaps of 1-2 px in a line where the hull
    # still covers a little (line on both sides, in a straight or diagonal run) - never beside a line,
    # so no line gets wider
    cov = m["hull"]
    line = cov >= S["cover"]
    weak = (cov >= S["weak"]) & ~line
    add = np.zeros_like(line)
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        ln_b, ln_a = shift(line, dy, dx, False), shift(line, -dy, -dx, False)
        add |= weak & ln_b & ln_a                                         # one-pixel gap
        wk_a = shift(weak, -dy, -dx, False)
        two = weak & ln_b & wk_a & shift(line, -2 * dy, -2 * dx, False)   # two-pixel gap
        add |= two | shift(two, dy, dx, False)
    line |= add
    if S["ring"]:
        for dy, dx in NB4:
            line |= ~body & shift(body, dy, dx, False)
    # slivers: a texture colour reaching a pixel or two past the edge the line follows leaves a
    # staircase of 1-3 px bits of that part along the line, touching the rest of it only at corners.
    # Each such bit (4-connected, at most SLIVER px, touching a line) takes the colour most of the
    # fill pixels around it have. Lines are left as they are.
    fill = body & ~line
    near_line = np.zeros_like(fill)
    for dy, dx in NB8:
        near_line |= shift(line, dy, dx, False)
    seen = np.zeros_like(fill)
    for y0, x0 in np.argwhere(fill & near_line):
        if seen[y0, x0]:
            continue
        p, comp, stack = part[y0, x0], [], [(y0, x0)]
        seen[y0, x0] = True
        while stack and len(comp) <= SLIVER:
            y, x = stack.pop()
            comp.append((y, x))
            for dy, dx in NB4:
                yy, xx = y + dy, x + dx
                if 0 <= yy < H and 0 <= xx < W and fill[yy, xx] and not seen[yy, xx] and part[yy, xx] == p:
                    seen[yy, xx] = True
                    stack.append((yy, xx))
        if len(comp) > SLIVER or stack:
            continue
        cs = set(comp)
        nb = [tuple(out[y + dy, x + dx, :3]) for y, x in comp for dy, dx in NB8
              if 0 <= y + dy < H and 0 <= x + dx < W and fill[y + dy, x + dx] and (y + dy, x + dx) not in cs
              and part[y + dy, x + dx] != p]
        if nb:
            c = max(set(nb), key=nb.count)
            for y, x in comp:
                out[y, x, :3] = c
    if S["despeckle"]:
        despeckle(out, fill, part, S["despeckle"])
    out[line, :3] = S["out"]
    out[line, 3] = 255
    return out


def despeckle(out, fill, part, size):
    """style.despeckle N: a shade island of at most N px (4-connected, one colour) inside one
    part - every pixel around it fill of that same part - takes the colour most of that ring has,
    if at least 3/4 of the ring agrees. A surface whose N.L sits right on a band limit (or a texture
    detail smaller than a sprite pixel) otherwise flickers single pixels of the next shade.
    Fill only: line pixels are never read or changed."""
    H, W = fill.shape
    key = (out[..., 0].astype(np.int32) << 16) | (out[..., 1].astype(np.int32) << 8) | out[..., 2]
    seen = ~fill.copy()
    for y0, x0 in np.argwhere(fill):
        if seen[y0, x0]:
            continue
        k, p, comp, stack = key[y0, x0], part[y0, x0], [], [(y0, x0)]
        seen[y0, x0] = True
        while stack and len(comp) <= size:
            y, x = stack.pop()
            comp.append((y, x))
            for dy, dx in NB4:
                yy, xx = y + dy, x + dx
                if 0 <= yy < H and 0 <= xx < W and not seen[yy, xx] and key[yy, xx] == k and part[yy, xx] == p:
                    seen[yy, xx] = True
                    stack.append((yy, xx))
        if len(comp) > size or stack:
            continue
        cs = set(comp)
        ring = {(y + dy, x + dx) for y, x in comp for dy, dx in NB8} - cs
        if any(not (0 <= y < H and 0 <= x < W) or not fill[y, x] or part[y, x] != p for y, x in ring):
            continue
        nb = [key[y, x] for y, x in ring]
        c = max(set(nb), key=nb.count)
        if nb.count(c) * 4 >= len(nb) * 3:
            for y, x in comp:
                out[y, x, :3] = (c >> 16, (c >> 8) & 255, c & 255)


def _frame(cfg, p, box, size, bands, deep=None):
    S = _setup(cfg)
    return draw(cfg, measure(cfg, p, box, size, S), bands, S, deep)


def loop(cfg, paths, box, size):
    """the whole loop: one RGBA array per frame. box / size: framing(), grown here by MARGIN
    sprite px on every side for the silhouette line"""
    per_x = (box[2] - box[0]) / size[0]
    per_y = (box[3] - box[1]) / size[1]
    mx, my = round(MARGIN * per_x), round(MARGIN * per_y)
    box = (box[0] - mx, box[1] - my, box[2] + mx, box[3] + my)
    size = (size[0] + 2 * MARGIN, size[1] + 2 * MARGIN)
    bands = cfg["style"].get("bands")
    dp = cfg["style"].get("deep_parts")
    deep = None
    if bands is None or dp:
        S = _setup(cfg)
        m0 = measure(cfg, paths[0], box, size, S)
        ndl0 = _ndl(S, m0["n"])
        if bands is None:
            bands = [float(v) for v in np.percentile(ndl0[m0["body"]], [25, 70])]
        if dp:
            deep = {}
            for name, pct in dp.items():
                i = S["parts"].index(name)
                sel = m0["body"] & (m0["part"] == i)
                deep[i] = [float(v) for v in np.percentile(ndl0[sel], pct)]
    return bob(cfg, pmap(_frame, [(cfg, p, box, size, bands, deep) for p in paths]))


def bob(cfg, sprites):
    """style.pixel_bob: each finished sprite moved by whole pixels (motion.offsets; the pose renders
    only the leftover fraction with the same function), on a canvas grown to fit every shift"""
    import motion
    offs = motion.offsets(cfg, len(sprites))
    A = max(abs(dy) for dy, _ in offs)
    B = max(abs(dx) for _, dx in offs)
    if not A and not B:
        return sprites
    out = []
    for s, (dy, dx) in zip(sprites, offs):
        y0, x0 = A - dy, B + dx                               # + = up / right
        c = np.zeros((s.shape[0] + 2 * A, s.shape[1] + 2 * B, 4), np.uint8)
        c[y0:y0 + s.shape[0], x0:x0 + s.shape[1]] = s
        out.append(c)
    return out


# --- GIFs -------------------------------------------------------------------------

def save_gif(cfg, sprites, path):
    pal = palette(cfg)
    T = len(pal)
    # palette index per pixel in one lookup (the palette's colours are distinct); a colour outside
    # the palette, like transparency, gets index T
    pk = np.array([c[0] << 16 | c[1] << 8 | c[2] for c in pal], np.int64)
    order = np.argsort(pk)
    frames = []
    for s in sprites:
        k = s[..., 0].astype(np.int64) << 16 | s[..., 1].astype(np.int64) << 8 | s[..., 2]
        j = np.clip(np.searchsorted(pk[order], k), 0, T - 1)
        idx = np.where((s[..., 3] > 0) & (pk[order][j] == k), order[j], T).astype(np.uint8)
        p = Image.fromarray(idx, "P")
        p.putpalette([v for c in pal for v in c] + [0, 0, 0] * (256 - T))
        frames.append(p)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=cfg["style"]["frame_ms"],
                   loop=0, transparency=T, disposal=2, optimize=False)


def gif_frames(path):
    """All frames of a GIF as RGBA arrays, one per display tick: GIF writers merge identical
    consecutive frames into one longer frame, so a frame shown for 2 ticks is repeated twice."""
    arrs, durs = [], []
    for im in ImageSequence.Iterator(Image.open(path)):     # (the iterator re-uses one image object)
        arrs.append(np.array(im.convert("RGBA"))); durs.append(im.info.get("duration", 0) or 0)
    base = min([d for d in durs if d > 0], default=0)
    out = []
    for a, d in zip(arrs, durs):
        out += [a] * (max(1, round(d / base)) if base else 1)
    return out
