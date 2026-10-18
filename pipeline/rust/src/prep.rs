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
