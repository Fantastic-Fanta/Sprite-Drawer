"""Paint-over of a Mega Zygarde frame, art direction from the official artwork:
  - the head is a long barrel: cylinder shading (lit band on top, dark underside), lines only on
    the silhouette, big overlaps and long panel seams; no hatching on spikes
  - flat, bright marks (red band, lavender X)
  - the hanging body reads as limbs: neon green with its own lit / shadow side, black hex panels
Run by pipeline/paint_over.py (style.paint_over): python3 paint_zygarde.py FRAME.pkl OUT.png OUT.npz"""
import json
import pickle
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import sprite_style as ss

# art switches
EYE = True              # paint the core's mech face: dark mask, white diamond, two pale eyes
FACE_PLATE = "lit"      # the face plate: "dark" (near-black, like the hood) or "lit" (a step lighter, outlined)
FACE_DEPTH = True       # with the lit plate: form shading, a bevel, eye sockets and the crown's shadow
HEAD_RIM = False        # a 1 px rim of the core's green glow along the underside of the head
CHEAT_EYES = False      # mirror the visible eye across the diamond (when the head faces away)
GEMS = "game"           # chest gems as in the game: pale blue / coral on green hex bases ("flat": saturated)

f = pickle.load(open(sys.argv[1], "rb"))
solid, n, depth, part = f["solid"], f["n"], f["depth"].astype(float), f["part"].copy()
part = ss.smooth_parts(part, solid, 2)
h, w = solid.shape
# sizes below were set at style.height 210 (a 216 px tall frame); they scale with the sprite
SC = h / 216
sc = lambda v: max(1, int(round(v * SC)))
# small see-through slits inside the sprite flicker as white specks when the head turns: filled
# as deep shadow, set back behind their surroundings. The gap round the head itself (~65 px) stays
# open - it's the only place the head's silhouette shows against the background
solid = solid.copy(); n = n.copy()
for comp in ss.components(~solid):
    ys, xs = zip(*comp)
    if len(comp) <= 30 * SC * SC and min(ys) > 0 and min(xs) > 0 and max(ys) < h - 1 and max(xs) < w - 1:
        ring = [depth[y + dy, x + dx] for y, x in comp for dy, dx in ss.NB4 if solid[y + dy, x + dx]]
        solid[ys, xs] = True
        part[ys, xs] = "black"
        depth[ys, xs] = (min(ring) if ring else 0) - 30
        n[ys, xs] = (0.0, 0.0, 1.0)
h, w = solid.shape
hx = lambda s: tuple(int(s[i:i + 2], 16) for i in (1, 3, 5))

# ramps [deep, shadow, mid, lit, highlight], colours picked from the official art
RAMP = {
    "gray": ["#211d1c", "#2f2a29", "#3e3836", "#544c49", "#6e6561"],     # barrel / spikes
    "collar": ["#151111", "#1f1919", "#2b2423", "#413835", "#5e524e"],    # spikes: near-black, lit edges
    "black": ["#121010", "#1a1717", "#242020", "#302b2a", "#3e3836"],    # body hex panels, tail
    "green": ["#2f6a0e", "#4c9615", "#6fc21f", "#97e335", "#c4f56a"],
    "white": ["#9aa29e", "#c2c9c5", "#e2e7e4", "#f6f9f7", "#ffffff"],
    "face": ["#262120", "#353030", "#474040", "#5c5450", "#7a706b"],     # the X face, a dome
    "glow": ["#7fb02e", "#a6d64a", "#c8ec7a", "#e2f8a8", "#f4ffd0"],
    "pink": ["#8a62a6", "#a57cc2", "#c09ad9", "#d6b6ec", "#ecd6fb"],
    "red": ["#6a0c0c", "#9a1212", "#c41a18", "#e2302a", "#f2584c"],
    "blue": ["#0d2f4e", "#123f68", "#1a5a8e", "#2475b0", "#3a92cf"],
    "yellow": ["#9a2f28", "#c0443a", "#e0645a", "#f08478", "#ffa89c"],   # the coral hex
}
OUTLINE = hx("#110e0e")
JUMP = 6
NB4, NB8, shift = ss.NB4, ss.NB8, ss.shift

