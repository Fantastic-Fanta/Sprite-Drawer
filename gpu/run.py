"""python3 gpu/run.py CONFIG.json OUT_DIR [--workers 4]: the prototype route end to end, timed per stage:
bake (Blender poses, 4 workers) -> sprite_gpu (wgpu passes as TGA) -> sprite_style (unchanged) -> GIF.
Writes OUT_DIR/<stem>.gif (+ _4x) and OUT_DIR/timing.json."""
import json, shutil, subprocess, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "pipeline")); sys.path.insert(0, str(HERE))
from build import load
from run_bake import bake
import sprite_style as ss

BIN = HERE / "renderer/target/release/sprite_gpu"

if __name__ == "__main__":
    a = sys.argv[1:]
    workers = int(a.pop(a.index("--workers") + 1)) if "--workers" in a else 4
    cfg_path, out = Path(a[0]).resolve(), Path(a[1]).resolve()
    if not BIN.exists():
        subprocess.run(["cargo", "build", "--release"], cwd=HERE / "renderer", check=True)
    cfg = load(cfg_path)
    t, tm = time.time(), {}
    shutil.rmtree(out / "bake", ignore_errors=True); shutil.rmtree(out / "frames", ignore_errors=True)
    tm["bake"] = bake(cfg_path, out / "bake", workers)
    t1 = time.time()
    r = subprocess.run([str(BIN), str(out / "bake"), str(out / "frames")], check=True, capture_output=True, text=True)
    tm["gpu_render"] = time.time() - t1
    tm["gpu_detail"] = json.loads(r.stdout.strip().splitlines()[-1])
    t1 = time.time()
    sprites, clipped = ss.sprites(cfg, out / "frames")
    tm["sprite"] = time.time() - t1
    t1 = time.time()
    ss.save_gif(cfg, sprites, out / f"{cfg_path.stem}.gif")
    tm["gif"] = time.time() - t1
    tm["total"] = time.time() - t
    (out / "timing.json").write_text(json.dumps(tm, indent=1))
    print(json.dumps(tm))
