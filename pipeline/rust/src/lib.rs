//! Rust versions of sprite_style.py's per-pixel rules, called through ctypes (rustcore.py).
//! Every function reproduces its Python original exactly, tie-breaks included: Python's
//! `max(set(cols), key=cols.count)` follows CPython's set iteration order, emulated in `pyset`.

mod pyset;
mod frame;
mod lines;
mod timeline;
mod faults;
mod parts;
mod prep;
mod seal;
mod qa;
mod trace;

use frame::{Cfg, Frame};

/// sprite_style.clean_lines on one frame, in place. cfg: rustcore.pack_cfg. protect / prev / nxt
/// may be null. corners: 0 = off, 1 = on, 2 = "inner". Returns the number of pixels changed.
#[no_mangle]
pub unsafe extern "C" fn sc_clean_lines(cfg: *const i64, cfglen: usize, s: *mut u8, h: usize, w: usize,
                                        protect: *const u8, prev: *const u8, nxt: *const u8, corners: i32) -> i32 {
    if h == 0 || w == 0 {
        return 0;
    }
    let cfg = Cfg::parse(std::slice::from_raw_parts(cfg, cfglen));
    let s = std::slice::from_raw_parts_mut(s, h * w * 4);
    let zeros;
    let protect = if protect.is_null() { zeros = vec![0u8; h * w]; &zeros[..] } else { std::slice::from_raw_parts(protect, h * w) };
    let opt = |p: *const u8| if p.is_null() { None } else { Some(std::slice::from_raw_parts(p, h * w * 4)) };
    lines::clean_lines(&cfg, s, h, w, protect, opt(prev), opt(nxt), corners)
}

/// sprite_style.debounce on the stacked loop S (n x h x w x 4), in place; skip (h x w) may be null
#[no_mangle]
pub unsafe extern "C" fn sc_debounce(s: *mut u8, n: usize, h: usize, w: usize, max_run: usize, skip: *const u8) {
    if h == 0 || w == 0 {
        return;
    }
    let skip = if skip.is_null() { None } else { Some(std::slice::from_raw_parts(skip, h * w)) };
    timeline::debounce(s, n, h, w, max_run, skip);
}

/// sprite_style.hard_faults(cfg, s, protect); protect may be null
#[no_mangle]
pub unsafe extern "C" fn sc_hard_faults(cfg: *const i64, cfglen: usize, s: *mut u8, h: usize, w: usize, protect: *const u8) -> i64 {
    if h == 0 || w == 0 {
        return 0;
    }
    let cfg = Cfg::parse(std::slice::from_raw_parts(cfg, cfglen));
    let s = std::slice::from_raw_parts_mut(s, h * w * 4);
    let zeros;
    let protect = if protect.is_null() { zeros = vec![0u8; h * w]; &zeros[..] } else { std::slice::from_raw_parts(protect, h * w) };
    faults::hard_faults(&Frame { h, w, s, protect, cfg: &cfg })
}

/// check_loop.pupil_blobs(s, l) into out (h x w, 0/1)
#[no_mangle]
pub unsafe extern "C" fn sc_pupil_blobs(s: *mut u8, h: usize, w: usize, l: *const u8, out: *mut u8) {
    if h == 0 || w == 0 {
        return;
    }
    let cfg = Cfg { out: 0, dark: vec![], parts: vec![] };
    let zeros = vec![0u8; h * w];
    let f = Frame { h, w, s: std::slice::from_raw_parts_mut(s, h * w * 4), protect: &zeros, cfg: &cfg };
    let l: Vec<bool> = std::slice::from_raw_parts(l, h * w).iter().map(|&v| v != 0).collect();
    let b = faults::pupil_blobs(&f, &l);
    let out = std::slice::from_raw_parts_mut(out, h * w);
    for i in 0..h * w {
        out[i] = b[i] as u8;
    }
}

/// sprite_style.steady_shape's run merging: solid (n x h x w) -> event / src (n x h x w)
#[no_mangle]
pub unsafe extern "C" fn sc_steady_shape(solid: *const u8, n: usize, hw: usize, max_run: usize, event: *mut i8, src: *mut i32) {
    if n == 0 || hw == 0 {
        return;
    }
    timeline::steady_shape(std::slice::from_raw_parts(solid, n * hw), n, hw, max_run,
                           std::slice::from_raw_parts_mut(event, n * hw), std::slice::from_raw_parts_mut(src, n * hw));
}

/// sprite_style.transport_shading_frame's search (rank changed in place)
#[no_mangle]
pub unsafe extern "C" fn sc_transport(h: usize, w: usize, r: *const u8, rk: *const u8, okf: *const u8, okk: *const u8,
                                      part: *const i32, kpart: *const i32, krank: *const i64, rank: *mut i64, search: i64, lim: f64) {
    if h == 0 || w == 0 {
        return;
    }
    let n = h * w;
    timeline::transport(h, w, std::slice::from_raw_parts(r, n * 4), std::slice::from_raw_parts(rk, n * 4),
                        std::slice::from_raw_parts(okf, n), std::slice::from_raw_parts(okk, n),
                        std::slice::from_raw_parts(part, n), std::slice::from_raw_parts(kpart, n),
                        std::slice::from_raw_parts(krank, n), std::slice::from_raw_parts_mut(rank, n), search as isize, lim);
}

