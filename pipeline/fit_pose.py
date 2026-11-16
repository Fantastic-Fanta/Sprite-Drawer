"""Fit the pose + camera numbers in CONFIG.json to the reference Showdown frame.

Run:
  Blender -b MODEL.blend --python fit_pose.py -- CONFIG.json TMP_DIR [--restarts 30] [--seed 1] [--local K]
Updates CONFIG.json "pose_params" in place (the old values are kept in "pose_params_previous").

Method (see SPRITE_PIPELINE.md, step 3):
  * Reference part map: every reference pixel's palette colour -> part (or outline).
  * Ours: render the colour pass at low resolution (no anti-aliasing), classify each pixel
    into a part the same way sprite_style.py does, scale to the reference height.
  * Score: best over small shifts of the share of the combined shape where both have the
    same part (reference outline pixels match anything). Matching parts, not just the
    outline, stops the fit cheating (e.g. turning the face away to fill the head shape).
  * Search: random starts inside the "fit" ranges, each refined by coordinate descent
    (nudge one number up/down, keep improvements, halve steps when stuck); the best start
    is then refined further. --local K: restarts start within K steps of the current pose instead
    of anywhere in the ranges (for many numbers, where uniform random starts land far off).
Runs inside Blender's Python (numpy only, no PIL).
"""
import bpy, sys, json, os, random
from pathlib import Path
import numpy as np

args = sys.argv[sys.argv.index("--") + 1:]
cfg_path, tmp_dir = Path(args[0]).resolve(), args[1]
restarts = int(args[args.index("--restarts") + 1]) if "--restarts" in args else 30
random.seed(int(args[args.index("--seed") + 1]) if "--seed" in args else 1)
cfg = json.loads(cfg_path.read_text())
here = Path(__file__).parent if "__file__" in globals() else cfg_path.parent

sys.argv = [sys.argv[0], "--", str(cfg_path), tmp_dir, "--setup-only"]
src = here / "render_sprite.py" if (here / "render_sprite.py").exists() else cfg_path.parent / "render_sprite.py"
g = {"__name__": "render_sprite", "__file__": str(src)}       # so it finds motion.py next to it
exec(compile(src.read_text(), str(src), "exec"), g)
scene, P = g["scene"], g["P"]
scene.render.resolution_x = cfg["render"]["width"] // 2
scene.render.resolution_y = cfg["render"]["height"] // 2
scene.render.image_settings.file_format = "PNG"          # render() below reads fit_*.png


def hexrgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def load_rgba(path):
    img = bpy.data.images.load(str(path), check_existing=False)
    w, h = img.size
    px = np.array(img.pixels[:]).reshape(h, w, 4)[::-1]
    bpy.data.images.remove(img)
    return px


# reference part map
PARTS = list(cfg["palette"]["parts"])
code = {hexrgb(cfg["palette"]["outline"]): 9}
for i, (name, shades) in enumerate(cfg["palette"]["parts"].items()):
    for h in shades:
        code.setdefault(hexrgb(h), i + 1)
# fit_reference: what to fit to (default: the style reference). fit_silhouette_only: compare
# shapes only (e.g. a back view fitted to the normal form's Showdown back sprite, whose colours
# belong to another form): every solid pixel is one part, on both sides
SIL = bool(cfg.get("fit_silhouette_only"))
ref_px = np.round(load_rgba(cfg_path.parent / cfg.get("fit_reference", cfg.get("reference"))) * 255).astype(int)
ref = np.zeros(ref_px.shape[:2], int)
if SIL:
    ref[ref_px[..., 3] > 0] = 1
for col, k in ({} if SIL else code).items():
    ref[(ref_px[..., 3] > 0) & np.all(ref_px[..., :3] == col, -1)] = k
