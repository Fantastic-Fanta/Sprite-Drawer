"""Blender under machine-wide slots (file locks in .blender_slots/), and the bake pool with its cache
(.bake_cache/). One-off: python3 blender.py [--timeout 900] -- BLENDER_ARGS...
SPRITE_BLENDER: the Blender executable (default: `blender` on PATH, else the macOS app).
SPRITE_BLENDER_SLOTS: Blender processes at once (default: 1 per 4 GB of RAM, at most one per core, 1-8)."""
import fcntl
import hashlib
import inspect
import json
import os
import queue
import random
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback
from collections import deque
from pathlib import Path

BLENDER = os.environ.get("SPRITE_BLENDER") or shutil.which("blender") or "/Applications/Blender.app/Contents/MacOS/Blender"
HERE = Path(__file__).resolve().parent
LOCKS, CACHE = HERE.parent / ".blender_slots", HERE.parent / ".bake_cache"
MODEL_FILES = {".blend", ".png", ".tga", ".jpg", ".jpeg", ".exr", ".tif", ".tiff", ".bmp", ".webp", ".hdr"}
RAM_GB = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30
SLOTS = int(os.environ.get("SPRITE_BLENDER_SLOTS") or max(1, min(8, os.cpu_count() or 1, int(RAM_GB // 4))))
HANG, CACHE_GB = 180, 10


def acquire(count, label):
    """block until `count` slots are free (all or nothing, so two pools never deadlock)"""
    LOCKS.mkdir(exist_ok=True)
    count = min(count, SLOTS)
    while True:
        held = []
        for i in range(SLOTS):
            if len(held) == count:
                break
            f = open(LOCKS / f"slot{i}", "a+")
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                held.append(f)
            except BlockingIOError:
                f.close()
        if len(held) == count:
            for f in held:
                f.seek(0); f.truncate(); f.write(f"{os.getpid()} {label}\n"); f.flush()
            return held
        for f in held:
            f.close()
        time.sleep(0.3 + random.random())


def run(args, timeout=900):
    """one Blender (args after the executable) under a slot; killed with its children on timeout"""
    held = acquire(1, " ".join(args)[:150])
    proc = subprocess.Popen([BLENDER] + args, start_new_session=True)
    kill = lambda *_: os.killpg(proc.pid, signal.SIGKILL) if proc.poll() is None else None
    signal.signal(signal.SIGTERM, lambda *a: (kill(), sys.exit(143)))
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill(); print(f"killed Blender after {timeout:.0f}s", file=sys.stderr); return 124
    except KeyboardInterrupt:
        kill(); return 130
    finally:
        for f in held:
            f.close()


def bake_key(cfg, frames):
    """hash of everything a bake depends on"""
    h = hashlib.sha256()
    st, pm = cfg.get("style", {}), cfg.get("parts", {})
    used = {k: cfg.get(k) for k in ("render", "camera", "pose", "pose_params", "motion")}
    used.update(materials=pm.get("materials"), default_material=pm.get("default_material"), height=st.get("height"),
                fast_frames=st.get("fast_frames"), frames=frames)
    h.update(json.dumps(used, sort_keys=True).encode())
    model_dir = Path(cfg["model"]).parent
    for root, dirs, files in sorted(os.walk(model_dir)):
        dirs.sort()
        for f in sorted(files):
            if Path(f).suffix.lower() in MODEL_FILES:
                s = os.stat(os.path.join(root, f))
                h.update(f"{os.path.relpath(os.path.join(root, f), model_dir)}:{s.st_size}:{s.st_mtime_ns};".encode())
    for f in ("bake.py", "motion.py"):
        h.update((HERE / f).read_bytes())
    s = os.stat(BLENDER)
    h.update(f"{inspect.getsource(serve)}blender:{s.st_size}:{s.st_mtime_ns}".encode())
    return h.hexdigest()[:32]


def link_tree(src, dst):
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.iterdir():
        if f.is_file() and not f.name.startswith("."):
            (dst / f.name).unlink(missing_ok=True)
            os.link(f, dst / f.name)


class BakePool:
    """SLOTS Blender workers (blender.py --serve); bake() splits a loop's frames over them"""

    def __init__(self):
        self.procs, self.slots, self.next_id = None, [], 0

    def bake(self, cfg, out, cache=True):
        """bake the loop of cfg (a config dict, model path absolute) into out; 0 if from the cache"""
        out = Path(out)
        shutil.rmtree(out, ignore_errors=True)
        frames = list(range(cfg["motion"]["frames"]))
        entry = CACHE / bake_key(cfg, frames)
        if cache and (entry / ".complete").exists():
            link_tree(entry, out)
            os.utime(entry / ".complete")
            return 0
        self._bake(cfg, out, frames)
        if cache:
            tmp = CACHE / f".tmp-{os.getpid()}-{entry.name}"
            shutil.rmtree(tmp, ignore_errors=True)
            link_tree(out, tmp)
            (tmp / ".complete").write_text(cfg.get("name", ""))
            shutil.rmtree(entry, ignore_errors=True)
            tmp.rename(entry)
            ents = sorted(((d / ".complete").stat().st_mtime, sum(f.stat().st_size for f in d.iterdir()), d)
                          for d in CACHE.iterdir() if (d / ".complete").exists())
            total = sum(s for _, s, _ in ents)
            for _, s, d in ents:                     # drop the least recently used beyond CACHE_GB
                if total <= CACHE_GB * 1e9:
                    break
                shutil.rmtree(d, ignore_errors=True); total -= s
        return len(frames)

    def _spawn(self):
        proc = subprocess.Popen([BLENDER, "-t", "1", "-b", "--python", str(HERE / "blender.py"), "--", "--serve"],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        lines = queue.Queue()
        threading.Thread(target=lambda: ([lines.put(l) for l in proc.stdout], lines.put(None)), daemon=True).start()
        return proc, lines

    def _bake(self, cfg, out, frames):
        if self.procs is None:
            self.slots = acquire(SLOTS, f"bake pool {cfg.get('name', '')}")
            self.procs = [self._spawn() for _ in self.slots]
        out.mkdir(parents=True, exist_ok=True)
        n, errors = len(self.procs), []
        self.next_id += 1

        def one(k, chunk):
            for attempt in range(3):                 # a worker silent for HANG s is hung: replaced, retried
                proc, lines = self.procs[k]
                rid = f"{self.next_id}.{k}.{attempt}"
                proc.stdin.write(json.dumps({"id": rid, "config": cfg, "out": str(out), "frames": chunk}) + "\n")
                proc.stdin.flush()
                log = deque(maxlen=40)
                while True:
                    try:
                        line = lines.get(timeout=HANG)
                    except queue.Empty:
                        break
                    if line is None:
                        return errors.append("Blender exited:\n" + "".join(log))
                    if line.startswith(f"@@DONE {rid}"):
                        return
                    if line.startswith(f"@@FAIL {rid}"):
                        return errors.append(line.split(" ", 2)[2].replace(" | ", "\n"))
                    log.append(line)
                print(f"bake worker {k} hung: restarting it", file=sys.stderr, flush=True)
                proc.kill(); proc.wait()
                self.procs[k] = self._spawn()
            errors.append(f"bake worker {k} hung 3 times")

        ts = [threading.Thread(target=one, args=(k, frames[k::n])) for k in range(n) if frames[k::n]]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        if errors:
            raise RuntimeError(errors[0][-3000:])

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        for p, _ in self.procs or []:
            p.stdin.close()
        for p, _ in self.procs or []:
            p.wait()
        for f in self.slots:
            f.close()


def serve():
    """inside Blender: one job per stdin line, bake.py on the freshly reopened model"""
    import bpy
    src = HERE / "bake.py"
    code = compile(src.read_text(), str(src), "exec")
    for line in sys.stdin:
        if not line.strip():
            continue
        job = json.loads(line)
        try:
            bpy.ops.wm.open_mainfile(filepath=job["config"]["model"])
            exec(code, {"__name__": "__main__", "__file__": str(src), "JOB": job})
            print(f"@@DONE {job['id']}", flush=True)
        except Exception:
            print(f"@@FAIL {job['id']} " + traceback.format_exc().replace("\n", " | "), flush=True)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        serve()
    elif "--" in sys.argv:
        a = sys.argv[1:]
        sys.exit(run(a[a.index("--") + 1:], float(a[a.index("--timeout") + 1]) if a[0] == "--timeout" else 900))
    else:
        print(__doc__)
