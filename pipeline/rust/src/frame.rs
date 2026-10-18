//! Config (colour sets packed by rustcore.pack_cfg) and per-pixel lookups on an RGBA frame,
//! with the edge rules of sprite_style.shift: beyond the canvas is "nothing", or "outside" for
//! touches-the-outside tests.

pub struct PartCfg {
    pub own: Vec<u32>,
    pub other: Vec<u32>,
    pub hl: Option<u32>,
}

pub struct Cfg {
    pub out: u32,
    pub dark: Vec<u32>,
    pub parts: Vec<PartCfg>,          // style.part_outline, as check_loop.part_masks sees them
}

impl Cfg {
    /// [out, n_dark, dark.., n_parts, (n_own, own.., n_other, other.., hl or -1)..]
    pub fn parse(b: &[i64]) -> Cfg {
        let mut i = 0;
        let mut next = || { let v = b[i]; i += 1; v };
        let out = next() as u32;
        let nd = next() as usize;
        let dark = (0..nd).map(|_| next() as u32).collect();
        let np = next() as usize;
        let mut parts = Vec::with_capacity(np);
        for _ in 0..np {
            let n = next() as usize;
            let own = (0..n).map(|_| next() as u32).collect();
            let n = next() as usize;
            let other = (0..n).map(|_| next() as u32).collect();
            let hl = next();
            parts.push(PartCfg { own, other, hl: if hl < 0 { None } else { Some(hl as u32) } });
        }
        Cfg { out, dark, parts }
    }
}

pub const NB4: [(isize, isize); 4] = [(1, 0), (-1, 0), (0, 1), (0, -1)];
pub const NB8: [(isize, isize); 8] = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)];

pub struct Frame<'a> {
    pub h: usize,
    pub w: usize,
    pub s: &'a mut [u8],
    pub protect: &'a [u8],
    pub cfg: &'a Cfg,
    flags: Vec<u8>,          // per pixel: 1 solid, 2 line colour, 4 outline colour (kept up to date by refresh)
}

impl<'a> Frame<'a> {
    pub fn new(h: usize, w: usize, s: &'a mut [u8], protect: &'a [u8], cfg: &'a Cfg) -> Frame<'a> {
        let mut f = Frame { h, w, s, protect, cfg, flags: vec![0; h * w] };
        for i in 0..h * w {
            f.refresh(i);
        }
        f
    }
    /// after s changed at pixel i
    pub fn refresh(&mut self, i: usize) {
        let solid = self.s[i * 4 + 3] > 0;
        let k = self.key(i);
        self.flags[i] = solid as u8 | ((solid && self.cfg.dark.contains(&k)) as u8) << 1 | ((solid && k == self.cfg.out) as u8) << 2;
    }
    #[inline]
    pub fn at(&self, y: isize, x: isize) -> Option<usize> {
        if y >= 0 && x >= 0 && (y as usize) < self.h && (x as usize) < self.w { Some(y as usize * self.w + x as usize) } else { None }
    }
    #[inline]
    pub fn key(&self, i: usize) -> u32 {
        (self.s[i * 4] as u32) << 16 | (self.s[i * 4 + 1] as u32) << 8 | self.s[i * 4 + 2] as u32
    }
    #[inline]
    pub fn solid(&self, i: usize) -> bool { self.flags[i] & 1 != 0 }
    #[inline]
    pub fn line_all(&self, i: usize) -> bool { self.flags[i] & 2 != 0 }
    #[inline]
    pub fn is_out(&self, i: usize) -> bool { self.flags[i] & 4 != 0 }
    #[inline]
    pub fn line(&self, i: usize) -> bool { self.line_all(i) && self.protect[i] == 0 }
    #[inline]
    pub fn body(&self, i: usize) -> bool { self.solid(i) && !self.line_all(i) }

    /// f at (y + dy, x + dx), false beyond the canvas
    #[inline]
    pub fn nb(&self, y: isize, x: isize, dy: isize, dx: isize, f: impl Fn(usize) -> bool) -> bool {
        self.at(y + dy, x + dx).map_or(false, f)
    }
    pub fn any4(&self, y: isize, x: isize, f: impl Fn(usize) -> bool) -> bool {
        NB4.iter().any(|&(dy, dx)| self.at(y + dy, x + dx).map_or(false, &f))
    }
    pub fn touches_out(&self, y: isize, x: isize) -> bool {
        NB4.iter().any(|&(dy, dx)| self.at(y + dy, x + dx).map_or(true, |j| !self.solid(j)))
    }
    pub fn touches_body(&self, y: isize, x: isize) -> bool { self.any4(y, x, |j| self.body(j)) }

    // check_loop.part_masks: an outlined part's body pixels ("own") and every other part's
    // ("other"); its highlight colour next to its own pixels counts as its own
    #[inline]
    fn body2(&self, i: usize) -> bool { self.body(i) && self.protect[i] == 0 }
    #[inline]
    fn own0(&self, p: &PartCfg, i: usize) -> bool { self.body2(i) && p.own.contains(&self.key(i)) }
    fn hl_near(&self, p: &PartCfg, y: isize, x: isize, i: usize) -> bool {
        p.hl == Some(self.key(i)) && self.body2(i) && self.any4(y, x, |j| self.own0(p, j))
    }
    pub fn own(&self, p: &PartCfg, y: isize, x: isize) -> bool {
        self.at(y, x).map_or(false, |i| self.own0(p, i) || self.hl_near(p, y, x, i))
    }
    pub fn other(&self, p: &PartCfg, y: isize, x: isize) -> bool {
        self.at(y, x).map_or(false, |i| self.body2(i) && p.other.contains(&self.key(i)) && !self.hl_near(p, y, x, i))
    }
    /// check_loop.open_outline's part leakage: pixels of an outlined part touching another part
    pub fn leaks(&self) -> i64 {
        let mut n = 0;
        for p in &self.cfg.parts {
            for y in 0..self.h as isize {
                for x in 0..self.w as isize {
                    if self.own(p, y, x) && NB4.iter().any(|&(dy, dx)| self.other(p, y + dy, x + dx)) {
                        n += 1;
                    }
                }
            }
        }
        n
    }

    /// check_loop.separators(cfg, s, line_all, protect): a line pixel with an outlined part on
    /// one side and another part on the other
    pub fn separator(&self, y: isize, x: isize, i: usize) -> bool {
        self.line_all(i) && self.cfg.parts.iter().any(|p| {
            NB4.iter().any(|&(dy, dx)| self.own(p, y + dy, x + dx)) && NB4.iter().any(|&(dy, dx)| self.other(p, y + dy, x + dx))
        })
    }
}
