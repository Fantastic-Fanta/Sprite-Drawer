"""python3 build.py [POKEMON ...] [--out DIR]      every models/<pokemon>/*_front.json -> out/<pokemon>/ GIFs
python3 build.py --publish POKEMON ...          out/<pokemon>/ -> sprites/<pokemon>/ (after review)
Per front config: front, back (camera turned 180, from above) and, when the model has *_rare_alb textures,
both shinies (palette recoloured), each with a 4x copy. Optional overrides in the front config:
"back": {...} merged into the derived back, "shiny": {"palette": {...}} instead of the derived palette.
Blender poses each loop (bake.py, BakePool); sprite/ (Rust, GPU) renders it and draws the GIFs."""
import copy
import json
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MODELS, SPRITES, OUT = ROOT / "models", ROOT / "sprites", ROOT / "out"
sys.path.insert(0, str(HERE))
import motion                                   # noqa: E402
from blender import BakePool                    # noqa: E402

CRATE = HERE / "sprite"
SPRITE = CRATE / "target/release/sprite"


def merge(a, b):
    for k, v in b.items():
        a[k] = merge(a.get(k, {}), v) if isinstance(v, dict) and isinstance(a.get(k), dict) else v
    return a


def load(front):
    cfg = json.loads(front.read_text())
    cfg["model"] = str((front.parent / cfg["model"]).resolve())
    return cfg


def back_of(cfg):
    b = copy.deepcopy(cfg)
    pp = b["pose_params"]
    pp["AZIMUTH"] = round((float(pp["AZIMUTH"]) + 180) % 360, 3)
    pp["ELEVATION"] = max(float(pp.get("ELEVATION", 12)), 10)
    return merge(b, copy.deepcopy(cfg.get("back", {})))


# --- shiny palette: per part, the mean linear colour change normal -> *_rare_alb texture moves its albedo;
# its ramp keeps its brightness steps (shifted, compressed below white) and takes the hue change in Lab
hexrgb = lambda h: np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], float)
lin = lambda c: np.where(c / 255 <= 0.04045, c / 255 / 12.92, ((c / 255 + 0.055) / 1.055) ** 2.4)
srgb = lambda l: 255 * np.where(l <= 0.0031308, l * 12.92, 1.055 * np.clip(l, 0, None) ** (1 / 2.4) - 0.055)
luma = lambda c: float(np.dot(np.asarray(c, float), [0.3, 0.59, 0.11]) / 255)


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
        for _ in range(40):                      # lightness for the target brightness
            m = (a + b) / 2
            a, b = (m, b) if luma(unlab(np.array([m, z[i].real, z[i].imag]))) < Yt[i] else (a, m)
        out.append(unlab(np.array([(a + b) / 2, z[i].real, z[i].imag])))
    return ["#%02x%02x%02x" % tuple(c.astype(int)) for c in out]


def shiny_palette(cfg):
    """the shiny palette, or None when the model has no shiny textures"""
    if "shiny" in cfg:
        return cfg["shiny"] and cfg["shiny"]["palette"]
    alb = {k: hexrgb(v) for k, v in cfg["parts"]["albedo"].items()}
    names, groups = list(alb), cfg["parts"].get("materials", {})
    sums, found = {k: [np.zeros(3), np.zeros(3), 0] for k in names}, False
    for normal in sorted(Path(cfg["model"]).parent.glob("*_alb (Composite).png")):
        shiny = normal.with_name(normal.name.replace("_alb (Composite)", "_rare_alb (Composite)"))
        if "_rare_" in normal.name or not shiny.exists():
            continue
        found = True
        a, b = (np.array(Image.open(p).convert("RGBA").resize((256, 256), Image.Resampling.NEAREST)).reshape(-1, 4).astype(float)
                for p in (normal, shiny))
        ok = (a[:, 3] > 127) & (b[:, 3] > 127)
        allowed = names
        for frag, grp in groups.items():
            if frag in normal.name and all(p in alb for p in grp.split("|")):
                allowed = grp.split("|")
        near = np.argmin(((a[:, None, :3] - np.array([alb[k] for k in allowed])[None]) ** 2).sum(-1), -1)
        for j, k in enumerate(allowed):
            m = ok & (near == j)
            sums[k][0] += lin(a[m, :3]).sum(0); sums[k][1] += lin(b[m, :3]).sum(0); sums[k][2] += int(m.sum())
    if not found:
        return None
    pal = copy.deepcopy(cfg["palette"])
    for k in names:
        s_n, s_s, n = sums[k]
        if n >= 50:                              # fewer texture pixels: colours kept
            shiny_alb = np.clip(np.round(srgb(lin(alb[k]) * (s_s / n + 1e-4) / (s_n / n + 1e-4))), 0, 255)
            pal["parts"][k] = keep_steps(cfg["palette"]["parts"][k], alb[k], shiny_alb)
    return pal


