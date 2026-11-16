//! The sprite look: a loop's passes -> palette pixel art (flat colours, cel bands, hull lines).
//! style keys: height, frame_ms (required); light [x,y,z]; bands [lo,hi]; flat_parts; deep_parts;
//! cover; weak_cover; ring; despeckle; fast_frames; frame_anchor; pixel_bob; mirror.
use serde_json::Value;

const NB4: [(i32, i32); 4] = [(1, 0), (-1, 0), (0, 1), (0, -1)];
const NB8: [(i32, i32); 8] = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)];
pub const MARGIN: i64 = 3; // sprite px around the body's box: the hull's silhouette line sits outside it
const Q: u32 = 5; // bits per channel of the colour -> part lookup
const SLIVER: usize = 3; // largest bit of a part along a line that is recoloured as a sliver (see draw)

pub type Rgb = [u8; 3];
pub fn hexrgb(h: &str) -> Rgb { [1, 3, 5].map(|i| u8::from_str_radix(&h[i..i + 2], 16).unwrap()) }

/// every colour a sprite may use: the outline, then each part's shades
pub fn palette(pal: &Value) -> Vec<Rgb> {
    let mut cols = vec![hexrgb(pal["outline"].as_str().unwrap())];
    for shades in pal["parts"].as_object().unwrap().values() {
        for h in shades.as_array().unwrap() {
            let c = hexrgb(h.as_str().unwrap());
            if !cols.contains(&c) { cols.push(c); }
        }
    }
    cols
}

/// Python's round(): halves to even
fn pyround(x: f64) -> i64 { x.round_ties_even() as i64 }

pub struct Style {
    pub parts: Vec<String>, shades: Vec<Vec<[f64; 3]>>, lut: Vec<Vec<u16>>, light: [f64; 3], shaded: Vec<bool>,
    out: Rgb, cover: f64, weak: f64, ring: bool, despeckle: usize,
}

impl Style {
    pub fn new(cfg: &Value) -> Style {
        let st = &cfg["style"];
        let pp = cfg["palette"]["parts"].as_object().unwrap();
        let parts: Vec<String> = pp.keys().cloned().collect();
        let shades: Vec<Vec<[f64; 3]>> = pp.values().map(|s| s.as_array().unwrap().iter()
            .map(|h| hexrgb(h.as_str().unwrap()).map(|v| v as f64)).collect()).collect();
        // each part's reference colours: its palette shades, or with parts.match "albedo" its one texture colour
        let pm = &cfg["parts"];
        let alb = if pm["match"] == "albedo" { pm["albedo"].clone() } else { Value::Null };
        let (mut flat, mut part_of) = (vec![], vec![]);
        for (i, p) in parts.iter().enumerate() {
            match alb.get(p) {
                Some(h) => { flat.push(hexrgb(h.as_str().unwrap()).map(|v| v as f64)); part_of.push(i); }
                None => for s in &shades[i] { flat.push(*s); part_of.push(i); },
            }
        }
        // one colour -> part table per material group: a group's colours only go to the parts it allows
        let mut groups: Vec<String> = pm["materials"].as_object().map(|m| m.values().map(|v| v.as_str().unwrap().to_string()).collect()).unwrap_or_default();
        groups.sort(); groups.dedup();
        let lut = std::iter::once(None).chain(groups.iter().map(Some)).map(|g| {
            let ok: Vec<usize> = g.map(|g| g.split('|').filter_map(|n| parts.iter().position(|p| p == n)).collect()).unwrap_or_default();
            (0..1u32 << (3 * Q)).map(|q| {
                let c = [q >> (2 * Q), (q >> Q) & 31, q & 31].map(|v| ((v << (8 - Q)) + (1 << (7 - Q))) as f64);
                let (mut best, mut bd) = (0, f64::INFINITY);
                for (k, f) in flat.iter().enumerate() {
                    if !ok.is_empty() && !ok.contains(&part_of[k]) { continue; }
                    let d = (c[0] - f[0]).powi(2) + (c[1] - f[1]).powi(2) + (c[2] - f[2]).powi(2);
                    if d < bd { bd = d; best = part_of[k]; }
                }
                best as u16
            }).collect()
        }).collect();
        let l = st.get("light").map(|l| [0, 1, 2].map(|i| l[i].as_f64().unwrap())).unwrap_or([-0.15, 0.45, 0.88]);
        let n = l[2].mul_add(l[2], l[1].mul_add(l[1], l[0] * l[0])).sqrt(); // numpy's norm
        let flat_parts: Vec<&str> = st["flat_parts"].as_array().map(|a| a.iter().map(|v| v.as_str().unwrap()).collect()).unwrap_or_default();
        Style {
            shaded: parts.iter().map(|p| !flat_parts.contains(&p.as_str())).collect(), parts, shades, lut,
            light: l.map(|v| v / n), out: hexrgb(cfg["palette"]["outline"].as_str().unwrap()),
            cover: st["cover"].as_f64().unwrap_or(0.35), weak: st["weak_cover"].as_f64().unwrap_or(0.12),
            ring: st["ring"].as_bool().unwrap_or(true), despeckle: st["despeckle"].as_u64().unwrap_or(0) as usize,
        }
    }
}

