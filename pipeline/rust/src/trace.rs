//! linetrace.trace_numpy in Rust: the lines pass from the mesh's own edges. Same operations in
//! the same order as the numpy reference, so the same pixels.

use std::collections::HashMap;

pub struct Mesh<'a> {
    pub v: &'a [f64],        // nv x 3, world
    pub sx: &'a [f64],
    pub sy: &'a [f64],
    pub z: &'a [f64],        // NDC depth
    pub campos: [f64; 3],
    pub tris: &'a [i32],     // nt x 3
    pub loops: &'a [i32],
    pub poly: &'a [i32],     // np x 2: loop start, count
    pub edges: &'a [i32],    // ne x 2
}

const SS: usize = 4;

/// kinds: 1 = borders, 2 = silhouettes, 4 = creases
pub fn trace(m: &Mesh, w: usize, h: usize, cos_lim: f64, thickness: f64, eps: f64, kinds: i32, out: &mut [u8]) {
    // depth buffer: nearest NDC depth per pixel centre
    let mut zb = vec![f64::INFINITY; w * h];
    for t in m.tris.chunks_exact(3) {
        let (a, b, c) = (t[0] as usize, t[1] as usize, t[2] as usize);
        let xs = [m.sx[a], m.sx[b], m.sx[c]];
        let ys = [m.sy[a], m.sy[b], m.sy[c]];
        let x0 = ((xs[0].min(xs[1]).min(xs[2]) - 0.5).floor() as i64).max(0);
        let x1 = ((xs[0].max(xs[1]).max(xs[2]) - 0.5).ceil() as i64).min(w as i64 - 1);
        let y0 = ((ys[0].min(ys[1]).min(ys[2]) - 0.5).floor() as i64).max(0);
        let y1 = ((ys[0].max(ys[1]).max(ys[2]) - 0.5).ceil() as i64).min(h as i64 - 1);
        if x1 < x0 || y1 < y0 {
            continue;
        }
        let den = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2]);
        if den.abs() < 1e-12 {
            continue;
        }
        for yi in y0..=y1 {
            let py = yi as f64 + 0.5;
            for xi in x0..=x1 {
                let px = xi as f64 + 0.5;
                let l0 = ((ys[1] - ys[2]) * (px - xs[2]) + (xs[2] - xs[1]) * (py - ys[2])) / den;
                let l1 = ((ys[2] - ys[0]) * (px - xs[2]) + (xs[0] - xs[2]) * (py - ys[2])) / den;
                let l2 = 1.0 - l0 - l1;
                if l0 >= 0.0 && l1 >= 0.0 && l2 >= 0.0 {
                    let zz = l0 * m.z[a] + l1 * m.z[b] + l2 * m.z[c];
                    let k = yi as usize * w + xi as usize;
                    if zz < zb[k] {
                        zb[k] = zz;
                    }
                }
            }
        }
    }
    // faces: normal (Newell), facing the camera or not; edges -> their faces
    let nf = m.poly.len() / 2;
    let mut nrm = vec![[0f64; 3]; nf];
    let mut front = vec![false; nf];
    let mut adj: HashMap<(i32, i32), Vec<usize>> = HashMap::new();
    for k in 0..nf {
        let (ls, lt) = (m.poly[2 * k] as usize, m.poly[2 * k + 1] as usize);
        let vi = &m.loops[ls..ls + lt];
        let (mut n0, mut n1, mut n2, mut c0, mut c1, mut c2) = (0f64, 0f64, 0f64, 0f64, 0f64, 0f64);
        for i in 0..lt {
            let (pi, qi) = (vi[i] as usize, vi[(i + 1) % lt] as usize);
            let (p, q) = (&m.v[pi * 3..pi * 3 + 3], &m.v[qi * 3..qi * 3 + 3]);
            n0 += (p[1] - q[1]) * (p[2] + q[2]);
            n1 += (p[2] - q[2]) * (p[0] + q[0]);
            n2 += (p[0] - q[0]) * (p[1] + q[1]);
            c0 += p[0]; c1 += p[1]; c2 += p[2];
            let e = (vi[i].min(vi[(i + 1) % lt]), vi[i].max(vi[(i + 1) % lt]));
            adj.entry(e).or_default().push(k);
        }
        let ln = (n0 * n0 + n1 * n1 + n2 * n2).sqrt() + 1e-20;
        nrm[k] = [n0 / ln, n1 / ln, n2 / ln];
        let (c0, c1, c2) = (c0 / lt as f64 - m.campos[0], c1 / lt as f64 - m.campos[1], c2 / lt as f64 - m.campos[2]);
        front[k] = n0 * c0 + n1 * c1 + n2 * c2 < 0.0;
    }
    // lines: borders, silhouettes, creases; visible samples stamped as stroke-wide discs
    let r = thickness / 2.0 * SS as f64;
    let rr = r.ceil() as i64;
    let mut disc = Vec::new();
    for dy in -rr..=rr {
        for dx in -rr..=rr {
            if ((dx * dx + dy * dy) as f64) <= r * r {
                disc.push((dy, dx));
            }
        }
    }
    let (cw, ch) = ((w * SS) as i64, (h * SS) as i64);
    let mut cov = vec![false; w * h * SS * SS];
    for e in m.edges.chunks_exact(2) {
        let (a, b) = (e[0], e[1]);
        let fs = adj.get(&(a.min(b), a.max(b))).map_or(&[][..], |v| &v[..]);
        if fs.len() == 2 {
            let (f0, f1) = (fs[0], fs[1]);
            let d = nrm[f0][0] * nrm[f1][0] + nrm[f0][1] * nrm[f1][1] + nrm[f0][2] * nrm[f1][2];
            if !((kinds & 2 != 0 && front[f0] != front[f1]) || (kinds & 4 != 0 && d < cos_lim)) {
                continue;
            }
        } else if fs.len() != 1 || kinds & 1 == 0 {
            continue;
        }
        let (a, b) = (a as usize, b as usize);
        let (xa, ya, za) = (m.sx[a], m.sy[a], m.z[a]);
        let (dxe, dye, dze) = (m.sx[b] - xa, m.sy[b] - ya, m.z[b] - za);
        let n = (((dxe.hypot(dye) * 2.0) as i64) + 1).max(2);
        let step = 1.0 / (n - 1) as f64;
        for i in 0..n {
            let t = if i == n - 1 { 1.0 } else { i as f64 * step };
            let (x, y, zz) = (xa + dxe * t, ya + dye * t, za + dze * t);
            let (ix, iy) = (x.floor() as i64, y.floor() as i64);
            if ix < 0 || iy < 0 || ix >= w as i64 || iy >= h as i64 || !(zz <= zb[iy as usize * w + ix as usize] + eps) {
                continue;
            }
            let (cx, cy) = ((x * SS as f64) as i64, (y * SS as f64) as i64);
            for &(dy, dx) in &disc {
                let (qx, qy) = (cx + dx, cy + dy);
                if qx >= 0 && qy >= 0 && qx < cw && qy < ch {
                    cov[qy as usize * cw as usize + qx as usize] = true;
                }
            }
        }
    }
    for y in 0..h {
        for x in 0..w {
            let mut k = 0;
            for sy in 0..SS {
                for sx in 0..SS {
                    k += cov[(y * SS + sy) * w * SS + x * SS + sx] as u32;
                }
            }
            out[y * w + x] = (k as f64 / (SS * SS) as f64 * 255.0).round() as u8;
        }
    }
}
