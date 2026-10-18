"""Turn render_sprite.py output into a Showdown-style pixel sprite GIF, then check it.

Run:  python3 make_gif.py CONFIG.json FRAMES_DIR out.gif [--scale 4] [--first-only out.png] [--auto] [--no-qa]

After building, every quality check runs (qa.py: frame-0 match and line placement against
Showdown, 1-px lines, blinks, visible flicker / pops over the loop) against the limits in the
config's "qa" section, and a PASS / FAIL report is printed and saved as out.qa.json.
--auto: first fit each qa.region_parts part's shade thresholds to Showdown's area colour mix
(saved back to the config); then, if a check still fails, try the config's qa.remedies (style
changes) one after another and keep the build that fails the fewest checks (ties: smallest pop).
Exit code 1 if the final build fails.
--scale N also writes out_Nx.gif, enlarged with hard pixel edges.
--first-only writes just frame 0 as a PNG (for compare.py / quick checks), no QA.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import sprite_style as ss

args = sys.argv[1:]
cfg_path = Path(args[0])
cfg = json.loads(cfg_path.read_text())
frames_dir, out_path = args[1], args[2]
first_only = args[args.index("--first-only") + 1] if "--first-only" in args else None

passes = ss.load_passes(frames_dir, only_first=bool(first_only))
# the model must fit inside the render: a frame touching the render's edge is cut off (a wing
# ending in a straight edge) - a hard failure, fixed by a wider render (render.width / height
# with the FOV widened to match), never by the sprite steps
_clipped = []
for _k, (_color, *_) in enumerate(passes):
    _a = np.array(_color.getchannel("A")) > 8
    if _a[0].any() or _a[-1].any() or _a[:, 0].any() or _a[:, -1].any():
        _clipped.append(_k)
if _clipped:
    print(f"  FAIL  render_clipped   {len(_clipped)} frames touch the render edge (first: {_clipped[:5]})")
# pixel grid: style.frame_anchor "first" = frame 0's own grid (the one tune_style / fit_pose / compare
# see), grown by whole sprite px to fit the loop - so changing the motion can't resample frame 0;
# otherwise with fast_frames, the slow frames' grid; otherwise the whole loop's box
_fast = {i for a, b in cfg["style"].get("fast_frames", []) for i in range(a, b + 1)}
_anchor = None
if not first_only and cfg["style"].get("frame_anchor") == "first":
    _anchor = [0]
elif not first_only and _fast:
    _anchor = [i for i in range(len(passes)) if i not in _fast]
box, size = ss.framing(passes, cfg["style"]["height"], anchor=_anchor)


def build(style_cfg, path):
    frames = [ss.prepare(style_cfg, *p, box, size) for p in passes]
    sprites = ss.stylize_loop(style_cfg, frames)   # stabilised over time
    ss.save_gif(style_cfg, sprites, path)
    if ss.LAST_EYE_MASKS is not None:              # where the eye stamp is, so checks can skip it
        Path(path).with_suffix(".eyes.json").write_text(json.dumps(
            [np.argwhere(m).tolist() for m in ss.LAST_EYE_MASKS]))
    return sprites


if first_only:
    f = ss.prepare(cfg, *passes[0], box, size)
    Image.fromarray(ss.stylize(cfg, f)).save(first_only)
    print(f"wrote {first_only}")
    sys.exit(0)

def fit_region_shades(cfg):
    """--auto: for each part in qa.region_parts, fit that part's shade thresholds so its area's
    colour mix (lines, shades, highlights included) matches Showdown's - on frame 0 only, so
    it's quick. Coordinate descent on the thresholds; returns the updated config."""
    import compare
    ref = compare.load(cfg_path.parent / cfg["reference"])
    f0 = ss.prepare(cfg, *passes[0], box, size)
    for part in cfg.get("qa", {}).get("region_parts", []):
        qa_lim = cfg.get("qa", {})
        def err(c):
            ours = compare.crop(ss.stylize(c, f0))
            mr, _ = compare.part_region_mix(c, ref, part)
            mo, _ = compare.part_region_mix(c, ours, part)
            e = sum(abs(mr.get(k, 0) - mo.get(k, 0)) for k in set(mr) | set(mo))
            # the gate's shadow limits are constraints here too (as in tune_style.py): fitting one
            # part's colour mix must not push where its shadows fall over a limit
            if any(k in qa_lim for k in ("shadow_f1", "blob_shade_err", "dark_rim_excess")):
                r = compare.score(c, ref, ours)
                e += 100 * max(0, qa_lim.get("shadow_f1", 0) - r["shadow_f1"])
                e += 100 * max(0, r["blob_shade_err"] - qa_lim.get("blob_shade_err", 9))
                e += 100 * max(0, r["dark_rim_excess"] - qa_lim.get("dark_rim_excess", 9))
            return e
        best = err(cfg); step = 0.08
        while step > 0.005:
            improved = False
            for i in range(len(cfg["style"]["thresholds"][part])):
                for sgn in (1, -1):
                    trial = json.loads(json.dumps(cfg))
                    trial["style"]["thresholds"][part][i] = round(trial["style"]["thresholds"][part][i] + sgn * step, 4)
                    e = err(trial)
                    if e < best - 1e-4:
                        best, cfg, improved = e, trial, True
            if not improved:
                step /= 2
        print(f"fitted {part} shade thresholds to Showdown's {part} area: mix L1 {best:.3f} -> {cfg['style']['thresholds'][part]}")
    return cfg


