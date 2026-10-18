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
    lib.sc_pupil_blobs.argtypes = [_u8p, _sz, _sz, _u8p, _u8p]
    lib.sc_pupil_blobs.restype = None
    lib.sc_steady_shape.argtypes = [_u8p, _sz, _sz, _sz, ctypes.POINTER(ctypes.c_int8), ctypes.POINTER(ctypes.c_int32)]
    lib.sc_steady_shape.restype = None
    lib.sc_transport.argtypes = [_sz, _sz, _u8p, _u8p, _u8p, _u8p, ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int32),
                                 _i64p, _i64p, ctypes.c_int64, ctypes.c_double]
    lib.sc_transport.restype = None


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


def pupil_blobs(a, l):
    s = np.ascontiguousarray(a, np.uint8)
    h, w = s.shape[:2]
    lm = np.ascontiguousarray(l, np.uint8)
    out = np.zeros((h, w), np.uint8)
    lib.sc_pupil_blobs(_p(s), h, w, _p(lm), _p(out))
    return out.astype(bool)


def steady_events(solid, max_run):
    """steady_shape's run merging per pixel: (event, src), each n x h x w (see timeline.rs)"""
    S = np.ascontiguousarray(solid, np.uint8)
    n = S.shape[0]
    hw = S.shape[1] * S.shape[2]
    event = np.full(S.shape, -1, np.int8)
    src = np.full(S.shape, -1, np.int32)
    lib.sc_steady_shape(_p(S), n, hw, max_run, _p(event, ctypes.c_int8), _p(src, ctypes.c_int32))
    return event, src


def transport_shading_frame(kf, k_rank, f, L, search, tol):
    names = {n: i for i, n in enumerate(sorted(set(np.unique(f["part"]).tolist()) | set(np.unique(kf["part"]).tolist())))}
    code = np.vectorize(names.__getitem__, otypes=[np.int32])
    h, w = kf["solid"].shape
    r, rk = np.ascontiguousarray(f["rest"], np.uint8), np.ascontiguousarray(kf["rest"], np.uint8)
    okf = np.ascontiguousarray((f["rest"][..., 3] > 0) & f["solid"], np.uint8)
    okk = np.ascontiguousarray((kf["rest"][..., 3] > 0) & kf["solid"], np.uint8)
    part, kpart = np.ascontiguousarray(code(f["part"])), np.ascontiguousarray(code(kf["part"]))
    krank = np.ascontiguousarray(k_rank, np.int64)
    rank = np.array(L["rank"], np.int64, order="C")
    lib.sc_transport(h, w, _p(r), _p(rk), _p(okf), _p(okk), _p(part, ctypes.c_int32), _p(kpart, ctypes.c_int32),
                     _p(krank, ctypes.c_int64), _p(rank, ctypes.c_int64), int(search), float(tol * tol * 3))
    L = dict(L); L["rank"] = rank.astype(np.result_type(L["rank"], k_rank), copy=False)
    return L