# the body's dark panels come through as "gray" (same texture colour as the barrel): gray that
# sits among green / white is the body's black, not barrel
greenish = np.isin(part, ["green", "white"]).astype(float)
dens = ss.box_sum(greenish, sc(4)) / np.maximum(ss.box_sum(solid.astype(float), sc(4)), 1)
body = solid & (part == "gray") & (dens > 0.2)
for _ in range(3):                                   # grow along connected gray in the body
    nb = np.zeros_like(body)
    for dy, dx in NB4:
        nb |= shift(body, dy, dx, False)
    body |= nb & solid & (part == "gray") & (dens > 0.08)
part[body] = "black"
# the spike collar round the neck: gray near the body (within ~10 px), not the barrel
bodyish = np.isin(part, ["green", "white", "black"]).astype(float)
near_body = ss.box_sum(bodyish, sc(10)) / np.maximum(ss.box_sum(solid.astype(float), sc(10)), 1)
collar = solid & (part == "gray") & (near_body > 0.06)
part[collar] = "collar"
# yellow on the body is the core's pale glow (face, chest), not the barrel's coral hex
part[solid & (part == "yellow") & (near_body > 0.06)] = "glow"


# the barrel's front face (the X face): gray whose normal points to camera-left, the biggest
# connected piece - shaded as its own dome, like the artwork's rounded front
fm = solid & (part == "gray") & (n[..., 0] < -0.45)
comps = sorted(ss.components(fm), key=len, reverse=True)
face = np.zeros_like(solid)
if comps:
    ys, xs = zip(*comps[0]); face[ys, xs] = True
part[face] = "face"
# the body's white hex outlines come out as blobs at this size: draw them as the chest's pale
# lime glow instead
was_white = solid & (part == "white")
part[was_white] = "green"      # one green, shaded as limbs (no camo)


def surface_avg(v, r, mask, jump=JUMP):
    """v averaged over a disc of radius r, only over pixels on the same surface (no depth step,
    same part): bands follow forms, not facets"""
    acc, wt = np.zeros((h, w)), np.zeros((h, w))
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dy * dy + dx * dx > r * r:
                continue
            ok = solid & shift(solid, dy, dx, False) & (np.abs(shift(depth, dy, dx, -1e9) - depth) < jump) \
                & (shift(part, dy, dx, "") == part)
            acc += np.where(ok, shift(v, dy, dx, 0), 0); wt += ok
    return np.where(mask & (wt > 0), acc / np.maximum(wt, 1), v)


# spots on the core found by surface position (rest pass, frame 0's values): they move with the
# body in every frame
REST = f["rest"][..., :3].astype(int)
def at_rest(v, tol):
    return solid & (np.sqrt(((REST - np.array(v)) ** 2).sum(-1)) < tol)

# the core's glow as a second light: Zygarde's chest glows, so it lights the head and spills a
# little green onto what faces it (the barrel's underside, the arms, the collar) - the head reads
# against a pool of light instead of sinking into the barrel's shadow. The key light stays top-left
core_spot = at_rest((175, 97, 124), 6)
glow_l = np.zeros((h, w))
if core_spot.any():
    cy, cx = [v.mean() for v in np.nonzero(core_spot)]
    cy -= 14 * SC                                               # up at the neck, between the head and the chest
    cz = depth[core_spot].mean() + 12                         # a little in front of the chest
    yy, xx = np.mgrid[0:h, 0:w]
    v = np.stack([cx - xx, -(cy - yy), (cz - depth) * 0.6], -1)   # depth counted short: the hood sits well back
    dist = np.linalg.norm(v, axis=-1)
    facing = np.clip((n * v).sum(-1) / np.maximum(dist, 1e-6), 0, 1)
    glow_l = solid * facing * np.clip(1 - dist / (45 * SC), 0, 1) ** 1.2
    core_body = solid & np.isin(part, ["green", "glow", "black", "collar"]) & (dist < 14 * SC)
    glow_l[core_body] = np.maximum(glow_l[core_body], 0.6)

