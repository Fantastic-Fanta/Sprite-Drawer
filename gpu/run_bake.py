"""python3 gpu/run_bake.py CONFIG.json OUTDIR [WORKERS]: bake.py in WORKERS Blenders at once (blender.py's
slots), frames split k::WORKERS like the render pool. Worker 0 also writes meta.json / static.bin."""
import json, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from build import load


def bake(cfg_path, out, workers=4):
    cfg, out = load(Path(cfg_path).resolve()), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    frames = list(range(cfg["motion"]["frames"]))
    procs, t = [], time.time()
    for k in range(workers):
        job = out / f"job{k}.json"
        job.write_text(json.dumps({"config": cfg, "out": str(out), "pipeline": str(ROOT / "pipeline"),
                                   "worker": k, "frames": frames[k::workers]}))
        procs.append(subprocess.Popen([sys.executable, str(ROOT / "pipeline/blender.py"), "--timeout", "900", "--", "-b", "--python-exit-code", "1",
                                       cfg["model"], "--python", str(ROOT / "gpu/bake.py"), "--", str(job)],
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True))
    for p in procs:
        log = p.communicate()[0]
        if p.returncode:
            sys.exit(f"bake failed:\n{log[-3000:]}")
    return time.time() - t


if __name__ == "__main__":
    print(f"bake {bake(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 4):.1f}s")
