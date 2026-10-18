"""Showdown / Gen 6 sprite look: turns render_sprite.py passes into palette pixel art.

Used by make_gif.py (whole loop) and tune_style.py (frame 0, many times).
All numbers come from the config's "palette", "parts" and "style" sections;
SPRITE_PIPELINE.md explains each rule and where it was measured from.
"""
import math
from pathlib import Path

import numpy as np
from PIL import Image

import rustcore

NB4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
LAST_EYE_MASKS = None          # eye stamp pixels per frame of the last stylize_loop (for the checks)
NB8 = NB4 + ((1, 1), (1, -1), (-1, 1), (-1, -1))
ID_RGB = np.array([(1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0), (1, 0, 1), (0, 1, 1), (1, 1, 1)], float) * 255


def hexrgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def colour(cfg, ref):
    """'outline', '#rrggbb', 'line:name' (palette.lines) or 'part:index' -> rgb"""
    if ref == "outline":
        return hexrgb(cfg["palette"]["outline"])
    if ref.startswith("#"):
        return hexrgb(ref)
    if ref.startswith("line:"):
        return hexrgb(cfg["palette"]["lines"][ref[5:]])
    part, i = ref.split(":")
    return hexrgb(cfg["palette"]["parts"][part][int(i)])


def palette(cfg):
    cols = [hexrgb(cfg["palette"]["outline"])]
    for shades in cfg["palette"]["parts"].values():
        cols += [hexrgb(h) for h in shades if hexrgb(h) not in cols]
    # palette.lines {name: "#rrggbb"} (per Pokemon): inner-line colours, e.g. a softer line inside
    # light armour than the outline (style.inner_line {part: "line:name"}); keyed by part name so
    # make_shiny can recolour each with its part
    cols += [hexrgb(h) for h in cfg["palette"].get("lines", {}).values() if hexrgb(h) not in cols]
    return cols


def id_order(cfg):
    return [cfg["parts"]["default_material"]] + sorted(set(cfg["parts"]["materials"].values()))


def box_sum(a, r):
    """sum over the (2r+1)x(2r+1) square around each pixel (zero outside)"""
    p = np.pad(a, r)
    c = p.cumsum(0).cumsum(1)
    c = np.pad(c, ((1, 0), (1, 0)))
    k = 2 * r + 1
    return c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]


def components(mask):
    """8-connected groups of True pixels, as lists of (y, x)"""
    seen = np.zeros_like(mask)
    groups = []
    for y0, x0 in zip(*np.nonzero(mask)):
        if seen[y0, x0]:
            continue
        stack, comp = [(y0, x0)], []
        seen[y0, x0] = True
        while stack:
            y, x = stack.pop()
            comp.append((y, x))
            for yy in (y - 1, y, y + 1):
                for xx in (x - 1, x, x + 1):
                    if 0 <= yy < mask.shape[0] and 0 <= xx < mask.shape[1] and mask[yy, xx] and not seen[yy, xx]:
                        seen[yy, xx] = True
                        stack.append((yy, xx))
        groups.append(comp)
    return groups


_POOL, _POOL_JOBS = None, 0


def _call(job):
    fn, args = job
    return fn(*args)


def pmap(fn, arg_list):
    """[fn(*args) for args in arg_list], spread over worker processes (SPRITE_JOBS, default all
    cores; SPRITE_JOBS=1 runs everything here). Only for per-frame steps that don't depend on
    each other's results, so the output is the same as the plain loop."""
    global _POOL, _POOL_JOBS
    import os
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


# --- loading ------------------------------------------------------------------

def frame_paths(frames_dir, only_first=False):
    """one path per frame: its colour pass (the other passes sit next to it)"""
    paths = sorted(p for p in Path(frames_dir).glob("color_*") if p.suffix in (".png", ".tga"))
    return paths[:1] if only_first else paths


def load_frame(p):
    """every pass of one frame (colour pass path p)"""
    ims = [Image.open(p.with_name(p.name.replace("color_", k + "_"))).convert("RGBA") for k in ("color", "id", "data")]
    for extra in ("rest", "lines", "shadow", "seams", "islands"):      # optional passes
        q = p.with_name(p.name.replace("color_", extra + "_"))
        ims.append(Image.open(q).convert("RGBA") if q.exists() else None)
    return tuple(ims)


def load_passes(frames_dir, only_first=False):
    return [load_frame(p) for p in frame_paths(frames_dir, only_first)]


def alpha_bbox(color):
    return color.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()


def color_info(p):
    """a frame's box for framing(), and whether it touches the render's edge (cut off)"""
    color = Image.open(p).convert("RGBA")
    a = np.array(color.getchannel("A")) > 8
    return alpha_bbox(color), bool(a[0].any() or a[-1].any() or a[:, 0].any() or a[:, -1].any())


def load_prepare(cfg, p, box, size):
    return prepare(cfg, *load_frame(p), box, size)


def framing(passes, height, anchor=None, boxes=None):
    """One crop box for the whole loop (no jitter); scale so frame 0 is `height` px tall.
    anchor: indices of the frames that fix the pixel grid (e.g. all but a fast spin, whose
    in-between poses reach a little further); the box is then grown by whole sprite pixels to
    fit the rest, so the anchor frames sample exactly as they would on their own.
    boxes: each frame's alpha_bbox, if already known (then passes isn't needed)."""
    if boxes is None:
        boxes = [alpha_bbox(color) for color, *_ in passes]
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


def prepare(cfg, color_im, id_im, data_im, *rest):
    """Everything about a frame that doesn't depend on the style numbers."""
    *extra, box, size = rest
    rest_im = extra[0] if len(extra) > 0 else None
    lines_im = extra[1] if len(extra) > 1 else None
    shadow_im = extra[2] if len(extra) > 2 else None
    seams_im = extra[3] if len(extra) > 3 else None
    islands_im = extra[4] if len(extra) > 4 else None
    # coverage from the box-filtered render; colour from one centre sample per pixel, like the
    # game rendering at native resolution (box-filtered edge colours bleed toward white)
    c = np.array(color_im.crop(box).resize(size, Image.Resampling.BOX))
    ids = np.array(id_im.crop(box).resize(size, Image.Resampling.NEAREST)).astype(float)
    d = np.array(data_im.crop(box).resize(size, Image.Resampling.NEAREST)).astype(float)
    solid = c[..., 3] > 127
    albedo = np.array(color_im.crop(box).resize(size, Image.Resampling.NEAREST))[..., :3].astype(float)
    if (~(np.array(color_im.crop(box).resize(size, Image.Resampling.NEAREST))[..., 3] > 127) & solid).any():
        # centre sample fell outside the shape on a covered edge pixel: borrow the box colour
        near_alpha = np.array(color_im.crop(box).resize(size, Image.Resampling.NEAREST))[..., 3] > 127
        albedo[solid & ~near_alpha] = c[solid & ~near_alpha][:, :3]

    n = d[..., :3] / 255 * 2 - 1
    n[..., 2] = np.sqrt(np.clip(1 - n[..., 0] ** 2 - n[..., 1] ** 2, 0, 1))
    lum = albedo @ np.array([0.3, 0.6, 0.1])

    # part per pixel: ID pass picks the material group, body texture colour splits the body
    order = id_order(cfg)
    which = np.argmin(((ids[..., None, :3] - ID_RGB[None, None, :len(order)]) ** 2).sum(-1), -1)
    alb_names = list(cfg["parts"]["albedo"])
    alb_cols = np.array([hexrgb(cfg["parts"]["albedo"][k]) for k in alb_names], float)
    nearest = np.array(alb_names, dtype=object)[np.argmin(((albedo[..., None, :] - alb_cols) ** 2).sum(-1), -1)]
    part = np.full(solid.shape, "", dtype=object)
    fixed = np.zeros(solid.shape, bool)                      # pixels with a fixed colour (eyes)
    fixed_rgb = np.zeros((*solid.shape, 3), np.uint8)
    eye_area = np.zeros(solid.shape, bool)
    eye_xy = None
    for i, name in enumerate(order):
        m = solid & (which == i)
        if name == cfg["parts"]["default_material"]:
            part[m] = nearest[m]
        elif "|" in name:
            # a material limited to some parts (parts.materials {"body_b": "petal|teal"}): nearest
            # albedo among those only, so e.g. a petal's dark base can't turn into spike colour
            allowed = [alb_names.index(k) for k in name.split("|")]
            sub = np.array(alb_names, dtype=object)[allowed]
            part[m] = sub[np.argmin(((albedo[..., None, :] - alb_cols[allowed]) ** 2).sum(-1), -1)][m]
        elif name == "eye":
            part[m] = nearest[m]
            eye_area |= m
        else:
            part[m] = name

    if "eye" in order:
        # Eyes by coverage at full render resolution, not one centre sample: a sprite pixel is
        # pupil if at least `cover` of it is pupil, eye-white likewise. Point sampling made the
        # eye blurry/broken and flicker as it moved.
        eye = cfg["parts"]["eye"]
        cover = eye.get("cover", 0.4)
        id_hi = np.array(id_im.crop(box)).astype(float)
        col_hi = np.array(color_im.crop(box)).astype(float)
        eye_hi = (np.argmin(((id_hi[..., None, :3] - ID_RGB[None, None, :len(order)]) ** 2).sum(-1), -1)
                  == order.index("eye")) & (id_hi[..., 3] > 127)
        lum_hi = col_hi[..., :3] @ np.array([0.3, 0.6, 0.1])
        near_hi = np.argmin(((col_hi[..., None, :3] - alb_cols) ** 2).sum(-1), -1)
        dark_hi = eye_hi & (lum_hi < eye["dark_below"])
        white_hi = eye_hi & ~dark_hi & (near_hi == alb_names.index(eye["white_is"]))
        frac = lambda m: np.array(Image.fromarray(m.astype(np.uint8) * 255).resize(size, Image.Resampling.BOX)) / 255
        dark = solid & (frac(dark_hi) >= cover)
        white = solid & ~dark & (frac(white_hi) >= cover)
        fixed_rgb[dark] = colour(cfg, eye["dark"])
        fixed_rgb[white] = colour(cfg, eye["light"])
        fixed = dark | white
        eye_area |= fixed
        # eye centre in sprite pixels (sub-pixel), for placing the eye stamp
        ys_, xs_ = np.nonzero(dark_hi)
        if len(xs_):
            kx_, ky_ = (box[2] - box[0]) / size[0], (box[3] - box[1]) / size[1]
            eye_xy = ((xs_.mean() + 0.5) / kx_ - 0.5, (ys_.mean() + 0.5) / ky_ - 0.5)

    # small fragments of a part (parts.min_region {part: px}, per Pokemon): a piece of that part
    # smaller than px pixels takes the part most of its border touches - scattered splashes of an
    # accent colour (Mega Golisopod's purple) and features a few pixels big read as noise at
    # sprite size, where an artist would leave them out
    for name, n_min in cfg["parts"].get("min_region", {}).items():
        mask = solid & (part == name) & ~eye_area
        H_, W_ = mask.shape; seen = np.zeros_like(mask)
        for y0, x0 in zip(*np.nonzero(mask)):
            if seen[y0, x0]:
                continue
            comp, st_, border = [], [(y0, x0)], {}
            seen[y0, x0] = True
            while st_:
                y, x = st_.pop(); comp.append((y, x))
                for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if 0 <= yy < H_ and 0 <= xx < W_ and solid[yy, xx]:
                        if mask[yy, xx]:
                            if not seen[yy, xx]:
                                seen[yy, xx] = True; st_.append((yy, xx))
                        elif part[yy, xx] and not eye_area[yy, xx]:
                            border[part[yy, xx]] = border.get(part[yy, xx], 0) + 1
            if len(comp) < n_min and border:
                new = max(border, key=border.get)
                for y, x in comp:
                    part[y, x] = new

    # texture detail for grain: brightness against the local average of the *same part* only.
    # (Averaging across a part border makes every border pixel look dark -> dark specks.)
    detail = np.zeros(solid.shape)
    for name in set(part[solid].tolist()):
        m = (part == name).astype(float)
        local = box_sum(lum * m, 2) / np.maximum(box_sum(m, 2), 1e-6)
        detail[m > 0] = ((lum - local) / 255)[m > 0]
    detail[fixed] = 0

    # full-resolution silhouette with a margin, for the supersampled outline
    kx, ky = (box[2] - box[0]) / size[0], (box[3] - box[1]) / size[1]   # render px per sprite px
    margin = round(4 * max(kx, ky))
    hi_box = (box[0] - margin, box[1] - margin, box[2] + margin, box[3] + margin)
    alpha_hi = np.array(color_im.crop(hi_box).getchannel("A")) > 127
    # high-resolution inner lines (style.hires_lines): depth jumps / folds found on the full-size
    # data pass, then per sprite pixel the fraction of it they cover. Point-sampling the data
    # at sprite size made thin features' lines (Glimmora's crown separators) depend on the
    # sub-pixel crop offset: a third of them vanished when the loop's crop box shifted.
    line_cov = None
    hl_cfg = cfg["style"].get("hires_lines")
    if hl_cfg:
        dh = np.array(data_im.crop(box)).astype(float)
        okh = dh[..., 3] > 0
        nh = dh[..., :3] / 255 * 2 - 1
        nh[..., 2] = np.sqrt(np.clip(1 - nh[..., 0] ** 2 - nh[..., 1] ** 2, 0, 1))
        dep = dh[..., 2]
        Lh = np.zeros(okh.shape, bool)
        for dy, dx in NB4:
            nb = shift(okh, dy, dx, False) & shift(okh, -dy, -dx, False)
            jump = shift(dep, dy, dx, 0) - dep
            other = dep - shift(dep, -dy, -dx, 0)
            Lh |= okh & nb & (jump > hl_cfg.get("depth_jump", 2)) & (jump - other > hl_cfg.get("depth_jump", 2))
            bend = (nh * shift(nh, dy, dx, 0)).sum(-1)
            Lh |= okh & nb & (bend < hl_cfg.get("crease_cos", 0.3)) & (jump >= 0)
        line_cov = np.array(Image.fromarray(Lh.astype(np.uint8) * 255).resize(size, Image.Resampling.BOX)) / 255

    # cast shadow (render.shadow): at full render resolution, pixels that face the sun
    # (N.L > 0.15 from the data pass) but receive under 35% of the light they should = blocked by
    # another part; per sprite pixel, the covered fraction
    cast = unlit_frac = None
    if shadow_im is not None and cfg["render"].get("shadow"):
        Lc = np.array(cfg["render"]["shadow"]["light_cam"], float); Lc /= np.linalg.norm(Lc)
        dh = np.array(data_im.crop(box)).astype(float)
        nh = dh[..., :3] / 255 * 2 - 1
        nh[..., 2] = np.sqrt(np.clip(1 - nh[..., 0] ** 2 - nh[..., 1] ** 2, 0, 1))
        cos = nh @ Lc
        sh = np.array(shadow_im.crop(box)).astype(float)
        lit = sh[..., 0] / 255
        blocked = (sh[..., 3] > 127) & (dh[..., 3] > 0) & (cos > 0.15) & (lit < 0.35 * cos)
        unlit = (sh[..., 3] > 127) & (lit < 0.08)       # everything the sun doesn't reach
        if cfg["style"].get("cast_shadow", {}).get("mode") == "unlit":
            blocked = unlit
        frac = lambda m: np.array(Image.fromarray(m.astype(np.uint8) * 255).resize(size, Image.Resampling.BOX)) / 255
        cast = frac(blocked)
        unlit_frac = frac(unlit)
    # seam lines (render.seams, per Pokemon): the seam pass's brightness, per sprite pixel the
    # fraction of it a seam covers
    seam_cov = None
    if seams_im is not None:
        sm = np.array(seams_im.crop(box)).astype(float)
        sv = sm[..., :3].mean(-1) * (sm[..., 3] / 255)
        seam_cov = np.array(Image.fromarray(np.clip(sv, 0, 255).astype(np.uint8)).resize(size, Image.Resampling.BOX)) / 255
    # plate id per sprite pixel (islands pass, per Pokemon; make_seams.py --islands): which UV
    # island = which armour plate / segment the pixel's centre shows; 0 = none
    plate = None
    if islands_im is not None:
        il = np.array(islands_im.crop(box).resize(size, Image.Resampling.NEAREST)).astype(float)
        lv = np.clip(np.round(il[..., :3] / 36), 0, 7).astype(int)
        plate = np.where(il[..., 3] > 127, lv[..., 0] * 64 + lv[..., 1] * 8 + lv[..., 2], 0)
        plate[~solid] = 0
    return {"solid": solid, "n": n, "depth": d[..., 2], "has_data": d[..., 3] > 0, "cast": cast, "unlit": unlit_frac, "line_cov": line_cov,
            "seam_cov": seam_cov, "plate": plate,
            "detail": detail, "part": part, "fixed": fixed, "fixed_rgb": fixed_rgb, "eye_area": eye_area,
            "eye_xy": eye_xy,
            "rest": (np.array(rest_im.crop(box).resize(size, Image.Resampling.NEAREST)) if rest_im is not None else None),
            # Freestyle line coverage per sprite pixel (0..1), from the full-size line render
            "fs_cov": (np.array(lines_im.crop(box).getchannel("A").resize(size, Image.Resampling.BOX)) / 255
                       if lines_im is not None else None),
            "alpha_hi": alpha_hi, "hi_margin": margin, "hi_per_px": (kx, ky)}


