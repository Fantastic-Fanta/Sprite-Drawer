"""Make the shiny config from a normal one: same geometry, motion and shading, shiny colours.

Run:  python3 -I make_shiny.py CONFIG.json SHINY.json [--keep-steps]
--keep-steps (use with palette_swap.py): instead of scaling every shade by the light ratio (which
stretches or clips a ramp that gets much brighter), keep the normal ramp's lightness steps.
The shiny textures ("..._rare_alb ...") share the normal textures' UV layout, so each texture
pixel can be compared directly: every pixel is assigned to a part (nearest albedo, limited by
the material groups as in prepare()), and per part the mean colour change normal -> shiny is
measured in linear light. Each palette shade of that part is moved by the same change, so the
shade ramp (and every shading / line decision) stays exactly as tuned; only colours change.
The outline stays (Showdown's shinies keep it). Writes render.texture_swap and parts.albedo.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

cfg_path, out_path = Path(sys.argv[1]), Path(sys.argv[2])
cfg = json.loads(cfg_path.read_text())
model_dir = (cfg_path.parent / cfg["model"]).parent
hexrgb = lambda h: np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], float)
lin = lambda c: np.where(c / 255 <= 0.04045, c / 255 / 12.92, ((c / 255 + 0.055) / 1.055) ** 2.4)
srgb = lambda l: 255 * np.where(l <= 0.0031308, l * 12.92, 1.055 * np.clip(l, 0, None) ** (1 / 2.4) - 0.055)
alb = {k: hexrgb(v) for k, v in cfg["parts"]["albedo"].items()}
names = list(alb)
groups = cfg["parts"].get("materials", {})
swap, sums = {}, {k: [np.zeros(3), np.zeros(3), 0] for k in names}
for normal in sorted(model_dir.glob("*_alb (Composite).png")):
    if "_rare_" in normal.name:
        continue
    shiny = normal.with_name(normal.name.replace("_alb (Composite)", "_rare_alb (Composite)"))
    if not shiny.exists():
        continue
    swap[normal.name] = shiny.name
    a = np.array(Image.open(normal).convert("RGBA").resize((256, 256), Image.Resampling.NEAREST)).reshape(-1, 4).astype(float)
    b = np.array(Image.open(shiny).convert("RGBA").resize((256, 256), Image.Resampling.NEAREST)).reshape(-1, 4).astype(float)
    ok = (a[:, 3] > 127) & (b[:, 3] > 127)
    allowed = names
    for frag, grp in groups.items():                 # material group of this texture, if any
        if frag in normal.name and all(p in alb for p in grp.split("|")):
            allowed = grp.split("|")                  # (a one-part group too: all its texels are that part)
    cols = np.array([alb[k] for k in allowed])
    near = np.argmin(((a[:, None, :3] - cols[None]) ** 2).sum(-1), -1)
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


def luma(c):          # the brightness flicker_map / QA measure steps in (Rec.601 on sRGB values)
    return float(np.dot(np.asarray(c, float), [0.3, 0.59, 0.11]) / 255)


def keep_steps(ramp, alb_n, alb_s, top=0.95):
    """--keep-steps: the shiny ramp keeps the normal ramp's brightness steps (Showdown shinies
    are recolours of the same sprite, so a shade step looks - and measures - the same size).
    Brightness is shifted by the albedo's change, compressed (never clipped) to stay below white;
    hue/chroma move by the albedo's change in Lab: rotated + scaled when the part is coloured,
    shifted when it is near grey. Each shade's Lab lightness is then solved to hit its brightness."""
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
        for _ in range(40):                          # brightness rises with lightness at fixed chroma
            m = (a + b) / 2
            if luma(unlab(np.array([m, z[i].real, z[i].imag]))) < Yt[i]:
                a = m
            else:
                b = m
        out.append(unlab(np.array([(a + b) / 2, z[i].real, z[i].imag])))
    return ["#%02x%02x%02x" % tuple(c.astype(int)) for c in out]


KEEP_STEPS = "--keep-steps" in sys.argv
shiny_cfg = json.loads(json.dumps(cfg))
report = {}
for k in names:
    s_n, s_s, n = sums[k]
    if n < 50:
        report[k] = "too few texture pixels: colours kept"; continue
    ratio = (s_s / n + 1e-4) / (s_n / n + 1e-4)
    shiny_alb = np.clip(np.round(srgb(lin(alb[k]) * ratio)), 0, 255)
    # a part's inner-line colour (palette.lines[part]) moves with the part, as the darkest step
    line = [cfg["palette"]["lines"][k]] if k in cfg["palette"].get("lines", {}) else []
    if KEEP_STEPS:
        ramp = keep_steps(line + cfg["palette"]["parts"][k], alb[k], shiny_alb)
    else:
        ramp = ["#%02x%02x%02x" % tuple(np.clip(np.round(srgb(lin(hexrgb(h)) * ratio)), 0, 255).astype(int))
                for h in line + cfg["palette"]["parts"][k]]
    if line:
        shiny_cfg["palette"]["lines"][k] = ramp[0]
    shiny_cfg["palette"]["parts"][k] = ramp[len(line):]
    shiny_cfg["parts"]["albedo"][k] = "#%02x%02x%02x" % tuple(shiny_alb.astype(int))
    report[k] = {"texture_px": n, "linear_ratio": [round(float(v), 3) for v in ratio], "palette": shiny_cfg["palette"]["parts"][k]}
shiny_cfg["render"]["texture_swap"] = swap
q = shiny_cfg.get("qa", {})
# brightness mix: checked on the normal sprite only. The shiny is an exact recolour of it with the
# brightness steps kept (palette_swap.py); its overall brightness comes from the game's shiny
# textures, not from shading choices (Showdown's own back / back-shiny Golisopod differ by 0.96)
for k in ("tone_mix_l1", "tone_ref", "tone_ref_shiny"):
    q.pop(k, None)
# limits measured on Showdown's own shiny of the same animation, where there is one (qa_shiny)
q.update(q.pop("qa_shiny", {}))
shiny_cfg["name"] = cfg["name"] + " (shiny)"
shiny_cfg["shiny_note"] = ("shiny: colours from the model's shiny textures (make_shiny.py: per-part colour change normal -> shiny, "
                           "applied to every shade); geometry, motion, lighting and shading decisions identical to " + cfg_path.name)
out_path.write_text(json.dumps(shiny_cfg, indent=2))
print(json.dumps(report, indent=1))