/// One crop box for the whole loop (no jitter); scale so frame 0 is `height` px tall. anchor: the frames
/// that fix the pixel grid; the box is then grown by whole sprite pixels to fit the rest. boxes: alpha boxes.
pub fn framing(height: f64, boxes: &[[i64; 4]], anchor: Option<&[usize]>) -> ([i64; 4], [i64; 2]) {
    let union = |it: &mut dyn Iterator<Item = [i64; 4]>| it.reduce(|a, b| [a[0].min(b[0]), a[1].min(b[1]), a[2].max(b[2]), a[3].max(b[3])]).unwrap();
    let scale = height / (boxes[0][3] - boxes[0][1]) as f64;
    let full = union(&mut boxes.iter().cloned());
    let Some(anchor) = anchor else {
        return (full, [pyround((full[2] - full[0]) as f64 * scale), pyround((full[3] - full[1]) as f64 * scale)]);
    };
    let mut b = union(&mut anchor.iter().map(|&i| boxes[i]));
    let mut size = [pyround((b[2] - b[0]) as f64 * scale), pyround((b[3] - b[1]) as f64 * scale)];
    for (side, k, sgn) in [(0, 0, -1i64), (1, 1, -1), (2, 0, 1), (3, 1, 1)] {
        let need = (b[side] - full[side]) * -sgn;
        if need > 0 {
            // whole sprite pixels to add: of the few that fit, the one closest to whole render px
            let m0 = (need as f64 * scale).ceil() as i64;
            let m = (m0..m0 + 4).min_by(|&p, &q| {
                let e = |q: i64| (q as f64 / scale - (q as f64 / scale).round_ties_even()).abs();
                e(p).partial_cmp(&e(q)).unwrap()
            }).unwrap();
            b[side] += sgn * pyround(m as f64 / scale);
            size[k] += m;
        }
    }
    (b, size)
}

/// the loop's box and sprite size grown by MARGIN sprite px on every side
pub fn grow(b: [i64; 4], size: [i64; 2]) -> ([i64; 4], [i64; 2]) {
    let mx = pyround(MARGIN as f64 * ((b[2] - b[0]) as f64 / size[0] as f64));
    let my = pyround(MARGIN as f64 * ((b[3] - b[1]) as f64 / size[1] as f64));
    ([b[0] - mx, b[1] - my, b[2] + mx, b[3] + my], [size[0] + 2 * MARGIN, size[1] + 2 * MARGIN])
}

/// one frame's sprite-pixel arrays
pub struct Measure { pub w: usize, pub h: usize, body: Vec<bool>, part: Vec<usize>, rgb: Vec<[f64; 3]>, n: Vec<[f64; 2]>, hull: Vec<f64> }

