"""Render resolution vs sprite quality: build sprites with the render scaled down and report
render time, QA, the score against Showdown (configs with a reference) and how much of each
frame changes compared with the full-resolution build.

Run:  python3 pipeline/res_study.py OUT_DIR SCALE[,SCALE...] CONFIG.json [CONFIG.json ...]
SCALE 1 = the config as it is; 0.5 = half the render width and height (same camera framing;
Freestyle stroke thickness scaled along, so lines keep their width relative to the model).
Writes OUT_DIR/res_study.json; the configs themselves are never changed.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from regress import gif_frames          # noqa: E402
from render_parallel import RenderPool  # noqa: E402


def variant(cfg_path, scale):
    """a copy of the config with the render scaled, next to the original (relative paths hold)"""
    cfg = json.loads(cfg_path.read_text())
    r = cfg["render"]
    r["width"], r["height"] = round(r["width"] * scale), round(r["height"] * scale)
    if r.get("freestyle"):
        r["freestyle"]["thickness"] = r["freestyle"].get("thickness", 3.0) * scale
    p = cfg_path.with_name(f"_res{scale}_{cfg_path.name}")
    p.write_text(json.dumps(cfg, indent=2))
    return p


def main():
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    scales = [float(s) for s in sys.argv[2].split(",")]
    results = []
    with RenderPool() as pool:
        for cfg_path in [Path(c).resolve() for c in sys.argv[3:]]:
            full = None
            for scale in scales:
                p = variant(cfg_path, scale) if scale != 1 else cfg_path
                try:
                    tag = f"{cfg_path.stem}_{scale}"
                    frames = out / "frames" / tag
                    t = time.time(); pool.render(p, frames); t_render = time.time() - t
                    gif = out / f"{tag}.gif"
                    t = time.time()
                    subprocess.run([sys.executable, str(HERE / "make_gif.py"), str(p), str(frames), str(gif)],
                                   capture_output=True, text=True, env=dict(os.environ, PYTHONHASHSEED="0"))
                    t_build = time.time() - t
                    qa = json.loads(gif.with_suffix(".qa.json").read_text())
                    row = {"config": cfg_path.stem, "scale": scale, "render_s": round(t_render, 1), "build_s": round(t_build, 1),
                           "qa_pass": qa.get("pass"), "qa": qa.get("values")}
                    cmp_json = out / f"{tag}.compare.json"
                    if json.loads(cfg_path.read_text()).get("reference"):
                        subprocess.run([sys.executable, str(HERE / "compare.py"), str(p), str(gif), "--json", str(cmp_json)],
                                       capture_output=True, text=True, env=dict(os.environ, PYTHONHASHSEED="0"))
                        if cmp_json.exists():
                            row["compare_score"] = json.loads(cmp_json.read_text()).get("score")
                    fr = gif_frames(gif)
                    if scale == scales[0]:
                        full = fr
                    if full is not None:
                        same = [a.shape == b.shape for a, b in zip(full, fr)]
                        if all(same):
                            row["px_changed_pct"] = round(100 * np.mean([(a != b).any(-1).mean() for a, b in zip(full, fr)]), 2)
                        row["size"] = list(fr[0].shape[:2])
                    results.append(row)
                    print(json.dumps({k: v for k, v in row.items() if k != "qa"}), flush=True)
                finally:
                    if p != cfg_path:
                        p.unlink(missing_ok=True)
    (out / "res_study.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
