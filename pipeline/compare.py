"""Score a rendered sprite frame against the official Showdown frame, metric by metric.

Run:  python3 compare.py CONFIG.json OURS.(gif|png) [--frame 0] [--out compare.png] [--json result.json]

Everything is measured on the palette: each colour belongs to a part (e.g. blue skin,
cream belly, shell) at a shade rank 0 = darkest, or is the outline. The two frames are
lined up at the offset where their silhouettes overlap most, then compared on:

  silhouette   overlap of the two shapes (IoU)
  parts        share of the combined shape where both have the same part (outline counts as any)
  shading      within matching parts, how often the shade rank is the same (exact, and within
               1 px: the score uses the within-1px version, since 1-px pose offsets aren't style)
  palette      L1 distance between the two colour histograms (0 = identical mix of colours)
  lines        line share, inner/silhouette line pixels, stair-corner share, grain
and an overall style score (0..100, weights in score()). --out writes reference | ours | difference
(grey = same, yellow = same part but different shade, red = different part / only one has a pixel)
| line placement (magenta = our line where Showdown has none, cyan = Showdown line we lack).
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def hexrgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def colour_info(cfg):
    info = {hexrgb(cfg["palette"]["outline"]): ("L", 0)}
    for part, shades in cfg["palette"]["parts"].items():
        for rank, h in enumerate(shades):
            info.setdefault(hexrgb(h), (part, rank))
    return info


def load(path, frame=0):
    im = Image.open(path)
    if getattr(im, "n_frames", 1) > 1:
        im.seek(frame)
    return crop(np.array(im.convert("RGBA")))


def crop(a):
    ys, xs = np.nonzero(a[..., 3] > 0)
    return a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def describe(a, info):
    """part letter grid and shade rank grid"""
    key = a[..., 0].astype(int) * 65536 + a[..., 1].astype(int) * 256 + a[..., 2]
    part = np.full(a.shape[:2], ".", dtype=object)
    rank = np.full(a.shape[:2], -1)
    solid = a[..., 3] > 0
    part[solid] = "?"
    for (r, g, b), (p, k) in info.items():
        m = solid & (key == r * 65536 + g * 256 + b)
        part[m], rank[m] = p, k
    return part, rank


def line_stats(a, part, rank_grid):
    isL = part == "L"
    solid = part != "."
    L, S = np.pad(isL, 1), np.pad(solid, 1)
    l, r, u, d = L[1:-1, :-2], L[1:-1, 2:], L[:-2, 1:-1], L[2:, 1:-1]
    touches_empty = ~(S[1:-1, :-2] & S[1:-1, 2:] & S[:-2, 1:-1] & S[2:, 1:-1])
    corner = isL & (((l & u) & ~r & ~d) | ((u & r) & ~l & ~d) | ((r & d) & ~l & ~u) | ((d & l) & ~r & ~u))
    clump = isL & r & d & L[2:, 2:]
    nb8 = l | r | u | d | L[:-2, :-2] | L[:-2, 2:] | L[2:, :-2] | L[2:, 2:]
    lone = isL & ~nb8
    key = a[..., 0].astype(int) * 65536 + a[..., 1].astype(int) * 256 + a[..., 2]
    K = np.pad(np.where(solid, key, -1), 1, constant_values=-2)
    c = K[1:-1, 1:-1]
    isolated = solid & (K[1:-1, :-2] != c) & (K[1:-1, 2:] != c) & (K[:-2, 1:-1] != c) & (K[2:, 1:-1] != c)
    n_solid, n_line = solid.sum(), isL.sum()
    # short fragments: 8-connected groups of line pixels with <= 3 pixels (dotted / broken lines)
    seen = np.zeros_like(isL)
    fragments = 0
    for y0, x0 in zip(*np.nonzero(isL)):
        if seen[y0, x0]:
            continue
        stack, size = [(y0, x0)], 0
        seen[y0, x0] = True
        while stack:
            y, x = stack.pop(); size += 1
            for yy in (y - 1, y, y + 1):
                for xx in (x - 1, x, x + 1):
                    if 0 <= yy < isL.shape[0] and 0 <= xx < isL.shape[1] and isL[yy, xx] and not seen[yy, xx]:
                        seen[yy, xx] = True; stack.append((yy, xx))
        fragments += size <= 3
    # dark specks: groups of <= 3 dark pixels (outline colour or a part's darkest shade, ranks
    # come from describe) at least 2 px away from the silhouette, i.e. dots inside the body
    S8 = np.pad(solid, 1)
    ring = solid & ~(S8[1:-1, :-2] & S8[1:-1, 2:] & S8[:-2, 1:-1] & S8[2:, 1:-1]
                     & S8[:-2, :-2] & S8[:-2, 2:] & S8[2:, :-2] & S8[2:, 2:])
    near_ring = ring.copy()
    R = np.pad(ring, 2)
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            near_ring |= R[2 + dy:2 + dy + ring.shape[0], 2 + dx:2 + dx + ring.shape[1]]
    dark = isL | (rank_grid == 0)
    seen2 = np.zeros_like(dark)
    specks = 0
    for y0, x0 in zip(*np.nonzero(dark)):
        if seen2[y0, x0]:
            continue
        stack, comp = [(y0, x0)], []
        seen2[y0, x0] = True
        while stack:
            y, x = stack.pop(); comp.append((y, x))
            for yy in (y - 1, y, y + 1):
                for xx in (x - 1, x, x + 1):
                    if 0 <= yy < dark.shape[0] and 0 <= xx < dark.shape[1] and dark[yy, xx] and not seen2[yy, xx]:
                        seen2[yy, xx] = True; stack.append((yy, xx))
        specks += len(comp) <= 3 and not any(near_ring[y, x] for y, x in comp)
    part_grain = {}
    for name in sorted(set(part[solid].tolist()) - {"L", "?"}):
        m = part == name
        part_grain[name] = float((isolated & m).sum() / max(1, m.sum()))
    return {
        "line_share": float(n_line / n_solid),
        "silhouette_line_px": int((isL & touches_empty).sum()),
        "inner_line_px": int((isL & ~touches_empty).sum()),
        "stair_corner_share": float(corner.sum() / max(1, n_line)),
        "line_2x2_clumps": int(clump.sum()),
        "lone_line_px": int(lone.sum()),
        "line_fragments": int(fragments),
        "dark_specks": int(specks),
        "grain_share": float(isolated.sum() / n_solid),
        **{f"grain_{k}": v for k, v in part_grain.items()},
    }


def histogram(a):
    solid = a[..., 3] > 0
    cols, counts = np.unique(a[solid][:, :3], axis=0, return_counts=True)
    n = solid.sum()
    return {"#%02x%02x%02x" % tuple(int(v) for v in c): k / n for c, k in zip(cols, counts)}


def align(pa, pb):
    """offset (dy, dx) of b relative to a that maximises silhouette overlap"""
    ha, wa = pa.shape
    hb, wb = pb.shape
    H, W = max(ha, hb) + 8, max(wa, wb) + 16
    A = np.zeros((H, W), bool); A[4:4 + ha, 8:8 + wa] = pa != "."
    best = (-1, 0, 0)
    for dy in range(-4, 5):
        for dx in range(-8, 9):
            y0, x0 = 4 + dy, 8 + dx
            if y0 < 0 or x0 < 0 or y0 + hb > H or x0 + wb > W:
                continue
            B = np.zeros((H, W), bool)
            B[y0:y0 + hb, x0:x0 + wb] = pb != "."
            iou = (A & B).sum() / (A | B).sum()
            if iou > best[0]:
                best = (iou, dy, dx)
    return best, H, W


def place(grid, H, W, y0, x0, fill):
    out = np.full((H, W), fill, dtype=grid.dtype)
    out[y0:y0 + grid.shape[0], x0:x0 + grid.shape[1]] = grid
    return out


def place_rgba(a, H, W, y0, x0):
    out = np.zeros((H, W, 4), np.uint8)
    out[y0:y0 + a.shape[0], x0:x0 + a.shape[1]] = a
    return out


def line_colours(cfg):
    """outline + every colour the style uses to draw lines (inner lines, crease shades, borders)"""
    st = cfg["style"]
    refs = ["outline"] + list(st.get("inner_line", {}).values()) + list(st.get("line_shade", {}).values()) \
        + [b["colour"] for b in st.get("border_lines", [])]
    out = set()
    for r in refs:
        if r == "outline":
            out.add(hexrgb(cfg["palette"]["outline"]))
        else:
            part, i = r.split(":")
            out.add(hexrgb(cfg["palette"]["parts"][part][int(i)]))
    return out


def grow2(m, r=2):
    out = m.copy()
    for _ in range(r):
        P = np.pad(out, 1)
        out = out | P[:-2, 1:-1] | P[2:, 1:-1] | P[1:-1, :-2] | P[1:-1, 2:] | P[:-2, :-2] | P[:-2, 2:] | P[2:, :-2] | P[2:, 2:]
    return out


def line_placement(cfg, ref, ours, tol=2):
    """Inner lines (line-coloured pixels not on the silhouette) in ours with no reference line
    within `tol` px (extra), and the reverse (missing). Counts *where* lines are, not how many."""
    cols = line_colours(cfg)
    def masks(a):
        solid = a[..., 3] > 0
        line = solid & np.any([np.all(a[..., :3] == c, -1) for c in cols], 0)
        P = np.pad(solid, 1)
        inside = solid & P[:-2, 1:-1] & P[2:, 1:-1] & P[1:-1, :-2] & P[1:-1, 2:]
        return line, line & inside
    ref_line, ref_inner = masks(ref)
    our_line, our_inner = masks(ours)
    extra = our_inner & ~grow2(ref_line, tol)
    missing = ref_inner & ~grow2(our_line, tol)
    return extra, missing, int(ref_inner.sum())


def part_region_mix(cfg, a, part):
    """Colour shares inside a part's area: the part's own colours plus any line / highlight /
    shade pixel mostly surrounded by it (e.g. the shell with its crease, '=' shade and
    highlights). Catches wrong structure inside a part that whole-sprite counts average away."""
    solid = a[..., 3] > 0
    key = a[..., 0].astype(int) * 65536 + a[..., 1].astype(int) * 256 + a[..., 2]
    own = np.zeros(solid.shape, bool)
    for h in cfg["palette"]["parts"][part]:
        r, g, b = hexrgb(h); own |= solid & (key == r * 65536 + g * 256 + b)
    reg = own.copy()
    for _ in range(2):                                   # pull in lines/highlights inside the part
        P = np.pad(reg, 1)
        n8 = sum(P[1 + dy:P.shape[0] - 1 + dy, 1 + dx:P.shape[1] - 1 + dx].astype(int)
                 for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx)
        reg |= solid & (n8 >= 5)
    vals, cnt = np.unique(key[reg], return_counts=True)
    tot = cnt.sum()
    return {"#%06x" % v: c / tot for v, c in zip(vals, cnt)}, int(tot)


def score(cfg, ref, ours):
    info = colour_info(cfg)
    pr, rr = describe(ref, info)
    po, ro = describe(ours, info)
    (iou, dy, dx), H, W = align(pr, po)
    PR, RR = place(pr, H, W, 4, 8, "."), place(rr, H, W, 4, 8, -1)
    PO, RO = place(po, H, W, 4 + dy, 8 + dx, "."), place(ro, H, W, 4 + dy, 8 + dx, -1)
    union = (PR != ".") | (PO != ".")
    both = (PR != ".") & (PO != ".")
    place_px = lambda a, y0, x0: place_rgba(a, H, W, y0, x0)
    extra, missing, n_ref_inner = line_placement(cfg, place_px(ref, 4, 8), place_px(ours, 4 + dy, 8 + dx))
    part_ok = both & ((PR == "L") | (PO == "L") | (PR == PO))
    same_part = both & (PR == PO) & (PR != "L")
    shade_same = (same_part & (RR == RO)).sum() / max(1, same_part.sum())
    shade_diff = float(np.abs(RR - RO)[same_part].mean()) if same_part.any() else 9.0
    # tolerant version: our shade appears in the reference within 1 px (same part)
    near = np.zeros_like(same_part)
    for yy in (-1, 0, 1):
        for xx in (-1, 0, 1):
            R2 = np.roll(np.roll(RR, yy, 0), xx, 1)
            P2 = np.roll(np.roll(PR, yy, 0), xx, 1)
            near |= same_part & (P2 == PO) & (R2 == RO)
    shade_near = near.sum() / max(1, same_part.sum())

    hr, ho = histogram(ref), histogram(ours)
    palette_l1 = sum(abs(hr.get(k, 0) - ho.get(k, 0)) for k in set(hr) | set(ho))
    lr, lo = line_stats(ref, pr, rr), line_stats(ours, po, ro)
    per_part = {}
    for name, shades in cfg["palette"]["parts"].items():
        tr = sum(hr.get(s, 0) for s in shades)
        to = sum(ho.get(s, 0) for s in shades)
        per_part[name] = {
            "share_ref": round(float(tr), 3), "share_ours": round(float(to), 3),
            "shades_ref": [round(float(hr.get(s, 0) / max(tr, 1e-9)), 3) for s in shades],
            "shades_ours": [round(float(ho.get(s, 0) / max(to, 1e-9)), 3) for s in shades],
        }
    keys = ["line_share", "inner_line_px", "silhouette_line_px", "stair_corner_share", "grain_share"]
    grain_keys = [k for k in lr if k.startswith("grain_") and k != "grain_share"]
    line_err = float(np.mean([abs(lo[k] - lr[k]) / lr[k] for k in keys]
                             # one-sided: more specks / broken bits than the reference costs, fewer doesn't
                             + [max(0, lo["lone_line_px"] - lr["lone_line_px"]) / max(10, lr["lone_line_px"]),
                                max(0, lo["line_fragments"] - lr["line_fragments"]) / max(5, lr["line_fragments"]),
                                max(0, lo["dark_specks"] - lr["dark_specks"]) / max(3, lr["dark_specks"])]
                             + [abs(lo.get(k, 0) - lr[k]) / max(0.02, lr[k]) for k in grain_keys]))
    size_err = abs(ours.shape[0] - ref.shape[0]) / ref.shape[0] + abs(ours.shape[1] - ref.shape[1]) / ref.shape[1]
    parts_score = part_ok.sum() / union.sum()
    place_err = (extra.sum() + missing.sum()) / max(1, n_ref_inner)
    region_mix = {}
    for name in cfg.get("qa", {}).get("region_parts", []):
        mr, _ = part_region_mix(cfg, ref, name)
        mo, _ = part_region_mix(cfg, ours, name)
        region_mix[name] = {"l1": round(float(sum(abs(mr.get(k, 0) - mo.get(k, 0)) for k in set(mr) | set(mo))), 3),
                            "ref": {k: round(v, 3) for k, v in sorted(mr.items(), key=lambda kv: -kv[1])},
                            "ours": {k: round(v, 3) for k, v in sorted(mo.items(), key=lambda kv: -kv[1])}}
    # shadow placement: where each part's darkest fill shade (style.first_shade) sits. Shade
    # counts can match while the darks are in the wrong place - e.g. a thin rim along the outline
    # instead of whole shadowed petals - which reads as much weaker shadows.
    #   shadow_f1: our dark pixels with a reference dark pixel of the same part within 1 px, and
    #              the reverse (F1 of the two)
    #   dark_rim_excess: share of our darks touching the outline / outside, minus the reference's
    #                    (worst part)
    def dil(m):
        out = m.copy()
        for yy in (-1, 0, 1):
            for xx in (-1, 0, 1):
                out |= np.roll(np.roll(m, yy, 0), xx, 1)
        return out
    edge_r = dil((PR == "L") | (PR == ".")) & (PR != "L") & (PR != ".")
    edge_o = dil((PO == "L") | (PO == ".")) & (PO != "L") & (PO != ".")
    hit_o = hit_r = n_o = n_r = rim_o = rim_r = 0
    rim_parts = {}
    shadow_parts = {}
    for name in cfg["palette"]["parts"]:
        fs = cfg["style"].get("first_shade", {}).get(name, 0)
        dr = (PR == name) & (RR == fs); do = (PO == name) & (RO == fs)
        ho, hr_ = int((do & dil(dr)).sum()), int((dr & dil(do)).sum())
        hit_o += ho; hit_r += hr_; n_o += int(do.sum()); n_r += int(dr.sum())
        rim_o += int((do & edge_o).sum()); rim_r += int((dr & edge_r).sum())
        if do.sum() >= 30 and dr.sum() >= 30:     # per part, so one part's rim can't hide in the pool
            rim_parts[name] = float((do & edge_o).sum() / do.sum() - (dr & edge_r).sum() / dr.sum())
        p_, r_ = ho / max(1, do.sum()), hr_ / max(1, dr.sum())
        shadow_parts[name] = round(2 * p_ * r_ / max(1e-9, p_ + r_), 3)
    # blob_shade_err: how dark each separate piece is (each petal, flipper, ...: a part's pixels
    # split by lines), vs the reference piece it overlaps most; mean shade 0 (darkest fill) .. 1,
    # error weighted by piece size. Catches 'all petals the same mid-tone' when Showdown has
    # whole dark and whole light pieces.
    def pieces(Pg, part):
        m = Pg == part; lab = np.zeros(m.shape, int); k = 0
        for y0, x0 in zip(*np.nonzero(m)):
            if lab[y0, x0]: continue
            k += 1; st = [(y0, x0)]; lab[y0, x0] = k
            while st:
                y, x = st.pop()
                for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                    if 0 <= yy < m.shape[0] and 0 <= xx < m.shape[1] and m[yy, xx] and not lab[yy, xx]:
                        lab[yy, xx] = k; st.append((yy, xx))
        return lab, k
    berr = bw = 0.0
    for name, shades in cfg["palette"]["parts"].items():
        fs = cfg["style"].get("first_shade", {}).get(name, 0); top = len(shades) - 1
        if top <= fs:
            continue
        norm = lambda R, m: float(np.clip((R[m] - fs) / (top - fs), 0, 1).mean())
        lr_, kr = pieces(PR, name); lo_, ko = pieces(PO, name)
        for i in range(1, kr + 1):
            mr = lr_ == i
            if mr.sum() < 40:
                continue
            ov = np.bincount(lo_[mr], minlength=ko + 1); ov[0] = 0
            if ov.max() == 0:
                continue
            mo = lo_ == int(ov.argmax())
            berr += mr.sum() * abs(norm(RR, mr) - norm(RO, mo)); bw += mr.sum()
    blob_shade_err = berr / max(1, bw)
    # edge_ratio (qa.structure_parts): how much of a part is drawn as edges - pixels touching the
    # outline, an inner line or the outside - ours / reference. A part drawn as one flat blob (e.g.
    # Glimmora's crown without the separators between its petals) scores low.
    edge_ratio, shape_f1, shape_box, tone_count = {}, {}, {}, {}
    for name in cfg.get("qa", {}).get("structure_parts", []):
        def edged(Pg, Rg):
            inner = np.zeros(Pg.shape, bool)            # the style's inner-line colours are lines too
            for r_ in cfg["style"].get("inner_line", {}).values():
                lp, li = r_.split(":")
                inner |= (Pg == lp) & (Rg == int(li))
            m = (Pg == name) & ~inner
            nonpart = (Pg == "L") | (Pg == ".") | inner
            Q = np.pad(nonpart, 1, constant_values=True)
            return int((m & (Q[:-2, 1:-1] | Q[2:, 1:-1] | Q[1:-1, :-2] | Q[1:-1, 2:])).sum()), int(m.sum())
        er, ar = edged(PR, RR); eo, ao = edged(PO, RO)
        edge_ratio[name] = round((eo / max(1, ao)) / max(1e-9, er / max(1, ar)), 3)
        # shape: does our part cover the same place as the reference's (within 1 px, both ways)
        # tones: shades of the part actually used (each on >= 1 % of the part, at least 3 px)
        def tones(Pg, Rg):
            m = Pg == name; n = m.sum()
            return int(sum(1 for k in set(Rg[m].tolist()) if (Rg[m] == k).sum() >= max(3, 0.01 * n)))
        tone_count[name] = {"ours": tones(PO, RO), "ref": tones(PR, RR)}
        mr, mo = PR == name, PO == name
        p_, r_ = (mo & dil(mr)).sum() / max(1, mo.sum()), (mr & dil(mo)).sum() / max(1, mr.sum())
        shape_f1[name] = round(float(2 * p_ * r_ / max(1e-9, p_ + r_)), 3)
        ys_, xs_ = np.nonzero(mo); yr_, xr_ = np.nonzero(mr)
        if len(ys_) and len(yr_):
            # 2nd..98th percentile extent: one stray pixel of the part's colour mustn't stretch it
            ext = lambda v: int(np.percentile(v, 98) - np.percentile(v, 2) + 1)
            shape_box[name] = {"ours": [ext(xs_), ext(ys_)], "ref": [ext(xr_), ext(yr_)]}
    prec, rec = hit_o / max(1, n_o), hit_r / max(1, n_r)
    shadow_f1 = 2 * prec * rec / max(1e-9, prec + rec)
    dark_rim_excess = max(rim_parts.values()) if rim_parts else rim_o / max(1, n_o) - rim_r / max(1, n_r)
    total = 100 * (0.2 * iou + 0.2 * parts_score + 0.2 * shade_near + 0.1 * max(0, 1 - palette_l1)
                   + 0.1 * max(0, 1 - line_err) + 0.15 * max(0, 1 - place_err) + 0.05 * max(0, 1 - size_err))
    return {
        "style_score": round(total, 1),
        "extra_line_px": int(extra.sum()), "missing_line_px": int(missing.sum()),
        "line_placement_err": round(float(place_err), 3),
        "region_mix": region_mix,
        "size_ref": f"{ref.shape[1]}x{ref.shape[0]}", "size_ours": f"{ours.shape[1]}x{ours.shape[0]}",
        "unknown_colours_ours": int((po == "?").sum()),
        "silhouette_iou": round(float(iou), 3), "parts_match": round(float(parts_score), 3),
        "shade_rank_same": round(float(shade_same), 3), "shade_rank_near": round(float(shade_near), 3), "shade_rank_diff": round(shade_diff, 3),
        "palette_l1": round(float(palette_l1), 3), "line_err": round(line_err, 3),
        "shadow_f1": round(float(shadow_f1), 3), "shadow_f1_parts": shadow_parts,
        "dark_rim_excess": round(float(dark_rim_excess), 3), "blob_shade_err": round(float(blob_shade_err), 3),
        "dark_rim_parts": {k: round(v, 3) for k, v in rim_parts.items()},
        "edge_ratio": edge_ratio, "shape_f1": shape_f1, "shape_box": shape_box, "tone_count": tone_count,
        "lines_ref": {k: round(v, 3) for k, v in lr.items()}, "lines_ours": {k: round(v, 3) for k, v in lo.items()},
        "parts": per_part,
        "_grids": (PR, RR, PO, RO, union, both, part_ok, same_part, H, W),
        "_lines": (extra, missing),
    }


def report(res):
    r = res
    print(f"style score {r['style_score']}/100   size {r['size_ours']} (ref {r['size_ref']})")
    print(f"  silhouette IoU {r['silhouette_iou']:.3f}   parts match {r['parts_match']:.3f}   "
          f"shade rank same {r['shade_rank_same']:.3f} / within 1px {r['shade_rank_near']:.3f} (mean diff {r['shade_rank_diff']:.2f})   "
          f"palette L1 {r['palette_l1']:.3f}   line err {r['line_err']:.3f}   unknown colours {r['unknown_colours_ours']}")
    print(f"  shadow placement: F1 {r['shadow_f1']:.3f} {r['shadow_f1_parts']}   dark-rim excess {r['dark_rim_excess']:+.3f} {r['dark_rim_parts']}   piece shade error {r['blob_shade_err']:.3f}"
          + (f"   edge ratio {r['edge_ratio']}  shape F1 {r['shape_f1']}  box {r['shape_box']}  tones {r['tone_count']}" if r.get('edge_ratio') else ""))
    for name, m in r.get("region_mix", {}).items():
        names = {v: k for k, v in []}
        print(f"  {name} area colour mix: L1 {m['l1']:.3f}")
        keys = list(dict.fromkeys(list(m["ref"]) + list(m["ours"])))
        print("     " + "  ".join(f"{k}: {m['ours'].get(k, 0):.2f} (ref {m['ref'].get(k, 0):.2f})" for k in keys))
    print(f"  line placement: {r['extra_line_px']} extra line px (no Showdown line within 2 px), "
          f"{r['missing_line_px']} missing   (err {r['line_placement_err']:.3f})")
    for k in r["lines_ref"]:
        print(f"  {k:20s} ours {r['lines_ours'][k]:8.3f}   ref {r['lines_ref'][k]:8.3f}")
    for name, p in r["parts"].items():
        print(f"  {name:6s} share {p['share_ours']:.3f} (ref {p['share_ref']:.3f})  "
              f"shades {p['shades_ours']}  ref {p['shades_ref']}")


def picture(ref, ours, res, path, S=4):
    PR, RR, PO, RO, union, both, part_ok, same_part, H, W = res["_grids"]
    diff = np.zeros((H, W, 4), np.uint8)
    diff[union] = (220, 60, 60, 255)
    diff[part_ok] = (230, 180, 60, 255)
    diff[same_part & (RR == RO)] = (90, 90, 90, 255)
    diff[both & (PR == "L") & (PO == "L")] = (90, 90, 90, 255)
    extra, missing = res["_lines"]
    lines_pic = np.zeros((H, W, 4), np.uint8)
    lines_pic[union] = (200, 200, 200, 255)
    lines_pic[extra] = (230, 0, 200, 255)          # magenta: our line, none in Showdown
    lines_pic[missing] = (0, 170, 230, 255)        # cyan: Showdown line, none in ours
    tiles = [ref, ours, diff, lines_pic]
    th = max(t.shape[0] for t in tiles)
    canvas = Image.new("RGBA", (sum(t.shape[1] for t in tiles) * S + 2 * 6 * S, th * S), (122, 170, 153, 255))
    x = 0
    for t in tiles:
        canvas.alpha_composite(Image.fromarray(t).resize((t.shape[1] * S, t.shape[0] * S), Image.Resampling.NEAREST), (x, 0))
        x += t.shape[1] * S + 6 * S
    canvas.save(path)


if __name__ == "__main__":
    args = sys.argv[1:]
    cfg_path = Path(args[0])
    cfg = json.loads(cfg_path.read_text())
    frame = int(args[args.index("--frame") + 1]) if "--frame" in args else 0
    ref = load(cfg_path.parent / cfg["reference"])
    ours = load(args[1], frame)
    res = score(cfg, ref, ours)
    report(res)
    if "--out" in args:
        picture(ref, ours, res, args[args.index("--out") + 1])
    if "--json" in args:
        Path(args[args.index("--json") + 1]).write_text(json.dumps({k: v for k, v in res.items() if not k.startswith("_")}, indent=2, default=float))
