//! sprite_style.seal_parts: close every gap in a part outline (an outlined part's pixel touching
//! another part directly), choosing the fix that leaves the fewest 2x2 line blocks + 2-px
//! diagonals. Same candidates in the same order and the same ranking as the Python.

use crate::faults::{blocks, pupil_blobs, stairs};
use crate::frame::{Cfg, Frame, NB4};

fn masks(f: &Frame, p: usize) -> (Vec<bool>, Vec<bool>) {
    let part = &f.cfg.parts[p];
    let n = f.h * f.w;
    let mut own = vec![false; n];
    let mut other = vec![false; n];
    for i in 0..n {
        let (y, x) = ((i / f.w) as isize, (i % f.w) as isize);
        own[i] = f.own(part, y, x);
        other[i] = f.other(part, y, x);
    }
    (own, other)
}

fn line_faults(f: &Frame) -> i64 {
    let l: Vec<bool> = (0..f.h * f.w).map(|i| f.line(i)).collect();
    let blobs = pupil_blobs(f, &l);
    blocks(f, &l, None) + stairs(f, &l, &blobs)
}

pub fn seal_parts(cfg: &Cfg, s: &mut [u8], h: usize, w: usize, protect: &[u8]) -> i32 {
    let out = [(cfg.out >> 16) as u8, (cfg.out >> 8) as u8, cfg.out as u8, 255];
    let at = |y: isize, x: isize| if y >= 0 && x >= 0 && (y as usize) < h && (x as usize) < w { Some(y as usize * w + x as usize) } else { None };
    let mut changed = 0;
    for _ in 0..200 {
        let (contacts, options) = {
            let f = Frame { h, w, s: &mut *s, protect, cfg };
            let contacts = f.leaks();
            if contacts == 0 {
                break;
            }
            let mut options: Vec<(usize, [u8; 4], bool)> = Vec::new();
            for p in 0..cfg.parts.len() {
                let (own, other) = masks(&f, p);
                for (side, opp, own_side) in [(&own, &other, true), (&other, &own, false)] {
                    for i in 0..h * w {
                        let (y, x) = ((i / w) as isize, (i % w) as isize);
                        if !side[i] || !NB4.iter().any(|&(dy, dx)| at(y + dy, x + dx).map_or(false, |j| opp[j])) {
                            continue;
                        }
                        options.push((i, out, own_side));
                        if !NB4.iter().any(|&(dy, dx)| at(y + dy, x + dx).map_or(false, |j| side[j])) {   // a 1-px sliver: absorb it
                            if let Some(j) = NB4.iter().filter_map(|&(dy, dx)| at(y + dy, x + dx)).find(|&j| opp[j]) {
                                let mut v = [0u8; 4];
                                v.copy_from_slice(&f.s[j * 4..j * 4 + 4]);
                                options.push((i, v, own_side));
                            }
                        }
                    }
                }
            }
            (contacts, options)
        };
        let mut best: Option<((i64, i64, bool), usize, [u8; 4])> = None;
        let mut t = s.to_vec();
        for &(i, v, own_side) in &options {
            t.copy_from_slice(s);
            t[i * 4..i * 4 + 4].copy_from_slice(&v);
            let f = Frame { h, w, s: &mut t, protect, cfg };
            let c = f.leaks();
            if c >= contacts {
                continue;
            }
            let key = (line_faults(&f), c, !own_side);
            if best.map_or(true, |(k, _, _)| key < k) {
                best = Some((key, i, v));
            }
        }
        match best {
            None => break,
            Some((_, i, v)) => {
                s[i * 4..i * 4 + 4].copy_from_slice(&v);
                changed += 1;
            }
        }
    }
    changed
}
