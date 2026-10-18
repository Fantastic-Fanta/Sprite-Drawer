//! Parts of sprite_style.prepare that work at full render resolution.

/// prepare's hires_lines: depth jumps and folds found on the full-size data pass (normal in R/G,
/// depth in B). Same float operations in the same order as the numpy code, so the same pixels.
pub fn hires_lines(d: &[u8], h: usize, w: usize, depth_jump: f64, crease_cos: f64, out: &mut [u8]) {
    let n = h * w;
    let mut nh = vec![[0f64; 3]; n];
    for i in 0..n {
        let nx = d[i * 4] as f64 / 255.0 * 2.0 - 1.0;
        let ny = d[i * 4 + 1] as f64 / 255.0 * 2.0 - 1.0;
        nh[i] = [nx, ny, (1.0 - nx * nx - ny * ny).clamp(0.0, 1.0).sqrt()];
    }
    let ok = |y: isize, x: isize| y >= 0 && x >= 0 && (y as usize) < h && (x as usize) < w && d[(y as usize * w + x as usize) * 4 + 3] > 0;
    let dep = |y: isize, x: isize| d[(y as usize * w + x as usize) * 4 + 2] as f64;
    for y in 0..h as isize {
        for x in 0..w as isize {
            let i = y as usize * w + x as usize;
            out[i] = 0;
            if d[i * 4 + 3] == 0 {
                continue;
            }
            for &(dy, dx) in crate::frame::NB4.iter() {
                let (py, px, qy, qx) = (y - dy, x - dx, y + dy, x + dx);   // shift(a, dy, dx)[y, x] = a[y - dy, x - dx]
                if !(ok(py, px) && ok(qy, qx)) {
                    continue;
                }
                let jump = dep(py, px) - dep(y, x);
                let other = dep(y, x) - dep(qy, qx);
                if jump > depth_jump && jump - other > depth_jump {
                    out[i] = 1;
                    break;
                }
                let s = nh[py as usize * w + px as usize];
                let bend = nh[i][0] * s[0] + nh[i][1] * s[1] + nh[i][2] * s[2];
                if bend < crease_cos && jump >= 0.0 {
                    out[i] = 1;
                    break;
                }
            }
        }
    }
}

/// prepare's cast shadow at full resolution: blocked = facing the sun but under 35% of its light,
/// unlit = the sun doesn't reach it (data pass: normal in R/G; shadow pass: lit white in R)
pub fn cast_shadow(d: &[u8], s: &[u8], n: usize, l: [f64; 3], blocked: &mut [u8], unlit: &mut [u8]) {
    for i in 0..n {
        let nx = d[i * 4] as f64 / 255.0 * 2.0 - 1.0;
        let ny = d[i * 4 + 1] as f64 / 255.0 * 2.0 - 1.0;
        let nz = (1.0 - nx * nx - ny * ny).clamp(0.0, 1.0).sqrt();
        let cos = nx * l[0] + ny * l[1] + nz * l[2];
        let lit = s[i * 4] as f64 / 255.0;
        let sh = s[i * 4 + 3] > 127;
        blocked[i] = (sh && d[i * 4 + 3] > 0 && cos > 0.15 && lit < 0.35 * cos) as u8;
        unlit[i] = (sh && lit < 0.08) as u8;
    }
}

/// sprite_style.matcap_light: bilinear lookup of the matcap (size x size) by normal x, y
pub fn matcap_light(nx: &[f64], ny: &[f64], m: &[f64], size: usize, out: &mut [f64]) {
    let nf = size as f64;
    let top = (size - 1) as f64;
    for i in 0..nx.len() {
        let fx = ((nx[i] + 1.0) / 2.0 * nf - 0.5).clamp(0.0, top);
        let fy = ((ny[i] + 1.0) / 2.0 * nf - 0.5).clamp(0.0, top);
        let (x0, y0) = (fx.floor() as usize, fy.floor() as usize);
        let (x1, y1) = ((x0 + 1).min(size - 1), (y0 + 1).min(size - 1));
        let (tx, ty) = (fx - x0 as f64, fy - y0 as f64);
        out[i] = (m[y0 * size + x0] * (1.0 - tx) * (1.0 - ty) + m[y0 * size + x1] * tx * (1.0 - ty)
            + m[y1 * size + x0] * (1.0 - tx) * ty + m[y1 * size + x1] * tx * ty) * 2.0 - 1.0;
    }
}
