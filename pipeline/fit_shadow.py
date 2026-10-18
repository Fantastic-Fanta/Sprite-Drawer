"""Fit the cast-shadow sun (config render.shadow.light_cam) and its strength to the reference.

Run:  python3 fit_shadow.py CONFIG.json FRAME0_DIR TMP_DIR [--strengths 0.5,1,2] [--mode cast|unlit]
  mode cast: only pixels facing the sun but blocked; unlit: everything the sun doesn't reach
FRAME0_DIR holds render_sprite.py's passes for frame 0 (render with --test 0).
Renders frame 0's shadow pass for a grid of sun directions (render_sprite.py --shadow-dirs, one
Blender run), then for each direction and strength: shade thresholds matched to the reference's
shade mix (as tune_style.py does), stylize, and score with compare.py. Picks the best by
shadow placement (shadow_f1) without losing style score, and writes render.shadow.light_cam and
style.cast_shadow.strength to the config.
"""
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import compare
import sprite_style as ss

ss.pin_hash_seed()       # repeatable tie-breaks

args = sys.argv[1:]
cfg_path, frame_dir, tmp = Path(args[0]), Path(args[1]), Path(args[2])
MODE = args[args.index("--mode") + 1] if "--mode" in args else "cast"   # cast | unlit
strengths = [float(v) for v in args[args.index("--strengths") + 1].split(",")] if "--strengths" in args else [0.5, 1.0, 2.0]
cfg = json.loads(cfg_path.read_text())
here = Path(__file__).parent
ref = compare.load(cfg_path.parent / cfg["reference"])
hist_ref = compare.histogram(ref)

# candidate directions toward the light, camera space (x right, y up, z toward viewer)
dirs = [(0.0, 0.0, 1.0)]
for tilt in (25, 50, 75, 100, 125):          # > 90: from behind (rim / back light)
    for az in range(0, 360, 30):
        t, a = math.radians(tilt), math.radians(az)
        dirs.append((round(math.sin(t) * math.cos(a), 3), round(math.sin(t) * math.sin(a), 3), round(math.cos(t), 3)))
if "--dirs" in args:                            # explicit candidates, e.g. a finer search near a best one
    dirs = [dirs[0]] + [tuple(float(v) for v in d.split(",")) for d in args[args.index("--dirs") + 1].split(";")]
tmp.mkdir(parents=True, exist_ok=True)
subprocess.run(["/Applications/Blender.app/Contents/MacOS/Blender", "-b", str(cfg_path.parent / cfg["model"]),
                "--python", str(here / "render_sprite.py"), "--", str(cfg_path), str(tmp),
                "--shadow-dirs", ";".join(",".join(str(v) for v in d) for d in dirs)], capture_output=True, check=True)

passes = ss.load_passes(frame_dir, only_first=True)
color, idp, data, rest, lines, _ = passes[0]
box, size = ss.framing(passes, cfg["style"]["height"])


def matched(style, f):
    out = {}
    light = ss.lighting(style, f)
    for name, shades in cfg["palette"]["parts"].items():
        vals = light[f["solid"] & (f["part"] == name)]
        first = style["first_shade"].get(name, 0)
        mix = np.array([hist_ref.get(s, 0) for s in shades][first:], float)
        if len(vals) == 0 or mix.sum() == 0:
            out[name] = style["thresholds"][name]; continue
        cum = np.cumsum(mix / mix.sum())[:-1]
        out[name] = [round(float(q), 4) for q in np.quantile(vals, np.clip(cum, 0, 1))]
    return out


def run(d, s, shadow_im):
    c = json.loads(json.dumps(cfg))
    c["render"]["shadow"] = {"light_cam": list(d)}
    st = dict(c["style"], cast_shadow=dict(c["style"].get("cast_shadow", {}), strength=s, mode=MODE))
    c["style"] = st
    f = ss.prepare(c, color, idp, data, rest, lines, shadow_im, box, size)
    st["thresholds"] = matched(st, f)
    c["style"] = st
    r = compare.score(c, ref, compare.crop(ss.stylize(c, f)))
    return r, st


base, _ = run(dirs[0], 0.0, None)
print(f"no cast shadow: style {base['style_score']}  shadow F1 {base['shadow_f1']}  rim excess {base['dark_rim_excess']}  piece err {base['blob_shade_err']}")
results = []
for k, d in enumerate(dirs):
    sim = Image.open(tmp / f"shadowdir{k:03d}.png").convert("RGBA")
    for s in strengths:
        r, st = run(d, s, sim)
        results.append((r["shadow_f1"], r["style_score"], r["dark_rim_excess"], d, s, st["thresholds"], r["blob_shade_err"]))
        print(f"dir {d} strength {s}: style {r['style_score']}  shadow F1 {r['shadow_f1']}  rim excess {r['dark_rim_excess']:+.3f}  piece err {r['blob_shade_err']}", flush=True)
ok = [x for x in results if x[1] >= base["style_score"] - 1.0] or results
# best: pieces as dark / light as Showdown's, then dark placement, then style
best = min(ok, key=lambda x: (round(x[6], 2), -x[0], -x[1]))
print(f"BEST dir {best[3]} strength {best[4]}: shadow F1 {best[0]} style {best[1]} rim excess {best[2]:+.3f} piece err {best[6]}")
cfg = json.loads(cfg_path.read_text())
cfg["render"]["shadow"] = {"light_cam": list(best[3]),
                           "note": "fitted by fit_shadow.py: sun direction (camera space) for cast shadows"}
cfg["style"]["cast_shadow"] = dict(cfg["style"].get("cast_shadow", {}), strength=best[4], mode=MODE)
cfg["style"]["thresholds"] = best[5]
cfg.setdefault("log", []).append({"step": "fit_shadow", "light_cam": list(best[3]), "strength": best[4],
                                  "shadow_f1": best[0], "style_score": best[1], "blob_shade_err": best[6],
                                  "before": {"shadow_f1": base["shadow_f1"], "style_score": base["style_score"], "blob_shade_err": base["blob_shade_err"]}})
cfg_path.write_text(json.dumps(cfg, indent=2))
