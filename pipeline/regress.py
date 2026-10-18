"""Regression check: build sprites with the current code and compare them with saved goldens.

Run (from anywhere):
  python3 pipeline/regress.py golden [NAME ...] [--rev GIT_REV]  snapshot the config, render (once) +
                                                       build, save the result as golden
  python3 pipeline/regress.py check [NAME ...]         build again, compare with the golden frame by frame
  python3 pipeline/regress.py render-check [NAME ...]  render again, compare every pass with the cached render
NAME: lapras, glimmora, golisopod, dragalge, dragalge_back (default: all); a sprite with a shiny
(SHINY below) also checks its palette_swap recolour. Data lives in .regress/ (gitignored):
the config snapshots, the rendered passes per sprite and the golden GIFs. Checks always use the
snapshot taken with the golden (paths made absolute), so editing a config - or another session
editing it - doesn't move the target; --rev takes the config as committed at that revision. Builds run with PYTHONHASHSEED fixed, since some
tie-breaks follow Python's per-process hash order. Exit code 1 if anything differs.
"""
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
    "lapras": "lapras-model/Lapras/lapras.json",
    "glimmora": "glimmora-model/glimmora_front.json",
    "golisopod": "golisopod-model/golisopod_front.json",
    "dragalge": "dragalge-model/dragalge_front.json",
    "dragalge_back": "dragalge-model/dragalge_back.json",      # back view + the shiny recolour
}
SHINY = {"dragalge_back": "dragalge-model/dragalge_back_shiny.json"}
SEED = "0"


def frames_dir(name):
    return DATA / "frames" / name


def config(name):
    p = DATA / "configs" / f"{name}.json"
    if not p.exists():
        sys.exit(f"{name}: no config snapshot, run: regress.py golden {name}")
    return p


def snapshot(name, rev=None, rel=None, key=None):
    """the config as it is (or as committed at rev), paths made absolute, saved for the checks"""
    rel = rel or CONFIGS[name]
    live = ROOT / rel
    text = subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:{rel}"], capture_output=True, text=True,
                          check=True).stdout if rev else live.read_text()
    cfg = json.loads(text)
    for k in ("model", "reference", "fit_reference"):
        if cfg.get(k):
            cfg[k] = str((live.parent / cfg[k]).resolve())
    p = DATA / "configs" / f"{key or name}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2))
    if name in SHINY and key is None:
        snapshot(name, rev, SHINY[name], f"{name}_shiny")
    return p


def shiny(name, normal_gif, out_gif):
    """the shiny recolour of a built sprite (palette_swap.py), if the sprite has one"""
    if name not in SHINY:
        return
    r = subprocess.run([sys.executable, str(HERE / "palette_swap.py"), str(config(name)), str(DATA / "configs" / f"{name}_shiny.json"),
                        str(normal_gif), str(out_gif)], env=dict(os.environ, PYTHONHASHSEED=SEED), capture_output=True, text=True)
    if "Traceback" in r.stderr:
        print(r.stderr[-3000:])
        sys.exit(1)


def render(name, out):
    t0 = time.time()
    subprocess.run([sys.executable, str(HERE / "render_parallel.py"), str(config(name)), str(out), "--no-cache"], check=True)
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
    """differences between two builds: frame pixels, eye masks, QA report"""
    A, B = gif_frames(a), gif_frames(b)
    out = []
    if len(A) != len(B):
        out.append(f"{len(A)} vs {len(B)} frames")
    bad = [i for i, (x, y) in enumerate(zip(A, B)) if x.shape != y.shape or (x != y).any()]
    if bad:
        px = sum(int((x != y).any(-1).sum()) for i, (x, y) in enumerate(zip(A, B)) if i in bad and x.shape == y.shape)
        out.append(f"{len(bad)} frames differ ({px} px), first {bad[:6]}")
    for ext in (".eyes.json", ".qa.json"):
        pa, pb = a.with_suffix(ext), b.with_suffix(ext)
        if pa.exists() != pb.exists() or (pa.exists() and json.loads(pa.read_text()) != json.loads(pb.read_text())):
            out.append(f"{ext} differs")
    return out


def main():
    args = sys.argv[1:]
    rev = args[args.index("--rev") + 1] if "--rev" in args else None
    args = [a for i, a in enumerate(args) if a != "--rev" and (i == 0 or args[i - 1] != "--rev")]
    mode = args[0] if args else "check"
    names = args[1:] or list(CONFIGS)
    failed = False
    for name in names:
        golden = DATA / "golden" / f"{name}.gif"
        if mode == "golden":
            snapshot(name, rev)
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
        elif mode == "render-check":
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
