//! Rust versions of sprite_style.py's per-pixel rules, called through ctypes (rustcore.py).
//! Every function reproduces its Python original exactly, tie-breaks included: Python's
//! `max(set(cols), key=cols.count)` follows CPython's set iteration order, emulated in `pyset`.

mod pyset;
mod frame;
mod lines;
mod timeline;
mod faults;

use frame::{Cfg, Frame};

/// sprite_style.clean_lines on one frame, in place. cfg: rustcore.pack_cfg. protect / prev / nxt
/// may be null. corners: 0 = off, 1 = on, 2 = "inner". Returns the number of pixels changed.
#[no_mangle]
pub unsafe extern "C" fn sc_clean_lines(cfg: *const i64, cfglen: usize, s: *mut u8, h: usize, w: usize,
                                        protect: *const u8, prev: *const u8, nxt: *const u8, corners: i32) -> i32 {
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
    let skip = if skip.is_null() { None } else { Some(std::slice::from_raw_parts(skip, h * w)) };
    timeline::debounce(s, n, h, w, max_run, skip);
}

/// sprite_style.hard_faults(cfg, s, protect); protect may be null
#[no_mangle]
pub unsafe extern "C" fn sc_hard_faults(cfg: *const i64, cfglen: usize, s: *mut u8, h: usize, w: usize, protect: *const u8) -> i64 {
    let cfg = Cfg::parse(std::slice::from_raw_parts(cfg, cfglen));
    let s = std::slice::from_raw_parts_mut(s, h * w * 4);
    let zeros;
    let protect = if protect.is_null() { zeros = vec![0u8; h * w]; &zeros[..] } else { std::slice::from_raw_parts(protect, h * w) };
    faults::hard_faults(&Frame { h, w, s, protect, cfg: &cfg })
}
