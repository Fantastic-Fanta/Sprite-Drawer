"""Render the whole loop with several Blender processes at once (one slice of frames each).

Run:  python3 render_parallel.py CONFIG.json OUT_DIR [--jobs 4] [--frames 0,30,60,...]
Same output as render_sprite.py on its own (each frame keeps its loop number), ~jobs x faster
on a multi-core machine. --frames renders only those frames (a quick preview of the motion).
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"
args = sys.argv[1:]
cfg_path, out = Path(args[0]).resolve(), Path(args[1])
cfg = json.loads(cfg_path.read_text())
# 4 suits a 16 GB machine; more processes thrash (shared GPU / memory): SPRITE_RENDER_JOBS on a bigger one
jobs = int(args[args.index("--jobs") + 1]) if "--jobs" in args else int(os.environ.get("SPRITE_RENDER_JOBS", 4))
here = Path(__file__).parent
frames = ([int(v) for v in args[args.index("--frames") + 1].split(",")] if "--frames" in args
          else list(range(cfg["motion"]["frames"])))
out.mkdir(parents=True, exist_ok=True)
chunks = [frames[k::jobs] for k in range(jobs) if frames[k::jobs]]     # interleaved: even load
t0 = time.time()
procs = [subprocess.Popen([BLENDER, "-b", str(cfg_path.parent / cfg["model"]), "--python", str(here / "render_sprite.py"),
                           "--", str(cfg_path), str(out), "--frames", ",".join(map(str, c))],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) for c in chunks]
errs = [p.communicate()[0] for p in procs]          # Blender prints Python tracebacks to stdout
bad = [e for p, e in zip(procs, errs) if p.returncode != 0 or "Traceback" in e]
if bad:
    print(bad[0][-2000:]); sys.exit(1)
print(f"rendered {len(frames)} frames with {len(chunks)} processes in {time.time() - t0:.0f}s")