# 1. light: key from upper-left-front, as in the artwork
L = np.array([-0.45, 0.7, 0.55]); L /= np.linalg.norm(L)
lit = n @ L
lit = surface_avg(lit, sc(3), solid)
lit = surface_avg(lit, sc(10), solid & (part == "gray"), JUMP * 3)   # the barrel: one smooth cylinder across its plates
lit = surface_avg(lit, sc(10), solid & (part == "gray"), JUMP * 3)   # twice: the plates' facets still showed
# the X face painted as an ideal dome: an ellipse fitted to the face's outline gives each pixel
# a sphere normal, lit by the same key light - the model's low-poly facets don't show through
fy, fx = np.nonzero(face)
if len(fy) > 50:
    cy, cx = fy.mean(), fx.mean()
    cov = np.cov(np.stack([fx - cx, fy - cy]))
    ev, evec = np.linalg.eigh(cov)
    yy, xx = np.mgrid[0:h, 0:w]
    u = np.stack([xx - cx, yy - cy], -1) @ evec / (2 * np.sqrt(ev))   # ~unit ellipse coords
    r2 = np.clip((u ** 2).sum(-1), 0, 0.98)
    # back to image axes for the normal: x right, y up
    d = (u / np.sqrt(np.maximum(r2, 1e-6))[..., None] * np.sqrt(r2)[..., None]) @ evec.T
    ns = np.stack([d[..., 0], -d[..., 1], np.sqrt(1 - r2)], -1)
    # tilt the dome toward camera-left, where the face points
    ns = ns * 0.75 + np.array([-0.6, 0.0, 0.4]) * 0.25
    ns /= np.linalg.norm(ns, axis=-1, keepdims=True)
    lit = np.where(face, ns @ L, lit)

# 2. occlusion (behind something near) and cast shadow (a nearer surface toward the light)
dep = np.where(solid, depth, -np.inf); near = dep.copy()
for dy in range(-sc(6), sc(6) + 1):
    for dx in range(-sc(6), sc(6) + 1):
        if dy * dy + dx * dx <= sc(6) ** 2:
            near = np.maximum(near, shift(dep, dy, dx, -np.inf))
gap = np.zeros_like(depth); np.subtract(near, depth, out=gap, where=solid)
behind = solid & (gap > 16) & (glow_l < 0.35)
cast = np.zeros_like(solid)
d_or_low = np.where(solid, depth, -1e9)
for k in range(1, sc(4) + 1):
    for dy, dx in ((-k, -round(k * 0.6)), (-k, -k), (-round(k * 0.6), -k)):
        cast |= solid & (shift(d_or_low, -dy, -dx, -1e9) - depth > JUMP * 1.5)

# 3. tones: shadow 1 / mid 2 / lit 3 by quantile per part, highlight 4 on the top few % of big
#    parts, cast one step down, behind = deep 0
tone = np.full((h, w), 2)
for p in RAMP:
    m = solid & (part == p)
    free = m & ~behind & ~cast
    if free.sum() < 10:
        continue
    q1, q2, q3 = np.quantile(lit[free], [0.3, 0.7, 0.95])
    tone[m] = 2 + (lit[m] >= q2) - (lit[m] < q1)
    if m.sum() > 3000 or p == "face":
        tone[free & (lit >= q3)] = 4