/// sprite_style.clean_parts on one frame, in place. bits: rustcore.pack_parts. protect may be null.
#[no_mangle]
pub unsafe extern "C" fn sc_clean_parts(bits: *const i64, bitslen: usize, s: *mut u8, h: usize, w: usize, protect: *const u8) -> i32 {
    if h == 0 || w == 0 {
        return 0;
    }
    let pb = parts::PartBits::parse(std::slice::from_raw_parts(bits, bitslen));
    let s = std::slice::from_raw_parts_mut(s, h * w * 4);
    let zeros;
    let protect = if protect.is_null() { zeros = vec![0u8; h * w]; &zeros[..] } else { std::slice::from_raw_parts(protect, h * w) };
    parts::clean_parts(&pb, s, h, w, protect)
}

/// sprite_style.prepare's high-resolution line mask from the cropped data pass
#[no_mangle]
pub unsafe extern "C" fn sc_hires_lines(d: *const u8, h: usize, w: usize, depth_jump: f64, crease_cos: f64, out: *mut u8) {
    if h == 0 || w == 0 {
        return;
    }
    prep::hires_lines(std::slice::from_raw_parts(d, h * w * 4), h, w, depth_jump, crease_cos, std::slice::from_raw_parts_mut(out, h * w));
}

/// sprite_style.seal_parts on one frame, in place; protect may be null
#[no_mangle]
pub unsafe extern "C" fn sc_seal_parts(cfg: *const i64, cfglen: usize, s: *mut u8, h: usize, w: usize, protect: *const u8) -> i32 {
    if h == 0 || w == 0 {
        return 0;
    }
    let cfg = Cfg::parse(std::slice::from_raw_parts(cfg, cfglen));
    let s = std::slice::from_raw_parts_mut(s, h * w * 4);
    let zeros;
    let protect = if protect.is_null() { zeros = vec![0u8; h * w]; &zeros[..] } else { std::slice::from_raw_parts(protect, h * w) };
    seal::seal_parts(&cfg, s, h, w, protect)
}

/// sprite_style.repair on one frame, in place. cfg: pack_cfg, bits: pack_parts; protect / prev /
/// nxt may be null.
#[no_mangle]
pub unsafe extern "C" fn sc_repair(cfg: *const i64, cfglen: usize, bits: *const i64, bitslen: usize, s: *mut u8, h: usize, w: usize,
                                   protect: *const u8, prev: *const u8, nxt: *const u8) {
    if h == 0 || w == 0 {
        return;
    }
    let cfg = Cfg::parse(std::slice::from_raw_parts(cfg, cfglen));
    let pb = parts::PartBits::parse(std::slice::from_raw_parts(bits, bitslen));
    let s = std::slice::from_raw_parts_mut(s, h * w * 4);
    let zeros;
    let protect = if protect.is_null() { zeros = vec![0u8; h * w]; &zeros[..] } else { std::slice::from_raw_parts(protect, h * w) };
    let opt = |p: *const u8| if p.is_null() { None } else { Some(std::slice::from_raw_parts(p, h * w * 4)) };
    parts::repair(&cfg, &pb, s, h, w, protect, opt(prev), opt(nxt));
}

/// check_loop.short_runs: series (n x hw, int64) -> out (hw), added to
#[no_mangle]
pub unsafe extern "C" fn sc_short_runs(series: *const i64, n: usize, hw: usize, max_len: usize, out: *mut i64) {
    if n == 0 || hw == 0 {
        return;
    }
    qa::short_runs(std::slice::from_raw_parts(series, n * hw), n, hw, max_len, std::slice::from_raw_parts_mut(out, hw));
}

/// flicker_map.pops' biggest patch: returns its summed weight; comp (h*w) gets its pixels, ncomp their number
#[no_mangle]
pub unsafe extern "C" fn sc_best_patch(resid: *const f64, h: usize, w: usize, thr: f64, comp: *mut u32, ncomp: *mut usize) -> f64 {
    if h == 0 || w == 0 {
        *ncomp = 0;
        return 0.0;
    }
    let (best, k) = qa::best_patch(std::slice::from_raw_parts(resid, h * w), h, w, thr, std::slice::from_raw_parts_mut(comp, h * w));
    *ncomp = k;
    best
}

/// linetrace: the lines pass's alpha (h x w) from the projected meshes
#[no_mangle]
pub unsafe extern "C" fn sc_trace_lines(v: *const f64, sx: *const f64, sy: *const f64, z: *const f64, nv: usize, campos: *const f64,
                                        tris: *const i32, nt: usize, loops: *const i32, nl: usize, poly: *const i32, np: usize,
                                        edges: *const i32, ne: usize, w: usize, h: usize, cos_lim: f64, thickness: f64, eps: f64,
                                        kinds: i32, out: *mut u8) {
    if w == 0 || h == 0 {
        return;
    }
    let c = std::slice::from_raw_parts(campos, 3);
    let m = trace::Mesh {
        v: std::slice::from_raw_parts(v, nv * 3), sx: std::slice::from_raw_parts(sx, nv), sy: std::slice::from_raw_parts(sy, nv),
        z: std::slice::from_raw_parts(z, nv), campos: [c[0], c[1], c[2]], tris: std::slice::from_raw_parts(tris, nt * 3),
        loops: std::slice::from_raw_parts(loops, nl), poly: std::slice::from_raw_parts(poly, np * 2),
        edges: std::slice::from_raw_parts(edges, ne * 2),
    };
    trace::trace(&m, w, h, cos_lim, thickness, eps, kinds, std::slice::from_raw_parts_mut(out, w * h));
}
