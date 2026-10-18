"""Blender: a render worker that stays up between jobs, so Blender starts (and compiles its
shaders) once per worker instead of once per sprite. Each job is render_sprite.py on a freshly
reloaded .blend file. render_parallel.RenderPool runs several of these.

Run:  Blender -b --python render_many.py -- --serve
Reads one job per line on stdin, {"id": ..., "model": .blend, "config": CONFIG.json, "out": DIR,
"frames": "0,4,8" (optional)}, and answers "@@DONE id" or "@@FAIL id <error>" on stdout.
"""
import json
import sys
import traceback
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
SRC = HERE / "render_sprite.py"
code = compile(SRC.read_text(), str(SRC), "exec")
argv0 = sys.argv[0]


def run(job):
    bpy.ops.wm.open_mainfile(filepath=str(job["model"]))         # a clean scene for every job
    sys.argv = [argv0, "--python", str(SRC), "--", str(job["config"]), str(job["out"])] + \
        (["--frames", job["frames"]] if job.get("frames") else [])
    exec(code, {"__name__": "__main__", "__file__": str(SRC)})


for line in sys.stdin:
    if not line.strip():
        continue
    job = json.loads(line)
    try:
        run(job)
        print(f"@@DONE {job['id']}", flush=True)
    except Exception:
        print(f"@@FAIL {job['id']} " + traceback.format_exc().replace("\n", " | "), flush=True)