/// col: RGBA, aux: (normal x, normal y, material group, hull) per render px of the crop (cw x ch)
pub fn measure(s: &Style, col: &[u8], aux: &[u8], cw: usize, ch: usize, w: usize, h: usize) -> Measure {
    let n = w * h;
    let np = s.parts.len();
    let sx: Vec<usize> = (0..cw).map(|x| (x * w / cw).min(w - 1)).collect();
    let cell = |i: usize| (i / cw * h / ch).min(h - 1) * w + sx[i % cw];
    let (mut total, mut body_cnt, mut hull_cnt, mut use_cnt) = (vec![0u32; n], vec![0u32; n], vec![0f64; n], vec![0u32; n]);
    let mut part = vec![0usize; cw * ch];
    for i in 0..cw * ch {
        let c = cell(i);
        total[c] += 1;
        let (px, ax) = (&col[i * 4..i * 4 + 4], &aux[i * 4..i * 4 + 4]);
        if ax[3] > 127 { hull_cnt[c] += 1.0; }
        if px[3] > 127 {
            body_cnt[c] += 1;
            let q = ((px[0] as usize >> 3) << 10) | ((px[1] as usize >> 3) << 5) | (px[2] as usize >> 3);
            part[i] = s.lut[ax[2] as usize][q] as usize;
            if ax[3] <= 127 { use_cnt[c] += 1; }
        }
    }
    // the part: majority of the body samples the hull doesn't cover (all of them where it covers all)
    let usable = |i: usize, c: usize| col[i * 4 + 3] > 127 && (aux[i * 4 + 3] <= 127 || use_cnt[c] == 0);
    let mut counts = vec![0u32; n * np];
    for i in 0..cw * ch { let c = cell(i); if usable(i, c) { counts[c * np + part[i]] += 1; } }
    let best: Vec<usize> = (0..n).map(|c| {
        let row = &counts[c * np..(c + 1) * np];
        (0..np).fold(0, |b, k| if row[k] > row[b] { k } else { b })
    }).collect();
    // the winning part's samples: their mean colour and mean normal
    let (mut k, mut rgb, mut nrm) = (vec![0u32; n], vec![[0f64; 3]; n], vec![[0f64; 2]; n]);
    for i in 0..cw * ch {
        let c = cell(i);
        if usable(i, c) && part[i] == best[c] {
            k[c] += 1;
            for j in 0..3 { rgb[c][j] += col[i * 4 + j] as f64; }
            for j in 0..2 { nrm[c][j] += aux[i * 4 + j] as f64 / 255.0 * 2.0 - 1.0; }
        }
    }
    for c in 0..n {
        let kk = k[c].max(1) as f64;
        for j in 0..3 { rgb[c][j] /= kk; }
        for j in 0..2 { nrm[c][j] /= kk; }
    }
    let t = |c: usize| (total[c] as f64).max(1.0);
    Measure { w, h, body: (0..n).map(|c| body_cnt[c] as f64 / t(c) >= 0.5).collect(), part: best, rgb, n: nrm,
              hull: (0..n).map(|c| hull_cnt[c] / t(c)).collect() }
}

pub fn ndl(s: &Style, m: &Measure) -> Vec<f64> {
    m.n.iter().map(|v| {
        let nz = (1.0 - (v[0] * v[0] + v[1] * v[1])).clamp(0.0, 1.0).sqrt();
        v[0] * s.light[0] + v[1] * s.light[1] + nz * s.light[2]
    }).collect()
}

/// numpy's percentile (linear)
pub fn percentile(mut v: Vec<f64>, q: f64) -> f64 {
    v.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let vi = (v.len() - 1) as f64 * (q / 100.0);
    if vi >= (v.len() - 1) as f64 { return v[v.len() - 1]; }
    let lo = vi.floor();
    let (a, b, t) = (v[lo as usize], v[lo as usize + 1], vi - lo);
    let d = b - a;
    if t >= 0.5 { b - d * (1.0 - t) } else { a + d * t }
}

/// N.L thresholds: bands [lo, hi] and per deep part 4 limits (style.deep_parts), from frame 0
pub fn thresholds(cfg: &Value, s: &Style, m0: &Measure) -> ([f64; 2], Vec<Option<Vec<f64>>>) {
    let st = &cfg["style"];
    let nd = ndl(s, m0);
    let sel = |f: &dyn Fn(usize) -> bool| (0..nd.len()).filter(|&c| m0.body[c] && f(c)).map(|c| nd[c]).collect::<Vec<_>>();
    let bands = match st.get("bands") {
        Some(b) => [b[0].as_f64().unwrap(), b[1].as_f64().unwrap()],
        None => { let v = sel(&|_| true); [percentile(v.clone(), 25.0), percentile(v, 70.0)] }
    };
    let mut deep = vec![None; s.parts.len()];
    for (name, pct) in st["deep_parts"].as_object().into_iter().flatten() {
        let i = s.parts.iter().position(|p| p == name).unwrap();
        let v = sel(&|c| m0.part[c] == i);
        deep[i] = Some(pct.as_array().unwrap().iter().map(|q| percentile(v.clone(), q.as_f64().unwrap())).collect());
    }
    (bands, deep)
}