tone[cast] = np.maximum(np.minimum(tone[cast], 3) - 1, 1)
tone[behind] = 0
tone[cast & (glow_l >= 0.35)] = np.maximum(tone[cast & (glow_l >= 0.35)], 2)   # the glow fills cast shadow too
# the glow lifts tones near the core (up to two steps, at the core itself)
lift = np.round(np.clip(glow_l, 0, 1) * 2.4).astype(int)
tone = np.where(solid, np.clip(tone + lift, 0, 4), tone)

# clean tones: 1 px slivers take their neighbours' tone, then regions under 16 px go
for _ in range(2):
    for (ay, ax), (by, bx) in (((-1, 0), (1, 0)), ((0, -1), (0, 1))):
        a, b = shift(tone, ay, ax, -1), shift(tone, by, bx, -1)
        sl = solid & (a == b) & (a >= 0) & (a != tone) & (shift(part, ay, ax, "") == part) & (shift(part, by, bx, "") == part)
        tone[sl] = a[sl]
for t in range(5):
    for comp in ss.components(solid & (tone == t)):
        if len(comp) < 16 * SC * SC:
            ys, xs = zip(*comp)
            nb = [tone[y + dy, x + dx] for y, x in comp for dy, dx in NB4
                  if 0 <= y + dy < h and 0 <= x + dx < w and solid[y + dy, x + dx] and tone[y + dy, x + dx] != t
                  and part[y + dy, x + dx] == part[y, x]]
            if nb:
                tone[ys, xs] = max(set(nb), key=nb.count)

# 4. lines: occlusion contours where something is clearly in front (a real overlap), panel seams
#    (sharp creases) only on thick barrel areas and only as long strokes; the hanging body gets
#    its overlaps lined so the limbs separate
def steps(j):
    m = np.zeros_like(solid)
    for dy, dx in NB4:
        m |= solid & shift(solid, dy, dx, False) & (shift(depth, dy, dx, 0) - depth > j)
    return m
occl = steps(JUMP * 1.5)
crease = np.zeros_like(solid)
for dy, dx in NB4:
    crease |= solid & shift(solid, dy, dx, False) & ((n * shift(n, dy, dx, 0)).sum(-1) < 0.8) \
        & (shift(depth, dy, dx, 0) >= depth) & np.isin(part, ["gray", "face"])
thick = ss.edge_distance(solid & ~steps(JUMP)) >= sc(3)
crease_all = crease & ~behind
crease &= thick & ~behind
# long creases on thin pieces too: the edges between the back claw-fingers lie next to depth
# steps, so the thickness rule dropped them and the fingers merged into one mass
long_crease = np.zeros_like(solid)
for comp in ss.components(ss.thin(crease_all)):
    if len(comp) >= 20 * SC:
        ys, xs = zip(*comp); long_crease[ys, xs] = True
crease |= long_crease
line = ss.thin(occl | crease)
edge_in = np.zeros_like(solid)
for dy, dx in NB4:
    edge_in |= solid & ~shift(solid, dy, dx, False)
for comp in ss.components(line):
    touches_edge = any(edge_in[y, x] for y, x in comp)
    is_seam = all(crease[y, x] or not occl[y, x] for y, x in comp[:3])
    if len(comp) < (8 if touches_edge else 16) * SC or (is_seam and not touches_edge and len(comp) < 25 * SC):
        ys, xs = zip(*comp); line[ys, xs] = False

# a line end 1-3 px short of another line or the silhouette is carried on to it
def touches(y, x, own):
    for dy, dx in NB8:
        yy, xx = y + dy, x + dx
        if not (0 <= yy < h and 0 <= xx < w) or not solid[yy, xx]:
            return True
        if line[yy, xx] and (yy, xx) not in own:
            return True
    return False
