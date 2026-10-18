//! Loop checks for qa.py, as check_loop.short_runs and flicker_map.pops count them.

/// check_loop.short_runs: per pixel, runs (cyclic) of length <= max_len in its series over the loop
pub fn short_runs(series: &[i64], n: usize, hw: usize, max_len: usize, out: &mut [i64]) {
    let mut t = vec![0i64; n];
    for p in 0..hw {
        let first = series[p];
        if (0..n).all(|f| series[f * hw + p] == first) {
            continue;
        }
        let last = series[(n - 1) * hw + p];
        let k = (0..n).position(|f| series[f * hw + p] != last).unwrap_or(0);
        for i in 0..n {
            t[i] = series[((i + k) % n) * hw + p];
        }
        let mut len = 1;
        for i in 1..=n {
            if i < n && t[i] == t[i - 1] {
                len += 1;
            } else {
                out[p] += (len <= max_len) as i64;
                len = 1;
            }
        }
    }
}

/// flicker_map.pops' patch search: the 8-connected group of resid > thr with the biggest summed
/// resid (summed in the Python's visiting order); its pixels go to comp (visiting order), and the
/// return value is (sum, number of pixels)
pub fn best_patch(resid: &[f64], h: usize, w: usize, thr: f64, comp_out: &mut [u32]) -> (f64, usize) {
    let mut seen = vec![false; h * w];
    let (mut best, mut best_comp): (f64, Vec<u32>) = (0.0, Vec::new());
    let mut st: Vec<usize> = Vec::new();
    let mut comp: Vec<u32> = Vec::new();
    for start in 0..h * w {
        if !(resid[start] > thr) || seen[start] {
            continue;
        }
        st.clear(); comp.clear();
        st.push(start);
        seen[start] = true;
        while let Some(i) = st.pop() {
            comp.push(i as u32);
            let (y, x) = ((i / w) as isize, (i % w) as isize);
            for yy in y - 1..=y + 1 {
                for xx in x - 1..=x + 1 {
                    if yy >= 0 && xx >= 0 && (yy as usize) < h && (xx as usize) < w {
                        let j = yy as usize * w + xx as usize;
                        if resid[j] > thr && !seen[j] {
                            seen[j] = true;
                            st.push(j);
                        }
                    }
                }
            }
        }
        let mut wsum = 0.0f64;                     // Python: sum(...) starting from int 0
        for &i in &comp {
            wsum += resid[i as usize];
        }
        if wsum > best {
            best = wsum;
            best_comp = comp.clone();
        }
    }
    comp_out[..best_comp.len()].copy_from_slice(&best_comp);
    (best, best_comp.len())
}
