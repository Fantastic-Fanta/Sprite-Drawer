"""Everything about running Blender: a machine-wide cap on Blender processes, the render pool
with its cache, and the render worker that runs inside Blender.

  python3 pipeline/blender.py render CONFIG.json OUT_DIR [--jobs 4] [--frames 0,30,60] [--no-cache]
      render the loop (or those frames) with several Blender processes at once; same output as
      render_sprite.py on its own, ~jobs x faster
  python3 pipeline/blender.py [--timeout 900] -- [Blender args...]
      a one-off Blender under a slot (killed, with anything it started, on the timeout, on Ctrl-C,
      or when this script is killed), e.g.  -- -b MODEL.blend --python look.py -- CONFIG.json out/look
  python3 pipeline/blender.py --status     what holds the slots, and any background Blenders
  python3 pipeline/blender.py --reap       kill stray background Blenders (-b, parent gone)

Slots: SPRITE_BLENDER_SLOTS (default 4, the render pool's size, which fills a 16 GB Mac). Every
Blender process holds one: a RenderPool one per worker, a one-off run one. A run without a free
slot waits instead of piling more Blenders onto the machine. Slots are file locks in
.blender_slots/: the system drops a lock the moment its process dies, so a killed run never leaves
a slot taken.

Render cache (SPRITE_RENDER_CACHE: a folder, default .render_cache/; 0 = off): a render whose
inputs are unchanged - the config's render / camera / pose / motion / parts materials,
style.height and fast_frames, the .blend and textures next to the model, the render code, Blender,
the output format, the frames - is hard-linked from the cache instead of rendered again.
SPRITE_RENDER_CACHE_GB caps its size (default 20; oldest first). A worker silent for
SPRITE_RENDER_HANG_S seconds (default 180) is hung: killed, replaced, its frames rendered again.

Inside Blender (blender.py -- --serve, started by RenderPool): reads one job per line on stdin,
{"id", "model": .blend, "config", "out", "frames": "0,4,8"}, runs render_sprite.py on the freshly
reopened .blend (Blender starts and compiles its shaders once per worker, not once per sprite),
and answers "@@DONE id" or "@@FAIL id <error>".
"""
import fcntl
import hashlib
import inspect
import json
import os
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback
from collections import deque
from pathlib import Path

BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"
HERE = Path(__file__).resolve().parent
LOCKS = HERE.parent / ".blender_slots"
RENDER_SOURCES = ("render_sprite.py", "motion.py")
PASS_NAMES = {"color", "id", "data", "hull"}
RETRIES = 2          # restarts of a hung render worker (SPRITE_RENDER_HANG_S) before the render fails
# files next to the model that a render can load: the .blend and image textures (configs, GIFs
# and the like often share the folder and must not count)
MODEL_FILES = {".blend", ".png", ".tga", ".jpg", ".jpeg", ".exr", ".tif", ".tiff", ".bmp", ".webp", ".hdr"}


# --- slots ---------------------------------------------------------------------------------------

def n_slots():
    return int(os.environ.get("SPRITE_BLENDER_SLOTS", 4))


def acquire(count=1, label=""):
    """block until `count` slots are free; returns their open lock files (close them, or exit, to
    free the slots). All or nothing: a request that can't get every slot it needs lets go of the
    ones it got and tries again a moment later, so two pools never each hold part and wait forever."""
    import random
    LOCKS.mkdir(exist_ok=True)
    warned, start = False, time.time()
    count = min(count, n_slots())
    while True:
        held = []
        for i in range(n_slots()):
            if len(held) == count:
                break
            f = open(LOCKS / f"slot{i}", "a+")
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                f.close()
                continue
            held.append(f)
        if len(held) == count:
            for f in held:
                f.seek(0); f.truncate(); f.write(f"{os.getpid()} {label}\n"); f.flush()
            return held
        release(held)
        if not warned and time.time() - start > 5:
            print(f"waiting for {count} Blender slot(s) (--status shows who has them)", file=sys.stderr, flush=True)
            warned = True
        time.sleep(0.3 + random.random() * (0.4 if count == 1 else 1.2))