def grow(mask, steps):
    """dilate by `steps` render pixels, alternating + and square kernels (close to a disc)"""
    for i in range(steps):
        nb = NB4 if i % 2 == 0 else NB8
        out = mask.copy()
        for dy, dx in nb:
            out |= shift(mask, dy, dx, False)
        mask = out
    return mask


def supersampled_outline(f, width, cover, pad):
    """Outline drawn at render resolution `width` sprite-px wide, then shrunk to sprite size:
    a pixel is outline if at least `cover` of it is covered. Gives the mix of clean diagonal
    steps and filled corners seen in the game's own outlines."""
    kx, ky = f["hi_per_px"]
    hi = grow(f["alpha_hi"], max(1, round(width * (kx + ky) / 2)))
    h, w = f["solid"].shape
    M = f["hi_margin"]
    region = (M - pad * kx, M - pad * ky, M + (w + pad) * kx, M + (h + pad) * ky)
    small = np.array(Image.fromarray(hi.astype(np.uint8) * 255)
                     .resize((w + 2 * pad, h + 2 * pad), Image.Resampling.BOX, box=region))
    return small >= cover * 255


# --- the look -----------------------------------------------------------------

def matcap_light(matcap, n):
    """bilinear lookup of a learned matcap (learn_matcap.py) by camera-space normal x, y"""
    M = np.array(matcap["values"], float)
    N = matcap["size"]
    fx = np.clip((n[..., 0] + 1) / 2 * N - 0.5, 0, N - 1)
    fy = np.clip((n[..., 1] + 1) / 2 * N - 0.5, 0, N - 1)
    x0, y0 = np.floor(fx).astype(int), np.floor(fy).astype(int)
    x1, y1 = np.minimum(x0 + 1, N - 1), np.minimum(y0 + 1, N - 1)
    tx, ty = fx - x0, fy - y0
    return (M[y0, x0] * (1 - tx) * (1 - ty) + M[y0, x1] * tx * (1 - ty)
            + M[y1, x0] * (1 - tx) * ty + M[y1, x1] * tx * ty) * 2 - 1     # same -1..1 range as n·L


def lighting(st, f, grain=True):
    """per-pixel light value: learned matcap if present, else a single light; plus texture grain"""
    if st.get("matcap") and st.get("use_matcap", True):
        n = f["n"]
        clamp = st.get("matcap_edge_clamp")
        if clamp:
            # grazing normals (silhouette edges) looked up as if at radius `clamp`: the matcap's
            # darkest ring otherwise draws a dark band along every outline (a rim, not a shadow)
            r = np.linalg.norm(n[..., :2], axis=-1, keepdims=True)
            n = np.where(r > clamp, n * (clamp / np.maximum(r, 1e-6)), n)
        base = matcap_light(st["matcap"], n)
    else:
        L = np.array(st["light"], float); L /= np.linalg.norm(L)
        base = f["n"] @ L
    r = st.get("shade_blur")
    if r:
        # light averaged over a (2r+1)^2 window within the same part: every pixel otherwise takes
        # its normal from one point of the render, so small modelled detail (plate ridges, wing
        # folds) flips shade bands pixel by pixel - blotches and streaks instead of Showdown's
        # broad shade masses. Within the part only, so a border doesn't borrow its neighbour's light
        out = base.copy()
        for name in set(f["part"][f["solid"]].tolist()):
            m = ((f["part"] == name) & f["solid"]).astype(float)
            avg = box_sum(base * m, int(r)) / np.maximum(box_sum(m, int(r)), 1e-6)
            out[m > 0] = avg[m > 0]
        base = out
    ps = st.get("plate_shading")
    plate_parts = np.zeros(f["solid"].shape, bool)
    if ps and f.get("plate") is not None:
        # per Pokemon (style.plate_shading): shade each plate (UV island = armour piece, from the
        # islands pass) as one unit, the way a sprite artist does: the plate's mean light, keeping
        # `follow` of the per-pixel light (0 = flat plate, 1 = no change), then `edge.dark` darker
        # within `edge.width` px of the plate's border on the `edge.dir` side ([1, 0] = its lower
        # edge, away from a light above). Shading then follows the armour, not stray folds / shadows.
        P = f["plate"]
        plate_parts = np.isin(f["part"], ps["parts"]) & f["solid"] & (P > 0)
        follow = ps.get("follow", 0.3)
        key = np.where(plate_parts, P * 64 + np.searchsorted(sorted(ps["parts"]), f["part"].astype(str)), -1)
        out = base.copy()
        for k in np.unique(key[plate_parts]):
            m = key == k
            mu = base[m].mean()
            out[m] = mu + follow * (base[m] - mu)
        e = ps.get("edge")
        if e:
            dy, dx = e.get("dir", [1, 0])
            near = np.zeros_like(plate_parts)
            for w in range(1, int(e.get("width", 1)) + 1):
                other = shift(key, -dy * w, -dx * w, -1)          # the pixel w steps toward the edge side
                near |= plate_parts & (other != key)
            out[near] -= e.get("dark", 0.3)
        base = np.where(plate_parts, out, base)
    lift = st.get("edge_lift")
    if lift:
        # pixels right inside the silhouette (1 px) lit up by `lift` per part: thin curled-away
        # edges otherwise read as a dark rim along every outline (Showdown keeps its darks in
        # shadow masses, not along the line)
        d1 = f["solid"] & (edge_distance(f["solid"]) == 1)
        add = np.zeros(f["solid"].shape)
        for name, v in (lift.items() if isinstance(lift, dict) else ((p, lift) for p in set(f["part"][f["solid"]].tolist()))):
            add[d1 & (f["part"] == name)] = v
        base = base + add
    cs = st.get("cast_shadow")
    if cs and f.get("cast") is not None:
        # cast shadow: a pixel mostly covered by it is pushed down by `strength` (light values
        # run about -1..1), so it lands in the part's dark shades as one solid mass
        on = f["cast"] >= cs.get("cover", 0.5)
        if ps and not ps.get("cast", True):          # plate-shaded parts take no cast shadow
            on &= ~plate_parts
        base = base - cs.get("strength", 1.0) * on
        if cs.get("unlit_strength") and f.get("unlit") is not None:
            # faces turned away from the sun (not cast-shadowed): a separate, usually gentler push
            un = (f["unlit"] >= cs.get("cover", 0.5)) & ~on
            if ps and not ps.get("cast", True):
                un &= ~plate_parts
            base = base - cs["unlit_strength"] * un
    if not grain:
        return base
    g = np.zeros(f["solid"].shape)
    for name, v in st["grain"].items():
        g[f["part"] == name] = v
    return base + g * f["detail"]


def shade_ranks(st, f, pal):
    """shade index per pixel (-1 = no part). Grain may move a pixel at most
    `grain_max_bands` shades away from its grain-free shade (big jumps read as specks)."""
    light, plain = lighting(st, f), lighting(st, f, grain=False)
    rank = np.full(f["solid"].shape, -1)
    for name, shades in pal.items():
        m = f["part"] == name
        band = lambda v: np.minimum(st["first_shade"].get(name, 0)
                                    + sum((v >= t).astype(int) for t in st["thresholds"][name]), len(shades) - 1)
        b0, b1 = band(plain), band(light)
        k = st.get("grain_max_bands", 1)
        rank[m] = np.clip(b1, b0 - k, b0 + k)[m]
    for name, n_t in st.get("part_tones", {}).items():
        # per Pokemon (style.part_tones {part: n}): the part uses only n shades, spread evenly over
        # its ramp from first_shade; every rank snaps to the nearest kept one (fewer colours where a
        # small part - claw tips, spikes - doesn't need a full ramp)
        if name not in pal:
            continue
        lo, hi = st["first_shade"].get(name, 0), len(pal[name]) - 1
        kept = np.array(sorted({int(round(v)) for v in np.linspace(lo, hi, int(n_t))}))
        m = (f["part"] == name) & (rank >= 0)
        rank[m] = kept[np.abs(rank[m][:, None] - kept[None, :]).argmin(1)]
    return rank


