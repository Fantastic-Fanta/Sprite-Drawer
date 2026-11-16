"""Build sprites: python3 pipeline/build.py [POKEMON | CONFIG.json ...] [--out DIR] [--keep-frames]
                     python3 pipeline/build.py --publish POKEMON [POKEMON ...]

Build: every models/<pokemon>/ (no arguments), the named Pokemon (models/ folder names, e.g.
mega-absol-z), or single configs. Each sprite config (*_front.json, *_back.json) is rendered,
built (make_gif.py, quality gate included) with its 4x copy, and recoloured into its shiny when
NAME_shiny.json sits next to it (palette_swap.py). Output: out/<pokemon>/NAME(_shiny)(_4x).gif, or
straight into DIR with --out. The next sprite renders (Blender, mostly GPU) while the previous one
builds (CPU). Prints a line per step; exit code 1 if any step fails (the others still run).

Publish: once the GIFs in out/<pokemon>/ are approved, copy them into sprites/<pokemon>/ as they
are (no rebuild, so what was reviewed is what lands).
"""
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MODELS, SPRITES, OUT = ROOT / "models", ROOT / "sprites", ROOT / "out"
SCALE = "4"
sys.path.insert(0, str(HERE))
from render_parallel import RenderPool      # noqa: E402


def sprite_configs(folder):
    """a model folder's sprite configs: front and back (their shinies are built from them)"""
    return sorted(p for p in folder.glob("*.json") if p.stem.endswith(("_front", "_back")) and not p.name.startswith("_"))


def pokemon_of(cfg):
    return cfg.parent.name if cfg.parent.parent == MODELS else cfg.stem.rsplit("_", 1)[0].replace("_", "-")


def publish(names):
    for name in names:
        src = OUT / name
        gifs = sorted(src.glob("*.gif"))
        if not gifs:
            sys.exit(f"{name}: nothing built in {src.relative_to(ROOT)}/ (build it first)")
        dst = SPRITES / name
        dst.mkdir(parents=True, exist_ok=True)
        for g in gifs:
            shutil.copy2(g, dst / g.name)
        print(f"{name}: {len(gifs)} GIFs -> {dst.relative_to(ROOT)}/")


def main():
    args = sys.argv[1:]
    if "--publish" in args:
        return publish([a for a in args if a != "--publish"])
    keep = "--keep-frames" in args
    flat = Path(args[args.index("--out") + 1]).resolve() if "--out" in args else None
    pos = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] != "--out")]
    configs = []
    for a in pos or sorted(d.name for d in MODELS.iterdir() if d.is_dir()):
        p = Path(a)
        configs += [p.resolve()] if p.suffix == ".json" else sprite_configs(MODELS / a)
    if not configs:
        sys.exit("no sprite configs found")
    dest = lambda cfg: flat or OUT / pokemon_of(cfg)
    work = flat or OUT
    rendered = queue.Queue()
    failed = []
    t0 = time.time()

    def log(msg):
        print(f"[{time.time() - t0:6.1f}s] {msg}", flush=True)

    def run(cmd, what, made=None):
        """run a step; made = the file it writes, so a quality-gate FAIL (exit 1, file written)
        reads as such rather than as a crash"""
        t = time.time()
        r = subprocess.run([sys.executable] + [str(c) for c in cmd], capture_output=True, text=True)
        ok = r.returncode == 0
        qa_fail = not ok and made is not None and made.exists() and "Traceback" not in r.stderr
        log(f"{what}: {'done' if ok else 'QA FAIL' if qa_fail else 'FAILED'} in {time.time() - t:.1f}s")
        if not ok:
            failed.append(what)
            if not qa_fail:
                print((r.stdout + r.stderr)[-1500:], flush=True)
        return ok or qa_fail

    def renderer():
        # one pool for the whole batch: each Blender process starts once, not once per sprite
        with RenderPool() as pool:
            for cfg in configs:
                frames = work / "frames" / cfg.stem
                t = time.time()
                try:
                    n = pool.render(cfg, frames)
                    log(f"render {cfg.stem}: {'done' if n else 'from the cache'} in {time.time() - t:.1f}s")
                    rendered.put((cfg, frames))
                except RuntimeError as e:
                    log(f"render {cfg.stem}: FAILED in {time.time() - t:.1f}s")
                    print(e, flush=True)
                    failed.append(f"render {cfg.stem}")
                    rendered.put((cfg, None))
        rendered.put(None)

    def builder():
        while (item := rendered.get()) is not None:
            cfg, frames = item
            if frames is None:
                continue
            d = dest(cfg)
            d.mkdir(parents=True, exist_ok=True)
            gif = d / f"{cfg.stem}.gif"
            extra = ["--scale", SCALE]
            gif.unlink(missing_ok=True)
            if run([HERE / "make_gif.py", cfg, frames, gif] + extra, f"build {cfg.stem}", gif):
                shiny = cfg.with_name(cfg.stem + "_shiny.json")
                if shiny.exists():
                    sgif = d / f"{shiny.stem}.gif"
                    sgif.unlink(missing_ok=True)
                    run([HERE / "palette_swap.py", cfg, shiny, gif, sgif] + extra, f"shiny {shiny.stem}", sgif)
            if not keep:
                shutil.rmtree(frames, ignore_errors=True)

    threads = [threading.Thread(target=renderer), threading.Thread(target=builder)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    log(f"{len(configs)} sprites, {len(failed)} failed steps")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
