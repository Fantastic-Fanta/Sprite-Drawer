//! Per-pixel rules over the loop (time): sprite_style.debounce. Each pixel's history is
//! independent, so the pixels are split over threads.

/// the runs of equal values around the loop, starting at a change (as the Python builds them)
fn runs(seq: &[i64]) -> Vec<Vec<usize>> {
    let n = seq.len();
    let start = if seq.iter().any(|&v| v != seq[0]) { seq.iter().position(|&v| v != seq[n - 1]).unwrap() } else { 0 };
    let mut out: Vec<Vec<usize>> = Vec::new();
    let mut cur = vec![start];
    for k in 1..n {
        let i = (start + k) % n;
        if seq[i] == seq[cur[0]] {
            cur.push(i);
        } else {
            out.push(std::mem::replace(&mut cur, vec![i]));
        }
    }
    out.push(cur);
    out
}

/// one pixel's frames (n x 4 bytes, `stride` apart in `s`): any colour lasting max_run frames or
/// fewer takes the longer neighbouring run's colour
unsafe fn debounce_pixel(s: *mut u8, off: usize, stride: usize, n: usize, max_run: usize) {
    let px = |f: usize| s.add(off + f * stride);
    let key = |f: usize| -> i64 {
        let p = px(f);
        if *p.add(3) > 0 { (*p as i64) << 16 | (*p.add(1) as i64) << 8 | *p.add(2) as i64 } else { -1 }
    };
    let mut seq: Vec<i64> = (0..n).map(key).collect();
    if seq.iter().all(|&v| v == seq[0]) {
        return;
    }
    for _ in 0..n {
        let rs = runs(&seq);
        if rs.len() < 2 {
            break;
        }
        // min(short, key=len): the first of the shortest runs
        let mut k = usize::MAX;
        for (j, r) in rs.iter().enumerate() {
            if r.len() <= max_run && (k == usize::MAX || r.len() < rs[k].len()) {
                k = j;
            }
        }
        if k == usize::MAX {
            break;
        }
        let before = &rs[(k + rs.len() - 1) % rs.len()];
        let after = &rs[(k + 1) % rs.len()];
        let src = if before.len() >= after.len() { before[0] } else { after[0] };
        for &i in &rs[k] {
            seq[i] = seq[src];
            std::ptr::copy_nonoverlapping(px(src), px(i), 4);
        }
    }
}

struct Ptr(*mut u8);
unsafe impl Send for Ptr {}
unsafe impl Sync for Ptr {}

/// sprite_style.debounce on S (n x h x w x 4, in place); skip (h x w) may be null
pub unsafe fn debounce(s: *mut u8, n: usize, h: usize, w: usize, max_run: usize, skip: Option<&[u8]>) {
    let stride = h * w * 4;
    let threads = std::thread::available_parallelism().map_or(1, |v| v.get()).min(h.max(1));
    let rows_per = (h + threads - 1) / threads;
    let base = Ptr(s);
    std::thread::scope(|sc| {
        for t in 0..threads {
            let base = &base;
            sc.spawn(move || {
                for y in t * rows_per..((t + 1) * rows_per).min(h) {
                    for x in 0..w {
                        if skip.map_or(false, |m| m[y * w + x] != 0) {
                            continue;
                        }
                        debounce_pixel(base.0, (y * w + x) * 4, stride, n, max_run);
                    }
                }
            });
        }
    });
}

/// sprite_style.steady_shape's per-pixel part: being in the shape or not must last more than
/// max_run frames. Per frame and pixel it returns what the Python does last there:
/// event -1 = untouched, 0 = dropped from the shape, 1 = filled; src = the frame whose data was
/// copied by the last fill (-1 = none). solid: n x h x w (0/1).
pub fn steady_shape(solid: &[u8], n: usize, hw: usize, max_run: usize, event: &mut [i8], src_out: &mut [i32]) {
    for p in 0..hw {
        let first = solid[p];
        if (0..n).all(|f| solid[f * hw + p] == first) {
            continue;
        }
        let mut seq: Vec<i64> = (0..n).map(|f| solid[f * hw + p] as i64).collect();
        for _ in 0..n {
            let rs = runs(&seq);
            let mut k = usize::MAX;
            for (j, r) in rs.iter().enumerate() {
                if r.len() <= max_run && (k == usize::MAX || r.len() < rs[k].len()) {
                    k = j;
                }
            }
            if rs.len() < 2 || k == usize::MAX {
                break;
            }
            let before = &rs[(k + rs.len() - 1) % rs.len()];
            let after = &rs[(k + 1) % rs.len()];
            let src_is_before = before.len() >= after.len();
            let src = if src_is_before { before } else { after };
            let j = if src_is_before { src[src.len() - 1] } else { src[0] };   // nearest frame in time
            for &i in &rs[k] {
                seq[i] = seq[src[0]];
                event[i * hw + p] = seq[i] as i8;
                if seq[i] != 0 {
                    src_out[i * hw + p] = j as i32;
                }
            }
        }
    }
}

/// sprite_style.transport_shading_frame: each pixel takes the rank of the key-frame pixel showing
/// the same surface spot (nearest rest position within +-search px, same part, within tol)
pub fn transport(h: usize, w: usize, r: &[u8], rk: &[u8], okf: &[u8], okk: &[u8], part: &[i32], kpart: &[i32],
                 krank: &[i64], rank: &mut [i64], search: isize, lim: f64) {
    for y in 0..h as isize {
        for x in 0..w as isize {
            let i = y as usize * w + x as usize;
            if okf[i] == 0 {
                continue;
            }
            let mut best = f64::INFINITY;
            let mut got = rank[i];
            for dy in -search..=search {
                for dx in -search..=search {
                    let (sy, sx) = (y + dy, x + dx);
                    if sy < 0 || sx < 0 || sy >= h as isize || sx >= w as isize {
                        continue;
                    }
                    let j = sy as usize * w + sx as usize;
                    if okk[j] == 0 || part[i] != kpart[j] {
                        continue;
                    }
                    let mut d2 = 0i64;
                    for c in 0..3 {
                        let e = r[i * 4 + c] as i64 - rk[j * 4 + c] as i64;
                        d2 += e * e;
                    }
                    let d = d2 as f64 + 0.01 * ((dy * dy + dx * dx) as f64);
                    if d < best {
                        best = d;
                        got = krank[j];
                    }
                }
            }
            if best <= lim {
                rank[i] = got;
            }
        }
    }
}
