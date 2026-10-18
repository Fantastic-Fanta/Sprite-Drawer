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