def despeckle(rank, f, pal, st):
    """A pixel two or more shades darker than all four neighbours (same part), or a lone
    pixel in its part's darkest shade, is a speck: lift it to its lightest-dark neighbour."""
    part, solid = f["part"], f["solid"]
    inner = solid & ~f["fixed"]
    nbr = [shift(rank, dy, dx, -1) for dy, dx in NB4]
    same = np.all([shift(part, dy, dx, "") == part for dy, dx in NB4], axis=0)
    lo = np.min(nbr, axis=0)
    lowest = np.zeros_like(rank)
    for name in pal:
        lowest[part == name] = st["first_shade"].get(name, 0)
    speck = inner & same & (lo >= 0) & ((rank <= lo - 2) | ((rank == lowest) & (rank < lo)))
    out = rank.copy()
    out[speck] = lo[speck]
    n = st.get("min_region")
    if n:
        out = merge_small_regions(out, part, inner, int(n))
    return out


def merge_small_regions(rank, part, inner, n, rounds=4):
    """style.min_region: a shade island (4-connected pixels of one part and one shade) smaller
    than n pixels takes the shade most of its same-part border has. Showdown shades in broad
    masses; islands of a few pixels in the middle of a plate read as dirt."""
    H, W = rank.shape
    rank = rank.copy()
    for _ in range(rounds):
        seen = np.zeros((H, W), bool); changed = 0
        for y0, x0 in zip(*np.nonzero(inner & (rank >= 0))):
            if seen[y0, x0]:
                continue
            r0, p0 = rank[y0, x0], part[y0, x0]
            comp, st, border = [], [(y0, x0)], {}
            seen[y0, x0] = True
            while st:
                y, x = st.pop(); comp.append((y, x))
                for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if not (0 <= yy < H and 0 <= xx < W) or not inner[yy, xx] or part[yy, xx] != p0 or rank[yy, xx] < 0:
                        continue
                    if rank[yy, xx] == r0:
                        if not seen[yy, xx]:
                            seen[yy, xx] = True; st.append((yy, xx))
                    else:
                        border[rank[yy, xx]] = border.get(rank[yy, xx], 0) + 1
            if len(comp) < n and border:
                new = max(border, key=border.get)
                for y, x in comp:
                    rank[y, x] = new
                changed += 1
        if not changed:
            break
    return rank


def edge_distance(solid):
    """pixels from the nearest non-body pixel (1 = on the edge), by repeated erosion"""
    d = np.zeros(solid.shape, int)
    cur = solid.copy()
    k = 0
    while cur.any():
        k += 1
        inner = cur.copy()
        for dy, dx in NB4:
            inner &= shift(cur, dy, dx, False)
        d[cur & ~inner] = k
        cur = inner
    return d


def part_border_distance(solid, part, name, eye_area):
    """inside part `name`: 4-step distance from the pixels touching another body part
    (1 = touching); 0 outside the part or where it can't be reached"""
    pm = solid & (part == name) & ~eye_area
    other = solid & (part != name) & ~eye_area
    d = np.zeros(solid.shape, int)
    frontier = np.zeros_like(pm)
    for dy, dx in NB4:
        frontier |= pm & shift(other, dy, dx, False)
    k = 1; seen = frontier.copy(); d[frontier] = 1
    while frontier.any() and k < 16:
        nxt = np.zeros_like(pm)
        for dy, dx in NB4:
            nxt |= pm & ~seen & shift(frontier, dy, dx, False)
        k += 1; d[nxt] = k; seen |= nxt; frontier = nxt
    return d


def thin(mask):
    """Zhang-Suen thinning: reduce line blobs to 1-pixel-wide, 8-connected skeletons."""
    m = mask.copy()
    while True:
        changed = False
        for step in (0, 1):
            P = np.pad(m, 1)
            p2, p3, p4, p5 = P[:-2, 1:-1], P[:-2, 2:], P[1:-1, 2:], P[2:, 2:]
            p6, p7, p8, p9 = P[2:, 1:-1], P[2:, :-2], P[1:-1, :-2], P[:-2, :-2]
            ring = [p2, p3, p4, p5, p6, p7, p8, p9, p2]
            B = sum(r.astype(int) for r in ring[:8])
            A = sum((~ring[k] & ring[k + 1]).astype(int) for k in range(8))
            if step == 0:
                c = ~(p2 & p4 & p6) & ~(p4 & p6 & p8)
            else:
                c = ~(p2 & p4 & p8) & ~(p2 & p6 & p8)
            rem = m & (B >= 2) & (B <= 6) & (A == 1) & c
            if rem.any():
                m &= ~rem
                changed = True
        if not changed:
            return m


def blocks2x2(mask):
    """top-left corners of 2x2 blocks that are all True"""
    b = np.zeros_like(mask)
    b[:-1, :-1] = mask[:-1, :-1] & mask[1:, :-1] & mask[:-1, 1:] & mask[1:, 1:]
    return b


# --- stage 1: per-frame layers (no drawing yet) ---------------------------------

def layers(cfg, f, style=None):
    """Shade ranks, raw inner lines and rim for one frame. Kept separate from drawing so a
    whole loop can be stabilised over time (vote_over_time) before compose()."""
    st = dict(cfg["style"], **(style or {}))
    pal = cfg["palette"]["parts"]
    solid, n, depth, part = f["solid"], f["n"], f["depth"], f["part"]
    light = lighting(st, f)
    rank = despeckle(shade_ranks(st, f, pal), f, pal, st)

    ok = solid & f["has_data"] & ~f["eye_area"]          # the eye has its own drawing
    hy = st.get("line_hysteresis", {})
    # fold-line threshold, optionally stricter per part (Showdown's shell has few inner lines)
    crease = np.full(solid.shape, float(st["crease_cos"]))
    for name, v in st.get("crease_cos_part", {}).items():
        crease[part == name] = v
    djump = np.full(solid.shape, float(st["depth_jump"]))
    for name, v in st.get("depth_jump_part", {}).items():
        djump[part == name] = v
    line = np.zeros_like(solid)
    weak = np.zeros_like(solid)
    part_line = np.zeros_like(solid)
    outlined = np.isin(part, st.get("part_outline", []))
    wjump = np.maximum(1.0, djump * hy.get("depth_factor", 0.5))
    wcrease = np.minimum(0.97, crease + hy.get("crease_add", 0.1))
    for dy, dx in NB4:
        nb_ok = shift(ok, dy, dx, False) & shift(ok, -dy, -dx, False)
        # overlap: a depth jump toward a nearer neighbour, bigger than the slope on the other side
        jump = shift(depth, dy, dx, 0) - depth
        other = depth - shift(depth, -dy, -dx, 0)
        line |= ok & nb_ok & (jump > djump) & (jump - other > djump)
        weak |= ok & nb_ok & (jump > wjump) & (jump - other > wjump)
        # fold: neighbouring normals far apart (shell rims, spikes, flipper roots)
        bend = (n * shift(n, dy, dx, 0)).sum(-1)
        line |= ok & nb_ok & (bend < crease) & (jump >= 0)
        weak |= ok & nb_ok & (bend < wcrease) & (jump >= 0)
        # parts outlined all round (e.g. Lapras's shell): line the other part's side
        part_line |= solid & ~outlined & shift(outlined, dy, dx, False) & shift(solid, dy, dx, False)

    hl_cfg = st.get("hires_lines")
    cov = (f.get("fs_cov") if hl_cfg and hl_cfg.get("source") == "freestyle" else f.get("line_cov")) if hl_cfg else None
    if hl_cfg and cov is not None:
        # for these parts, inner lines come from the full-resolution detection (see prepare), or
        # with source "freestyle" from the mesh-traced lines pass (every crown petal's own edge)
        hp = np.isin(part, hl_cfg["parts"]) & solid & ~f["eye_area"]
        hi = hp & (cov >= hl_cfg.get("cover", 0.15))
        line = (line & ~hp) | hi
        weak = (weak & ~hp) | hi

    sl = st.get("seam_lines")
    if sl and f.get("seam_cov") is not None:
        # per Pokemon (style.seam_lines {parts, cover}): plate edges / grooves from the seam maps,
        # added to the detected lines for these parts only (Golisopod's armour: Showdown traces
        # every plate; Lapras has none of this). A pixel is a line if `cover` of it is seam
        sp = np.isin(part, sl["parts"]) & solid & ~f["eye_area"]
        on = sp & (f["seam_cov"] >= sl.get("cover", 0.25))
        line |= on
        weak |= on
        b = sl.get("bridge")
        if b:
            # close small gaps: a pixel with at least `bridge` seam coverage whose neighbours on two
            # opposite sides are both seam lines joins them (a seam split across two sprite
            # pixels otherwise leaves a stub-gap-stub)
            weakseam = sp & ~on & (f["seam_cov"] >= b)
            for (ay, ax), (by, bx) in (((-1, 0), (1, 0)), ((0, -1), (0, 1)), ((-1, -1), (1, 1)), ((-1, 1), (1, -1))):
                join = weakseam & shift(on, -ay, -ax, False) & shift(on, -by, -bx, False)
                line |= join
                weak |= join

    if st.get("line_source") == "freestyle" and f.get("fs_cov") is not None:
        # lines traced from the mesh (creases, inner contours, borders): replaces the per-pixel
        # depth / fold detection, which re-traced lines differently every frame
        line = solid & ~f["eye_area"] & (f["fs_cov"] >= st.get("fs_cover", 0.35)) & ~part_line
        weak = line.copy()

    # parallel lines: a line (and optional shade) at a fixed distance inside a part, counted from
    # where it touches the rest of the body (Showdown's shell lip: outline, 2 lip px, "=" at 3,
    # "#" at 4). Part of the line layer, so it's decided on the key frame and carried.
    shade_line = np.zeros_like(solid)
    pl_line = np.zeros_like(solid)
    border_dist = {}
    for pl in st.get("parallel_lines", []):
        d = part_border_distance(solid, part, pl["part"], f["eye_area"])
        border_dist[pl["part"]] = d
        # only where the part is thick enough that the band always exists (else it blinks
        # in and out as the part's thickness crosses the band distance)
        thick = d >= pl.get("min_thickness", pl["distance"] + 2)
        near_thick = thick.copy()
        for _ in range(pl.get("min_thickness", pl["distance"] + 2)):
            grown = near_thick.copy()
            for dy, dx in NB8:
                grown |= shift(near_thick, dy, dx, False)
            near_thick = grown
        if "offset" in pl:
            # a shifted copy of the border: every border pixel (touching the body) puts the line
            # `distance` steps along `offset` and the shade `shade.distance` steps, where that
            # pixel is still inside the part. Moves exactly with the border (no isoline jumps).
            ox, oy = pl["offset"]
            pm = solid & (part == pl["part"]) & ~f["eye_area"]
            border = d == 1
            pl_line |= shift(border, oy * pl["distance"], ox * pl["distance"], False) & pm & ~border
            if "shade" in pl:
                k = pl["shade"]["distance"]
                shade_line |= shift(border, oy * k, ox * k, False) & pm & ~border
        else:
            pl_line |= (d == pl["distance"]) & near_thick
            if "shade" in pl:
                shade_line |= (d == pl["shade"]["distance"]) & near_thick

    edge = np.zeros_like(solid)
    for dy, dx in NB4:
        edge |= solid & ~shift(solid, dy, dx, False)
    rim = edge & (light < st["rim_light"]) & ~f["eye_area"]
    # specular highlight: the most lit pixels of a part take a brighter colour (Showdown's
    # shell spikes catch cream-white highlights)
    hl = np.zeros_like(solid)
    dist = edge_distance(solid)
    for name, h in st.get("highlight", {}).items():
        value = n[..., 1] if h.get("by") == "facing_up" else light     # up-facing surfaces, or most lit
        hl |= (part == name) & (value >= h["above"]) & ~f["eye_area"] & (dist >= h.get("min_edge_dist", 0))
        if "min_border_dist" in h:                       # keep off e.g. the shell lip next to the body
            bd = border_dist.get(name)
            if bd is None:
                bd = part_border_distance(solid, part, name, f["eye_area"])
            hl &= (bd == 0) | (bd >= h["min_border_dist"])
    return {"rank": rank, "line": line & ~part_line, "part_line": part_line, "rim": rim, "edge": edge,
            "highlight": hl, "light": light, "dist": dist, "weak": (weak | line) & ~part_line,
            "shade_line": shade_line & ~line & ~part_line & ~pl_line, "pl_line": pl_line & ~part_line}


# --- stage 2: draw one frame -------------------------------------------------------