/// the value CPython's max(set(items), key=items.count) picks: the first in set order with the top count
fn py_set_max<T: Copy + PartialEq>(items: &[T], hash: impl Fn(T) -> u64) -> T {
    let (mut table, mut mask, mut used): (Vec<Option<(T, u64)>>, usize, usize) = (vec![None; 8], 7, 0);
    fn place<T: Copy>(t: &mut [Option<(T, u64)>], mask: usize, e: (T, u64)) {
        let (mut i, mut perturb) = (e.1 as usize & mask, e.1 as usize);
        loop {
            let probes = if i + 9 <= mask { 9 } else { 0 };
            for j in i..=i + probes { if t[j].is_none() { t[j] = Some(e); return; } }
            perturb >>= 5;
            i = (i.wrapping_mul(5).wrapping_add(1).wrapping_add(perturb)) & mask;
        }
    }
    for &x in items {
        if table.iter().flatten().any(|e| e.0 == x) { continue; }
        place(&mut table, mask, (x, hash(x)));
        used += 1;
        if used * 5 >= mask * 3 {
            let mut size = 8;
            while size <= used * 4 { size <<= 1; }
            let old = std::mem::replace(&mut table, vec![None; size]);
            mask = size - 1;
            for e in old.into_iter().flatten() { place(&mut table, mask, e); }
        }
    }
    let count = |x: T| items.iter().filter(|&&y| y == x).count();
    let mut best: Option<(T, usize)> = None;
    for (x, _) in table.into_iter().flatten() {
        let c = count(x);
        if best.is_none_or(|b| c > b.1) { best = Some((x, c)); }
    }
    best.unwrap().0
}

/// CPython's hash of a tuple of small ints
fn tuple_hash(t: Rgb) -> u64 {
    const P1: u64 = 11400714785074694791; const P2: u64 = 14029467366897019727; const P5: u64 = 2870177450012600261;
    let mut acc = P5;
    for v in t { acc = acc.wrapping_add((v as u64).wrapping_mul(P2)).rotate_left(31).wrapping_mul(P1); }
    acc = acc.wrapping_add(3 ^ (P5 ^ 3527539));
    if acc == u64::MAX { 1546275796 } else { acc }
}

/// one frame's RGBA sprite; deep: per part 4 N.L thresholds (style.deep_parts)
pub fn draw(s: &Style, m: &Measure, bands: [f64; 2], deep: &[Option<Vec<f64>>]) -> Vec<[u8; 4]> {
    let (w, h) = (m.w as i32, m.h as i32);
    let at = |y: i32, x: i32| (y * w + x) as usize;
    let inside = |y: i32, x: i32| 0 <= y && y < h && 0 <= x && x < w;
    // a moved by (dy, dx): out[y, x] = a[y - dy, x - dx], false coming in at the border
    let shift = |a: &[bool], dy: i32, dx: i32| -> Vec<bool> {
        (0..h * w).map(|i| { let (y, x) = (i / w - dy, i % w - dx); inside(y, x) && a[at(y, x)] }).collect()
    };
    let nd = ndl(s, m);
    let mut out = vec![[0u8; 4]; m.body.len()];
    for c in 0..out.len() {
        if !m.body[c] { continue; }
        let (i, sh) = (m.part[c], &s.shades[m.part[c]]);
        let d = |k: usize| { let e = [0, 1, 2].map(|j| m.rgb[c][j] - sh[k][j]); e[0] * e[0] + e[1] * e[1] + e[2] * e[2] };
        let mut j = (0..sh.len()).fold(0, |b, k| if d(k) < d(b) { k } else { b }) as i64;
        let v = nd[c];
        if let Some(b) = &deep[i] {
            j += (v > b[2]) as i64 + (v > b[3]) as i64 - (v < b[1]) as i64 - (v < b[0]) as i64;
        } else if s.shaded[i] {
            j += if v > bands[1] { 1 } else if v < bands[0] { -1 } else { 0 };
        }
        let rgb = sh[j.clamp(0, sh.len() as i64 - 1) as usize];
        out[c] = [rgb[0] as u8, rgb[1] as u8, rgb[2] as u8, 255];
    }
    // lines: where the hull covers enough of the pixel; plus gaps of 1-2 px in a line where the hull still
    // covers a little (line on both sides, straight or diagonal) - never beside a line, so none gets wider
    let mut line: Vec<bool> = m.hull.iter().map(|&c| c >= s.cover).collect();
    let weak: Vec<bool> = m.hull.iter().zip(&line).map(|(&c, &l)| c >= s.weak && !l).collect();
    let mut add = vec![false; line.len()];
    for (dy, dx) in [(0, 1), (1, 0), (1, 1), (1, -1)] {
        let (lb, la, wa, l2) = (shift(&line, dy, dx), shift(&line, -dy, -dx), shift(&weak, -dy, -dx), shift(&line, -2 * dy, -2 * dx));
        let two: Vec<bool> = (0..line.len()).map(|i| weak[i] && lb[i] && wa[i] && l2[i]).collect();
        let two_b = shift(&two, dy, dx);
        for i in 0..line.len() { add[i] |= (weak[i] && lb[i] && la[i]) || two[i] || two_b[i]; }
    }
    for i in 0..line.len() { line[i] |= add[i]; }
    if s.ring {
        for (dy, dx) in NB4 { let b = shift(&m.body, dy, dx); for i in 0..line.len() { line[i] |= !m.body[i] && b[i]; } }
    }
    // slivers: 1-3 px bits of a part along a line, touching the rest of it only at corners, take the colour
    // most of the fill pixels around them have. Lines are left as they are.
    let fill: Vec<bool> = (0..line.len()).map(|i| m.body[i] && !line[i]).collect();
    let mut near = vec![false; line.len()];
    for (dy, dx) in NB8 { let l = shift(&line, dy, dx); for i in 0..near.len() { near[i] |= l[i]; } }
    let mut seen = vec![false; line.len()];
    let part = &m.part;
    for i0 in 0..line.len() {
        if !(fill[i0] && near[i0]) || seen[i0] { continue; }
        let Some(comp) = island(i0, SLIVER, w, h, &mut seen, |c| fill[c] && part[c] == part[i0]) else { continue };
        let mut nb = vec![];
        for &c in &comp {
            for (dy, dx) in NB8 {
                let (y, x) = (c as i32 / w + dy, c as i32 % w + dx);
                if inside(y, x) && fill[at(y, x)] && !comp.contains(&at(y, x)) && part[at(y, x)] != part[i0] {
                    let o = out[at(y, x)]; nb.push([o[0], o[1], o[2]]);
                }
            }
        }
        if !nb.is_empty() {
            let c = py_set_max(&nb, tuple_hash);
            for &p in &comp { out[p][..3].copy_from_slice(&c); }
        }
    }
    if s.despeckle > 0 { despeckle(&mut out, &fill, part, s.despeckle, w, h); }
    for i in 0..line.len() { if line[i] { out[i] = [s.out[0], s.out[1], s.out[2], 255]; } }
    out
}