if "--auto" in args and cfg.get("qa", {}).get("region_parts") and cfg.get("reference"):
    cfg = fit_region_shades(cfg)
    cfg_path.write_text(json.dumps(cfg, indent=2))      # keep the fitted thresholds

sprites = build(cfg, out_path)
h, w = sprites[0].shape[:2]
print(f"wrote {out_path}: {len(sprites)} frames, {w}x{h}")

ok = True
if "--no-qa" not in args and cfg.get("qa"):
    import qa
    values, results = qa.run(cfg_path, out_path)
    ok = qa.report(results)
    if not ok and "--auto" in args:
        def rank(res, vals):
            return (sum(not r[4] for r in res), vals.get("pop_max", 0))
        best = (rank(results, values), cfg, values, results)
        for k, remedy in enumerate(cfg["qa"].get("remedies", [])):
            trial = json.loads(json.dumps(cfg))
            trial["style"].update(remedy)
            tmp_cfg = cfg_path.with_name(f".qa_trial_{k}.json")
            tmp_gif = str(Path(out_path).with_name(f".qa_trial_{k}.gif"))
            tmp_cfg.write_text(json.dumps(trial))
            build(trial, tmp_gif)
            v, r = qa.run(tmp_cfg, tmp_gif)
            print(f"--- remedy {k + 1}: {json.dumps(remedy)}")
            qa.report(r)
            if rank(r, v) < best[0]:
                best = (rank(r, v), trial, v, r)
            tmp_cfg.unlink(missing_ok=True)
            Path(tmp_gif).unlink(missing_ok=True)
            if not rank(r, v)[0]:
                break
        if best[1] is not cfg:
            cfg = best[1]
            sprites = build(cfg, out_path)
            cfg_path.write_text(json.dumps(cfg, indent=2))   # keep the winning remedy in the config
            print("kept the best remedy; style changes:",
                  {k: v for k, v in cfg["style"].items() if json.loads(cfg_path.read_text())["style"].get(k) != v})
        values, results = best[2], best[3]
        ok = qa.report(results)
    if _clipped:
        ok = False
        values["render_clipped"] = len(_clipped)
        results.append(("render_clipped", len(_clipped), 0, "max", False))
        print("QA: FAIL (render_clipped)")
    Path(out_path).with_suffix(".qa.json").write_text(json.dumps(
        {"values": values, "pass": bool(ok),
         "checks": [{"name": n, "value": v, "limit": l, "pass": bool(p)} for n, v, l, _, p in results]}, indent=2))

if "--scale" in args:
    k = int(args[args.index("--scale") + 1])
    big = [Image.fromarray(s).resize((s.shape[1] * k, s.shape[0] * k), Image.Resampling.NEAREST) for s in sprites]
    big_path = str(Path(out_path).with_name(Path(out_path).stem + f"_{k}x.gif"))
    ss.save_gif(cfg, [np.array(b) for b in big], big_path)
    print(f"wrote {big_path}")
sys.exit(0 if ok else 1)
