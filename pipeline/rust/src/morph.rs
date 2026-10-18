//! Boolean / integer image steps of sprite_style (thin, components, edge_distance,
//! part_border_distance), exactly as the Python computes them.

#[inline]
fn get(m: &[bool], h: usize, w: usize, y: isize, x: isize) -> bool {
    y >= 0 && x >= 0 && (y as usize) < h && (x as usize) < w && m[y as usize * w + x as usize]
}

/// Zhang-Suen thinning (sprite_style.thin), in place
pub fn thin(m: &mut [bool], h: usize, w: usize) {
    loop {
        let mut changed = false;
        for step in 0..2 {
            let snap = m.to_vec();
            let mut rem = Vec::new();
            for y in 0..h as isize {
                for x in 0..w as isize {
                    if !snap[y as usize * w + x as usize] {
                        continue;
                    }
                    let g = |dy: isize, dx: isize| get(&snap, h, w, y + dy, x + dx);
                    let (p2, p3, p4, p5) = (g(-1, 0), g(-1, 1), g(0, 1), g(1, 1));
                    let (p6, p7, p8, p9) = (g(1, 0), g(1, -1), g(0, -1), g(-1, -1));
                    let ring = [p2, p3, p4, p5, p6, p7, p8, p9, p2];
                    let b = ring[..8].iter().filter(|&&v| v).count();
                    let a = (0..8).filter(|&k| !ring[k] && ring[k + 1]).count();
                    let c = if step == 0 { !(p2 && p4 && p6) && !(p4 && p6 && p8) } else { !(p2 && p4 && p8) && !(p2 && p6 && p8) };
                    if (2..=6).contains(&b) && a == 1 && c {
                        rem.push(y as usize * w + x as usize);
                    }
                }
            }
            if !rem.is_empty() {
                for i in rem {
                    m[i] = false;
                }
                changed = true;
            }
        }
        if !changed {
            return;
        }
    }
}

/// sprite_style.components: 8-connected groups in the Python's visiting order. Writes the pixels
/// (flat index) group after group into pix, the group sizes into sizes; returns the group count.
pub fn components(m: &[bool], h: usize, w: usize, pix: &mut [u32], sizes: &mut [u32]) -> usize {
    let mut seen = vec![false; h * w];
    let (mut np, mut ng) = (0usize, 0usize);
    let mut st: Vec<(isize, isize)> = Vec::new();
    for start in 0..h * w {
        if !m[start] || seen[start] {
            continue;
        }
        seen[start] = true;
        st.push(((start / w) as isize, (start % w) as isize));
        let first = np;
        while let Some((y, x)) = st.pop() {
            pix[np] = (y as usize * w + x as usize) as u32;
            np += 1;
            for yy in y - 1..=y + 1 {
                for xx in x - 1..=x + 1 {
                    if get(m, h, w, yy, xx) && !seen[yy as usize * w + xx as usize] {
                        seen[yy as usize * w + xx as usize] = true;
                        st.push((yy, xx));
                    }
                }
            }
        }
        sizes[ng] = (np - first) as u32;
        ng += 1;
    }
    ng
}

/// sprite_style.edge_distance: pixels from the nearest non-body pixel (1 = on the edge). The
/// Python erodes repeatedly; a pixel survives k erosions exactly when every pixel within k
/// 4-steps is body, so this is the 4-step distance to the nearest non-body pixel (beyond the
/// canvas counts as non-body), found in one breadth-first pass.
pub fn edge_distance(solid: &[bool], h: usize, w: usize, out: &mut [i64]) {
    let mut q = std::collections::VecDeque::new();
    for y in 0..h {
        for x in 0..w {
            let i = y * w + x;
            if solid[i] && (y == 0 || x == 0 || y == h - 1 || x == w - 1 || !solid[i - w] || !solid[i + w] || !solid[i - 1] || !solid[i + 1]) {
                out[i] = 1;
                q.push_back(i);
            }
        }
    }
    while let Some(i) = q.pop_front() {
        let (y, x) = (i / w, i % w);
        let d = out[i] + 1;
        for j in [if y > 0 { Some(i - w) } else { None }, if y + 1 < h { Some(i + w) } else { None },
                  if x > 0 { Some(i - 1) } else { None }, if x + 1 < w { Some(i + 1) } else { None }].into_iter().flatten() {
            if solid[j] && out[j] == 0 {
                out[j] = d;
                q.push_back(j);
            }
        }
    }
}

/// sprite_style.part_border_distance from the part / other-part masks (eye area already out)
pub fn part_border_distance(pm: &[bool], other: &[bool], h: usize, w: usize, out: &mut [i64]) {
    let near = |m: &[bool], y: isize, x: isize| get(m, h, w, y - 1, x) || get(m, h, w, y + 1, x) || get(m, h, w, y, x - 1) || get(m, h, w, y, x + 1);
    let mut frontier = vec![false; h * w];
    for y in 0..h as isize {
        for x in 0..w as isize {
            let i = y as usize * w + x as usize;
            frontier[i] = pm[i] && near(other, y, x);
        }
    }
    let mut seen = frontier.clone();
    for i in 0..h * w {
        if frontier[i] {
            out[i] = 1;
        }
    }
    let mut k = 1;
    while frontier.iter().any(|&v| v) && k < 16 {
        let mut nxt = vec![false; h * w];
        for y in 0..h as isize {
            for x in 0..w as isize {
                let i = y as usize * w + x as usize;
                nxt[i] = pm[i] && !seen[i] && near(&frontier, y, x);
            }
        }
        k += 1;
        for i in 0..h * w {
            if nxt[i] {
                out[i] = k;
                seen[i] = true;
            }
        }
        frontier = nxt;
    }
}