def dark_line_colours(cfg):
    """every colour that counts as a line for the 1-px rule: the outline plus the style's
    dark_line_colours (e.g. the dark blue used for inner lines / shades). Shared with the checks."""
    return [colour(cfg, "outline")] + [colour(cfg, r) for r in cfg["style"].get("dark_line_colours", [])]


def part_of_colour(cfg):
    """rgb -> set of part names it can belong to (outline -> {'O'}); a part's highlight
    colour (style.highlight) counts as that part too"""
    m = {colour(cfg, "outline"): {"O"}}
    for name, shades in cfg["palette"]["parts"].items():
        for h in shades:
            m.setdefault(hexrgb(h), set()).add(name)
    for name, h in cfg["style"].get("highlight", {}).items():
        m.setdefault(colour(cfg, h["colour"]), set()).add(name)
    for name, ref in cfg["style"].get("line_shade", {}).items():     # crease shades belong too
        m.setdefault(colour(cfg, ref), set()).add(name)
    for pl in cfg["style"].get("parallel_lines", []):                 # and lip-band shades
        if "shade" in pl:
            m.setdefault(colour(cfg, pl["shade"]["colour"]), set()).add(pl["part"])
    return m


def clean_lines(cfg, s, protect=None, prev=None, nxt=None, corners=True):
    """Make every outline-colour line pixel-perfect and 1 px wide, counting diagonals:
      * staircase corners: a line pixel with one horizontal and one vertical line neighbour
        (and not the pixel between them) is dropped, unless it's needed to close the outline
        (it touches both the body and the outside);
      * an inner line pixel (not touching the outside) that touches the outline at 2+
        points, diagonals included, runs alongside it and is dropped;
      * 2x2 blocks are broken up.
    A dropped outline pixel becomes transparent; a dropped inner pixel takes the most common
    body colour around it. protect = pixels never touched (the eye stamp). With prev / next
    frames, where there is a choice the replacement agreeing with them is preferred."""
    if rustcore.lib is not None:
        return rustcore.clean_lines(cfg, s, protect, prev, nxt, corners)
    OUT = colour(cfg, "outline")
    s = s.copy()
    H, W = s.shape[:2]
    protect = np.zeros((H, W), bool) if protect is None else protect
    DARK = dark_line_colours(cfg)

    def fixes(y0, y1, x0, x1):
        """candidates in s[y0:y1, x0:x1] with their new value and score (agreement with the
        neighbouring frames). Every rule looks at most 2 px away, so on a crop the result is
        exact except within 2 px of a cut that isn't the canvas edge."""
        t, pr = s[y0:y1, x0:x1], protect[y0:y1, x0:x1]
        h, w = t.shape[:2]
        solid = t[..., 3] > 0
        line_all = solid & np.any([np.all(t[..., :3] == c, -1) for c in DARK], 0)   # incl. protected (eye)
        is_out = solid & np.all(t[..., :3] == OUT, -1)
        line = line_all & ~pr                                   # the ones we may change
        body = solid & ~line_all
        out_ = ~solid
        nb = lambda m, dy, dx: shift(m, dy, dx, False)
        up, dn, lf, rt = nb(line_all, 1, 0), nb(line_all, -1, 0), nb(line_all, 0, 1), nb(line_all, 0, -1)
        touches_body = nb(body, 1, 0) | nb(body, -1, 0) | nb(body, 0, 1) | nb(body, 0, -1)
        nbo = lambda m, dy, dx: shift(m, dy, dx, True)          # beyond the canvas counts as outside
        touches_out = nbo(out_, 1, 0) | nbo(out_, -1, 0) | nbo(out_, 0, 1) | nbo(out_, 0, -1)
        required = touches_body & touches_out & is_out          # outline pixels that close the shape
        required |= line & separators(cfg, t, line_all, pr)     # and ones between an outlined part and the rest
        ul, ur, dl, dr = nb(line_all, 1, 1), nb(line_all, 1, -1), nb(line_all, -1, 1), nb(line_all, -1, -1)
        corner = line & (((up & lf) & ~dn & ~rt & ~ul) | ((up & rt) & ~dn & ~lf & ~ur)
                         | ((dn & lf) & ~up & ~rt & ~dl) | ((dn & rt) & ~up & ~lf & ~dr))
        ring = line & touches_out
        ring_n8 = sum(nb(ring, dy, dx).astype(int) for dy, dx in NB8)
        along = line & ~touches_out & (ring_n8 >= 2)
        blk = blocks2x2(line_all)
        in_block = (blk | nb(blk, 1, 0) | nb(blk, 0, 1) | nb(blk, 1, 1)) & line
        if not corners:
            corner = np.zeros_like(corner)
        elif corners == "inner":
            corner = corner & ~touches_out
        cand = (corner | along | (in_block & ~required)) & ~required

        def new_value(y, x):
            if touches_out[y, x] and is_out[y, x]:              # an outline pixel: drop it
                return np.zeros(4, np.uint8)
            cols = [tuple(t[y + dy, x + dx][:3]) for dy, dx in NB8
                    if 0 <= y + dy < h and 0 <= x + dx < w and body[y + dy, x + dx]]
            if not cols:
                return np.zeros(4, np.uint8)
            pick = max(set(cols), key=cols.count)
            for o in (prev, nxt):                       # prefer what the neighbouring frames show
                if o is not None and o[y0 + y, x0 + x, 3] and tuple(o[y0 + y, x0 + x, :3]) in cols:
                    pick = tuple(o[y0 + y, x0 + x, :3]); break
            return np.array((*pick, 255), np.uint8)

        out = []
        for y, x in np.argwhere(cand):
            v = new_value(y, x)
            score = sum(1 for o in (prev, nxt) if o is not None and np.array_equal(o[y0 + y, x0 + x], v))
            out.append((y0 + int(y), x0 + int(x), v, score))
        return out

    # of all pixels that could be fixed, fix first the one whose new colour agrees with the
    # neighbouring frames (so keeping lines 1 px doesn't create a blink); ties: raster order.
    # Each fix only changes candidates within 2 px of it, so only a small window is re-checked.
    score = np.full((H, W), -1, np.int8)
    value = np.zeros((H, W, 4), np.uint8)
    for y, x, v, sc in fixes(0, H, 0, W):
        score[y, x], value[y, x] = sc, v
    R, M = 3, 3                                     # window re-checked, + context it needs
    for _ in range(400):
        i = int(np.argmax(score))                   # first pixel with the best score
        y, x = divmod(i, W)
        if score[y, x] < 0:
            break
        s[y, x] = value[y, x]
        wy0, wy1, wx0, wx1 = max(0, y - R), min(H, y + R + 1), max(0, x - R), min(W, x + R + 1)
        score[wy0:wy1, wx0:wx1] = -1
        for yy, xx, v, sc in fixes(max(0, y - R - M), min(H, y + R + M + 1), max(0, x - R - M), min(W, x + R + M + 1)):
            if wy0 <= yy < wy1 and wx0 <= xx < wx1:
                score[yy, xx], value[yy, xx] = sc, v
    return s


def separators(cfg, s, line_all, protect):
    """line pixels with an outlined part (style.part_outline) on one side and another part on
    the other (4-neighbours): removing one would let the colours touch (the 'leakage' the
    open_outline check counts), so they are never pruned"""
    import check_loop
    return check_loop.separators(cfg, s, line_all, protect)


def seal_parts(cfg, s, protect=None):
    """Close every gap in a part outline: where an outlined part's pixel touches another part
    directly (same rule as the open_outline check), one of these is done, whichever leaves the
    fewest 2x2 line blocks and 2-px diagonals (same rules as the checks):
      * the part's pixel becomes outline colour,   * the other part's pixel does,
      * a stray 1-px sliver (no 4-neighbour of its own part) takes the other part's colour."""
    import check_loop as cl
    OUT = np.array((*colour(cfg, "outline"), 255), np.uint8)
    s = s.copy()
    protect = np.zeros(s.shape[:2], bool) if protect is None else protect
    DARK = dark_line_colours(cfg)

    def state(t):
        solid = t[..., 3] > 0
        line_all = solid & np.any([np.all(t[..., :3] == c, -1) for c in DARK], 0)
        pm = cl.part_masks(cfg, t, line_all, protect)
        contacts = sum(int((own & cl.n4(other)).sum()) for own, other in pm)
        lm = line_all & ~protect
        # the line faults are only needed to rank options that close a contact (the costly part)
        bad = lambda: int(blocks2x2(lm).sum()) + cl.stairs(t, lm, cl.separators(cfg, t, lm, protect))
        return contacts, bad, pm

    for _ in range(200):
        contacts, _, pm = state(s)
        if not contacts:
            break
        options = []
        for own, other in pm:
            for side, opp in ((own, other), (other, own)):
                for y, x in np.argwhere(side & cl.n4(opp)):
                    options.append(((y, x), OUT, side is own))
                    same = [side[y + dy, x + dx] for dy, dx in NB4
                            if 0 <= y + dy < s.shape[0] and 0 <= x + dx < s.shape[1]]
                    if not any(same):                               # a 1-px sliver: absorb it
                        for dy, dx in NB4:
                            yy, xx = y + dy, x + dx
                            if 0 <= yy < s.shape[0] and 0 <= xx < s.shape[1] and opp[yy, xx]:
                                options.append(((y, x), s[yy, xx].copy(), side is own)); break
        best = None
        for (y, x), v, own_side in options:
            t = s.copy(); t[y, x] = v
            c, b, _ = state(t)
            if c >= contacts:
                continue
            key = (b(), c, not own_side)
            if best is None or key < best[0]:
                best = (key, y, x, v)
        if best is None:
            break
        _, y, x, v = best
        s[y, x] = v
    return s


def clean_parts(cfg, s, protect=None):
    """A body pixel whose part differs from all its body 4-neighbours (a stray cream pixel in
    blue skin, a pale pixel against the outline) takes their most common colour.
    Same result as visiting every pixel in raster order, but only pixels that can change are
    visited: a pixel with an identical-colour body neighbour can't (they share a part), and when
    a pixel changes, its later neighbours are re-checked (the raster-order visit would see it)."""
    import heapq
    pc = part_of_colour(cfg)
    s = s.copy()
    H, W = s.shape[:2]
    protect = np.zeros((H, W), bool) if protect is None else protect
    key = lambda: s[..., 0].astype(np.int64) * 65536 + s[..., 1].astype(np.int64) * 256 + s[..., 2]

    def same_colour_nb(k, ok):
        m = np.zeros((H, W), bool)
        for dy, dx in NB4:
            m |= shift(ok, dy, dx, False) & (shift(k, dy, dx, -1) == k)
        return m

    def run(start_mask, check):
        heap = [int(y) * W + int(x) for y, x in np.argwhere(start_mask)]
        heapq.heapify(heap); seen = set(heap)
        while heap:
            i = heapq.heappop(heap); y, x = divmod(i, W)
            if check(y, x):
                for dy, dx in NB4:
                    yy, xx = y + dy, x + dx
                    j = yy * W + xx
                    if 0 <= yy < H and 0 <= xx < W and j > i and j not in seen:
                        seen.add(j); heapq.heappush(heap, j)

    def stray(y, x):
        if not s[y, x, 3] or protect[y, x]:
            return False
        me = pc.get(tuple(s[y, x, :3]))
        if not me or me == {"O"}:
            return False
        nbs = [tuple(s[y + dy, x + dx, :3]) for dy, dx in NB4
               if 0 <= y + dy < H and 0 <= x + dx < W and s[y + dy, x + dx, 3] and not protect[y + dy, x + dx]
               and pc.get(tuple(s[y + dy, x + dx, :3])) not in (None, {"O"})]
        if len(nbs) >= 2 and all(not (pc[c] & me) for c in nbs):
            new = max(set(nbs), key=nbs.count)
            if tuple(s[y, x, :3]) != new:
                s[y, x, :3] = new
                return True
        return False

    # which parts each pixel's colour belongs to, as bits: lets numpy skip the start pixels whose
    # check can't succeed on the frame as it is (a pixel only becomes worth checking again when a
    # neighbour changes, and run() queues it then), so the result is the same as checking them all
    names = sorted({n for v in pc.values() for n in v})
    bit = {n: 1 << i for i, n in enumerate(names)}
    OBIT = bit.get("O", 0)
    ck = np.array([c[0] * 65536 + c[1] * 256 + c[2] for c in pc], np.int64)
    cm = np.array([sum(bit[n] for n in v) for v in pc.values()], np.int64)
    order_ = np.argsort(ck); ck, cm = ck[order_], cm[order_]

    def part_bits():
        k = key()
        j = np.clip(np.searchsorted(ck, k), 0, len(ck) - 1)
        return np.where((ck[j] == k) & (s[..., 3] > 0), cm[j], 0)

    def could_be_stray():
        pb = part_bits()
        elig = (pb != 0) & (pb != OBIT) & ~protect           # a part pixel (not outline, not eye)
        cnt = np.zeros((H, W), int); clash = np.zeros((H, W), bool)
        for dy, dx in NB4:
            e, b = shift(elig, dy, dx, False), shift(pb, dy, dx, 0)
            cnt += e
            clash |= e & ((b & pb) != 0)
        return elig & (cnt >= 2) & ~clash

    def could_be_sliver(name):
        pb = part_bits()
        own = (pb & bit[name]) != 0
        has_own_nb = np.zeros((H, W), bool)
        for dy, dx in NB4:
            has_own_nb |= shift(own, dy, dx, False)
        return (pb == bit[name]) & ~protect & ~has_own_nb

    ok = (s[..., 3] > 0) & ~protect
    run(ok & ~same_colour_nb(key(), ok) & could_be_stray(), stray)
    # a 1-px sliver of an outlined part (no 4-neighbour of its own part, e.g. squeezed between
    # the outline and the body) can't get its own outline without a 2-px line: it takes the
    # most common other-part colour around it instead
    for name in cfg["style"].get("part_outline", []):
        def sliver(y, x, name=name):
            if not s[y, x, 3] or protect[y, x] or pc.get(tuple(s[y, x, :3])) != {name}:
                return False
            if any(0 <= y + dy < H and 0 <= x + dx < W and s[y + dy, x + dx, 3]
                   and name in pc.get(tuple(s[y + dy, x + dx, :3]), ()) for dy, dx in NB4):
                return False
            cols = [tuple(s[y + dy, x + dx, :3]) for dy, dx in NB8
                    if 0 <= y + dy < H and 0 <= x + dx < W and s[y + dy, x + dx, 3] and not protect[y + dy, x + dx]
                    and pc.get(tuple(s[y + dy, x + dx, :3])) not in (None, {"O"}) and name not in pc[tuple(s[y + dy, x + dx, :3])]]
            if cols:
                new = max(set(cols), key=cols.count)
                if tuple(s[y, x, :3]) != new:
                    s[y, x, :3] = new
                    return True
            return False
        solid = s[..., 3] > 0
        run(solid & ~protect & ~same_colour_nb(key(), solid) & could_be_sliver(name), sliver)
    return s