def build(names, out=None):
    """build the named Pokemon (models/ folder names); returns the failed steps"""
    subprocess.run(["cargo", "build", "--release", "-q"], cwd=CRATE, check=True)
    jobs = []
    for name in names:
        for front in sorted((MODELS / name).glob("*_front.json")):
            if front.name.startswith("_"):
                continue
            cfg, stem, dest = load(front), front.stem[:-6], Path(out or OUT / name)
            for view, c in (("front", cfg), ("back", back_of(cfg))):
                jobs.append((f"{stem}_{view}", c, shiny_palette(c), dest))
    work, baked, failed, t0 = Path(out or OUT) / "frames", queue.Queue(), [], time.time()
    log = lambda m: print(f"[{time.time() - t0:6.1f}s] {m}", flush=True)

    def baker():
        with BakePool() as pool:                 # one pool for the batch: Blender starts once per worker
            for name, cfg, _, _ in jobs:
                t = time.time()
                try:
                    n = pool.bake(cfg, work / name)
                    log(f"bake {name}: {'done' if n else 'cached'} in {time.time() - t:.1f}s")
                    baked.put(name)
                except RuntimeError as e:
                    log(f"bake {name}: FAILED\n{e}"); failed.append(name); baked.put(None)
        baked.put(False)

    def drawer():                                # GPU + CPU work while the next loop bakes
        for name, cfg, shiny, dest in jobs:
            if (got := baked.get()) is False:
                return
            if got is None:
                continue
            t = time.time()
            dest.mkdir(parents=True, exist_ok=True)
            job = work / name / "job.json"
            job.write_text(json.dumps({"config": cfg, "bake": str(work / name), "shiny": shiny, "out": str(dest / name),
                                       "offsets": motion.offsets(cfg, cfg["motion"]["frames"])}))
            r = subprocess.run([str(SPRITE), str(job)], capture_output=True, text=True)
            if r.returncode:
                log(f"draw {name}: FAILED\n{r.stderr[-3000:]}"); failed.append(name)
            else:
                clipped = json.loads(r.stdout.splitlines()[-1])["clipped"]
                if clipped:
                    failed.append(name)
                log(f"draw {name}: {'CUT OFF at the render edge (widen render.width/height)' if clipped else 'done'}"
                    f" in {time.time() - t:.1f}s")
            shutil.rmtree(work / name, ignore_errors=True)

    threads = [threading.Thread(target=baker), threading.Thread(target=drawer)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    shutil.rmtree(work, ignore_errors=True)
    log(f"{len(jobs)} sprites, {len(failed)} failed")
    return failed


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--publish":
        for name in a[1:]:
            gifs = sorted((OUT / name).glob("*.gif"))
            if not gifs:
                sys.exit(f"{name}: nothing built in out/{name}/")
            (SPRITES / name).mkdir(parents=True, exist_ok=True)
            for g in gifs:
                shutil.copy2(g, SPRITES / name / g.name)
            print(f"{name}: {len(gifs)} GIFs -> sprites/{name}/")
    else:
        out = a.pop(a.index("--out") + 1) if "--out" in a else None
        names = [x for x in a if x != "--out"] or sorted(d.name for d in MODELS.iterdir() if d.is_dir())
        sys.exit(1 if build(names, out) else 0)
