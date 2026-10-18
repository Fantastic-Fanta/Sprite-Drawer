//! sprite_style.clean_parts: a body pixel whose part differs from all its body 4-neighbours takes
//! their most common colour; then 1-px slivers of an outlined part take the other parts' colour.
//! The Python visits only pixels that can change (a heap, re-queueing the later neighbours of a
//! changed pixel); a plain raster scan of every pixel gives the same result, since a pixel the
//! heap skips can't change: its test only reads itself and its 4-neighbours, none changed yet.

use crate::frame::{NB4, NB8};
use crate::pyset::most_common;

pub struct PartBits {
    pub keys: Vec<(u32, u64)>,   // colour -> parts it can belong to (bit per part name)
    pub obit: u64,               // the outline's "part"
    pub outlined: Vec<u64>,      // style.part_outline, as bits
}

impl PartBits {
    /// [n, (key, bits)..., obit, n_outlined, bits...]
    pub fn parse(b: &[i64]) -> PartBits {
        let n = b[0] as usize;
        let keys = (0..n).map(|k| (b[1 + 2 * k] as u32, b[2 + 2 * k] as u64)).collect();
        let obit = b[1 + 2 * n] as u64;
        let m = b[2 + 2 * n] as usize;
        let outlined = (0..m).map(|k| b[3 + 2 * n + k] as u64).collect();
        PartBits { keys, obit, outlined }
    }
    fn of(&self, key: u32) -> u64 {
        self.keys.iter().find(|&&(k, _)| k == key).map_or(0, |&(_, b)| b)
    }
}

pub fn clean_parts(pb: &PartBits, s: &mut [u8], h: usize, w: usize, protect: &[u8]) -> i32 {
    let key = |s: &[u8], i: usize| (s[i * 4] as u32) << 16 | (s[i * 4 + 1] as u32) << 8 | s[i * 4 + 2] as u32;
    let at = |y: isize, x: isize| if y >= 0 && x >= 0 && (y as usize) < h && (x as usize) < w { Some(y as usize * w + x as usize) } else { None };
    let set = |s: &mut [u8], i: usize, k: u32| { s[i * 4] = (k >> 16) as u8; s[i * 4 + 1] = (k >> 8) as u8; s[i * 4 + 2] = k as u8; };
    let mut changed = 0;
    // stray pixels
    for i in 0..h * w {
        if s[i * 4 + 3] == 0 || protect[i] != 0 {
            continue;
        }
        let me = pb.of(key(s, i));
        if me == 0 || me == pb.obit {
            continue;
        }
        let (y, x) = ((i / w) as isize, (i % w) as isize);
        let mut nbs = Vec::with_capacity(4);
        let mut clash = false;
        for &(dy, dx) in NB4.iter() {
            if let Some(j) = at(y + dy, x + dx) {
                if s[j * 4 + 3] > 0 && protect[j] == 0 {
                    let k = key(s, j);
                    let b = pb.of(k);
                    if b != 0 && b != pb.obit {
                        nbs.push(k);
                        clash |= b & me != 0;
                    }
                }
            }
        }
        if nbs.len() >= 2 && !clash {
            let new = most_common(&nbs);
            if key(s, i) != new {
                set(s, i, new);
                changed += 1;
            }
        }
    }
    // 1-px slivers of each outlined part
    for &bit in &pb.outlined {
        for i in 0..h * w {
            if s[i * 4 + 3] == 0 || protect[i] != 0 || pb.of(key(s, i)) != bit {
                continue;
            }
            let (y, x) = ((i / w) as isize, (i % w) as isize);
            if NB4.iter().any(|&(dy, dx)| at(y + dy, x + dx).map_or(false, |j| s[j * 4 + 3] > 0 && pb.of(key(s, j)) & bit != 0)) {
                continue;
            }
            let mut cols = Vec::with_capacity(8);
            for &(dy, dx) in NB8.iter() {
                if let Some(j) = at(y + dy, x + dx) {
                    if s[j * 4 + 3] > 0 && protect[j] == 0 {
                        let b = pb.of(key(s, j));
                        if b != 0 && b != pb.obit && b & bit == 0 {
                            cols.push(key(s, j));
                        }
                    }
                }
            }
            if !cols.is_empty() {
                let new = most_common(&cols);
                if key(s, i) != new {
                    set(s, i, new);
                    changed += 1;
                }
            }
        }
    }
    changed
}

/// sprite_style.repair: re-close the outline (no body pixel touching transparency), fill 1-px
/// dents in the silhouette, then clean_parts, seal_parts (outlined parts) and clean_lines without
/// corner pruning, preferring fixes that agree with the neighbouring frames.
pub fn repair(cfg: &crate::frame::Cfg, pb: &PartBits, s: &mut [u8], h: usize, w: usize, protect: &[u8],
              prev: Option<&[u8]>, nxt: Option<&[u8]>) {
    let n = h * w;
    let out = [(cfg.out >> 16) as u8, (cfg.out >> 8) as u8, cfg.out as u8, 255];
    let key = |s: &[u8], i: usize| (s[i * 4] as u32) << 16 | (s[i * 4 + 1] as u32) << 8 | s[i * 4 + 2] as u32;
    let at = |y: isize, x: isize| if y >= 0 && x >= 0 && (y as usize) < h && (x as usize) < w { Some(y as usize * w + x as usize) } else { None };
    // gaps: outside pixels next to the body become outline
    let body: Vec<bool> = (0..n).map(|i| s[i * 4 + 3] > 0 && key(s, i) != cfg.out).collect();
    let solid: Vec<bool> = (0..n).map(|i| s[i * 4 + 3] > 0).collect();
    for i in 0..n {
        let (y, x) = ((i / w) as isize, (i % w) as isize);
        if !solid[i] && NB4.iter().any(|&(dy, dx)| at(y - dy, x - dx).map_or(false, |j| body[j])) {
            s[i * 4..i * 4 + 4].copy_from_slice(&out);
        }
    }
    // 1-px dents: an outside pixel boxed in by outline on 3 sides, on a straight run
    let solid: Vec<bool> = (0..n).map(|i| s[i * 4 + 3] > 0).collect();
    let line: Vec<bool> = (0..n).map(|i| solid[i] && key(s, i) == cfg.out).collect();
    let l = |y: isize, x: isize| at(y, x).map_or(false, |j| line[j]);
    let dents: Vec<usize> = (0..n).filter(|&i| {
        let (y, x) = ((i / w) as isize, (i % w) as isize);
        !solid[i] && NB4.iter().filter(|&&(dy, dx)| l(y + dy, x + dx)).count() >= 3
            && ((l(y, x - 1) && l(y, x + 1)) || (l(y - 1, x) && l(y + 1, x)))
    }).collect();
    for i in dents {
        s[i * 4..i * 4 + 4].copy_from_slice(&out);
    }
    clean_parts(pb, s, h, w, protect);
    if !cfg.parts.is_empty() {
        crate::seal::seal_parts(cfg, s, h, w, protect);
    }
    crate::lines::clean_lines(cfg, s, h, w, protect, prev, nxt, 0);
}
