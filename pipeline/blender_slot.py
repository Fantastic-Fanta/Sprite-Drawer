"""Keep Blender use on this machine bounded, however many sessions or scripts want it at once.

There are SPRITE_BLENDER_SLOTS slots (default 4: the render pool's size, which fills a 16 GB Mac).
Every Blender process holds one: a RenderPool takes one per worker, and a one-off run (a test
render, a pose check, fit_pose.py) takes one through this script. A run without a free slot waits
for one instead of piling more Blenders onto the machine. Slots are file locks in .blender_slots/
in the repo: the system drops a lock the moment its process dies, so a killed run never leaves a
slot taken.

Run a one-off Blender under a slot (it is killed - with anything it started - on the timeout, on
Ctrl-C, or when this script is killed):
  python3 pipeline/blender_slot.py [--timeout 900] -- [Blender args...]
  e.g. python3 pipeline/blender_slot.py -- -b MODEL.blend --python look.py -- CONFIG.json out/look
Show what holds the slots and any stray background Blenders:
  python3 pipeline/blender_slot.py --status
Kill stray background Blenders: -b processes whose parent is gone (their script was killed):
  python3 pipeline/blender_slot.py --reap
"""
import fcntl
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"
LOCKS = Path(__file__).resolve().parent.parent / ".blender_slots"


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
        print(f"blender_slot: killed Blender after {timeout:.0f}s", file=sys.stderr, flush=True)
        code = 124
    except KeyboardInterrupt:
        kill()
        code = 130
    finally:
        release(held)
    return code


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--status" in a:
        status()
    elif "--reap" in a:
        reap()
    elif "--" in a:
        timeout = float(a[a.index("--timeout") + 1]) if "--timeout" in a[:a.index("--")] else 900
        sys.exit(run(a[a.index("--") + 1:], timeout))
    else:
        print(__doc__)