for y, x in np.argwhere(line):
    nbs = [(y + dy, x + dx) for dy, dx in NB8 if 0 <= y + dy < h and 0 <= x + dx < w and line[y + dy, x + dx]]
    if len(nbs) != 1:
        continue
    own = {(y, x), nbs[0]} | {(nbs[0][0] + dy, nbs[0][1] + dx) for dy, dx in NB8}
    if touches(y, x, own):
        continue
    dy, dx = y - nbs[0][0], x - nbs[0][1]
    path = []
    for k in range(1, 4):
        yy, xx = y + dy * k, x + dx * k
        if not (0 <= yy < h and 0 <= xx < w) or not solid[yy, xx]:
            break
        path.append((yy, xx)); own.add((y + dy * (k - 1), x + dx * (k - 1)))
        if touches(yy, xx, own | set(path)):
            for py, px in path:
                line[py, px] = True
            break

# clean strokes: a tiny loop (facet edges meeting at a point leave a 1-4 px hole in the line) is
# filled and the stroke thinned again; then hooks - a free end reaching a junction within 3 px -
# are trimmed, so a seam is one stroke, not a squiggle
for _ in range(2):
    # holes by 4-connectivity (a diagonal gap between line pixels doesn't open a loop)
    seen = np.zeros_like(solid)
    for y0, x0 in np.argwhere(solid & ~line):
        if seen[y0, x0]:
            continue
        comp, st, open_ = [], [(y0, x0)], False
        seen[y0, x0] = True
        while st:
            y, x = st.pop(); comp.append((y, x))
            for dy, dx in NB4:
                yy, xx = y + dy, x + dx
                if not (0 <= yy < h and 0 <= xx < w) or not solid[yy, xx]:
                    open_ = True; continue
                if not line[yy, xx] and not seen[yy, xx]:
                    seen[yy, xx] = True; st.append((yy, xx))
        if not st and not open_ and len(comp) <= 4:
            ys, xs = zip(*comp); line[ys, xs] = True
    line = ss.thin(line)
    def nbrs(y, x):
        return [(y + dy, x + dx) for dy, dx in NB8 if 0 <= y + dy < h and 0 <= x + dx < w and line[y + dy, x + dx]]
    for y, x in np.argwhere(line):
        if not line[y, x] or len(nbrs(y, x)) != 1 or edge_in[y, x]:
            continue
        run, prev, cur = [(y, x)], None, (y, x)
        while len(run) <= 4:
            nx = [q for q in nbrs(*cur) if q != prev and q not in run]
            if len(nx) != 1:
                break
            prev, cur = cur, nx[0]
            if len(nbrs(*cur)) >= 3:
                if len(run) <= 3:
                    for q in run:
                        line[q] = False
                break
            run.append(cur)

# soft edges: a smaller overlap (fingers lying on each other, arms against the barrel) gets a
# 1 px step of darker shade instead of a line - it separates the pieces without inking them
soft = ss.thin(steps(JUMP * 0.5)) & ~line
near_line = np.zeros_like(solid)
for dy, dx in NB4:
    near_line |= shift(line, dy, dx, False)
soft &= ~near_line
for comp in ss.components(soft):
    if len(comp) < 8 * SC:
        ys, xs = zip(*comp); soft[ys, xs] = False
tone[soft] = np.maximum(tone[soft] - 1, 0)

# loose bits left by the clean-up: line pieces under 6 px that touch nothing go
for comp in ss.components(line):
    if len(comp) < 6 * SC and not any(edge_in[y, x] for y, x in comp):
        ys, xs = zip(*comp); line[ys, xs] = False

# hand decision: the arm root under the barrel's back end is busy geometry that only scribbles
# at this size - no inner lines or soft edges there, its shading carries it
ROOT = (slice(sc(78), sc(101)), slice(sc(188), sc(220)))
root = np.zeros_like(solid); root[ROOT] = True
line &= ~(root & ~edge_in)

# collar spikes: the upper edge of each spike (open to the sky / the light) catches the light
up_open = solid & (~shift(solid, 1, 0, False) | ~shift(solid, 1, 1, False))
tips = (part == "collar") & up_open & ~line & ((n @ L) > 0.2)
tone[tips] = 4

