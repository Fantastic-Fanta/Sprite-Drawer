"""The Rust versions of sprite_style's per-pixel rules (pipeline/rust), loaded through ctypes.

Build once:  cargo build --release --manifest-path pipeline/rust/Cargo.toml
Without the built library (or with SPRITE_RUST=0) sprite_style uses its Python code, which gives
the same pixels; regress.py checks that they agree.
"""
import ctypes
import os
from pathlib import Path

import numpy as np

_LIB_PATH = Path(__file__).resolve().parent / "rust" / "target" / "release" / "libspritecore.dylib"
lib = None
if os.environ.get("SPRITE_RUST", "1") != "0" and _LIB_PATH.exists():
    lib = ctypes.CDLL(str(_LIB_PATH))
    _u8p, _i64p, _sz = ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_int64), ctypes.c_size_t
    lib.sc_clean_lines.argtypes = [_i64p, _sz, _u8p, _sz, _sz, _u8p, _u8p, _u8p, ctypes.c_int]
    lib.sc_clean_lines.restype = ctypes.c_int
    lib.sc_debounce.argtypes = [_u8p, _sz, _sz, _sz, _sz, _u8p]
    lib.sc_debounce.restype = None
    lib.sc_hard_faults.argtypes = [_i64p, _sz, _u8p, _sz, _sz, _u8p]
    lib.sc_hard_faults.restype = ctypes.c_int64


def _hexkey(h):
    return int(h[1:3], 16) << 16 | int(h[3:5], 16) << 8 | int(h[5:7], 16)


def _key(rgb):
    return rgb[0] << 16 | rgb[1] << 8 | rgb[2]


def pack_cfg(cfg):
    """the colour sets the rules need: outline, line colours, and for each outlined part
    (style.part_outline) its own / other parts' colours and highlight, as check_loop.part_masks
    builds them"""
    import sprite_style as ss
    out = [_key(ss.colour(cfg, "outline"))]
    dark = [_key(c) for c in ss.dark_line_colours(cfg)]
    out += [len(dark)] + dark
    part_of = {}
    for name, shades in cfg["palette"]["parts"].items():
        for h in shades:
            part_of.setdefault(_hexkey(h), name)
    names = cfg["style"].get("part_outline", [])
    out.append(len(names))
    for name in names:
        own = [k for k, pn in part_of.items() if pn == name]
        other = [k for k, pn in part_of.items() if pn != name]
        hl = cfg["style"].get("highlight", {}).get(name)
        out += [len(own)] + own + [len(other)] + other + [_key(ss.colour(cfg, hl["colour"])) if hl else -1]
    return np.array(out, np.int64)


def _p(a, t=ctypes.c_uint8):
    return None if a is None else a.ctypes.data_as(ctypes.POINTER(t))


def _rgba(a):
    return None if a is None else np.ascontiguousarray(a, np.uint8)


def clean_lines(cfg, s, protect=None, prev=None, nxt=None, corners=True):
    out = np.array(s, np.uint8, order="C")              # a copy, changed in place
    h, w = out.shape[:2]
    pr = None if protect is None else np.ascontiguousarray(protect, np.uint8)
    prev, nxt = _rgba(prev), _rgba(nxt)
    c = pack_cfg(cfg)
    mode = 0 if not corners else (2 if corners == "inner" else 1)
    lib.sc_clean_lines(_p(c, ctypes.c_int64), len(c), _p(out), h, w, _p(pr), _p(prev), _p(nxt), mode)
    return out


def debounce(sprites, max_run=2, skip=None):
    S = np.ascontiguousarray(np.stack(sprites), np.uint8)
    n, h, w = S.shape[:3]
    sk = None if skip is None else np.ascontiguousarray(skip, np.uint8)
    lib.sc_debounce(_p(S), n, h, w, max_run, _p(sk))
    return [S[i] for i in range(n)]


def hard_faults(cfg, s, protect):
    a = np.ascontiguousarray(s, np.uint8)
    h, w = a.shape[:2]
    pr = None if protect is None else np.ascontiguousarray(protect, np.uint8)
    c = pack_cfg(cfg)
    return int(lib.sc_hard_faults(_p(c, ctypes.c_int64), len(c), _p(a), h, w, _p(pr)))
