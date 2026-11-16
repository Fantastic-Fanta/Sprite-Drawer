"""python3 make_configs.py models/SLUG/SLUG_front.json
Writes SLUG_back.json (camera turned 180 deg, looking down at least 10 deg) and SLUG_front_shiny.json /
SLUG_back_shiny.json (palette recoloured from the model's *_rare_alb textures). Edit the front config, not these.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

front = Path(sys.argv[1]).resolve()
stem = re.sub(r"_front$", "", front.stem)
cfg = json.loads(front.read_text())
write = lambda name, c: front.with_name(f"{stem}_{name}.json").write_text(json.dumps(c, indent=2) + "\n")

back = json.loads(front.read_text())
pp = back["pose_params"]
pp["AZIMUTH"] = round((float(pp["AZIMUTH"]) + 180) % 360, 3)
pp["ELEVATION"] = max(float(pp.get("ELEVATION", 12)), 10)
back["name"] = cfg["name"] + " (back)"
write("back", back)

# shiny: per part, the mean linear colour change normal -> shiny texture moves the albedo; the
# palette ramp keeps its brightness steps (shifted, compressed below white) and takes the hue change
hexrgb = lambda h: np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], float)
lin = lambda c: np.where(c / 255 <= 0.04045, c / 255 / 12.92, ((c / 255 + 0.055) / 1.055) ** 2.4)
srgb = lambda l: 255 * np.where(l <= 0.0031308, l * 12.92, 1.055 * np.clip(l, 0, None) ** (1 / 2.4) - 0.055)
luma = lambda c: float(np.dot(np.asarray(c, float), [0.3, 0.59, 0.11]) / 255)
alb = {k: hexrgb(v) for k, v in cfg["parts"]["albedo"].items()}
names = list(alb)
groups = cfg["parts"].get("materials", {})
swap, sums = {}, {k: [np.zeros(3), np.zeros(3), 0] for k in names}
for normal in sorted((front.parent / cfg["model"]).parent.glob("*_alb (Composite).png")):
    shiny = normal.with_name(normal.name.replace("_alb (Composite)", "_rare_alb (Composite)"))
    if "_rare_" in normal.name or not shiny.exists():
        continue
    swap[normal.name] = shiny.name
    a, b = (np.array(Image.open(p).convert("RGBA").resize((256, 256), Image.Resampling.NEAREST)).reshape(-1, 4).astype(float)
            for p in (normal, shiny))
    ok = (a[:, 3] > 127) & (b[:, 3] > 127)
    allowed = names
    for frag, grp in groups.items():                 # the texture's material group limits its parts
        if frag in normal.name and all(p in alb for p in grp.split("|")):
            allowed = grp.split("|")
    near = np.argmin(((a[:, None, :3] - np.array([alb[k] for k in allowed])[None]) ** 2).sum(-1), -1)
    for j, k in enumerate(allowed):
        m = ok & (near == j)
        sums[k][0] += lin(a[m, :3]).sum(0); sums[k][1] += lin(b[m, :3]).sum(0); sums[k][2] += int(m.sum())


def lab(c):
    xyz = lin(np.asarray(c, float)) @ np.array([[0.4124, 0.2126, 0.0193], [0.3576, 0.7152, 0.1192], [0.1805, 0.0722, 0.9505]])
    f = lambda t: np.where(t > 216 / 24389, np.cbrt(t), (24389 / 27 * t + 16) / 116)
    fx, fy, fz = f(xyz[..., 0] / 0.9505), f(xyz[..., 1]), f(xyz[..., 2] / 1.089)
    return np.stack([116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)], -1)


def unlab(L):
    fy = (L[..., 0] + 16) / 116; fx = fy + L[..., 1] / 500; fz = fy - L[..., 2] / 200
    g = lambda t: np.where(t ** 3 > 216 / 24389, t ** 3, (116 * t - 16) * 27 / 24389)
    xyz = np.stack([g(fx) * 0.9505, g(fy), g(fz) * 1.089], -1)
    l = xyz @ np.array([[3.2406, -0.9689, 0.0557], [-1.5372, 1.8758, -0.2040], [-0.4986, 0.0415, 1.0570]])
    return np.clip(np.round(srgb(np.clip(l, 0, 1))), 0, 255)


def keep_steps(ramp, alb_n, alb_s, top=0.95):
    rgb = np.array([hexrgb(h) for h in ramp]); L = lab(rgb); an, as_ = lab(alb_n), lab(alb_s)
    Y = np.array([luma(c) for c in rgb])
    Yt = Y + (luma(alb_s) - luma(alb_n))
    if Yt.max() > top:
        span = Y.max() - Y.min()
        lo = max(0.02, min(Yt.min(), top - span))
        Yt = lo + (Y - Y.min()) * (top - lo) / max(span, 1e-6)
    zn, zs = complex(an[1], an[2]), complex(as_[1], as_[2])
    z = L[:, 1] + 1j * L[:, 2]
    z = z * (zs / zn) if abs(zn) > 10 else z + (zs - zn)
    out = []
    for i in range(len(ramp)):
        a, b = 0.0, 100.0
        for _ in range(40):                          # solve lightness for the target brightness
            m = (a + b) / 2
            if luma(unlab(np.array([m, z[i].real, z[i].imag]))) < Yt[i]:
                a = m
            else:
                b = m
        out.append(unlab(np.array([(a + b) / 2, z[i].real, z[i].imag])))
    return ["#%02x%02x%02x" % tuple(c.astype(int)) for c in out]


fs = json.loads(front.read_text())
for k in names:
    s_n, s_s, n = sums[k]
    if n < 50:                                       # too few texture pixels: colours kept
        continue
    shiny_alb = np.clip(np.round(srgb(lin(alb[k]) * (s_s / n + 1e-4) / (s_n / n + 1e-4))), 0, 255)
    fs["palette"]["parts"][k] = keep_steps(cfg["palette"]["parts"][k], alb[k], shiny_alb)
    fs["parts"]["albedo"][k] = "#%02x%02x%02x" % tuple(shiny_alb.astype(int))
fs["render"]["texture_swap"] = swap
fs["name"] = cfg["name"] + " (shiny)"
write("front_shiny", fs)
back["palette"], back["parts"], back["name"] = fs["palette"], fs["parts"], fs["name"] + " (back)"
back["render"]["texture_swap"] = swap
write("back_shiny", back)
print(f"wrote {stem}_back, _front_shiny, _back_shiny")