# one soft highlight stroke along the barrel's top, where it's lit most (not a rim everywhere)
top_edge = solid & (part == "gray") & ~line
below_sky = np.zeros_like(solid)
for k in (2, 3):
    below_sky |= ~shift(solid, k, 0, False)
cand = top_edge & below_sky & ~up_open & (lit >= np.quantile(lit[solid & (part == "gray")], 0.9))
comps = sorted(ss.components(cand), key=len, reverse=True)
if comps:
    ys, xs = zip(*comps[0]); tone[ys, xs] = 4

# 5. compose
out = np.zeros((h, w, 4), np.uint8)
for p, ramp in RAMP.items():
    cols = np.array([hx(c) for c in ramp], np.uint8)
    m = solid & (part == p)
    out[m, :3] = cols[tone[m]]
out[solid, 3] = 255
# the glow's colour on the dark parts that face it: their own dark-green ramp (a grey mixed with
# green reads as mud), by the same tone
GLOWLIT = np.array([hx(c) for c in ("#1c2414", "#253318", "#31451d", "#425e23", "#577c2b")], np.uint8)
m = solid & np.isin(part, ["gray", "collar", "black", "face"]) & (glow_l >= 0.3)
out[m, :3] = GLOWLIT[tone[m]]
nb_black = np.zeros_like(solid)
for dy, dx in NB4:
    nb_black |= shift(part == "black", dy, dx, False)
hexl = ss.thin(was_white & nb_black) & ~line
for comp in ss.components(hexl):
    if len(comp) < 2:
        ys, xs = zip(*comp); hexl[ys, xs] = False
out[hexl, :3] = hx("#dff5c4")
if f.get("fixed") is not None:
    out[f["fixed"], :3] = f["fixed_rgb"][f["fixed"]]
# the chest gems (blue left, red right): a few px each at this size, so placed by surface position
# and drawn flat with a lit corner - otherwise they're absorbed into the dark collar
GEM_COLS = ((("#2b6fd6", "#8fbcff"), ("#d42020", "#ff8a78")) if GEMS == "flat" else
            (("#86c8ea", "#d2f0ff"), ("#ea8278", "#ffc2b6")))
for v, tol, (col, lite) in zip(((112, 107, 122), (145, 106, 120)), (4, 4), GEM_COLS):
    gem = at_rest(v, tol) & ~line
    if gem.any():
        if GEMS == "game":                                    # the green hex base round each gem
            base = np.zeros_like(gem)
            for dy, dx in NB8:
                base |= shift(gem, dy, dx, False)
            base &= solid & ~gem & ~line
            out[base, :3] = hx("#7cc22e")
        out[gem, :3] = hx(col)
        ys, xs = np.nonzero(gem)
        k = np.argmin(ys + xs)                                # the corner toward the key light
        out[ys[k], xs[k], :3] = hx(lite)
# coloured lines (selective outline): a line takes a dark shade of the colour it sits on - the
# part's deep tone, darker still in shadow, softer on the lit side - so it belongs to the
# shading instead of sitting on top of it as black ink
def line_colour(p, t):
    """two steps darker than the fill it sits on; below the ramp's bottom, the deep tone darkened"""
    if p not in RAMP:
        return np.array(OUTLINE, np.uint8)
    r = [np.array(hx(c), float) for c in RAMP[p]]
    i = int(t) - 2
    c = r[i] if i >= 0 else r[0] * (0.8 if i == -1 else 0.65)
    return np.clip(c, 0, 255).astype(np.uint8)
for y, x in np.argwhere(line):
    out[y, x, :3] = line_colour(part[y, x], tone[y, x])
