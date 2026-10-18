"""Shade shares fitted to a brightness mix, for sprites with no reference to match.

Run:  python3 match_tones.py CONFIG.json FRAME0_DIR
Uses qa.tone_ref.bands (the share of pixels in each luma band of the same Pokemon's Showdown
sprite - for a Mega with none, the base form's, same view). Two knobs: which shade most of each
part sits in (mu, 0 = darkest) and how widely the rest spread around it (s): target shares
w_k ~ exp(-(k - mu)^2 / 2 s^2). (A back sprite in Showdown sits mostly in one middle shade - lit
from the front - which a plain dark-to-light lean can't express.) For each pair, match_shares.py
sets the thresholds and frame 0 is drawn; the pair whose brightness mix is closest (L1) to the
reference is kept: style.target_shares_default and the thresholds are written to the config.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

import check_loop

cfg_path, frames = Path(sys.argv[1]), sys.argv[2]
cfg = json.loads(cfg_path.read_text())
ref = np.array(cfg["qa"]["tone_ref"]["bands"], float)
n_sh = max(len(v) for v in cfg["palette"]["parts"].values())
tmp = Path(tempfile.mkdtemp())


def shares(t):
    mu, s = t
    w = np.exp(-(np.arange(n_sh) - mu) ** 2 / (2 * s * s))
    return [round(float(v), 3) for v in w / w.sum()]


def trial(t):
    c = json.loads(json.dumps(cfg))
    c["style"]["target_shares_default"] = shares(t)
    p = cfg_path.with_name(f".tones_{t[0]:.1f}_{t[1]:.1f}.json")
    p.write_text(json.dumps(c))
    subprocess.run([sys.executable, "match_shares.py", str(p), frames], capture_output=True)
    png = tmp / f"{t[0]:.1f}_{t[1]:.1f}.png"
    subprocess.run([sys.executable, "make_gif.py", str(p), frames, str(png), "--first-only", str(png)], capture_output=True)
    fitted = json.loads(p.read_text())
    p.unlink()
    a = np.array(Image.open(png).convert("RGBA"))
    return float(np.abs(check_loop.tone_bands([a]) - ref).sum()), fitted


from concurrent.futures import ThreadPoolExecutor
grid = [(mu, s) for mu in np.arange(0, n_sh - 0.99, 0.5) for s in (0.6, 1.0, 1.6)]
with ThreadPoolExecutor(3) as ex:
    res = list(ex.map(trial, grid))
best = None
for t, (err, fitted) in zip(grid, res):
    print(f"mu {t[0]:.1f} s {t[1]:.1f}  shares {shares(t)}  tone L1 {err:.3f}", flush=True)
    if best is None or err < best[0]:
        best = (err, t, fitted)
err, t, fitted = best
cfg["style"]["target_shares_default"] = fitted["style"]["target_shares_default"]
cfg["style"]["thresholds"] = fitted["style"]["thresholds"]
cfg.setdefault("log", []).append({"step": "match_tones", "mu": float(t[0]), "s": float(t[1]), "tone_l1_frame0": round(err, 3)})
cfg_path.write_text(json.dumps(cfg, indent=2))
print(f"kept mu {t[0]:.1f} s {t[1]:.1f}: shares {shares(t)}, tone L1 {err:.3f} (frame 0)")