def release(held):
    for f in held:
        f.close()


def status():
    LOCKS.mkdir(exist_ok=True)
    for i in range(n_slots()):
        p = LOCKS / f"slot{i}"
        f = open(p, "a+")
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            print(f"slot {i}: free")
        except BlockingIOError:
            print(f"slot {i}: {p.read_text().strip()}")
        f.close()
    for pid, ppid, etime, cmd in strays(all_bg=True):
        print(f"{'STRAY ' if ppid == 1 else ''}blender {pid} (parent {ppid}, up {etime}): {cmd[:120]}")


def strays(all_bg=False):
    """background Blender processes ((pid, ppid, elapsed, command)); only orphans unless all_bg"""
    out = subprocess.run(["ps", "-axo", "pid=,ppid=,etime=,command="], capture_output=True, text=True).stdout
    found = []
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4 or not parts[3].startswith(BLENDER):
            continue
        pid, ppid = int(parts[0]), int(parts[1])
        if " -b " not in f" {parts[3]} ":
            continue                                     # a window someone is looking at: never touched
        if all_bg or ppid == 1:
            found.append((pid, ppid, parts[2], parts[3]))
    return found


def reap():
    for pid, _, etime, cmd in strays():
        os.kill(pid, signal.SIGKILL)
        print(f"killed stray blender {pid} (up {etime}): {cmd[:120]}")


def run(blender_args, timeout):
    held = acquire(1, "one-off: " + " ".join(blender_args)[:150])
    proc = subprocess.Popen([BLENDER] + blender_args, start_new_session=True)

    def kill(*_):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    signal.signal(signal.SIGTERM, lambda *a: (kill(), sys.exit(143)))
    signal.signal(signal.SIGHUP, lambda *a: (kill(), sys.exit(129)))
    try:
        code = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill()
        print(f"blender.py: killed Blender after {timeout:.0f}s", file=sys.stderr, flush=True)
        code = 124
    except KeyboardInterrupt:
        kill()
        code = 130
    finally:
        release(held)
    return code


# --- the render pool and its cache ---------------------------------------------------------------

def cache_dir():
    v = os.environ.get("SPRITE_RENDER_CACHE", str(HERE.parent / ".render_cache"))
    return None if v == "0" else Path(v)


def render_key(cfg_path, cfg, frames):
    """hash of everything a render depends on (see the module docstring)"""
    h = hashlib.sha256()
    used = {k: cfg.get(k) for k in ("render", "camera", "pose", "pose_params", "motion")}
    used.update(materials=cfg.get("parts", {}).get("materials"), default_material=cfg.get("parts", {}).get("default_material"),
                height=cfg.get("style", {}).get("height"),
                fast_frames=cfg.get("style", {}).get("fast_frames"), frames=frames,
                format=os.environ.get("SPRITE_RENDER_FORMAT", "TGA").upper())
    h.update(json.dumps(used, sort_keys=True).encode())
    model_dir = (cfg_path.parent / cfg["model"]).parent
    for root, dirs, files in sorted(os.walk(model_dir)):
        dirs.sort()
        for f in sorted(files):
            if Path(f).suffix.lower() not in MODEL_FILES:
                continue
            st = os.stat(os.path.join(root, f))
            h.update(f"{os.path.relpath(os.path.join(root, f), model_dir)}:{st.st_size}:{st.st_mtime_ns};".encode())
    for f in RENDER_SOURCES:
        h.update((HERE / f).read_bytes())
    h.update(inspect.getsource(serve).encode())          # the worker's own code
    st = os.stat(BLENDER)
    h.update(f"blender:{st.st_size}:{st.st_mtime_ns}".encode())
    return h.hexdigest()[:32]