ys, xs = np.nonzero(ref)
ref = ref[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
RH, RW = ref.shape

# our part map: each pixel's texture colour -> the part of its nearest palette shade, as in
# sprite_style.measure
PAL = np.array([hexrgb(h) for shades in cfg["palette"]["parts"].values() for h in shades], float) / 255
PAL_PART = np.array([i + 1 for i, shades in enumerate(cfg["palette"]["parts"].values()) for _ in shades])


def render(kind):
    g["use_pass"](kind)
    scene.display.render_aa = "OFF"
    path = os.path.join(tmp_dir, f"fit_{kind}.png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return load_rgba(path)


def our_parts():
    g["place_camera"]()
    g["pose_at"](0.0)
    col = render("color")
    solid = col[..., 3] > 0.5
    nearest = np.argmin(((col[..., None, :3] - PAL) ** 2).sum(-1), -1)
    return np.where(solid, PAL_PART[nearest], 0)


def score(ours):
    if SIL:
        ours = (ours > 0).astype(int)
    ys, xs = np.nonzero(ours)
    if len(ys) == 0:
        return 0.0
    crop = ours[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = crop.shape
    nw = max(1, round(w * RH / h))
    small = crop[(np.arange(RH) * h // RH)[:, None], (np.arange(nw) * w // nw)[None, :]]
    W = max(RW, nw) + 12
    A = np.zeros((RH, W), int); A[:, 6:6 + RW] = ref
    best = -9.0
    for dx in range(-6, 7):
        if 6 + dx < 0 or 6 + dx + nw > W:
            continue
        B = np.zeros((RH, W), int); B[:, 6 + dx:6 + dx + nw] = small
        union = (A > 0) | (B > 0)
        good = (A > 0) & (B > 0) & ((A == 9) | (A == B))
        s = good.sum() / union.sum()
        # fit_weights {part: w}: extra score for one part's own overlap (e.g. Glimmora's crown,
        # small next to the petals, so the whole-sprite match barely notices its pose)
        for pname, wgt in cfg.get("fit_weights", {}).items():
            code = PARTS.index(pname) + 1
            pa, pb = A == code, B == code
            s += wgt * (pa & pb).sum() / max(1, (pa | pb).sum())
        best = max(best, s)
    return best


SEARCH = cfg["fit"]
if "--only" in args:                    # fit just these parameters, keep the rest as they are
    SEARCH = {k: v for k, v in SEARCH.items() if k in args[args.index("--only") + 1].split(",")}


def evaluate(params):
    P.update(params)
    return score(our_parts())


def descend(params, budget, steps=None):
    steps = dict(steps or {k: v[0] for k, v in SEARCH.items()})
    best = evaluate(params)
    n = 1
    while max(s / SEARCH[k][0] for k, s in steps.items()) > 0.12 and n < budget:
        improved = False
        for k, (_, lo, hi) in SEARCH.items():
            for sign in (1, -1):
                trial = dict(params)
                trial[k] = round(min(hi, max(lo, params[k] + sign * steps[k])), 3)
                if trial[k] == params[k]:
                    continue
                s = evaluate(trial); n += 1
                if s > best + 1e-4:
                    best, params, improved = s, trial, True
                    break
        if not improved:
            steps = {k: v / 2 for k, v in steps.items()}
    return best, params


start = {k: P[k] for k in SEARCH}
results = [descend(start, 150)]
print(f"FIT current pose -> {results[0][0]:.3f}")
LOCAL = float(args[args.index("--local") + 1]) if "--local" in args else None
for r in range(restarts):
    if LOCAL:
        trial = {k: round(min(hi, max(lo, start[k] + random.uniform(-LOCAL, LOCAL) * st)), 2)
                 for k, (st, lo, hi) in SEARCH.items()}
    else:
        trial = {k: round(random.uniform(lo, hi), 2) for k, (_, lo, hi) in SEARCH.items()}
    results.append(descend(trial, 120))
    print(f"FIT start {r + 1:2d}/{restarts} -> {results[-1][0]:.3f}   best so far {max(x[0] for x in results):.3f}")
best_score, best = max(results, key=lambda x: x[0])
best_score, best = descend(best, 400, {k: v[0] / 2 for k, v in SEARCH.items()})
print(f"FIT final {best_score:.3f}")

cfg = json.loads(cfg_path.read_text())          # re-read: keep any edits made meanwhile
cfg["pose_params_previous"] = cfg["pose_params"]
cfg["pose_params"] = dict(cfg["pose_params"], **{k: round(v, 2) for k, v in best.items()})
cfg.setdefault("log", []).append({"step": "fit_pose", "parts_match": round(best_score, 3), "restarts": restarts})
cfg_path.write_text(json.dumps(cfg, indent=2))
print("FIT", json.dumps(best))
