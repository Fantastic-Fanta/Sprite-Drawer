"""Hull style: flat palette colours, cel bands and inverted-hull lines, instead of the line and
shading rules in sprite_style.py. The lines are wherever the hull shows (render.hull), so where the
interior lines go is decided by the 3D model, not by tracing or painting.

Used by make_gif.py when the config has style.hull:
  {"cover": 0.35,          a sprite pixel is line where the hull covers at least this much of it
   "weak_cover": 0.12,     ...or at least this much, next to a line pixel (closes thin stretches
                           of the hull, never moves a line off it)
   "bands": [lo, hi],      N.L of style.light: below lo one shade darker, above hi one lighter
                           (default: frame 0's 25th / 70th percentile, then fixed for the loop)
   "flat_parts": [...],    parts that keep their texture shade (default: the parts whose
                           style.thresholds are all 9, i.e. unshaded in the normal style)
   "ring": true}           close the silhouette where the hull has a crack: outline on every
                           pixel right outside the body

Per sprite pixel, from the full-size passes (colour_, data_, hull_ next to each other):
  * the part is the palette part most of its render samples snap to; its colour is the mean of
    those samples only, snapped to that part's shades, so a pixel on a border takes one side's
    colour instead of a blend that lands on a third colour
  * the shade moves one step up / down by the light on the mean normal of those samples
  * lines and outline are the outline colour; nothing is thinned or moved
"""
import numpy as np
from PIL import Image

import sprite_style as ss

MARGIN = 3        # sprite px around the body's box: the hull's silhouette line sits outside it
Q = 5             # bits per channel of the colour -> palette lookup
SLIVER = 3        # largest bit of a part along a line that is recoloured as a sliver (see draw)


def _setup(cfg):
    st = cfg["style"]
    hs = st["hull"]
    parts = list(cfg["palette"]["parts"])
    shades = [np.array([ss.hexrgb(c) for c in cfg["palette"]["parts"][p]], float) for p in parts]
    flat = np.concatenate(shades)
    part_of = np.concatenate([[i] * len(s) for i, s in enumerate(shades)])
    # every colour (at Q bits per channel) -> the part of its nearest palette shade
    g = (np.arange(1 << Q) << (8 - Q)) + (1 << (7 - Q))
    grid = np.stack(np.meshgrid(g, g, g, indexing="ij"), -1).reshape(-1, 3).astype(float)
    lut = part_of[((grid[:, None] - flat[None]) ** 2).sum(-1).argmin(-1)].astype(np.int16)
    flat_parts = hs.get("flat_parts")
    if flat_parts is None:
        flat_parts = [p for p in parts if all(v >= 9 for v in st.get("thresholds", {}).get(p, [9]))]
    light = np.array(st["light"], float)
    return {"parts": parts, "shades": shades, "lut": lut, "light": light / np.linalg.norm(light),
            "shaded": np.array([p not in flat_parts for p in parts]),
            "out": np.array(ss.hexrgb(cfg["palette"]["outline"]), np.uint8),
            "cover": hs.get("cover", 0.35), "weak": hs.get("weak_cover", 0.12), "ring": hs.get("ring", True)}


def _load(p, kind, box):
    q = p.with_name(p.name.replace("color_", kind + "_"))
    return np.array(Image.open(q).convert("RGBA").crop(box))


def measure(cfg, p, box, size, S=None):
    """one frame's sprite-pixel arrays: body coverage, part, mean colour of that part's samples,
    mean normal, hull coverage"""
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
    part = S["lut"][(q[:, 0] << 2 * Q) | (q[:, 1] << Q) | q[:, 2]]
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


def draw(cfg, m, bands, S=None):
    """one frame's RGBA sprite from measure()'s arrays"""
    S = S or _setup(cfg)
    body, part = m["body"], m["part"]
    H, W = body.shape
    out = np.zeros((H, W, 4), np.uint8)
    step = np.where(_ndl(S, m["n"]) > bands[1], 1, np.where(_ndl(S, m["n"]) < bands[0], -1, 0))
    for i, sh in enumerate(S["shades"]):
        sel = body & (part == i)
        if not sel.any():
            continue
        j = ((m["rgb"][sel][:, None] - sh[None]) ** 2).sum(-1).argmin(-1)
        if S["shaded"][i]:
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
        ln_b, ln_a = ss.shift(line, dy, dx, False), ss.shift(line, -dy, -dx, False)
        add |= weak & ln_b & ln_a                                         # one-pixel gap
        wk_a = ss.shift(weak, -dy, -dx, False)
        two = weak & ln_b & wk_a & ss.shift(line, -2 * dy, -2 * dx, False)  # two-pixel gap
        add |= two | ss.shift(two, dy, dx, False)
    line |= add
    if S["ring"]:
        for dy, dx in ss.NB4:
            line |= ~body & ss.shift(body, dy, dx, False)
    # slivers: a texture colour reaching a pixel or two past the edge the line follows leaves a
    # staircase of 1-3 px bits of that part along the line, touching the rest of it only at corners.
    # Each such bit (4-connected, at most SLIVER px, touching a line) takes the colour most of the
    # fill pixels around it have. Lines are left as they are.
    fill = body & ~line
    near_line = np.zeros_like(fill)
    for dy, dx in ss.NB8:
        near_line |= ss.shift(line, dy, dx, False)
    seen = np.zeros_like(fill)
    for y0, x0 in np.argwhere(fill & near_line):
        if seen[y0, x0]:
            continue
        p, comp, stack = part[y0, x0], [], [(y0, x0)]
        seen[y0, x0] = True
        while stack and len(comp) <= SLIVER:
            y, x = stack.pop()
            comp.append((y, x))
            for dy, dx in ss.NB4:
                yy, xx = y + dy, x + dx
                if 0 <= yy < H and 0 <= xx < W and fill[yy, xx] and not seen[yy, xx] and part[yy, xx] == p:
                    seen[yy, xx] = True
                    stack.append((yy, xx))
        if len(comp) > SLIVER or stack:
            continue
        cs = set(comp)
        nb = [tuple(out[y + dy, x + dx, :3]) for y, x in comp for dy, dx in ss.NB8
              if 0 <= y + dy < H and 0 <= x + dx < W and fill[y + dy, x + dx] and (y + dy, x + dx) not in cs
              and part[y + dy, x + dx] != p]
        if nb:
            c = max(set(nb), key=nb.count)
            for y, x in comp:
                out[y, x, :3] = c
    out[line, :3] = S["out"]
    out[line, 3] = 255
    return out


def _frame(cfg, p, box, size, bands):
    S = _setup(cfg)
    return draw(cfg, measure(cfg, p, box, size, S), bands, S)


def loop(cfg, paths, box, size):
    """the whole loop: one RGBA array per frame. box / size: make_gif's framing (sprite_style.framing),
    grown by MARGIN sprite px on every side for the silhouette line"""
    per_x = (box[2] - box[0]) / size[0]
    per_y = (box[3] - box[1]) / size[1]
    mx, my = round(MARGIN * per_x), round(MARGIN * per_y)
    box = (box[0] - mx, box[1] - my, box[2] + mx, box[3] + my)
    size = (size[0] + 2 * MARGIN, size[1] + 2 * MARGIN)
    bands = cfg["style"]["hull"].get("bands")
    if bands is None:
        S = _setup(cfg)
        m0 = measure(cfg, paths[0], box, size, S)
        bands = [float(v) for v in np.percentile(_ndl(S, m0["n"])[m0["body"]], [25, 70])]
    return ss.pmap(_frame, [(cfg, p, box, size, bands) for p in paths])
