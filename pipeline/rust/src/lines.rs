//! sprite_style.clean_lines: every line pixel-perfect and 1 px wide (see the Python docstring).

use crate::frame::{Cfg, Frame, NB8};
use crate::pyset::most_common;

struct Ctx<'a> {
    f: Frame<'a>,
    prev: Option<&'a [u8]>,
    nxt: Option<&'a [u8]>,
    corners: i32,
}

impl<'a> Ctx<'a> {
    fn cand(&self, y: isize, x: isize, i: usize) -> bool {
        let f = &self.f;
        if !f.line(i) {
            return false;                 // corner, along and in_block all need a changeable line pixel
        }
        let la = |dy: isize, dx: isize| f.nb(y, x, dy, dx, |j| f.line_all(j));
        let (up, dn, lf, rt) = (la(-1, 0), la(1, 0), la(0, -1), la(0, 1));
        let (ul, ur, dl, dr) = (la(-1, -1), la(-1, 1), la(1, -1), la(1, 1));
        let touches_out = f.touches_out(y, x);
        let required = (f.touches_body(y, x) && touches_out && f.is_out(i)) || f.separator(y, x, i);
        if required {
            return false;
        }
        let mut corner = (up && lf && !dn && !rt && !ul) || (up && rt && !dn && !lf && !ur)
            || (dn && lf && !up && !rt && !dl) || (dn && rt && !up && !lf && !dr);
        match self.corners {
            0 => corner = false,
            2 => corner &= !touches_out,
            _ => {}
        }
        let ring = |yy: isize, xx: isize| f.at(yy, xx).map_or(false, |j| f.line(j) && f.touches_out(yy, xx));
        let ring_n8 = NB8.iter().filter(|&&(dy, dx)| ring(y + dy, x + dx)).count();
        let along = !touches_out && ring_n8 >= 2;
        let blk = |yy: isize, xx: isize| {
            yy >= 0 && xx >= 0 && (yy as usize) + 1 < f.h && (xx as usize) + 1 < f.w
                && [(0, 0), (1, 0), (0, 1), (1, 1)].iter().all(|&(a, b)| f.line_all(f.at(yy + a, xx + b).unwrap()))
        };
        let in_block = blk(y, x) || blk(y - 1, x) || blk(y, x - 1) || blk(y - 1, x - 1);
        corner || along || in_block
    }

    fn new_value(&self, y: isize, x: isize, i: usize) -> [u8; 4] {
        let f = &self.f;
        if f.touches_out(y, x) && f.is_out(i) {       // an outline pixel: drop it
            return [0; 4];
        }
        let mut cols = Vec::with_capacity(8);
        for &(dy, dx) in NB8.iter() {
            if let Some(j) = f.at(y + dy, x + dx) {
                if f.body(j) {
                    cols.push(f.key(j));
                }
            }
        }
        if cols.is_empty() {
            return [0; 4];
        }
        let mut pick = most_common(&cols);
        for o in [self.prev, self.nxt].into_iter().flatten() {   // prefer what the neighbouring frames show
            let k = (o[i * 4] as u32) << 16 | (o[i * 4 + 1] as u32) << 8 | o[i * 4 + 2] as u32;
            if o[i * 4 + 3] > 0 && cols.contains(&k) {
                pick = k;
                break;
            }
        }
        [(pick >> 16) as u8, (pick >> 8) as u8, pick as u8, 255]
    }

    fn score(&self, i: usize, v: &[u8; 4]) -> i8 {
        [self.prev, self.nxt].into_iter().flatten().filter(|o| &o[i * 4..i * 4 + 4] == v).count() as i8
    }

    fn eval(&self, y: usize, x: usize, score: &mut [i8], value: &mut [[u8; 4]]) {
        let i = y * self.f.w + x;
        let (yi, xi) = (y as isize, x as isize);
        if self.cand(yi, xi, i) {
            let v = self.new_value(yi, xi, i);
            score[i] = self.score(i, &v);
            value[i] = v;
        } else {
            score[i] = -1;
        }
    }
}

pub fn clean_lines(cfg: &Cfg, s: &mut [u8], h: usize, w: usize, protect: &[u8], prev: Option<&[u8]>, nxt: Option<&[u8]>, corners: i32) -> i32 {
    let mut c = Ctx { f: Frame::new(h, w, s, protect, cfg), prev, nxt, corners };
    let mut score = vec![-1i8; h * w];
    let mut value = vec![[0u8; 4]; h * w];
    for y in 0..h {
        for x in 0..w {
            c.eval(y, x, &mut score, &mut value);
        }
    }
    // fix first the candidate whose new colour agrees with the neighbouring frames; ties: raster
    // order. A fix changes candidates within 2 px only, so only that window is re-checked.
    const R: usize = 3;
    let mut changed = 0;
    for _ in 0..400 {
        let mut best = 0;
        for (k, &v) in score.iter().enumerate() {
            if v > score[best] {
                best = k;
            }
        }
        if score[best] < 0 {
            break;
        }
        c.f.s[best * 4..best * 4 + 4].copy_from_slice(&value[best]);
        c.f.refresh(best);
        changed += 1;
        let (y, x) = (best / w, best % w);
        for yy in y.saturating_sub(R)..(y + R + 1).min(h) {
            for xx in x.saturating_sub(R)..(x + R + 1).min(w) {
                c.eval(yy, xx, &mut score, &mut value);
            }
        }
    }
    changed
}
