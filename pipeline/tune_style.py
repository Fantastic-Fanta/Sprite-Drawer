"""Fit the style numbers in CONFIG.json to the reference frame.

Run:  python3 tune_style.py CONFIG.json FRAME0_DIR [--dry-run]
FRAME0_DIR holds render_sprite.py's passes for frame 0 (render with --test 0).
Updates CONFIG.json "style" in place (old values kept in "style_previous") and appends to "log".

Method (SPRITE_PIPELINE.md, step 3):
  * Shade thresholds are never searched directly. For any light direction and grain, each
    part's thresholds are set to the quantiles of its lighting values that reproduce the
    reference's shade mix for that part (histogram matching). So the palette mix matches
    by construction, and the search only has to decide *where* light and dark fall.
  * Searched by coordinate descent on compare.py's style score: light direction (yaw/pitch),
    rim light level, depth-jump and fold thresholds for inner lines, grain per part, and the
    outline variants (inside/outside, with/without diagonals).
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

import compare
import sprite_style as ss

ss.pin_hash_seed()       # repeatable tie-breaks

args = sys.argv[1:]
cfg_path = Path(args[0])
cfg = json.loads(cfg_path.read_text())
ref = compare.load(cfg_path.parent / cfg["reference"])
passes = ss.load_passes(args[1], only_first=True)
box, size = ss.framing(passes, cfg["style"]["height"])
frame = ss.prepare(cfg, *passes[0], box, size)

# reference shade mix per part (from the palette counts)
ref_mix = compare.score(cfg, ref, ref)["parts"]


def light_vec(yaw, pitch):
    y, p = math.radians(yaw), math.radians(pitch)
    return [math.sin(y) * math.cos(p), math.sin(p), math.cos(y) * math.cos(p)]


def matched_thresholds(style):
    """per part: thresholds on the lighting value that give the reference's shade shares"""
    light = ss.lighting(style, frame)
    out = {}
    for name in cfg["palette"]["parts"]:
        vals = light[frame["solid"] & (frame["part"] == name)]
        first = style["first_shade"].get(name, 0)
        mix = np.array(ref_mix[name]["shades_ref"][first:], float)
        if len(vals) == 0 or mix.sum() == 0:
            out[name] = style["thresholds"][name]
            continue
        cum = np.cumsum(mix / mix.sum())[:-1]
        out[name] = [round(float(q), 4) for q in np.quantile(vals, np.clip(cum, 0, 1))]
    return out


def build(knobs):
    st = dict(cfg["style"])
    st["light"] = light_vec(knobs["yaw"], knobs["pitch"])
    st["rim_light"] = knobs["rim_light"]
    st["depth_jump"] = knobs["depth_jump"]
    st["crease_cos"] = knobs["crease_cos"]
    st["grain"] = {k: knobs[f"grain_{k}"] for k in cfg["palette"]["parts"]}
    st["outline_outside"] = bool(knobs["outline_outside"])
    st["outline_diagonals"] = bool(knobs["outline_diagonals"])
    st["outline_width"] = knobs["outline_width"]
    st["outline_cover"] = knobs["outline_cover"]
    if "cast_strength" in knobs:
        st["cast_shadow"] = dict(cfg["style"].get("cast_shadow", {}), strength=knobs["cast_strength"])
    st["thresholds"] = matched_thresholds(st)
    return st


def evaluate(knobs):
    st = build(knobs)
    res = compare.score(cfg, ref, compare.crop(ss.stylize(cfg, frame, st)))
    # the QA gate's shadow limits are constraints, not trade-offs: a better score can't buy back
    # weak / misplaced shadows (each unit of violation costs 100 points)
    qa = cfg.get("qa", {})
    pen = 0.0
    if "shadow_f1" in qa:
        pen += 100 * max(0, qa["shadow_f1"] - res["shadow_f1"])
    for k in ("blob_shade_err", "dark_rim_excess"):
        if k in qa:
            pen += 100 * max(0, res[k] - qa[k])
    return res["style_score"] - pen, res, st


L0 = np.array(cfg["style"]["light"], float); L0 /= np.linalg.norm(L0)
knobs = {
    "yaw": round(math.degrees(math.atan2(L0[0], L0[2])), 1), "pitch": round(math.degrees(math.asin(L0[1])), 1),
    "rim_light": cfg["style"]["rim_light"], "depth_jump": cfg["style"]["depth_jump"],
    "crease_cos": cfg["style"]["crease_cos"],
    **{f"grain_{k}": cfg["style"]["grain"].get(k, 0.0) for k in cfg["palette"]["parts"]},
    "outline_outside": int(cfg["style"]["outline_outside"]), "outline_diagonals": int(cfg["style"]["outline_diagonals"]),
    "outline_width": cfg["style"].get("outline_width", 1.0), "outline_cover": cfg["style"].get("outline_cover", 0.5),
}
if cfg["render"].get("shadow"):              # cast shadows rendered: how dark they push
    knobs["cast_strength"] = cfg["style"].get("cast_shadow", {}).get("strength", 1.0)
# knob -> (step, low, high)
SEARCH = {"yaw": (20, -180, 180), "pitch": (15, -80, 80), "rim_light": (0.2, -1, 1.2),
          "depth_jump": (2, 2, 30), "crease_cos": (0.2, -0.9, 0.9),
          **{f"grain_{k}": (3, 0, 60) for k in cfg["palette"]["parts"]},
          "outline_outside": (1, 0, 1), "outline_diagonals": (1, 0, 1),
          "outline_width": (0.25, 0, 2), "outline_cover": (0.1, 0.2, 0.8)}
if "cast_strength" in knobs:
    SEARCH["cast_strength"] = (0.5, 0, 3)
# style.tune_fixed: knobs the tuner must not touch (a user rule beats the score, e.g. rim_light
# pinned off for Glimmora: rim darkening put the shadows in a thin band along the outline)
for k in cfg["style"].get("tune_fixed", []):
    SEARCH.pop(k, None)

best, res, st = evaluate(knobs)
print(f"TUNE start {best:.1f}")
steps = {k: v[0] for k, v in SEARCH.items()}
n = 0
while max(steps[k] / SEARCH[k][0] for k in steps) > 0.1 and n < 600:
    improved = False
    for k, (_, lo, hi) in SEARCH.items():
        if steps[k] < (1 if k.startswith("outline") else 0):
            continue
        for sign in (1, -1):
            trial = dict(knobs)
            trial[k] = round(min(hi, max(lo, knobs[k] + sign * steps[k])), 3)
            if k.startswith("outline"):
                trial[k] = int(round(trial[k]))
            if trial[k] == knobs[k]:
                continue
            s, r, t = evaluate(trial); n += 1
            if s > best + 1e-3:
                best, knobs, res, st, improved = s, trial, r, t, True
                print(f"TUNE {n:3d} {best:.1f}  {k}={trial[k]}")
                break
    if not improved:
        steps = {k: (v / 2 if not k.startswith("outline") else 0) for k, v in steps.items()}

compare.report(res)
print("TUNE knobs", json.dumps(knobs))
if "--dry-run" not in args:
    cfg = json.loads(cfg_path.read_text())
    cfg["style_previous"] = cfg["style"]
    cfg["style"] = {k: v for k, v in st.items()}
    cfg["style"]["light"] = [round(v, 4) for v in st["light"]]
    cfg.setdefault("log", []).append({"step": "tune_style", "style_score": res["style_score"]})
    cfg_path.write_text(json.dumps(cfg, indent=2))
    print(f"updated {cfg_path}")