# the core's mech face: a dark mask, a white diamond with a pale hexagon above it on the
# forehead, and two pale eyes below it, one either side,
# a few px each here (the eyes' pale yellow and the diamond's white would otherwise be painted as
# body glow / green). Each is the exact set of surface positions its pixels show in the full-size
# render (zygarde_face.json, from make_zygarde_face.py): its real outline and size at any sprite
# height, turning with the head - a blob round one point came out too big and lumpy
if EYE:
    FACE = json.loads((Path(__file__).resolve().parent / "zygarde_face.json").read_text())
    key = REST[..., 0] * 65536 + REST[..., 1] * 256 + REST[..., 2]
    def shows(name):
        vals = np.array([r * 65536 + g * 256 + b for r, g, b in FACE[name]])
        return solid & np.isin(key, vals)
    def clean(m, keep, passes=1):
        """the render stores surface positions coarsely: a few strays elsewhere share a feature's
        values and a few of its own px don't - close 1 px gaps, keep its `keep` biggest pieces"""
        for _ in range(passes):
            nb = np.zeros(m.shape, int)
            for dy, dx in NB4:
                nb += shift(m, dy, dx, False)
            m = (m | (solid & (nb >= 3))).copy()
        comps = sorted(ss.components(m), key=len, reverse=True)
        out_m = np.zeros_like(m)
        for comp in comps[:keep]:
            ys, xs = zip(*comp); out_m[ys, xs] = True
        return out_m
    eyes_m, dia_m = clean(shows("eyes"), 2), clean(shows("diamond"), 1)
    hex_m = clean(shows("hex"), 1) & ~dia_m if FACE.get("hex") else np.zeros_like(solid)
    plate = clean(shows("mask") | eyes_m | dia_m | hex_m, 1, passes=3) & ~eyes_m & ~dia_m & ~hex_m
    head = plate | eyes_m | dia_m | hex_m
    if FACE_PLATE == "lit":
        # a step lighter than the hood, outlined, so the head has its own shape against it
        out[plate, :3] = hx("#3b3534")
        edge = np.zeros_like(head)
        for dy, dx in NB4:
            edge |= head & ~shift(head, dy, dx, False)
        out[edge & plate, :3] = hx("#0d0a0a")
        if FACE_DEPTH:
            # the plate as a form, not a sticker: two tones from its own surface normals (lit
            # upper-left), a 1 px bevel inside the outline (light top / left, dark bottom / right)
            # and the crown's shadow where it overhangs the face
            inner = plate & ~edge
            fl = n @ L
            acc, cnt = np.zeros((h, w)), np.zeros((h, w))
            r = sc(2)                                        # averaged wide: the plate's bumps mottled it
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    m = shift(inner, dy, dx, False)
                    acc += np.where(m, shift(fl, dy, dx, 0), 0); cnt += m
            fl = np.where(cnt > 0, acc / np.maximum(cnt, 1), fl)
            if inner.sum() > 6:
                lit_side = fl >= np.median(fl[inner])
                out[inner & lit_side, :3] = hx("#433c3a")
                out[inner & ~lit_side, :3] = hx("#2c2625")
            tl = inner & (shift(edge, 1, 0, False) | shift(edge, 0, 1, False))      # outline above / left
            br = inner & (shift(edge, -1, 0, False) | shift(edge, 0, -1, False))    # outline below / right
            out[tl & ~br, :3] = hx("#5a514e")
            out[br & ~tl, :3] = hx("#221d1c")
            crown = part == "green"
            out[inner & (shift(crown, 1, 0, False) | shift(crown, 2, 0, False)), :3] = hx("#221d1c")
    else:
        out[plate, :3] = hx("#161212")
    if CHEAT_EYES and dia_m.any():
        # the far eye drawn as the near one mirrored across the diamond: a level pair reads as a face
        cx2 = 2 * np.nonzero(dia_m)[1].mean()
        ys, xs = np.nonzero(eyes_m)
        mx = np.round(cx2 - xs).astype(int)
        ok = (mx >= 0) & (mx < w)
        mirror = np.zeros_like(eyes_m); mirror[ys[ok], mx[ok]] = True
        eyes_m = eyes_m | (mirror & solid & ~dia_m)
    if HEAD_RIM:
        # the glow below catches the head's underside: its lower edge, 1 px, in the glow's green
        below_open = head & ~shift(head, -1, 0, False)
        out[below_open & ~eyes_m & ~dia_m, :3] = hx("#8fd63a")
    if FACE.get("beak"):
        # the beak / mask: the collar's central lobe below the face, a rounded grey form lit from
        # the upper left, outlined - it read as part of the dark collar under the glow's green
        beak_m = clean(shows("beak"), 1, passes=2) & ~head
        if beak_m.sum() > 6:
            bl = n @ L
            acc, cnt = np.zeros((h, w)), np.zeros((h, w))
            r = sc(2)
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    m = shift(beak_m, dy, dx, False)
                    acc += np.where(m, shift(bl, dy, dx, 0), 0); cnt += m
            bl = np.where(cnt > 0, acc / np.maximum(cnt, 1), bl)
            q1, q2 = np.quantile(bl[beak_m], [0.35, 0.75])
            ramp = np.array([hx(c) for c in ("#2d2726", "#433c3a", "#5a5250")], np.uint8)
            out[beak_m, :3] = ramp[(bl[beak_m] >= q1).astype(int) + (bl[beak_m] >= q2)]
            bedge = np.zeros_like(beak_m)
            for dy, dx in NB4:
                bedge |= beak_m & ~shift(beak_m, dy, dx, False)
            btl = beak_m & ~bedge & (shift(bedge, 1, 0, False) | shift(bedge, 0, 1, False))
            out[btl, :3] = hx("#6e6562")                    # its lit upper-left edge
            out[bedge, :3] = hx("#141010")
    if hex_m.any():
        # the forehead hexagon's own dark rim, so it separates from the crown's pale base
        ring_h = np.zeros_like(hex_m)
        for dy, dx in NB4:
            ring_h |= shift(hex_m, dy, dx, False)
        out[ring_h & ~hex_m & ~dia_m & ~eyes_m & solid, :3] = hx("#141010")
    out[dia_m, :3] = hx("#f2f6f4")
    ys, xs = np.nonzero(dia_m)
    if len(ys):
        shade = xs > xs.mean()                               # the side away from the key light
        out[ys[shade], xs[shade], :3] = hx("#b9c2bf")
    out[(eyes_m | hex_m) & ~dia_m, :3] = hx("#e6f08c")
    if FACE_PLATE == "lit" and FACE_DEPTH:
        # eye sockets: a dark brow line right above each eye, and a light glint in its top-left px
        brow = plate & shift(eyes_m, -1, 0, False)
        out[brow, :3] = hx("#141010")
        for comp in ss.components(eyes_m & ~dia_m):
            y, x = min(comp, key=lambda q: q[0] + q[1])
            out[y, x, :3] = hx("#fbffd6")
ring = np.zeros_like(solid)
for dy, dx in NB8:
    ring |= ~solid & shift(solid, dy, dx, False)
for y, x in np.argwhere(ring):
    # the outline beside the body pixel it borders; darker than inner lines (it's the silhouette)
    best = None
    for dy, dx in NB4 + NB8[4:]:
        yy, xx = y + dy, x + dx
        if 0 <= yy < h and 0 <= xx < w and solid[yy, xx] and not line[yy, xx]:
            best = (yy, xx); break
    if best is None:
        out[y, x] = (*OUTLINE, 255); continue
    c = line_colour(part[best], tone[best]).astype(float) * 0.7
    out[y, x] = (*np.clip(c, 0, 255).astype(np.uint8), 255)
pad = np.zeros((h + 4, w + 4, 4), np.uint8); pad[2:-2, 2:-2] = out
Image.fromarray(pad).save(sys.argv[2])
if len(sys.argv) > 3:
    np.savez(sys.argv[3], occl=occl, crease=crease, line=line, solid=solid)
print("tones", [int((solid & (tone == t)).sum()) for t in range(5)], "line", int(line.sum()), "body black", int(body.sum()))
