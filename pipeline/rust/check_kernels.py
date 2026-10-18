"""Run a real build with every ported kernel checked against its Python original on each call.

Run:  python3 pipeline/rust/check_kernels.py CONFIG.json FRAMES_DIR [KERNEL ...]
Prints, per kernel, how many calls agreed; saves the first disagreeing inputs to /tmp-free
.regress/kernel_fail_<name>.npz for debugging. Exit code 1 on any disagreement.
"""
import os
import runpy
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PIPE = HERE.parent
sys.path.insert(0, str(PIPE))
os.environ["SPRITE_JOBS"] = "1"                 # one process, so the wrappers see every call
os.environ.setdefault("PYTHONHASHSEED", "0")
import sprite_style as ss                       # noqa: E402
import rustcore                                 # noqa: E402

assert rustcore.lib is not None, "build pipeline/rust first"
cfg_path, frames = sys.argv[1], sys.argv[2]
wanted = sys.argv[3:] or ["clean_lines"]
stats = {}


def same(a, b):
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        return np.asarray(a).dtype == np.asarray(b).dtype and np.array_equal(a, b)
    return a == b


def wrap(name):
    py_fn, rs_fn = getattr(ss, name), getattr(rustcore, name)

    def both(*a, **k):
        if rustcore.lib is None:                         # inside another kernel's Python run
            return py_fn(*a, **k)
        lib, rustcore.lib = rustcore.lib, None          # the Python original, all the way down
        t0 = time.perf_counter(); want = py_fn(*a, **k); t1 = time.perf_counter()
        rustcore.lib = lib
        got = rs_fn(*a, **k); t2 = time.perf_counter()
        st = stats.setdefault(name, {"calls": 0, "bad": 0, "py": 0.0, "rs": 0.0})
        st["calls"] += 1; st["py"] += t1 - t0; st["rs"] += t2 - t1
        if not same(want, got):
            if not st["bad"]:
                arrays = {f"a{i}": v for i, v in enumerate(a) if isinstance(v, np.ndarray)}
                np.savez(PIPE.parent / ".regress" / f"kernel_fail_{name}.npz", want=want, got=got, **arrays,
                         kw=np.array(repr(k)))
            st["bad"] += 1
        return want
    setattr(ss, name, both)


for n in wanted:
    wrap(n)
sys.argv = [str(PIPE / "make_gif.py"), cfg_path, frames, str(PIPE.parent / ".regress" / "kernel_check.gif"), "--no-qa"]
try:
    runpy.run_path(str(PIPE / "make_gif.py"), run_name="__main__")
except SystemExit:
    pass
bad = False
for n, st in stats.items():
    bad |= st["bad"] > 0
    print(f"{n}: {st['calls'] - st['bad']}/{st['calls']} calls identical; python {st['py']:.2f}s, rust {st['rs']:.2f}s")
sys.exit(1 if bad else 0)
