//! sprite JOB.json: one sprite loop from bake.py's geometry to GIFs, in memory.
//! JOB: {config, bake (dir), offsets ([dy, dx] per frame, style.pixel_bob), shiny (palette or null), out (path stem)}.
//! Writes OUT.gif, OUT_4x.gif (+ OUT_shiny*.gif) and prints {"clipped": bool, timings} as one JSON line.
mod render;
mod style;
use rayon::prelude::*;
use serde_json::{json, Value};
use std::{fs, sync::Mutex, time::Instant};
use style::{Rgb, Style};

fn main() {
    let job: Value = serde_json::from_str(&fs::read_to_string(std::env::args().nth(1).expect("sprite JOB.json")).unwrap()).unwrap();
    let (cfg, out) = (&job["config"], job["out"].as_str().unwrap());
    let st = &cfg["style"];
    let n = cfg["motion"]["frames"].as_u64().unwrap() as usize;
    let t0 = Instant::now();
    let gpu = render::Gpu::new(job["bake"].as_str().unwrap().as_ref());
    let s = Style::new(cfg);

    // pixel grid: frame_anchor "first" = frame 0's; with fast_frames the slow frames'; else the whole loop's
    let boxes: Vec<[i64; 4]> = gpu.boxes(n).into_iter().map(|b| b.expect("empty frame")).collect();
    let clipped = boxes.iter().any(|b| b[0] == 0 || b[1] == 0 || b[2] == gpu.w as i64 || b[3] == gpu.h as i64);
    let fast: Vec<usize> = st["fast_frames"].as_array().into_iter().flatten()
        .flat_map(|r| r[0].as_u64().unwrap() as usize..=r[1].as_u64().unwrap() as usize).collect();
    let anchor: Option<Vec<usize>> = if st["frame_anchor"] == "first" { Some(vec![0]) }
        else if !fast.is_empty() { Some((0..n).filter(|i| !fast.contains(i)).collect()) } else { None };
    let (b, size) = style::framing(st["height"].as_f64().unwrap(), &boxes, anchor.as_deref());
    let (crop, size) = style::grow(b, size);
    let (cw, ch, w, h) = ((crop[2] - crop[0]) as usize, (crop[3] - crop[1]) as usize, size[0] as usize, size[1] as usize);

    // passes -> sprite-pixel measures, measured on every core while the GPU draws the next frame
    let ms = Mutex::new((0..n).map(|_| None).collect::<Vec<_>>());
    rayon::scope(|sc| gpu.passes(n, crop, |f, data| {
        let (s, ms) = (&s, &ms);
        sc.spawn(move |_| { let m = style::measure(s, &data[..cw * ch * 4], &data[cw * ch * 4..], cw, ch, w, h); ms.lock().unwrap()[f] = Some(m); });
    }));
    let ms: Vec<style::Measure> = ms.into_inner().unwrap().into_iter().map(Option::unwrap).collect();
    let t_render = t0.elapsed().as_secs_f64();
    let (bands, deep) = style::thresholds(cfg, &s, &ms[0]);
    let frames: Vec<Vec<[u8; 4]>> = ms.par_iter().map(|m| style::draw(&s, m, bands, &deep)).collect();

    // style.pixel_bob: whole-pixel shift per frame on a canvas grown to fit every shift; then style.mirror
    let offs: Vec<(i64, i64)> = job["offsets"].as_array().unwrap().iter().map(|o| (o[0].as_i64().unwrap(), o[1].as_i64().unwrap())).collect();
    let (a, bb) = (offs.iter().map(|o| o.0.abs()).max().unwrap(), offs.iter().map(|o| o.1.abs()).max().unwrap());
    let (cw2, ch2) = (w + 2 * bb as usize, h + 2 * a as usize);
    let mirror = st["mirror"].as_bool().unwrap_or(false);
    let sprites: Vec<Vec<[u8; 4]>> = frames.into_par_iter().zip(offs).map(|(f, (dy, dx))| {
        let mut c = vec![[0u8; 4]; cw2 * ch2];
        let (y0, x0) = ((a - dy) as usize, (bb + dx) as usize); // + = up / right
        for y in 0..h { for x in 0..w {
            let xx = x0 + x;
            c[(y0 + y) * cw2 + if mirror { cw2 - 1 - xx } else { xx }] = f[y * w + x];
        } }
        c
    }).collect();
    let t_sprite = t0.elapsed().as_secs_f64() - t_render;

    // GIFs: palette indices (the shiny: the same indices, its palette entry by entry)
    let pal = style::palette(&cfg["palette"]);
    let idx: Vec<Vec<u8>> = sprites.par_iter().map(|sp| sp.iter().map(|p| {
        if p[3] == 0 { return pal.len() as u8; }
        pal.iter().position(|c| c[..] == p[..3]).unwrap_or(pal.len()) as u8
    }).collect()).collect();
    let ms_ = st["frame_ms"].as_u64().unwrap();
    let mut todo = vec![(pal, String::new())];
    if !job["shiny"].is_null() {
        let sp = style::palette(&job["shiny"]);
        assert_eq!(sp.len(), todo[0].0.len(), "shiny palette differs in size");
        todo.push((sp, "_shiny".into()));
    }
    todo.par_iter().flat_map(|t| [(t, 1), (t, 4)]).for_each(|((pal, suffix), k)| {
        let path = format!("{out}{suffix}{}.gif", if k > 1 { format!("_{k}x") } else { String::new() });
        save_gif(&path, pal, &idx, cw2, ch2, k, ms_);
    });
    println!("{}", json!({"clipped": clipped, "render": t_render, "sprite": t_sprite, "gif": t0.elapsed().as_secs_f64() - t_render - t_sprite}));
}

/// as Pillow writes it: transparent index len(pal), restore to background, identical frames merged
fn save_gif(path: &str, pal: &[Rgb], idx: &[Vec<u8>], w: usize, h: usize, k: usize, frame_ms: u64) {
    let mut frames: Vec<(&Vec<u8>, u64)> = vec![];
    for f in idx {
        match frames.last_mut() { Some(l) if l.0 == f => l.1 += frame_ms, _ => frames.push((f, frame_ms)) }
    }
    let mut colours: Vec<u8> = pal.iter().flatten().copied().collect();
    colours.resize(768, 0);
    let mut enc = gif::Encoder::new(fs::File::create(path).unwrap(), (w * k) as u16, (h * k) as u16, &colours).unwrap();
    if frames.len() > 1 { enc.set_repeat(gif::Repeat::Infinite).unwrap(); }
    let frames: Vec<gif::Frame> = frames.into_par_iter().map(|(f, ms)| {
        let buf: Vec<u8> = (0..h * k).flat_map(|y| (0..w * k).map(move |x| f[y / k * w + x / k])).collect();
        let mut fr = gif::Frame { width: (w * k) as u16, height: (h * k) as u16, buffer: buf.into(), delay: (ms / 10) as u16,
            dispose: gif::DisposalMethod::Background, transparent: Some(pal.len() as u8), ..Default::default() };
        fr.make_lzw_pre_encoded();
        fr
    }).collect();
    for fr in &frames { enc.write_lzw_pre_encoded_frame(fr).unwrap(); }
}