def compose(cfg, f, L, style=None):
    """Draw a frame from its (possibly time-stabilised) layers. Every line is exactly 1 px:
    inner lines are thinned to a skeleton, no 2x2 block of line pixels survives anywhere
    (inner lines, silhouette outline, or where they meet), and broken bits are dropped."""
    st = dict(cfg["style"], **(style or {}))
    pal = cfg["palette"]["parts"]
    solid, part = f["solid"], f["part"]
    h, w = solid.shape
    OUT = colour(cfg, "outline")

    base = np.zeros((h, w, 3), np.uint8)
    for name, shades in pal.items():
        m = part == name
        cols = np.array([hexrgb(s) for s in shades], np.uint8)
        base[m] = cols[np.clip(L["rank"][m], 0, len(shades) - 1)]
    for name, hcfg in st.get("highlight", {}).items():
        base[L["highlight"] & (part == name)] = colour(cfg, hcfg["colour"])
    stamp = cfg["parts"].get("eye", {}).get("stamp")
    fixed = f["fixed"].copy()
    if stamp and f.get("eye_xy") is not None:
        # crisp eye: the reference's eye pixels, placed on the model's eye centre
        ex, ey = f.get("eye_pos") or (round(f["eye_xy"][0]), round(f["eye_xy"][1]))
        fixed[:] = False
        for dx, dy, ref in stamp["pixels"]:
            x, y = int(round(ex + dx)), int(round(ey + dy))
            if 0 <= y < h and 0 <= x < w and solid[y, x]:
                base[y, x] = colour(cfg, ref)
                fixed[y, x] = True
    else:
        base[fixed] = f["fixed_rgb"][fixed]
    near_eye = fixed.copy()
    for dy, dx in NB8:
        near_eye |= shift(fixed, dy, dx, False)
    f = dict(f, fixed=fixed, eye_area=f["eye_area"] | near_eye)

    # inner lines: skeleton, then drop short pieces that don't touch the silhouette
    inner = thin((L["line"] | L["part_line"]) & solid & ~f["eye_area"])   # lines keep clear of the eye
    inner |= L.get("pl_line", np.zeros_like(solid)) & solid & ~f["eye_area"]
    edge = L["edge"]
    for comp in ([] if L.get("_transported") else components(inner)):   # carried lines were decided on the key frame
        parts_here = [part[y, x] for y, x in comp]
        main = max(set(parts_here), key=parts_here.count)
        need = st.get("min_line_px_part", {}).get(main, st.get("min_line_px", 4))
        if len(comp) < need and (main in st.get("min_line_px_part", {}) or not any(edge[y, x] for y, x in comp)):
            ys, xs = zip(*comp)
            inner[ys, xs] = False

    # a line on a border between two parts goes on the preferred part's side (Showdown draws
    # the mouth on the blue side of the blue/cream crease, in dark blue)
    fold = inner & L["line"]
    for prefer in st.get("line_side", []):
        for y, x in np.argwhere(fold & (part != prefer)):
            for dy, dx in NB4:
                yy, xx = y + dy, x + dx
                if 0 <= yy < h and 0 <= xx < w and part[yy, xx] == prefer and solid[yy, xx] \
                        and not inner[yy, xx] and not f["eye_area"][yy, xx]:
                    inner[y, x] = False; fold[y, x] = False
                    inner[yy, xx] = True; fold[yy, xx] = True
                    break
    line_kind = fold

    out = base.copy()
    rim = L["rim"] & ~inner
    for name, i in st["rim_shade"].items():
        m = rim & (part == name)
        if isinstance(i, dict):              # relative: `drop` shades darker than the pixel's own shade
            cols = np.array([hexrgb(c) for c in pal[name]], np.uint8)
            lo = st["first_shade"].get(name, 0) if i.get("keep_first", False) else 0
            out[m] = cols[np.clip(L["rank"][m] - i["drop"], lo, len(cols) - 1)]
        else:
            out[m] = hexrgb(pal[name][i])
    out[inner] = OUT
    for name, ref in st["inner_line"].items():
        out[inner & line_kind & (part == name)] = colour(cfg, ref)
    # border lines in a box relative to the eye: e.g. the mouth / chin, where Showdown draws
    # the blue/cream border in dark blue on the blue side (but not further down the neck)
    for bl in st.get("border_lines", []):
        if f.get("eye_xy") is None:
            break
        ex, ey = f.get("eye_pos") or (round(f["eye_xy"][0]), round(f["eye_xy"][1]))
        (dx0, dx1), (dy0, dy1) = bl["box_dx"], bl["box_dy"]
        a_side, b_side = bl["between"]
        other = np.zeros_like(solid)
        for dy, dx in NB4:
            other |= shift(part == b_side, dy, dx, False)
        ys, xs = np.mgrid[0:h, 0:w]
        box = (xs >= ex + dx0) & (xs <= ex + dx1) & (ys >= ey + dy0) & (ys <= ey + dy1)
        m = solid & (part == a_side) & other & box & ~inner & ~f["eye_area"]
        out[m] = colour(cfg, bl["colour"])

    for pl in st.get("parallel_lines", []):
        if "shade" in pl:
            m = L.get("shade_line", np.zeros_like(solid)) & (part == pl["part"]) & ~inner
            out[m] = colour(cfg, pl["shade"]["colour"])

    # behind shade (style.behind_shade {part: {"colour": ref}}): beside an inner line, the pixel
    # of the same part on the far side (deeper in the depth pass = the petal tucked behind) takes
    # the shade, so each overlapping piece gets a dark edge where it disappears behind the next
    # one (Showdown's Mega Glimmora crown); the near piece's face stays light
    for name, spec in st.get("behind_shade", {}).items():
        col = colour(cfg, spec["colour"])
        dep = f["depth"]
        for y, x in np.argwhere(inner & line_kind & (part == name)):
            for dy, dx in NB4:
                yy, xx = y + dy, x + dx
                if (0 <= yy < h and 0 <= xx < w and solid[yy, xx] and part[yy, xx] == name and not inner[yy, xx]
                        and not f["fixed"][yy, xx] and dep[yy, xx] < dep[y, x] - spec.get("min_depth", 0)):
                    out[yy, xx] = col

    # crease shade: beside a fold line, the darker neighbour of the same part takes a shade
    # colour (Showdown's shell lip: "lip, =, #, top")
    for name, ref in st.get("line_shade", {}).items():
        col = colour(cfg, ref)
        for y, x in np.argwhere(inner & line_kind & (part == name)):
            cands = [(L["light"][y + dy, x + dx], y + dy, x + dx) for dy, dx in NB4
                     if 0 <= y + dy < h and 0 <= x + dx < w and solid[y + dy, x + dx]
                     and part[y + dy, x + dx] == name and not inner[y + dy, x + dx] and not f["fixed"][y + dy, x + dx]]
            if cands:
                # always on the side nearer the silhouette (the lip side), like Showdown
                _, yy, xx = min(cands, key=lambda c: (L["dist"][c[1], c[2]], c[0]))
                out[yy, xx] = col

    # no lone dark pixel inside the sprite (outline colour or a part's darkest shade, no dark
    # 8-neighbour, not on the edge): it takes the most common colour of its 4 neighbours
    if st.get("remove_lone_dark", True):
        dark_cols = [OUT] + [hexrgb(s[0]) for s in pal.values()]
        dark = solid & np.any([np.all(out == c, -1) for c in dark_cols], 0) & ~f["fixed"]
        dark_nb = np.zeros_like(dark)
        for dy, dx in NB8:
            dark_nb |= shift(dark | f["fixed"], dy, dx, False)
        for y, x in zip(*np.nonzero(dark & ~dark_nb & ~edge)):
            nb = [tuple(out[y + dy, x + dx]) for dy, dx in NB4 if 0 <= y + dy < h and 0 <= x + dx < w]
            out[y, x] = max(set(nb), key=nb.count)
            inner[y, x] = False

    # silhouette outline
    width = st.get("outline_width") or 0
    pad = max(1, math.ceil(width)) if width else (1 if st["outline_outside"] else 0)
    pad += st.get("canvas_margin", 1)          # empty margin: nothing may touch the canvas edge
    rgba = np.zeros((h + 2 * pad, w + 2 * pad, 4), np.uint8)
    rgba[pad:pad + h, pad:pad + w, :3] = out
    rgba[pad:pad + h, pad:pad + w, 3] = np.where(solid, 255, 0)
    body = rgba[..., 3] > 0
    # the outline must close: every body pixel's outside 4-neighbour is outline. That ring is
    # built from the body mask only (so a time-stabilised body gives a stable outline); the
    # supersampled outline only adds diagonal corner pixels on top (Showdown's stair look).
    ring = np.zeros_like(body)
    for dy, dx in NB4:
        ring |= ~body & shift(body, dy, dx, False)
    diag = np.zeros_like(body)
    for dy, dx in NB8[4:]:
        diag |= ~body & shift(body, dy, dx, False)
    if width and st.get("outline_diagonals"):
        ring |= supersampled_outline(f, width, st.get("outline_cover", 0.5), pad) & diag
    elif st.get("outline_diagonals"):
        ring |= diag
    rgba[ring] = (*OUT, 255)
    base_p = np.zeros((h + 2 * pad, w + 2 * pad, 3), np.uint8); base_p[pad:pad + h, pad:pad + w] = base
    inner_p = np.zeros_like(body); inner_p[pad:pad + h, pad:pad + w] = inner

    fixed_p = np.zeros_like(inner_p); fixed_p[pad:pad + h, pad:pad + w] = f["fixed"]
    rgba = clean_parts(cfg, rgba, fixed_p)
    rgba = clean_lines(cfg, rgba, fixed_p)
    return rgba


def stylize(cfg, f, style=None):
    """one frame on its own (no time stabilisation): used by tuning and comparison"""
    return compose(cfg, f, layers(cfg, f, style), style)


# --- stage 3: the whole loop, stabilised over time -----------------------------------