def link_tree(src, dst):
    """every file of src into dst, hard-linked (copied where links can't be made)"""
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.iterdir():
        if f.is_file() and not f.name.startswith("."):
            target = dst / f.name
            target.unlink(missing_ok=True)
            try:
                os.link(f, target)
            except OSError:
                shutil.copy2(f, target)


def trim_cache(root):
    """keep the cache under SPRITE_RENDER_CACHE_GB, dropping the least recently used renders"""
    cap = float(os.environ.get("SPRITE_RENDER_CACHE_GB", 20)) * 1e9
    entries = []
    for d in root.iterdir():
        if (d / ".complete").exists():
            entries.append(((d / ".complete").stat().st_mtime, sum(f.stat().st_size for f in d.iterdir()), d))
    total = sum(s for _, s, _ in entries)
    for _, size, d in sorted(entries):
        if total <= cap:
            break
        shutil.rmtree(d, ignore_errors=True)
        total -= size


class RenderPool:
    """N Blender workers (blender.py -- --serve); render() splits a loop's frames over them"""

    def __init__(self, jobs=None, threads=None):
        # 4 suits a 16 GB machine; more processes thrash (shared GPU / memory): SPRITE_RENDER_JOBS on a bigger one
        jobs = jobs or int(os.environ.get("SPRITE_RENDER_JOBS", 4))
        # one thread per Blender process: the passes are GPU work and single-threaded Freestyle, and the
        # processes already fill the cores (Blender's default, a thread per core each, costs ~12% more CPU)
        threads = threads or os.environ.get("SPRITE_RENDER_THREADS", "1")
        self.jobs, self.threads, self.procs = jobs, threads, None     # started on the first real render
        self.slots = []
        self.next_id = 0

    def render(self, cfg_path, out, frames=None, cache=True):
        """render frames (default: the whole loop) of CONFIG into out; raises on a failed worker.
        Returns the number of frames, or 0 if they came from the cache."""
        cfg_path, out = Path(cfg_path).resolve(), Path(out).resolve()
        cfg = json.loads(cfg_path.read_text())
        if frames is None and out.exists():
            # a whole loop replaces whatever was rendered here before: old pass files (a longer
            # loop, the other format) would otherwise be read as part of this one
            for f in out.iterdir():
                if f.suffix in (".png", ".tga") and f.stem.split("_")[0] in PASS_NAMES:
                    f.unlink()
        frames = list(range(cfg["motion"]["frames"])) if frames is None else frames
        root = cache_dir() if cache else None
        if root is not None:
            entry = root / render_key(cfg_path, cfg, frames)
            if (entry / ".complete").exists():
                link_tree(entry, out)
                os.utime(entry / ".complete")                     # recently used
                return 0
        n = self._render(cfg_path, cfg, out, frames)
        if root is not None:
            tmp = root / f".tmp-{os.getpid()}-{entry.name}"
            shutil.rmtree(tmp, ignore_errors=True)
            link_tree(out, tmp)
            (tmp / ".complete").write_text(str(cfg_path))
            shutil.rmtree(entry, ignore_errors=True)
            tmp.rename(entry)
            trim_cache(root)
        return n

    def _spawn(self):
        """one worker: the Blender process and a queue of its output lines (None when it exits),
        read by a thread so a silent worker can be timed out"""
        proc = subprocess.Popen([BLENDER, "-t", str(self.threads), "-b", "--python", str(HERE / "blender.py"), "--", "--serve"],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1)
        lines = queue.Queue()

        def pump():
            for line in proc.stdout:
                lines.put(line)
            lines.put(None)
        threading.Thread(target=pump, daemon=True).start()
        return proc, lines

    def _render(self, cfg_path, cfg, out, frames):
        if self.procs is None:
            # a few frames need no more workers than frames (a 2-frame look shouldn't take the machine)
            self.slots = acquire(min(self.jobs, len(frames)), f"render pool: {cfg_path.name}")
            self.procs = [self._spawn() for _ in self.slots]
        out.mkdir(parents=True, exist_ok=True)
        n = len(self.procs)
        chunks = [frames[k::n] for k in range(n)]                          # interleaved: even load
        errors = []
        # a worker silent this long is hung (seen: macOS's Metal shader cache deadlocking a worker at
        # 0% CPU forever); it is killed, replaced, and its frames rendered again (at most RETRIES times)
        hang = float(os.environ.get("SPRITE_RENDER_HANG_S", 180))

        def one(k, chunk, jid):
            if not chunk:
                return
            for attempt in range(RETRIES + 1):
                proc, lines = self.procs[k]
                rid = f"{jid}.{attempt}"
                proc.stdin.write(json.dumps({"id": rid, "model": str(cfg_path.parent / cfg["model"]), "config": str(cfg_path),
                                             "out": str(out), "frames": ",".join(map(str, chunk))}) + "\n")
                proc.stdin.flush()
                log = deque(maxlen=40)
                while True:
                    try:
                        line = lines.get(timeout=hang)
                    except queue.Empty:
                        break                                              # hung: retry below
                    if line is None:
                        errors.append("Blender exited:\n" + "".join(log)); return
                    if line.startswith(f"@@DONE {rid}"):
                        return
                    if line.startswith(f"@@FAIL {rid}"):
                        errors.append(line.split(" ", 2)[2].replace(" | ", "\n")); return
                    log.append(line)
                print(f"render worker {k} silent for {hang:.0f}s: restarting it ({attempt + 1}/{RETRIES})",
                      file=sys.stderr, flush=True)
                proc.kill()
                proc.wait()
                self.procs[k] = self._spawn()
            errors.append(f"render worker {k} hung {RETRIES + 1} times (frames {chunk[:5]}...)")

        self.next_id += 1
        ts = [threading.Thread(target=one, args=(k, c, f"{self.next_id}.{k}")) for k, c in enumerate(chunks)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        if errors:
            raise RuntimeError(errors[0][-3000:])
        return len(frames)

    def close(self):
        for p, _ in self.procs or []:
            p.stdin.close()
        for p, _ in self.procs or []:
            p.wait()
        release(self.slots)
        self.slots = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# --- the worker, inside Blender ------------------------------------------------------------------

def serve():
    import bpy
    src = HERE / "render_sprite.py"
    code = compile(src.read_text(), str(src), "exec")
    argv0 = sys.argv[0]
    for line in sys.stdin:
        if not line.strip():
            continue
        job = json.loads(line)
        try:
            bpy.ops.wm.open_mainfile(filepath=str(job["model"]))         # a clean scene for every job
            sys.argv = [argv0, "--python", str(src), "--", str(job["config"]), str(job["out"])] + \
                (["--frames", job["frames"]] if job.get("frames") else [])
            exec(code, {"__name__": "__main__", "__file__": str(src)})
            print(f"@@DONE {job['id']}", flush=True)
        except Exception:
            print(f"@@FAIL {job['id']} " + traceback.format_exc().replace("\n", " | "), flush=True)


def main():
    a = sys.argv[1:]
    if a and a[0] == "render":
        jobs = int(a[a.index("--jobs") + 1]) if "--jobs" in a else None
        frames = [int(v) for v in a[a.index("--frames") + 1].split(",")] if "--frames" in a else None
        t0 = time.time()
        try:
            with RenderPool(jobs) as pool:
                n = pool.render(a[1], a[2], frames, cache="--no-cache" not in a)
        except RuntimeError as e:
            print(e); sys.exit(1)
        if n:
            print(f"rendered {n} frames with {len(pool.procs or [])} processes in {time.time() - t0:.0f}s")
        else:
            print(f"frames from the render cache in {time.time() - t0:.1f}s")
    elif "--status" in a:
        status()
    elif "--reap" in a:
        reap()
    elif "--" in a:
        timeout = float(a[a.index("--timeout") + 1]) if "--timeout" in a[:a.index("--")] else 900
        sys.exit(run(a[a.index("--") + 1:], timeout))
    else:
        print(__doc__)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        serve()
    else:
        main()
