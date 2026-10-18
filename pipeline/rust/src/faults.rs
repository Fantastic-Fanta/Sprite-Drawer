//! The hard rules, counted exactly as check_loop counts them (sprite_style.hard_faults):
//! 2x2 line blocks + 2-px diagonals (staircase corners, lines hugging the outline) + open
//! outline / part leakage. Pupils (small dark blobs inside the body) aren't lines.

use crate::frame::{Frame, NB4, NB8};

/// check_loop.pupil_blobs: 8-connected groups of `l` within 5x5 that don't touch the outside
pub fn pupil_blobs(f: &Frame, l: &[bool]) -> Vec<bool> {
    let (h, w) = (f.h, f.w);
    let mut seen = vec![false; h * w];
    let mut blob = vec![false; h * w];
    let mut stack = Vec::new();
    let mut comp = Vec::new();
    for start in 0..h * w {
        if !l[start] || seen[start] {
            continue;
        }
        seen[start] = true;
        stack.push(start);
        comp.clear();
        while let Some(i) = stack.pop() {
            comp.push(i);
            let (y, x) = ((i / w) as isize, (i % w) as isize);
            for dy in -1..=1 {
                for dx in -1..=1 {
                    if let Some(j) = f.at(y + dy, x + dx) {
                        if l[j] && !seen[j] {
                            seen[j] = true;
                            stack.push(j);
                        }
                    }
                }
            }
        }
        let (mut y0, mut y1, mut x0, mut x1) = (usize::MAX, 0, usize::MAX, 0);
        for &i in &comp {
            y0 = y0.min(i / w); y1 = y1.max(i / w); x0 = x0.min(i % w); x1 = x1.max(i % w);
        }
        if y1 - y0 < 5 && x1 - x0 < 5 && !comp.iter().any(|&i| f.touches_out((i / w) as isize, (i % w) as isize)) {
            for &i in &comp {
                blob[i] = true;
            }
        }
    }
    blob
}

pub fn hard_faults(f: &Frame) -> i64 {
    let (h, w) = (f.h, f.w);
    let n = h * w;
    let l: Vec<bool> = (0..n).map(|i| f.line(i)).collect();
    let blobs = pupil_blobs(f, &l);
    let m = |y: isize, x: isize| f.at(y, x).map_or(false, |i| l[i]);
    let mut count = 0i64;
    // line_blocks: 2x2 blocks of line pixels (pupils excluded)
    for y in 0..h.saturating_sub(1) {
        for x in 0..w.saturating_sub(1) {
            if [(0, 0), (1, 0), (0, 1), (1, 1)].iter().all(|&(a, b)| { let i = (y + a) * w + x + b; l[i] && !blobs[i] }) {
                count += 1;
            }
        }
    }
    // stairs, with separators kept (a corner there is a T-junction)
    let to = |y: isize, x: isize| f.touches_out(y, x);
    for i in 0..n {
        if !l[i] || blobs[i] {
            continue;
        }
        let (y, x) = ((i / w) as isize, (i % w) as isize);
        if f.separator(y, x, i) {
            continue;
        }
        let (up, dn, lf, rt) = (m(y - 1, x), m(y + 1, x), m(y, x - 1), m(y, x + 1));
        let (ul, ur, dl, dr) = (m(y - 1, x - 1), m(y - 1, x + 1), m(y + 1, x - 1), m(y + 1, x + 1));
        let tb = NB4.iter().any(|&(dy, dx)| f.at(y + dy, x + dx).map_or(false, |j| f.solid(j) && !l[j]));
        let t_out = to(y, x);
        let corner = ((up && lf && !dn && !rt && !ul) || (up && rt && !dn && !lf && !ur)
            || (dn && lf && !up && !rt && !dl) || (dn && rt && !up && !lf && !dr)) && !(tb && t_out);
        let rn = NB8.iter().filter(|&&(dy, dx)| m(y + dy, x + dx) && to(y + dy, x + dx)).count();
        let along = !t_out && rn >= 2;
        if corner || along {
            count += 1;
        }
    }
    // open outline: body touching the outside, outlined part touching another part
    for i in 0..n {
        let (y, x) = ((i / w) as isize, (i % w) as isize);
        if f.solid(i) && !l[i] && f.protect[i] == 0 && !f.line_all(i) && to(y, x) {
            count += 1;
        }
    }
    count + f.leaks()
}