/// the 4-connected island of `same` pixels from i0, unseen ones only, as Python's stack search visits it;
/// None when it is larger than `size`
fn island(i0: usize, size: usize, w: i32, h: i32, seen: &mut [bool], same: impl Fn(usize) -> bool) -> Option<Vec<usize>> {
    let (mut comp, mut stack) = (vec![], vec![i0]);
    seen[i0] = true;
    while !stack.is_empty() && comp.len() <= size {
        let c = stack.pop().unwrap();
        comp.push(c);
        for (dy, dx) in NB4 {
            let (y, x) = (c as i32 / w + dy, c as i32 % w + dx);
            if 0 <= y && y < h && 0 <= x && x < w {
                let n = (y * w + x) as usize;
                if !seen[n] && same(n) { seen[n] = true; stack.push(n); }
            }
        }
    }
    (comp.len() <= size && stack.is_empty()).then_some(comp)
}

/// style.despeckle N: a shade island of at most N px inside one part (every pixel around it fill of that
/// part) takes the colour most of that ring has, if at least 3/4 of the ring agrees. Fill only.
fn despeckle(out: &mut [[u8; 4]], fill: &[bool], part: &[usize], size: usize, w: i32, h: i32) {
    let key: Vec<[u8; 3]> = out.iter().map(|o| [o[0], o[1], o[2]]).collect();
    let mut seen: Vec<bool> = fill.iter().map(|f| !f).collect();
    for i0 in 0..fill.len() {
        if seen[i0] { continue; }
        let Some(comp) = island(i0, size, w, h, &mut seen, |c| key[c] == key[i0] && part[c] == part[i0]) else { continue };
        let mut ring = vec![];
        for &c in &comp {
            for (dy, dx) in NB8 {
                let (y, x) = (c as i32 / w + dy, c as i32 % w + dx);
                let n = (y * w + x) as usize;
                if !(0 <= y && y < h && 0 <= x && x < w) { ring.push(None); }
                else if !comp.contains(&n) && !ring.contains(&Some(n)) { ring.push(Some(n)); }
            }
        }
        if ring.iter().any(|r| r.is_none_or(|n| !fill[n] || part[n] != part[i0])) { continue; }
        let nb: Vec<[u8; 3]> = ring.iter().map(|r| key[r.unwrap()]).collect();
        let c = nb.iter().copied().max_by_key(|c| nb.iter().filter(|x| *x == c).count()).unwrap();
        if nb.iter().filter(|x| **x == c).count() * 4 >= nb.len() * 3 {
            for &p in &comp { out[p][..3].copy_from_slice(&c); }
        }
    }
}
