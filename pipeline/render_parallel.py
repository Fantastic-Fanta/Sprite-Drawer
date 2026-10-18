"""Render the whole loop with several Blender processes at once (one slice of frames each).

Run:  python3 render_parallel.py CONFIG.json OUT_DIR [--jobs 4] [--frames 0,30,60,...]
Same output as render_sprite.py on its own (each frame keeps its loop number), ~jobs x faster
on a multi-core machine. --frames renders only those frames (a quick preview of the motion).
In a script, RenderPool keeps the Blender processes up between sprites (build_all.py), so
Blender starts and compiles its shaders once per process rather than once per sprite.
"""
import json
import os
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"
HERE = Path(__file__).resolve().parent


class RenderPool:
    """N Blender workers (render_many.py --serve); render() splits a loop's frames over them"""

    def __init__(self, jobs=None, threads=None):
        # 4 suits a 16 GB machine; more processes thrash (shared GPU / memory): SPRITE_RENDER_JOBS on a bigger one
        jobs = jobs or int(os.environ.get("SPRITE_RENDER_JOBS", 4))
        # one thread per Blender process: the passes are GPU work and single-threaded Freestyle, and the
        # processes already fill the cores (Blender's default, a thread per core each, costs ~12% more CPU)
        threads = threads or os.environ.get("SPRITE_RENDER_THREADS", "1")
        self.procs = [subprocess.Popen([BLENDER, "-t", str(threads), "-b", "--python", str(HERE / "render_many.py"), "--", "--serve"],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, bufsize=1) for _ in range(jobs)]
        self.next_id = 0

    def render(self, cfg_path, out, frames=None):
        """render frames (default: the whole loop) of CONFIG into out; raises on a failed worker"""
        cfg_path, out = Path(cfg_path).resolve(), Path(out).resolve()
        cfg = json.loads(cfg_path.read_text())
        frames = list(range(cfg["motion"]["frames"])) if frames is None else frames
        out.mkdir(parents=True, exist_ok=True)
        n = len(self.procs)
        chunks = [frames[k::n] for k in range(n)]                          # interleaved: even load
        errors = []

        def one(proc, chunk, jid):
            if not chunk:
                return
            proc.stdin.write(json.dumps({"id": jid, "model": str(cfg_path.parent / cfg["model"]), "config": str(cfg_path),
                                         "out": str(out), "frames": ",".join(map(str, chunk))}) + "\n")
            proc.stdin.flush()
            log = deque(maxlen=40)
            for line in proc.stdout:
                if line.startswith(f"@@DONE {jid}"):
                    return
                if line.startswith(f"@@FAIL {jid}"):
                    errors.append(line.split(" ", 2)[2].replace(" | ", "\n")); return
                log.append(line)
            errors.append("Blender exited:\n" + "".join(log))

        self.next_id += 1
        ts = [threading.Thread(target=one, args=(p, c, f"{self.next_id}.{k}")) for k, (p, c) in enumerate(zip(self.procs, chunks))]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        if errors:
            raise RuntimeError(errors[0][-3000:])
        return len(frames)

    def close(self):
        for p in self.procs:
            p.stdin.close()
        for p in self.procs:
            p.wait()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    jobs = int(args[args.index("--jobs") + 1]) if "--jobs" in args else None
    frames = [int(v) for v in args[args.index("--frames") + 1].split(",")] if "--frames" in args else None
    t0 = time.time()
    try:
        with RenderPool(jobs) as pool:
            n = pool.render(args[0], args[1], frames)
    except RuntimeError as e:
        print(e); sys.exit(1)
    print(f"rendered {n} frames with {len(pool.procs)} processes in {time.time() - t0:.0f}s")
