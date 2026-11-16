"""Pixel regression: python3 regress.py [check | render | golden] [NAME ...]
check (default, pre-push hook): rebuild GIFs from the saved renders, compare with the goldens.
render: re-render every pass, compare with the saved renders. golden: save the current result.
Exit code 1 if anything differs. Data in .regress/ (gitignored)."""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageSequence

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / ".regress"
CONFIGS = {
    "glimmora": "models/mega-glimmora/mega_glimmora_front.json",
    "golisopod": "models/mega-golisopod/mega_golisopod_front.json",
    "dragalge_back": "models/mega-dragalge/mega_dragalge_back.json",      # back view + shiny recolour
    "zygarde": "models/mega-zygarde/mega_zygarde_front.json",
}
SHINY = {"dragalge_back": "models/mega-dragalge/mega_dragalge_back_shiny.json"}
SEED = "0"


def frames_dir(name):
    return DATA / "frames" / name


def config(name):
    p = DATA / "configs" / f"{name}.json"
    if not p.exists():
        sys.exit(f"{name}: no config snapshot, run: regress.py golden {name}")
    return p


def snapshot(name, rel=None, key=None):
    """the config as it is now, model path made absolute, saved so later config edits don't move the target"""
    live = ROOT / (rel or CONFIGS[name])
    cfg = json.loads(live.read_text())
    cfg["model"] = str((live.parent / cfg["model"]).resolve())
    p = DATA / "configs" / f"{key or name}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2))
    if name in SHINY and key is None:
        snapshot(name, SHINY[name], f"{name}_shiny")
    return p


def shiny(name, normal_gif, out_gif):
    """the shiny recolour of a built sprite (make_gif.py --shiny), if the sprite has one"""
    if name not in SHINY:
        return
    r = subprocess.run([sys.executable, str(HERE / "make_gif.py"), "--shiny", str(config(name)), str(DATA / "configs" / f"{name}_shiny.json"),
                        str(normal_gif), str(out_gif)], env=dict(os.environ, PYTHONHASHSEED=SEED), capture_output=True, text=True)
    if "Traceback" in r.stderr:
        print(r.stderr[-3000:])
        sys.exit(1)


def render(name, out):
    t0 = time.time()
    subprocess.run([sys.executable, str(HERE / "blender.py"), "render", str(config(name)), str(out), "--no-cache"], check=True)
    return time.time() - t0


def build(name, out_gif):
    out_gif.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    r = subprocess.run([sys.executable, str(HERE / "make_gif.py"), str(config(name)), str(frames_dir(name)), str(out_gif)],
                       env=dict(os.environ, PYTHONHASHSEED=SEED), capture_output=True, text=True)
    if "Traceback" in r.stderr:
        print(r.stderr[-3000:])
        sys.exit(1)
    return time.time() - t0


def gif_frames(p):
    return [np.array(f.convert("RGBA")) for f in ImageSequence.Iterator(Image.open(p))]


def compare_build(a, b):
    """differences between two builds: frame pixels"""
    A, B = gif_frames(a), gif_frames(b)
    out = []
    if len(A) != len(B):
        out.append(f"{len(A)} vs {len(B)} frames")
    bad = [i for i, (x, y) in enumerate(zip(A, B)) if x.shape != y.shape or (x != y).any()]
    if bad:
        px = sum(int((x != y).any(-1).sum()) for i, (x, y) in enumerate(zip(A, B)) if i in bad and x.shape == y.shape)
        out.append(f"{len(bad)} frames differ ({px} px), first {bad[:6]}")
    return out


def main():
    args = sys.argv[1:]
    mode = args[0] if args else "check"
    names = args[1:] or list(CONFIGS)
    failed = False
    for name in names:
        golden = DATA / "golden" / f"{name}.gif"
        if mode == "golden":
            snapshot(name)
            if not frames_dir(name).exists():
                print(f"{name}: rendered in {render(name, frames_dir(name)):.1f}s")
            print(f"{name}: golden built in {build(name, golden):.1f}s")
            shiny(name, golden, golden.with_name(f"{name}_shiny.gif"))
        elif mode == "check":
            new = DATA / "check" / f"{name}.gif"
            t = build(name, new)
            diff = compare_build(golden, new)
            if name in SHINY:
                shiny(name, new, new.with_name(f"{name}_shiny.gif"))
                diff += [f"shiny: {d}" for d in compare_build(golden.with_name(f"{name}_shiny.gif"), new.with_name(f"{name}_shiny.gif"))]
            failed |= bool(diff)
            print(f"{name}: built in {t:.1f}s  {'IDENTICAL' if not diff else 'DIFFERS: ' + '; '.join(diff)}")
        elif mode == "render":
            new = DATA / "render_check" / name
            shutil.rmtree(new, ignore_errors=True)
            t = render(name, new)
            diffs = []
            made = {q.stem: q for q in new.iterdir() if q.suffix in (".png", ".tga")}   # either format
            for p in sorted(q for q in frames_dir(name).iterdir() if q.suffix in (".png", ".tga")):
                q = made.get(p.stem)
                if q is None:
                    diffs.append(f"{p.name} missing"); continue
                a, b = np.array(Image.open(p).convert("RGBA")), np.array(Image.open(q).convert("RGBA"))
                if a.shape != b.shape or (a != b).any():
                    diffs.append(f"{p.name}: {int((a != b).any(-1).sum()) if a.shape == b.shape else 'shape'} px")
            failed |= bool(diffs)
            print(f"{name}: rendered in {t:.1f}s  {'IDENTICAL passes' if not diffs else f'{len(diffs)} passes differ, e.g. ' + '; '.join(diffs[:4])}")
        else:
            sys.exit(__doc__)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
