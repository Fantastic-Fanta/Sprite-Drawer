"""The Rust versions of sprite_style's per-pixel rules (pipeline/rust), loaded through ctypes.

Build once:  cargo build --release --manifest-path pipeline/rust/Cargo.toml
Without the built library (or with SPRITE_RUST=0) sprite_style uses its Python code, which gives
the same pixels; regress.py checks that they agree.
"""
import ctypes
import os
from pathlib import Path

import numpy as np

import sys

_LIB_PATH = Path(__file__).resolve().parent / "rust" / "target" / "release" / {
    "darwin": "libspritecore.dylib", "win32": "spritecore.dll"}.get(sys.platform, "libspritecore.so")
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
    lib.sc_clean_parts.argtypes = [_i64p, _sz, _u8p, _sz, _sz, _u8p]
    lib.sc_clean_parts.restype = ctypes.c_int
    lib.sc_hires_lines.argtypes = [_u8p, _sz, _sz, ctypes.c_double, ctypes.c_double, _u8p]
    lib.sc_hires_lines.restype = None
    lib.sc_seal_parts.argtypes = [_i64p, _sz, _u8p, _sz, _sz, _u8p]
    lib.sc_seal_parts.restype = ctypes.c_int
    lib.sc_repair.argtypes = [_i64p, _sz, _i64p, _sz, _u8p, _sz, _sz, _u8p, _u8p, _u8p]
    lib.sc_repair.restype = None
    lib.sc_short_runs.argtypes = [_i64p, _sz, _sz, _sz, _i64p]
    lib.sc_short_runs.restype = None
    lib.sc_best_patch.argtypes = [ctypes.POINTER(ctypes.c_double), _sz, _sz, ctypes.c_double, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_size_t)]
    lib.sc_best_patch.restype = ctypes.c_double


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
    names = {}                                        # part name -> any int, the same for both frames

    def code(a):
        return np.fromiter((names.setdefault(x, len(names)) for x in a.ravel().tolist()), np.int32, a.size).reshape(a.shape)
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


def pack_parts(cfg):
    """sprite_style.part_of_colour as bits: [n, (colour, parts)..., outline bit, n, outlined part bits...]"""
    import sprite_style as ss
    pc = ss.part_of_colour(cfg)
    bit = {n: 1 << i for i, n in enumerate(sorted({n for v in pc.values() for n in v}))}
    out = [len(pc)]
    for c, names in pc.items():
        out += [_key(c), sum(bit[n] for n in names)]
    outlined = [bit[n] for n in cfg["style"].get("part_outline", []) if n in bit]   # unknown part: nothing to do
    out += [bit.get("O", 0), len(outlined)] + outlined
    return np.array(out, np.int64)


def clean_parts(cfg, s, protect=None):
    out = np.array(s, np.uint8, order="C")
    h, w = out.shape[:2]
    pr = None if protect is None else np.ascontiguousarray(protect, np.uint8)
    b = pack_parts(cfg)
    lib.sc_clean_parts(_p(b, ctypes.c_int64), len(b), _p(out), h, w, _p(pr))
    return out


def hires_lines(data, depth_jump, crease_cos):
    d = np.ascontiguousarray(data, np.uint8)
    h, w = d.shape[:2]
    out = np.zeros((h, w), np.uint8)
    lib.sc_hires_lines(_p(d), h, w, float(depth_jump), float(crease_cos), _p(out))
    return out.astype(bool)


def seal_parts(cfg, s, protect=None):
    out = np.array(s, np.uint8, order="C")
    h, w = out.shape[:2]
    pr = None if protect is None else np.ascontiguousarray(protect, np.uint8)
    c = pack_cfg(cfg)
    lib.sc_seal_parts(_p(c, ctypes.c_int64), len(c), _p(out), h, w, _p(pr))
    return out


def repair(cfg, s, prev=None, nxt=None, protect=None):
    out = np.array(s, np.uint8, order="C")
    h, w = out.shape[:2]
    pr = None if protect is None else np.ascontiguousarray(protect, np.uint8)
    prev, nxt = _rgba(prev), _rgba(nxt)
    c, b = pack_cfg(cfg), pack_parts(cfg)
    lib.sc_repair(_p(c, ctypes.c_int64), len(c), _p(b, ctypes.c_int64), len(b), _p(out), h, w, _p(pr), _p(prev), _p(nxt))
    return out


def short_runs(series_stack, max_len=2):
    s = np.ascontiguousarray(series_stack, np.int64)
    n, hw = s.shape[0], s[0].size
    out = np.zeros(s.shape[1:], np.int64)
    lib.sc_short_runs(_p(s, ctypes.c_int64), n, hw, max_len, _p(out, ctypes.c_int64))
    return out


def best_patch(resid, thr):
    """flicker_map.pops' patch search: (summed weight, [(y, x), ...] in the Python's order)"""
    r = np.ascontiguousarray(resid, np.float64)
    h, w = r.shape
    comp = np.zeros(h * w, np.uint32)
    k = ctypes.c_size_t(0)
    best = lib.sc_best_patch(_p(r, ctypes.c_double), h, w, float(thr), _p(comp, ctypes.c_uint32), ctypes.byref(k))
    return best, [(int(i) // w, int(i) % w) for i in comp[:k.value]]
