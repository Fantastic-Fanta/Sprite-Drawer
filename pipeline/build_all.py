"""Build many sprites, keeping the machine busy: the next sprite renders (Blender, mostly GPU)
while the previous one builds (make_gif, CPU), instead of one after the other.

Run:  python3 pipeline/build_all.py OUT_DIR CONFIG.json [CONFIG.json ...] [--scale 4] [--keep-frames]
Each CONFIG is a normal sprite: it is rendered to OUT_DIR/frames/NAME, built to OUT_DIR/NAME.gif
(make_gif.py, quality gate included), and if NAME_shiny.json sits next to it, recoloured to
OUT_DIR/NAME_shiny.gif (palette_swap.py). Frames are deleted after their build unless
--keep-frames. Prints a line per step; exit code 1 if any step fails (the others still run).
"""
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from render_parallel import RenderPool      # noqa: E402


def main():
    args = sys.argv[1:]
    scale = args[args.index("--scale") + 1] if "--scale" in args else None
    keep = "--keep-frames" in args
    pos = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] != "--scale")]
    out, configs = Path(pos[0]), [Path(c).resolve() for c in pos[1:]]
    out.mkdir(parents=True, exist_ok=True)
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
                frames = out / "frames" / cfg.stem
                t = time.time()
                try:
                    pool.render(cfg, frames)
                    log(f"render {cfg.stem}: done in {time.time() - t:.1f}s")
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
            gif = out / f"{cfg.stem}.gif"
            extra = ["--scale", scale] if scale else []
            gif.unlink(missing_ok=True)
            if run([HERE / "make_gif.py", cfg, frames, gif] + extra, f"build {cfg.stem}", gif):
                shiny = cfg.with_name(cfg.stem + "_shiny.json")
                if shiny.exists():
                    sgif = out / f"{shiny.stem}.gif"
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