def anchor_layer(frames, layer_list, key_name, keep=0.5, q=2, exclude=None):
    """Like anchor_lines, for any on/off layer (e.g. "highlight"): surface spots that are on in
    at least `keep` of the frames are on wherever they're visible, everything else off."""
    n = len(frames)
    if any(f.get("rest") is None for f in frames):
        return layer_list

    def voxels(f, m):
        r = f["rest"]
        ok = m & (r[..., 3] > 0)
        v = r[..., :3].astype(np.int64) // q
        return ok, v[..., 0] * 65536 + v[..., 1] * 256 + v[..., 2]

    offs = np.array([dx * 65536 + dy * 256 + dz for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)])
    counts = {}
    for f, L in zip(frames, layer_list):
        ok, key = voxels(f, L[key_name])
        for k in np.unique((key[ok][:, None] + offs[None, :]).ravel()).tolist():
            counts[k] = counts.get(k, 0) + 1
    good = np.array([k for k, c in counts.items() if c >= keep * n], np.int64)
    out = []
    for f, L in zip(frames, layer_list):
        ok, key = voxels(f, f["solid"])
        L = dict(L)
        m = ok & np.isin(key, good) & ~f["eye_area"]
        if exclude:
            m &= ~L[exclude]
        if key_name == "highlight":                       # keep it on the parts that have one
            m &= np.isin(f["part"], list(L.get("_hl_parts", [])) or [""]) if L.get("_hl_parts") else m
        L[key_name] = m
        out.append(L)
    return out


def anchor_lines(frames, layer_list, keep=0.5, q=2):
    """Lines attached to the model's surface. Every frame's detected lines are looked up in the
    rest pass (where on the unposed model each pixel is); a surface spot is a line if it was
    detected as one in at least `keep` of the frames (allowing one voxel of slack). Each frame
    then draws lines exactly where those spots are visible. Lines move with the body but can't
    pop in or out, and lines found in only a few frames (spam) never qualify.
    q = rest-space voxel size in 8-bit levels (2 ~ about 1 sprite pixel for Lapras)."""
    n = len(frames)
    if any(f.get("rest") is None for f in frames):
        return layer_list

    def voxels(f, m):
        r = f["rest"]
        ok = m & (r[..., 3] > 0)
        v = r[..., :3].astype(np.int64) // q
        return ok, v[..., 0] * 65536 + v[..., 1] * 256 + v[..., 2]

    offs = np.array([dx * 65536 + dy * 256 + dz for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)])
    counts = {}
    for f, L in zip(frames, layer_list):
        ok, key = voxels(f, L["line"])
        spots = np.unique((key[ok][:, None] + offs[None, :]).ravel())   # once per frame, with slack
        for k in spots.tolist():
            counts[k] = counts.get(k, 0) + 1
    good = np.array([k for k, c in counts.items() if c >= keep * n], np.int64)
    out = []
    for f, L in zip(frames, layer_list):
        ok, key = voxels(f, f["solid"])
        L = dict(L)
        L["line"] = ok & np.isin(key, good) & ~f["eye_area"] & ~L["part_line"]
        out.append(L)
    return out


