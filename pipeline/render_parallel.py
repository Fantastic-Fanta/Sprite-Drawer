"""Render the whole loop with several Blender processes at once (one slice of frames each).

Run:  python3 render_parallel.py CONFIG.json OUT_DIR [--jobs 4] [--frames 0,30,60,...] [--no-cache]
Same output as render_sprite.py on its own (each frame keeps its loop number), ~jobs x faster
on a multi-core machine. --frames renders only those frames (a quick preview of the motion).
In a script, RenderPool keeps the Blender processes up between sprites (build_all.py), so
Blender starts and compiles its shaders once per process rather than once per sprite.
Renders are cached (SPRITE_RENDER_CACHE: a folder, default .render_cache/ in the repo; 0 = off):
a render whose inputs are unchanged - the config's render / camera / pose / motion / parts
materials / fast_frames, the .blend and textures next to the model, the render scripts, Blender, the output
format, the frames - is hard-linked from the cache instead of rendered again.
SPRITE_RENDER_CACHE_GB caps its size (default 20; oldest renders go first).
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"
HERE = Path(__file__).resolve().parent
RENDER_SOURCES = ("render_sprite.py", "render_many.py", "linetrace.py", "motion.py")
# files next to the model that a render can load: the .blend and image textures (configs, GIFs
# and the like often share the folder and must not count)
MODEL_FILES = {".blend", ".png", ".tga", ".jpg", ".jpeg", ".exr", ".tif", ".tiff", ".bmp", ".webp", ".hdr"}


def cache_dir():
    v = os.environ.get("SPRITE_RENDER_CACHE", str(HERE.parent / ".render_cache"))
    return None if v == "0" else Path(v)


def render_key(cfg_path, cfg, frames):
    """hash of everything a render depends on (see the module docstring)"""
    h = hashlib.sha256()
    parts = cfg.get("parts", {})
    used = {k: cfg.get(k) for k in ("render", "camera", "pose", "pose_params", "motion")}
    used.update(materials=parts.get("materials"), default_material=parts.get("default_material"),
                fast_frames=cfg.get("style", {}).get("fast_frames"), frames=frames,
                format=os.environ.get("SPRITE_RENDER_FORMAT", "PNG").upper())
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
    """N Blender workers (render_many.py --serve); render() splits a loop's frames over them"""

    def __init__(self, jobs=None, threads=None):
        # 4 suits a 16 GB machine; more processes thrash (shared GPU / memory): SPRITE_RENDER_JOBS on a bigger one
        jobs = jobs or int(os.environ.get("SPRITE_RENDER_JOBS", 4))
        # one thread per Blender process: the passes are GPU work and single-threaded Freestyle, and the
        # processes already fill the cores (Blender's default, a thread per core each, costs ~12% more CPU)
        threads = threads or os.environ.get("SPRITE_RENDER_THREADS", "1")
        self.jobs, self.threads, self.procs = jobs, threads, None     # started on the first real render
        self.next_id = 0

    def render(self, cfg_path, out, frames=None, cache=True):
        """render frames (default: the whole loop) of CONFIG into out; raises on a failed worker.
        Returns the number of frames, or 0 if they came from the cache."""
        cfg_path, out = Path(cfg_path).resolve(), Path(out).resolve()
        cfg = json.loads(cfg_path.read_text())
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

    def _render(self, cfg_path, cfg, out, frames):
        if self.procs is None:
            jobs, threads = self.jobs, self.threads
            self.procs = [subprocess.Popen([BLENDER, "-t", str(threads), "-b", "--python", str(HERE / "render_many.py"), "--", "--serve"],
                                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           text=True, bufsize=1) for _ in range(jobs)]
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
        for p in self.procs or []:
            p.stdin.close()
        for p in self.procs or []:
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
            n = pool.render(args[0], args[1], frames, cache="--no-cache" not in args)
    except RuntimeError as e:
        print(e); sys.exit(1)
    if n:
        print(f"rendered {n} frames with {len(pool.procs or [])} processes in {time.time() - t0:.0f}s")
    else:
        print(f"frames from the render cache in {time.time() - t0:.1f}s")