def transport_lines(cfg, frames, layer_list, key_frame=0, search=3, style=None, tol=4):
    """Decide the line drawing once and carry it: frame `key_frame` is drawn normally; its final
    inner line pixels are then moved to every other frame through the rest pass (each line
    pixel goes to the pixel, within +-search, showing the same spot of the model's surface).
    The drawing keeps its structure in every frame and moves with the body, so lines can't
    re-configure (single <-> double, dashes) from frame to frame the way per-frame detection does."""
    if any(f.get("rest") is None for f in frames):
        return layer_list
    kf, kL = frames[key_frame], layer_list[key_frame]
    a = compose(cfg, kf, kL, style)
    pad = (a.shape[0] - kf["solid"].shape[0]) // 2
    h, w = kf["solid"].shape
    OUT = colour(cfg, "outline")
    line_cols = [OUT] + [colour(cfg, r) for r in cfg["style"].get("inner_line", {}).values()]
    drawn = np.any([np.all(a[pad:pad + h, pad:pad + w, :3] == c, -1) for c in line_cols], 0)
    src = drawn & (kL["line"] | kL["part_line"] | thin(kL["line"] | kL["part_line"]))
    # keep exactly the inner-line pixels the key frame ended up drawing
    src &= kf["solid"]
    rest_k = kf["rest"][..., :3].astype(float)
    shade_src = kL.get("shade_line", np.zeros_like(src)) & ~src

    def carry(f, mask):
        r = f["rest"][..., :3].astype(float); okr = (f["rest"][..., 3] > 0) & f["solid"]
        m = np.zeros((h, w), bool)
        for y, x in np.argwhere(mask):
            y0, y1, x0, x1 = max(0, y - search), min(h, y + search + 1), max(0, x - search), min(w, x + search + 1)
            win = ((r[y0:y1, x0:x1] - rest_k[y, x]) ** 2).sum(-1)
            win = np.where(okr[y0:y1, x0:x1], win, np.inf)
            k = int(np.argmin(win))
            if np.isfinite(win.flat[k]) and win.flat[k] <= tol * tol * 3:  # within ~tol levels per axis
                m[y0 + k // (x1 - x0), x0 + k % (x1 - x0)] = True
        return m

    out = []
    for i, (f, L) in enumerate(zip(frames, layer_list)):
        L = dict(L)
        m = src if i == key_frame else carry(f, src)
        # outlines between parts are rebuilt every frame from the real border (carrying them
        # left gaps where the shell touched the body directly)
        L["line"] = m & ~L["part_line"]
        L["_transported"] = True
        out.append(L)
    return out


def transport_shading(frames, layer_list, key_frame=0, search=4, tol=3):
    """Decide the shading once and carry it, like transport_lines: every pixel takes the shade
    rank of the key-frame pixel showing the same spot of the surface (nearest rest position
    within +-search px, same part, within ~tol levels per axis); pixels with no match (surface
    that comes into view) keep their own rank. For small idle motions this is what a sprite
    artist does: the light/dark pattern sticks to the body instead of re-banding every frame
    (complex surfaces such as Glimmora's crown otherwise pop as the bands re-form)."""
    if any(f.get("rest") is None for f in frames):
        return layer_list
    kf, kL = frames[key_frame], layer_list[key_frame]
    key = {k: kf[k] for k in ("rest", "solid", "part")}           # all a worker needs of the key frame
    others = [i for i in range(len(frames)) if i != key_frame]
    done = pmap(transport_shading_frame, [(key, kL["rank"], frames[i], layer_list[i], search, tol) for i in others])
    out = list(layer_list)
    for i, L in zip(others, done):
        out[i] = L
    return out


def transport_shading_frame(kf, k_rank, f, L, search, tol):
    """transport_shading for one frame: the key frame's ranks carried onto it"""
    if rustcore.lib is not None:
        return rustcore.transport_shading_frame(kf, k_rank, f, L, search, tol)
    rk = kf["rest"][..., :3].astype(float); okk = (kf["rest"][..., 3] > 0) & kf["solid"]
    h, w = kf["solid"].shape
    r = f["rest"][..., :3].astype(float); okf = (f["rest"][..., 3] > 0) & f["solid"]
    best = np.full((h, w), np.inf); got = np.array(L["rank"], copy=True)
    for dy in range(-search, search + 1):
        for dx in range(-search, search + 1):
            ys0, ys1 = max(0, -dy), min(h, h - dy); xs0, xs1 = max(0, -dx), min(w, w - dx)
            tgt = (slice(ys0, ys1), slice(xs0, xs1)); src = (slice(ys0 + dy, ys1 + dy), slice(xs0 + dx, xs1 + dx))
            d = ((r[tgt] - rk[src]) ** 2).sum(-1) + 0.01 * (dy * dy + dx * dx)
            valid = okf[tgt] & okk[src] & (f["part"][tgt] == kf["part"][src])
            d = np.where(valid, d, np.inf)
            upd = d < best[tgt]
            best[tgt] = np.where(upd, d, best[tgt])
            got[tgt] = np.where(upd, k_rank[src], got[tgt])
    use = best <= tol * tol * 3
    L = dict(L); L["rank"] = np.where(use, got, L["rank"])
    return L


def hysteresis_over_time(layer_list, window=4):
    """A line starts only on strong evidence, but once there it is kept on weaker evidence
    (relaxed thresholds) wherever it was strong within +-window frames (1 px of movement
    allowed). Lines then fade instead of a whole line vanishing in one frame - the biggest
    "pops" were long creases dropping out at once when they dipped under a threshold."""
    n = len(layer_list)
    strong = [L["line"] for L in layer_list]
    grown = []
    for m in strong:
        g = m.copy()
        for dy, dx in NB8:
            g |= shift(m, dy, dx, False)
        grown.append(g)
    out = []
    for i in range(n):
        support = np.any([grown[(i + k) % n] for k in range(-window, window + 1)], 0)
        L = dict(layer_list[i])
        L["line"] = layer_list[i]["weak"] & support
        out.append(L)
    return out


def vote_over_time(layer_list, frames, window=1):
    """Each pixel's line / rim state and shade rank becomes the majority (lines, rim) or the
    median (shade) over the frame and its `window` neighbours on each side, wrapping around
    the loop. Anything that exists for less than half the window can't survive, so nothing
    blinks for 1-2 frames. Applied only where the pixel shows the same part in all of them."""
    n = len(layer_list)
    out = []
    for i in range(n):
        idx = [(i + k) % n for k in range(-window, window + 1)]
        part = frames[i]["part"]
        same = np.all([frames[j]["part"] == part for j in idx], 0) & frames[i]["solid"]
        need = window + 1
        L = dict(layer_list[i])
        for key in ("line", "part_line", "rim", "highlight", "shade_line", "pl_line"):
            if key not in layer_list[i]:
                continue
            votes = sum(layer_list[j][key].astype(int) for j in idx)
            L[key] = np.where(same, votes >= need, layer_list[i][key])
        ranks = np.stack([layer_list[j]["rank"] for j in idx])
        L["rank"] = np.where(same, np.median(ranks, 0).astype(int), layer_list[i]["rank"])
        out.append(L)
    return out


def steady_shape(frames, max_run=2):
    """Per pixel over the loop: being part of the shape or not must last more than max_run
    frames. Pixels that join the shape briefly are dropped; brief holes are filled with the
    data (part, normal, depth, ...) from the neighbouring frame that has the pixel."""
    n = len(frames)
    solid = np.stack([f["solid"] for f in frames])
    keys = ("part", "n", "depth", "has_data", "detail", "fixed", "fixed_rgb", "eye_area")
    keys += tuple(k for k in ("cast", "unlit", "line_cov", "fs_cov") if frames[0].get(k) is not None)
    out = [dict(f, **{k: f[k].copy() for k in keys + ("solid",)}) for f in frames]
    if rustcore.lib is not None:
        # the run merging per pixel in Rust; here: what it did last per frame and pixel
        event, src = rustcore.steady_events(solid, max_run)
        for i in range(n):
            ev, sr = event[i], src[i]
            touched = ev >= 0
            out[i]["solid"][touched] = ev[touched] == 1
            for j in np.unique(sr[sr >= 0]).tolist():       # data copied by the last fill
                m = sr == j
                for key in keys:
                    out[i][key][m] = frames[j][key][m]
            emptied = ev == 0                                # dropped last: no part, no eye
            out[i]["part"][emptied] = ""
            out[i]["fixed"][emptied] = False
        return out
    for y, x in np.argwhere(solid.any(0) & ~solid.all(0)):
        seq = solid[:, y, x].copy()
        for _ in range(n):
            start = int(np.argmax(seq != seq[-1]))
            order = [(start + k) % n for k in range(n)]
            runs, cur = [], [order[0]]
            for i in order[1:]:
                if seq[i] == seq[cur[0]]:
                    cur.append(i)
                else:
                    runs.append(cur); cur = [i]
            runs.append(cur)
            short = [r for r in runs if len(r) <= max_run]
            if len(runs) < 2 or not short:
                break
            r = min(short, key=len)
            k = runs.index(r)
            before, after = runs[k - 1], runs[(k + 1) % len(runs)]
            src = before if len(before) >= len(after) else after
            for i in r:
                seq[i] = seq[src[0]]
                j = src[-1] if src is before else src[0]       # nearest frame in time
                out[i]["solid"][y, x] = seq[i]
                if seq[i]:
                    for key in keys:
                        out[i][key][y, x] = frames[j][key][y, x]
                else:
                    out[i]["part"][y, x] = ""
                    out[i]["fixed"][y, x] = False
    return out


def settle_shading(cfg, sprites, max_run=2, skip=None):
    """Final pass: a body shade lasting max_run frames or fewer (typically an edge pixel
    stepping through a neighbouring shade just before the outline reaches it) takes the shade
    of an adjacent run that is also a body shade. Never introduces outline or transparency,
    so it can't break the outline or the 1-px rule."""
    OUT = colour(cfg, "outline")
    S = np.stack(sprites)
    n = len(sprites)
    is_body = (S[..., 3] > 0) & ~np.all(S[..., :3] == OUT, -1)
    key = np.where(S[..., 3] > 0, S[..., 0].astype(np.int64) * 65536 + S[..., 1].astype(np.int64) * 256 + S[..., 2], -1)
    moving = (key != key[0]).any(0) & (~skip if skip is not None else True)
    for y, x in np.argwhere(moving):
        seq = key[:, y, x]
        for i in range(n):
            if not is_body[i, y, x] or seq[i] == seq[i - 1]:
                continue
            L = 1
            while L <= max_run and seq[(i + L) % n] == seq[i]:
                L += 1
            if L > max_run:
                continue
            a, b = (i - 1) % n, (i + L) % n
            src = a if is_body[a, y, x] else (b if is_body[b, y, x] else None)
            if src is None:
                continue
            for k in range(L):
                S[(i + k) % n, y, x] = S[src, y, x]
                seq[(i + k) % n] = seq[src]
    return [S[i] for i in range(n)]


def restamp(cfg, f, s, mask, zone):
    """After time smoothing: clear ghost eye pixels (eye colours where the eye was in another
    frame but isn't in this one) and draw the eye stamp crisply at this frame's position."""
    stamp = cfg["parts"].get("eye", {}).get("stamp")
    if not stamp or not mask.any():
        return s
    s = s.copy()
    eye_cols = {colour(cfg, r) for _, _, r in stamp["pixels"]} - {colour(cfg, r) for r in cfg["parts"]["eye"].get("stamp_extra", [])}
    H, W = s.shape[:2]
    for y, x in np.argwhere(zone & ~mask & (s[..., 3] > 0)):
        if tuple(s[y, x, :3]) in eye_cols:
            nbs = [tuple(s[y + dy, x + dx, :3]) for dy, dx in NB8
                   if 0 <= y + dy < H and 0 <= x + dx < W and s[y + dy, x + dx, 3] and not mask[y + dy, x + dx]
                   and tuple(s[y + dy, x + dx, :3]) not in eye_cols]
            if nbs:
                s[y, x, :3] = max(set(nbs), key=nbs.count)
    pad = (s.shape[0] - f["solid"].shape[0]) // 2
    ex, ey = f.get("eye_pos") or (round(f["eye_xy"][0]), round(f["eye_xy"][1]))
    for dx, dy, ref in stamp["pixels"]:
        x, y = int(round(ex + dx)) + pad, int(round(ey + dy)) + pad
        if 0 <= y < H and 0 <= x < W and s[y, x, 3]:
            s[y, x, :3] = colour(cfg, ref)
    return s


def stamp_mask(cfg, f, shape, pad):
    """where the eye stamp is drawn in a padded frame (never edited by clean-up passes)"""
    m = np.zeros(shape, bool)
    stamp = cfg["parts"].get("eye", {}).get("stamp")
    if not stamp or f.get("eye_xy") is None:
        return m
    ex, ey = f.get("eye_pos") or (round(f["eye_xy"][0]), round(f["eye_xy"][1]))
    for dx, dy, _ in stamp["pixels"]:
        x, y = int(round(ex + dx)) + pad, int(round(ey + dy)) + pad
        if 0 <= y < shape[0] and 0 <= x < shape[1]:
            m[y, x] = True
    return m


def stylize_loop(cfg, frames, style=None):
    """the whole loop: shape stabilised over time, layers per frame stabilised over time,
    then drawn, then a final per-pixel debounce + repair.
    style.fast_frames [[a, b], ...]: intentional fast motion (e.g. a spin). Those frames are drawn
    one by one with the same per-frame rules but no time smoothing (debouncing a spin would
    freeze or smear it); the other frames are stabilised as a loop of their own - so the fast
    motion must end where it started (a full turn), which keeps that loop seamless.
    style.pixel_bob: the finished sprites move in whole-pixel steps (float, drift, shake: see
    motion.py); a whole-sprite shift adds no new shapes, so it can't pop or flicker."""
    global LAST_EYE_MASKS
    ff = cfg["style"].get("fast_frames")
    if ff:
        n = len(frames)
        fast = sorted({i for a, b in ff for i in range(a, b + 1) if 0 <= i < n})
        slow = [i for i in range(n) if i not in fast]
        sub = dict(cfg, style={k: v for k, v in cfg["style"].items() if k not in ("fast_frames", "pixel_bob")})
        slow_sp = stylize_loop(sub, [frames[i] for i in slow], style)
        slow_masks = LAST_EYE_MASKS
        sprites, masks = [None] * n, [None] * n
        for k, i in enumerate(slow):
            sprites[i], masks[i] = slow_sp[k], slow_masks[k]
        for i, (sp, pm) in zip(fast, pmap(fast_frame, [(sub, frames[i], style) for i in fast])):
            sprites[i], masks[i] = sp, pm
        LAST_EYE_MASKS = masks
        return pixel_bob(cfg, sprites)
    return pixel_bob(cfg, _stylize_loop(cfg, frames, style))


def fast_frame(sub, f, style=None):
    """one frame of style.fast_frames: drawn on its own, then the per-frame hard rules"""
    sp = stylize(sub, f, style)
    pm = stamp_mask(sub, f, sp.shape[:2], (sp.shape[0] - f["solid"].shape[0]) // 2)
    sp = repair(sub, sp, None, None, pm)        # close the outline, fill dents, seal parts
    sp = smooth_silhouette(sub, sp, pm)
    if sub["style"].get("part_outline"):
        sp = seal_parts(sub, clean_parts(sub, sp, pm), pm)
    sp = clean_lines(sub, sp, pm, corners=True)
    for _ in range(8):                           # cleanup can reopen a pixel: repeat until clean
        if not hard_faults(sub, sp, pm):
            break
        sp = clean_lines(sub, repair(sub, sp, None, None, pm), pm, corners=True)
    return (fix_faults(sub, sp, pm) if hard_faults(sub, sp, pm) else sp), pm


def slow_t(f, n, fast):
    """frame f of n -> 0..1 loop position with style.fast_frames removed (held during them), so
    slow motions (the float) pause during a fast event. Same as render_sprite.slow_t."""
    total = sum(b - a for a, b in fast)
    lost = 0
    for a, b in sorted(fast):
        if f >= b:
            lost += b - a
        elif f > a:
            return (a - lost) / (n - total)
    return (f - lost) / (n - total)


def smooth_silhouette(cfg, s, protect=None, rounds=3):
    """1-px jags on the silhouette (the check_loop.teeth rule), for frames drawn without time
    smoothing (fast frames): a spur (outline pixel with the outside on 3 sides) is removed and,
    if a body pixel was behind it, that pixel becomes outline (the edge moves in by 1 px); a
    notch (outside pixel with outline on 3 sides) is filled with outline. clean_lines afterwards
    keeps every line 1 px."""
    OUT = np.array((*colour(cfg, "outline"), 255), np.uint8)
    s = s.copy()
    protect = np.zeros(s.shape[:2], bool) if protect is None else protect
    H, W = s.shape[:2]
    for _ in range(rounds):
        solid = s[..., 3] > 0
        line = solid & np.all(s[..., :3] == OUT[:3], -1)
        n_out = sum(shift(~solid, dy, dx, True).astype(int) for dy, dx in NB4)
        n_line = sum(shift(line, dy, dx, False).astype(int) for dy, dx in NB4)
        spurs = line & (n_out >= 3) & ~protect
        notches = ~solid & (n_line >= 3)
        if not spurs.any() and not notches.any():
            break
        for y, x in np.argwhere(spurs):
            s[y, x] = 0
            for dy, dx in NB4:
                yy, xx = y + dy, x + dx
                if 0 <= yy < H and 0 <= xx < W and s[yy, xx, 3] and not protect[yy, xx]:
                    s[yy, xx] = OUT
        s[notches] = OUT
    return s


def pixel_bob(cfg, sprites):
    """style.pixel_bob: shift each finished sprite by whole pixels (motion.offsets: the float, a
    sideways drift, a shake), on a canvas padded to fit; eye masks follow"""
    global LAST_EYE_MASKS
    if not cfg["style"].get("pixel_bob"):
        return sprites
    # the whole-pixel part of the float is this shift; the leftover fraction is rendered in 3-D
    # (pose expressions like PX_U*(FY - round(FY)) with the same function), so the sprite floats
    # smoothly while the time smoothing only ever sees sub-pixel change
    import motion
    offs = motion.offsets(cfg, len(sprites))
    A = max(abs(dy) for dy, _ in offs)
    B = max(abs(dx) for _, dx in offs)
    out, masks = [], []
    for i, s in enumerate(sprites):
        dy, dx = offs[i]
        y0, x0 = A - dy, B + dx                               # + = up / right
        c = np.zeros((s.shape[0] + 2 * A, s.shape[1] + 2 * B, 4), np.uint8)
        c[y0:y0 + s.shape[0], x0:x0 + s.shape[1]] = s
        out.append(c)
        if LAST_EYE_MASKS is not None:
            m = np.zeros(c.shape[:2], bool); m[y0:y0 + s.shape[0], x0:x0 + s.shape[1]] = LAST_EYE_MASKS[i]; masks.append(m)
    if LAST_EYE_MASKS is not None:
        LAST_EYE_MASKS = masks
    return out


def _stylize_loop(cfg, frames, style=None):
    if len(frames) > 2 and cfg["style"].get("steady_loop", True):
        frames = steady_shape(frames, cfg["style"].get("shape_min_frames", cfg["style"].get("min_frames", 2)))
    ls = pmap(layers, [(cfg, f, style) for f in frames])
    xy = [f.get("eye_xy") for f in frames]
    if all(p is not None for p in xy):
        # eye position: smoothed over 5 frames, and only moved when it has really moved
        # (more than 0.7 px from where it is drawn) so it never jitters between two pixels
        n = len(frames)
        sm = [np.mean([xy[(i + k) % n] for k in range(-2, 3)], 0) for i in range(n)]
        pos = [tuple(int(round(v)) for v in sm[0])]
        for i in range(1, n):
            p = pos[-1]
            pos.append(tuple(int(round(v)) if abs(v - q) > 0.7 else q for v, q in zip(sm[i], p)))
        # and every position is held for at least 3 frames (x and y steps on neighbouring
        # frames would otherwise give a 1-frame eye position = a blink of the whole eye)
        for _ in range(n):
            runs, cur = [], [0]
            for i in range(1, n):
                if pos[i] == pos[cur[0]]:
                    cur.append(i)
                else:
                    runs.append(cur); cur = [i]
            runs.append(cur)
            if len(runs) > 1 and pos[runs[0][0]] == pos[runs[-1][0]]:     # loop wraps
                runs[0] = runs[-1] + runs[0]; runs.pop()
            short = [r for r in runs if len(r) < 3]
            if len(runs) < 2 or not short:
                break
            r = min(short, key=len); k = runs.index(r)
            before, after = runs[k - 1], runs[(k + 1) % len(runs)]
            src = before if len(before) >= len(after) else after
            for i in r:
                pos[i] = pos[src[0]]
        frames = [dict(f, eye_pos=p) for f, p in zip(frames, pos)]
    if len(frames) > 2 and cfg["style"].get("steady_loop", True):
        if cfg["style"].get("transport_lines"):
            t = cfg["style"]["transport_lines"]
            ls = transport_lines(cfg, frames, ls, t.get("key_frame", 0), t.get("search", 3), style, t.get("tol", 4))
        if cfg["style"].get("transport_shading"):
            t = cfg["style"]["transport_shading"]
            ls = transport_shading(frames, ls, t.get("key_frame", 0), t.get("search", 4), t.get("tol", 3))
        if cfg["style"].get("anchor_lines"):
            a = cfg["style"]["anchor_lines"]
            ls = anchor_lines(frames, ls, a.get("keep", 0.5), a.get("voxel", 2))
            if a.get("highlights") and cfg["style"].get("highlight"):
                hl_parts = list(cfg["style"]["highlight"])
                ls = [dict(L, _hl_parts=hl_parts) for L in ls]
                ls = anchor_layer(frames, ls, "highlight", a.get("keep", 0.5), a.get("voxel", 2))
        if cfg["style"].get("line_hysteresis"):
            ls = hysteresis_over_time(ls, cfg["style"]["line_hysteresis"].get("window", 4))
        ls = vote_over_time(ls, frames, cfg["style"].get("steady_window", 1))
        # eyes: pupil / white majority over time as well
        n = len(frames)
        for i in range(n):
            idx = [(i - 1) % n, i, (i + 1) % n]
            for key in ("fixed",):
                votes = sum(frames[j][key].astype(int) for j in idx)
                keep = votes >= 2
                frames[i] = dict(frames[i], fixed=frames[i]["fixed"] & keep)
    sprites = pmap(compose, [(cfg, f, L, style) for f, L in zip(frames, ls)])
    protects = [stamp_mask(cfg, f, sp.shape[:2], (sp.shape[0] - f["solid"].shape[0]) // 2)
                for f, sp in zip(frames, sprites)]
    global LAST_EYE_MASKS
    LAST_EYE_MASKS = protects
    eye_zone = np.any(protects, 0)          # every pixel the eye stamp covers in some frame
    if len(frames) > 2 and cfg["style"].get("steady_loop", True):
        import os
        for it in range(cfg["style"].get("steady_rounds", 12)):   # debounce, repair, until stable
            before = np.stack(sprites)
            d = debounce(sprites, cfg["style"].get("min_frames", 2))
            sprites = pmap(repair, [(cfg, d[i], d[i - 1], d[(i + 1) % len(d)], protects[i]) for i in range(len(d))])
            changed = int((before != np.stack(sprites)).any(-1).sum())
            if os.environ.get("SPRITE_DEBUG"):
                print(f"  steady round {it + 1}: {changed} pixels changed")
            if not changed:
                break
        sprites = settle_shading(cfg, sprites, cfg["style"].get("min_frames", 2))
        # hard rules last: every part outline closed, every line 1 px, in every frame
        sprites = pmap(hard_rules, [(cfg, f, sp, pm, eye_zone) for f, sp, pm in zip(frames, sprites, protects)])
        sprites = pmap(clean_lines, [(cfg, sprites[i], protects[i], sprites[i - 1], sprites[(i + 1) % len(sprites)], True)
                                     for i in range(len(sprites))])
        sprites = rule_safe_debounce(cfg, sprites, protects, cfg["style"].get("min_frames", 2))
        # a frame that still breaks a hard rule (smoothing over time can leave one, e.g. a 1-px hole
        # next to the body): fix just that frame, as the fast frames are fixed; keep the fix only
        # if it lowers the fault count
        sprites = pmap(last_fix, list(zip([cfg] * len(sprites), sprites, protects)))
    return sprites


def hard_rules(cfg, f, sp, pm, eye_zone):
    """per frame, after time smoothing: the eye stamp, then 1-px silhouette jags and part outlines"""
    sp = restamp(cfg, f, sp, pm, eye_zone)
    if cfg["style"].get("smooth_silhouette"):          # 1-px spurs / notches on the silhouette
        sp = smooth_silhouette(cfg, sp, pm)
    if cfg["style"].get("part_outline"):
        sp = seal_parts(cfg, clean_parts(cfg, sp, pm), pm)
    return sp


def last_fix(cfg, sp, pm):
    """a frame that still breaks a hard rule: fix just that frame (as the fast frames are
    fixed), keeping each fix only if it lowers the fault count"""
    f0 = hard_faults(cfg, sp, pm)
    for _ in range(8):
        if not f0:
            break
        t = clean_lines(cfg, repair(cfg, sp, None, None, pm), pm, corners=True)
        f1 = hard_faults(cfg, t, pm)
        if f1 >= f0:
            break
        sp, f0 = t, f1
    return fix_faults(cfg, sp, pm) if f0 else sp


def hard_faults(cfg, s, protect):
    """the hard rules, counted exactly as the checks count them: 2x2 line blocks, 2-px
    diagonals, open outline / part leakage"""
    if rustcore.lib is not None:
        return rustcore.hard_faults(cfg, s, protect)
    import check_loop as cl
    DARK = dark_line_colours(cfg)
    l = (s[..., 3] > 0) & np.any([np.all(s[..., :3] == c, -1) for c in DARK], 0) & ~protect
    blobs = cl.pupil_blobs(s, l)
    return (cl.line_blocks(s, l, blobs) + cl.stairs(s, l, cl.separators(cfg, s, l, protect), blobs)
            + cl.open_outline(cfg, s, l, protect))


def fix_faults(cfg, s, protect, rounds=20):
    """Last resort for a frame that still breaks a hard rule after repair / clean_lines: try single
    pixel changes where the faults are - a 2x2 line block pixel takes its commonest neighbouring
    fill colour, a body pixel touching the outside becomes outline - and keep a change only if the
    frame's hard-fault count goes down. Greedy, local, deterministic."""
    DARK = dark_line_colours(cfg)
    OUT = np.array((*colour(cfg, "outline"), 255), np.uint8)
    s = s.copy()
    H, W = s.shape[:2]

    def candidates(s):
        solid = s[..., 3] > 0
        line = solid & np.any([np.all(s[..., :3] == c, -1) for c in DARK], 0) & ~protect
        cands = []
        blk = line[:-1, :-1] & line[1:, :-1] & line[:-1, 1:] & line[1:, 1:]
        for y, x in np.argwhere(blk):
            for yy, xx in ((y, x), (y + 1, x), (y, x + 1), (y + 1, x + 1)):
                nb = {tuple(s[q, r]) for q, r in ((yy - 1, xx), (yy + 1, xx), (yy, xx - 1), (yy, xx + 1))
                      if 0 <= q < H and 0 <= r < W and solid[q, r] and not line[q, r]}
                cands += [(yy, xx, np.array(c, np.uint8)) for c in nb]
        P = np.pad(~solid, 1, constant_values=True)
        to_out = solid & ~line & ~protect & (P[:-2, 1:-1] | P[2:, 1:-1] | P[1:-1, :-2] | P[1:-1, 2:])
        for y, x in np.argwhere(to_out):
            cands.append((y, x, OUT))                     # the body pixel becomes the outline ...
            for q, r in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if not (0 <= q < H and 0 <= r < W) or not solid[q, r]:
                    if 0 <= q < H and 0 <= r < W:
                        cands.append((q, r, OUT))         # ... or the outside next to it does
        return cands

    def score(s, y, x, c):
        old = s[y, x].copy(); s[y, x] = c
        f = hard_faults(cfg, s, protect)
        s[y, x] = old
        return f

    f0 = hard_faults(cfg, s, protect)
    for _ in range(rounds):
        if not f0:
            break
        best = None
        for y, x, c in candidates(s):                     # one change that lowers the count
            f = score(s, y, x, c)
            if f < f0 and (best is None or f < best[0]):
                best = (f, [(y, x, c)])
        if best is None:                                  # or two: a trade, then its fix
            for y, x, c in candidates(s):
                if score(s, y, x, c) > f0:
                    continue
                old = s[y, x].copy(); s[y, x] = c
                for y2, x2, c2 in candidates(s):
                    f = score(s, y2, x2, c2)
                    if f < f0 and (best is None or f < best[0]):
                        best = (f, [(y, x, c), (y2, x2, c2)])
                s[y, x] = old
        if best is None:
            break
        f0 = best[0]
        for y, x, c in best[1]:
            s[y, x] = c
    return s


def rule_safe_debounce(cfg, sprites, protects, max_run=2, rounds=4):
    """Last step: debounce once more (the 1-px / closed-outline fixes are made per frame and
    can blink), but keep each debounced pixel only if that frame's hard faults don't go up."""
    sprites = [s.copy() for s in sprites]
    for _ in range(rounds):
        d = debounce(sprites, max_run, skip=np.any(protects, 0))
        changed = 0
        for i, (s, t) in enumerate(zip(sprites, d)):
            diff = np.argwhere((s != t).any(-1))
            if not len(diff):
                continue
            pm = protects[i]
            H_, W_ = s.shape[:2]

            def local(y, x, r=6):
                # the hard faults are local rules (a few px): judge a change by the faults in a
                # window around it, before vs after - same decision as the whole frame, far faster
                ys, xs = slice(max(0, y - r), min(H_, y + r + 1)), slice(max(0, x - r), min(W_, x + r + 1))
                return hard_faults(cfg, s[ys, xs], pm[ys, xs])
            rejected = []
            for y, x in diff:
                old = s[y, x].copy()
                before = local(y, x)
                s[y, x] = t[y, x]
                if local(y, x) > before:
                    s[y, x] = old; rejected.append((y, x))
                else:
                    changed += 1
            # a change refused alone may be fine together with its neighbours' (a whole short-lived
            # bit of outline going away at once): try every debounced pixel within 2 px together
            for y, x in rejected:
                if (s[y, x] == t[y, x]).all():
                    continue
                # then: hold the whole neighbourhood as the previous / next frame draws it
                # (a patch that already satisfies the rules there)
                n = len(sprites)
                tries = [(2, t)] + [(r, src) for r in (2, 3) for src in (sprites[i - 1], sprites[(i + 1) % n])]
                for r, src in tries:
                    win = (slice(max(0, y - r), y + r + 1), slice(max(0, x - r), x + r + 1))
                    old = s[win].copy()
                    keep_eye = protects[i][win]
                    before = local(y, x, r + 6)
                    s[win] = np.where(keep_eye[..., None], old, src[win])
                    if local(y, x, r + 6) > before or (s[win] == old).all():
                        s[win] = old
                    else:
                        changed += 1
                        break
        if not changed:
            break
    return sprites


def debounce(sprites, max_run=2, skip=None):
    """Per pixel across the (looping) animation: any colour, transparency included, that lasts
    max_run frames or fewer is replaced by the longer of its neighbouring runs in time. After
    this nothing can blink on or off for 1-2 frames."""
    if rustcore.lib is not None:
        return rustcore.debounce(sprites, max_run, skip)
    S = np.stack(sprites)                                   # n, H, W, 4
    key = np.where(S[..., 3] > 0, S[..., 0].astype(np.int64) * 65536 + S[..., 1].astype(np.int64) * 256 + S[..., 2], -1)
    n = len(sprites)
    moving = (key != key[0]).any(0)
    if skip is not None:
        moving &= ~skip                   # the eye: its position is smoothed separately
    changing = np.argwhere(moving)
    for y, x in changing:
        seq = key[:, y, x].copy()
        for _ in range(n):
            # runs on the loop, starting at a change
            start = int(np.argmax(seq != seq[-1])) if (seq != seq[0]).any() else 0
            order = [(start + k) % n for k in range(n)]
            runs, cur = [], [order[0]]
            for i in order[1:]:
                if seq[i] == seq[cur[0]]:
                    cur.append(i)
                else:
                    runs.append(cur); cur = [i]
            runs.append(cur)
            if len(runs) < 2:
                break
            short = [r for r in runs if len(r) <= max_run]
            if not short:
                break
            r = min(short, key=len)
            k = runs.index(r)
            before, after = runs[k - 1], runs[(k + 1) % len(runs)]
            src = before if len(before) >= len(after) else after
            seq[r] = seq[src[0]]
            S[r, y, x] = S[src[0], y, x]
        key[:, y, x] = seq
    return [S[i] for i in range(n)]


def repair(cfg, s, prev=None, nxt=None, protect=None):
    """After debounce: re-close the outline (no body pixel touching transparency), then the
    same 1-px / pixel-perfect / stray-pixel cleanup as compose, preferring fixes that agree
    with the neighbouring frames so the fix doesn't itself blink."""
    OUT = colour(cfg, "outline")
    s = s.copy()
    solid = s[..., 3] > 0
    line = solid & np.all(s[..., :3] == OUT, -1)
    body = solid & ~line
    for dy, dx in NB4:
        gap = ~solid & shift(body, dy, dx, False)
        s[gap] = (*OUT, 255)
    # 1-px dents in the silhouette (outside pixel boxed in by outline on 3 sides) are filled;
    # clean_lines below then drops the line pixel left behind it, giving a straight edge
    solid = s[..., 3] > 0
    line = solid & np.all(s[..., :3] == OUT, -1)
    n_line = sum(shift(line, dy, dx, False).astype(int) for dy, dx in NB4)
    straight = ((shift(line, 0, 1, False) & shift(line, 0, -1, False))
                | (shift(line, 1, 0, False) & shift(line, -1, 0, False)))
    s[~solid & (n_line >= 3) & straight] = (*OUT, 255)
    s = clean_parts(cfg, s, protect)
    if cfg["style"].get("part_outline"):
        s = seal_parts(cfg, s, protect)
    # staircase corners were pruned when each frame was drawn; pruning them again here would
    # flip edge pixels on and off as an edge sweeps past (a blink is worse than a kept corner)
    return clean_lines(cfg, s, protect, prev, nxt, corners=False)


def save_gif(cfg, sprites, path):
    pal = palette(cfg)
    lookup = {c: i for i, c in enumerate(pal)}
    T = len(pal)
    frames = []
    for s in sprites:
        idx = np.full(s.shape[:2], T, np.uint8)
        for col, i in lookup.items():
            idx[(s[..., 3] > 0) & np.all(s[..., :3] == col, axis=-1)] = i
        p = Image.fromarray(idx, "P")
        p.putpalette([v for c in pal for v in c] + [0, 0, 0] * (256 - T))
        frames.append(p)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=cfg["style"]["frame_ms"],
                   loop=0, transparency=T, disposal=2, optimize=False)
