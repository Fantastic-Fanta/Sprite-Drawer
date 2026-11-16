//! sprite_gpu BAKE_DIR OUT_DIR [--no-write] [--frames N]
//! Draws render_sprite.py's four passes (color_, id_, data_, hull_) for every baked frame with wgpu and writes
//! them as RLE TGA, the names sprite_style.sprites() reads. Prints a JSON timing line.
use std::{fs, path::{Path, PathBuf}, time::Instant};
use wgpu::util::DeviceExt;

const AA: usize = 8; // Workbench render_aa "8"

fn read_u32(b: &[u8], off: usize, n: usize) -> Vec<u32> { bytemuck::cast_slice(&b[off..off + n * 4]).to_vec() }

fn mat_mul(a: &[[f64; 4]; 4], b: &[[f64; 4]; 4]) -> [[f64; 4]; 4] {
    let mut r = [[0.0; 4]; 4];
    for i in 0..4 { for j in 0..4 { for k in 0..4 { r[i][j] += a[i][k] * b[k][j]; } } }
    r
}
fn col_major(m: &[[f64; 4]; 4]) -> [f32; 16] {
    let mut o = [0f32; 16];
    for c in 0..4 { for r in 0..4 { o[c * 4 + r] = m[r][c] as f32; } }
    o
}
fn mat_of(v: &serde_json::Value) -> [[f64; 4]; 4] {
    let mut m = [[0.0; 4]; 4];
    for i in 0..4 { for j in 0..4 { m[i][j] = v[i][j].as_f64().unwrap(); } }
    m
}
/// Blender's BLI_jitter_init (drand48-style RNG, 24 relaxation rounds), then Workbench's TaaSamples:
/// closest sample moved to the centre, wrapped, scaled to [-1, 1], reordered farthest-from-previous.
fn workbench_taa_samples(num: usize) -> Vec<[f32; 2]> {
    let mut x_: u64 = ((31415926u64 + num as u64) << 16) | 0x330E;
    let mut rnd = || { x_ = (0x5DEECE66Du64.wrapping_mul(x_).wrapping_add(0xB)) & 0xFFFF_FFFF_FFFF; ((x_ >> 17) as u32 as i32) as f64 / 2147483648.0 };
    let nf = num as f32;
    let (rad1, rad2, rad3) = (1.0 / nf.sqrt(), 1.0 / nf, nf.sqrt() / nf);
    let mut j = vec![[0f32; 2]; num];
    let mut x = 0f32;
    for i in 0..num {
        j[i][0] = x + rad1 * (0.5 - rnd()) as f32;
        j[i][1] = i as f32 / nf + rad1 * (0.5 - rnd()) as f32;
        x += rad3; x -= x.floor();
    }
    let try_add = |vx: f32, vy: f32, d: &mut [f32; 2]| {
        if vx.abs() < rad1 && vy.abs() < rad1 {
            let len = (vx * vx + vy * vy).sqrt();
            if len > 0.0 && len < rad1 { let l = len / rad1; d[0] += vx / l; d[1] += vy / l; }
        }
    };
    let jit1 = |j: &mut Vec<[f32; 2]>| {
        let mut j2 = j.clone();
        for i in (0..num).rev() {
            let mut d = [0f32; 2];
            let (x, y) = (j[i][0], j[i][1]);
            for k in (0..num).rev() {
                if i == k { continue; }
                let mut vx = j[k][0] - x - 1.0;
                let mut vy = j[k][1] - y - 1.0;
                for _ in 0..3 {
                    try_add(vx, vy, &mut d); vx += 1.0;
                    try_add(vx, vy, &mut d); vx += 1.0;
                    try_add(vx, vy, &mut d); vx -= 2.0; vy += 1.0;
                }
            }
            let (mut x, mut y) = (x - d[0] / 18.0, y - d[1] / 18.0);
            x -= x.floor(); y -= y.floor();
            j2[i] = [x, y];
        }
        *j = j2;
    };
    let jit2 = |j: &mut Vec<[f32; 2]>| {
        let mut j2 = j.clone();
        for i in (0..num).rev() {
            let (mut dx, mut dy) = (0f32, 0f32);
            let (x, y) = (j[i][0], j[i][1]);
            for k in (0..num).rev() {
                if i == k { continue; }
                let mut vx = j[k][0] - x - 1.0;
                let mut vy = j[k][1] - y - 1.0;
                for _ in 0..3 { if vx.abs() < rad2 { dx += vx * rad2; } vx += 1.0; }
                for _ in 0..3 { if vy.abs() < rad2 { dy += vy * rad2; } vy += 1.0; }
            }
            let (mut x, mut y) = (x - dx / 2.0, y - dy / 2.0);
            x -= x.floor(); y -= y.floor();
            j2[i] = [x, y];
        }
        *j = j2;
    };
    for _ in 0..24 { jit1(&mut j); jit1(&mut j); jit2(&mut j); }
    for p in j.iter_mut() { p[0] -= 0.5; p[1] -= 0.5; }
    let mut ci = 0; let mut cd = 1.0f32;
    for (i, p) in j.iter().enumerate() { let d = p[0] * p[0] + p[1] * p[1]; if d < cd { cd = d; ci = i; } }
    let c = j[ci];
    for p in j.iter_mut() {
        let (sx, sy) = ((p[0] - c[0] + 0.5) % 1.0, (p[1] - c[1] + 0.5) % 1.0); // fmodf semantics
        *p = [sx * 2.0 - 1.0, sy * 2.0 - 1.0];
    }
    j.swap(0, ci);
    for i in 0..num - 2 {
        let (mut sd, mut idx) = (0f32, i);
        for k in i + 1..num {
            let d = (j[i][0] - j[k][0]).powi(2) + (j[i][1] - j[k][1]).powi(2);
            if d > sd { sd = d; idx = k; }
        }
        j.swap(i + 1, idx);
    }
    j
}
fn blackman_harris(x: f64, width: f64) -> f64 {
    if x > width * 0.5 { return 0.0; }
    let x = 2.0 * std::f64::consts::PI * (x / width + 0.5).clamp(0.0, 1.0);
    0.35875 - 0.48829 * x.cos() + 0.14128 * (2.0 * x).cos() - 0.01168 * (3.0 * x).cos()
}

/// uncompressed-size-agnostic RLE TGA (type 10), 32-bit BGRA, top-left origin
fn tga(path: &Path, w: usize, h: usize, rgba: &[u8], white_rgb: bool) {
    let mut o = Vec::with_capacity(w * h / 4);
    o.extend_from_slice(&[0, 0, 10, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
    o.extend_from_slice(&(w as u16).to_le_bytes());
    o.extend_from_slice(&(h as u16).to_le_bytes());
    o.extend_from_slice(&[32, 0x28]);
    let px = |i: usize| -> [u8; 4] {
        let p = &rgba[i * 4..i * 4 + 4];
        if white_rgb { [255, 255, 255, p[3]] } else { [p[2], p[1], p[0], p[3]] }
    };
    for y in 0..h {
        let row = y * w;
        let mut x = 0;
        while x < w {
            let p = px(row + x);
            let mut run = 1;
            while x + run < w && run < 128 && px(row + x + run) == p { run += 1; }
            if run > 1 {
                o.push(0x80 | (run - 1) as u8);
                o.extend_from_slice(&p);
                x += run;
            } else {
                let start = x;
                let mut n = 1;
                x += 1;
                while x < w && n < 128 && !(x + 1 < w && px(row + x) == px(row + x + 1)) { n += 1; x += 1; }
                o.push((n - 1) as u8);
                for i in start..start + n { o.extend_from_slice(&px(row + i)); }
            }
        }
    }
    fs::write(path, o).unwrap();
}

#[repr(C)]
#[derive(Clone, Copy, bytemuck::Pod, bytemuck::Zeroable)]
struct Cam { mvp: [f32; 16], view: [f32; 16] }
#[repr(C)]
#[derive(Clone, Copy, bytemuck::Pod, bytemuck::Zeroable)]
struct Mat { id: [f32; 4], color: [f32; 4], flags: [u32; 4] }
#[repr(C)]
#[derive(Clone, Copy, bytemuck::Pod, bytemuck::Zeroable)]
struct Acc { w: [f32; 12], size: [u32; 4] }

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let bake = PathBuf::from(&args[1]);
    let out = PathBuf::from(&args[2]);
    let write = !args.iter().any(|a| a == "--no-write");
    fs::create_dir_all(&out).unwrap();
    let t_start = Instant::now();

    // --- bake
    let meta: serde_json::Value = serde_json::from_str(&fs::read_to_string(bake.join("meta.json")).unwrap()).unwrap();
    let (w, h) = (meta["width"].as_u64().unwrap() as u32, meta["height"].as_u64().unwrap() as u32);
    let nframes = args.iter().position(|a| a == "--frames").map(|i| args[i + 1].parse().unwrap())
        .unwrap_or(meta["frames"].as_u64().unwrap() as usize);
    let g = |k: &str, f: &str| meta[k][f].as_u64().unwrap() as usize;
    let (bv, bl, bt, hv, hl, ht) = (g("body", "verts"), g("body", "loops"), g("body", "tris"), g("hull", "verts"), g("hull", "loops"), g("hull", "tris"));
    let st = fs::read(bake.join("static.bin")).unwrap();
    let mut off = 0;
    let mut take = |n: usize| { let v = read_u32(&st, off, n); off += n * 4; v };
    let (btl, blv, buv, bmat, htl, hlv, hshell) = (take(bt * 3), take(bl), take(bl * 2), take(bt), take(ht * 3), take(hl), take(ht));
    let frame_files: Vec<Vec<u8>> = (0..nframes).map(|f| fs::read(bake.join(format!("frame_{f:04}.bin"))).unwrap()).collect();
    let t_load = t_start.elapsed().as_secs_f64();

    // triangle draw order: body by material (one draw per material), hull body tris then shell tris
    let mats = meta["materials"].as_array().unwrap();
    let mut border = vec![];
    let mut ranges = vec![];
    for m in 0..mats.len() {
        let s = border.len();
        border.extend((0..bt as u32).filter(|&t| bmat[t as usize] == m as u32));
        if border.len() > s { ranges.push((m, s as u32, border.len() as u32)); }
    }
    let mut horder: Vec<u32> = (0..ht as u32).filter(|&t| hshell[t as usize] == 0).collect();
    let n_hold = horder.len() as u32;
    horder.extend((0..ht as u32).filter(|&t| hshell[t as usize] == 1));

    // camera: Blender's projection with a tight [0, 1] depth range for this model
    let view = mat_of(&meta["view"]);
    let mut proj = mat_of(&meta["proj"]);
    let p0: &[f32] = bytemuck::cast_slice(&frame_files[0][..bv * 12]);
    let (mut zn, mut zf) = (f64::MAX, f64::MIN);
    for v in p0.chunks(3) {
        let z = -(view[2][0] * v[0] as f64 + view[2][1] * v[1] as f64 + view[2][2] * v[2] as f64 + view[2][3]);
        zn = zn.min(z); zf = zf.max(z);
    }
    let span = zf - zn;
    let (n, f) = ((zn - span).max(zn * 0.1), zf + span);
    proj[2] = if meta["persp"].as_bool().unwrap() { [0.0, 0.0, f / (n - f), n * f / (n - f)] } else { [0.0, 0.0, -1.0 / (f - n), -n / (f - n)] };
    let vp = mat_mul(&proj, &view);
    let cam_for = |ox: f64, oy: f64| {
        let (dx, dy) = (ox / w as f64, oy / h as f64);   // NDC (y up)
        let mut m = vp;
        for c in 0..4 { m[0][c] += dx * vp[3][c]; m[1][c] += dy * vp[3][c]; }
        Cam { mvp: col_major(&m), view: col_major(&view) }
    };

    // --- device
    let instance = wgpu::Instance::new(wgpu::InstanceDescriptor::new_without_display_handle());
    let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
        power_preference: wgpu::PowerPreference::HighPerformance, ..Default::default() })).unwrap();
    let (device, queue) = pollster::block_on(adapter.request_device(&wgpu::DeviceDescriptor::default())).unwrap();
    let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor {
        label: None, source: wgpu::ShaderSource::Wgsl(include_str!("shader.wgsl").into()) });
    let st_ro = wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_DST;
    let buf = |data: &[u8], usage| device.create_buffer_init(&wgpu::util::BufferInitDescriptor { label: None, contents: data, usage });
    let empty = |size: usize, usage| device.create_buffer(&wgpu::BufferDescriptor { label: None, size: size as u64, usage, mapped_at_creation: false });
    let (b_pos, b_nrm, h_pos) = (empty(bv * 12, st_ro), empty(bl * 12, st_ro), empty(hv * 12, st_ro));
    let (b_uv, b_tl, b_lv, b_ord) = (buf(bytemuck::cast_slice(&buv), st_ro), buf(bytemuck::cast_slice(&btl), st_ro), buf(bytemuck::cast_slice(&blv), st_ro), buf(bytemuck::cast_slice(&border), st_ro));
    let (h_tl, h_lv, h_ord) = (buf(bytemuck::cast_slice(&htl), st_ro), buf(bytemuck::cast_slice(&hlv), st_ro), buf(bytemuck::cast_slice(&horder), st_ro));
    let uni = wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST;
    // Workbench TAA (workbench_effect_antialiasing.cc): sample offset o in [-1, 1] moves the image by o / 2 px
    // (window_translate_m4 with o / resolution in NDC), weights are Blackman-Harris(|(x, y) - o|, 2.0) over 3x3.
    let jit: Vec<(f64, f64)> = workbench_taa_samples(AA).iter().map(|p| (p[0] as f64, p[1] as f64)).collect();
    let cams: Vec<wgpu::Buffer> = std::iter::once((0.0, 0.0)).chain(jit.iter().cloned())
                .map(|(x, y)| buf(bytemuck::bytes_of(&cam_for(x, y)), uni)).collect();

    let vis = wgpu::ShaderStages::VERTEX_FRAGMENT;
    let sto = |b| wgpu::BindGroupLayoutEntry { binding: b, visibility: vis, ty: wgpu::BindingType::Buffer {
        ty: wgpu::BufferBindingType::Storage { read_only: true }, has_dynamic_offset: false, min_binding_size: None }, count: None };
    let unif = |b| wgpu::BindGroupLayoutEntry { binding: b, visibility: vis, ty: wgpu::BindingType::Buffer {
        ty: wgpu::BufferBindingType::Uniform, has_dynamic_offset: false, min_binding_size: None }, count: None };
    let geo_l = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor { label: None,
        entries: &[unif(0), sto(1), sto(2), sto(3), sto(4), sto(5), sto(6)] });
    let mat_l = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor { label: None, entries: &[unif(0),
        wgpu::BindGroupLayoutEntry { binding: 1, visibility: vis, ty: wgpu::BindingType::Texture {
            sample_type: wgpu::TextureSampleType::Float { filterable: true }, view_dimension: wgpu::TextureViewDimension::D2, multisampled: false }, count: None },
        wgpu::BindGroupLayoutEntry { binding: 2, visibility: vis, ty: wgpu::BindingType::Sampler(wgpu::SamplerBindingType::Filtering), count: None }] });
    let geo_bg = |cam: &wgpu::Buffer, pos: &wgpu::Buffer, tl: &wgpu::Buffer, lv: &wgpu::Buffer, ord: &wgpu::Buffer| {
        fn e(i: u32, b: &wgpu::Buffer) -> wgpu::BindGroupEntry<'_> { wgpu::BindGroupEntry { binding: i, resource: b.as_entire_binding() } }
        device.create_bind_group(&wgpu::BindGroupDescriptor { label: None, layout: &geo_l,
            entries: &[e(0, cam), e(1, pos), e(2, &b_nrm), e(3, &b_uv), e(4, tl), e(5, lv), e(6, ord)] })
    };
    let body_bgs: Vec<wgpu::BindGroup> = cams.iter().map(|c| geo_bg(c, &b_pos, &b_tl, &b_lv, &b_ord)).collect();
    let hull_bg = geo_bg(&cams[0], &h_pos, &h_tl, &h_lv, &h_ord);

    // textures (bottom row first, as Blender stores them, so UV v samples directly) and per-material groups
    let texs: Vec<wgpu::Texture> = meta["textures"].as_array().unwrap().iter().enumerate().map(|(i, t)| {
        let (tw, th) = (t["w"].as_u64().unwrap() as u32, t["h"].as_u64().unwrap() as u32);
        let fmt = if t["srgb"].as_bool().unwrap() { wgpu::TextureFormat::Rgba8UnormSrgb } else { wgpu::TextureFormat::Rgba8Unorm };
        device.create_texture_with_data(&queue, &wgpu::TextureDescriptor { label: None, size: wgpu::Extent3d { width: tw, height: th, depth_or_array_layers: 1 },
            mip_level_count: 1, sample_count: 1, dimension: wgpu::TextureDimension::D2, format: fmt,
            usage: wgpu::TextureUsages::TEXTURE_BINDING | wgpu::TextureUsages::COPY_DST, view_formats: &[] },
            wgpu::util::TextureDataOrder::LayerMajor, &fs::read(bake.join(format!("tex_{i}.rgba"))).unwrap())
    }).collect();
    let white = device.create_texture_with_data(&queue, &wgpu::TextureDescriptor { label: None, size: wgpu::Extent3d { width: 1, height: 1, depth_or_array_layers: 1 },
        mip_level_count: 1, sample_count: 1, dimension: wgpu::TextureDimension::D2, format: wgpu::TextureFormat::Rgba8Unorm,
        usage: wgpu::TextureUsages::TEXTURE_BINDING | wgpu::TextureUsages::COPY_DST, view_formats: &[] }, wgpu::util::TextureDataOrder::LayerMajor, &[255; 4]);
    let sampler = |filter| device.create_sampler(&wgpu::SamplerDescriptor { address_mode_u: wgpu::AddressMode::Repeat, address_mode_v: wgpu::AddressMode::Repeat,
        mag_filter: filter, min_filter: filter, ..Default::default() });
    let (lin_s, near_s) = (sampler(wgpu::FilterMode::Linear), sampler(wgpu::FilterMode::Nearest));
    let mat_bgs: Vec<wgpu::BindGroup> = mats.iter().map(|m| {
        let v3 = |k: &str| { let a = m[k].as_array().unwrap(); [a[0].as_f64().unwrap() as f32, a[1].as_f64().unwrap() as f32, a[2].as_f64().unwrap() as f32, 1.0] };
        let tex = m["tex"].as_u64();
        let u = buf(bytemuck::bytes_of(&Mat { id: v3("id"), color: v3("color"), flags: [tex.is_some() as u32, 0, 0, 0] }), uni);
        let view = tex.map(|t| &texs[t as usize]).unwrap_or(&white).create_view(&Default::default());
        device.create_bind_group(&wgpu::BindGroupDescriptor { label: None, layout: &mat_l, entries: &[
            wgpu::BindGroupEntry { binding: 0, resource: u.as_entire_binding() },
            wgpu::BindGroupEntry { binding: 1, resource: wgpu::BindingResource::TextureView(&view) },
            wgpu::BindGroupEntry { binding: 2, resource: wgpu::BindingResource::Sampler(if m["nearest"].as_bool().unwrap() { &near_s } else { &lin_s }) }] })
    }).collect();

    // --- targets
    let size = wgpu::Extent3d { width: w, height: h, depth_or_array_layers: 1 };
    let target = |fmt, extra| device.create_texture(&wgpu::TextureDescriptor { label: None, size, mip_level_count: 1, sample_count: 1,
        dimension: wgpu::TextureDimension::D2, format: fmt, usage: wgpu::TextureUsages::RENDER_ATTACHMENT | extra, view_formats: &[] });
    let sub = target(wgpu::TextureFormat::Rgba16Float, wgpu::TextureUsages::TEXTURE_BINDING);
    let idt = target(wgpu::TextureFormat::Rgba32Float, wgpu::TextureUsages::TEXTURE_BINDING);
    let dat = target(wgpu::TextureFormat::Rgba32Float, wgpu::TextureUsages::TEXTURE_BINDING);
    let hul = target(wgpu::TextureFormat::Rgba8Unorm, wgpu::TextureUsages::COPY_SRC);
    let depth = target(wgpu::TextureFormat::Depth32Float, wgpu::TextureUsages::empty());
    let (sub_v, id_v, dat_v, hul_v, dep_v) = (sub.create_view(&Default::default()), idt.create_view(&Default::default()),
        dat.create_view(&Default::default()), hul.create_view(&Default::default()), depth.create_view(&Default::default()));

    let rlayout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor { label: None, bind_group_layouts: &[Some(&geo_l), Some(&mat_l)], immediate_size: 0 });
    let pipe = |vs: &str, fs_: &str, fmt, cull| device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
        label: None, layout: Some(&rlayout),
        vertex: wgpu::VertexState { module: &shader, entry_point: Some(vs), compilation_options: Default::default(), buffers: &[] },
        fragment: Some(wgpu::FragmentState { module: &shader, entry_point: Some(fs_), compilation_options: Default::default(),
            targets: &[Some(wgpu::ColorTargetState { format: fmt, blend: None, write_mask: wgpu::ColorWrites::ALL })] }),
        primitive: wgpu::PrimitiveState { cull_mode: cull, front_face: wgpu::FrontFace::Ccw, ..Default::default() },
        depth_stencil: Some(wgpu::DepthStencilState { format: wgpu::TextureFormat::Depth32Float, depth_write_enabled: Some(true),
            depth_compare: Some(wgpu::CompareFunction::Less), stencil: Default::default(), bias: Default::default() }),
        multisample: Default::default(), multiview_mask: None, cache: None });
    let p_color = pipe("vs_body", "fs_color", wgpu::TextureFormat::Rgba16Float, None);
    let p_id = pipe("vs_body", "fs_id", wgpu::TextureFormat::Rgba32Float, None);
    let p_data = pipe("vs_body", "fs_data", wgpu::TextureFormat::Rgba32Float, None);
    let p_hold = pipe("vs_hull", "fs_hold", wgpu::TextureFormat::Rgba8Unorm, None);
    let p_shell = pipe("vs_hull", "fs_shell", wgpu::TextureFormat::Rgba8Unorm, Some(wgpu::Face::Back));

    // colour AA accumulation (compute)
    let npx = (w * h) as usize;
    let sum = empty(npx * 16, wgpu::BufferUsages::STORAGE);
    let colpx = empty(npx * 4, wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_SRC);
    let idpx = empty(npx * 4, wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_SRC);
    let datpx = empty(npx * 4, wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_SRC);
    let mut wsum = 0.0;
    let accs: Vec<wgpu::Buffer> = jit.iter().enumerate().map(|(s, &(jx, jy))| {
        let mut a = Acc { w: [0.0; 12], size: [w, h, (s == 0) as u32, 0] };
        for k in 0..9 {
            let (nx, ny) = ((k / 3) as f64 - 1.0, (k % 3) as f64 - 1.0);   // Blender's order: x outer, y inner
            let wk = blackman_harris(((nx - jx).powi(2) + (ny - jy).powi(2)).sqrt(), 2.0);
            a.w[k] = wk as f32; wsum += wk;
        }
        a
    }).collect::<Vec<_>>().into_iter().map(|mut a| { a.size[3] = (wsum as f32).to_bits(); buf(bytemuck::bytes_of(&a), uni) }).collect();
    let comp = device.create_compute_pipeline(&wgpu::ComputePipelineDescriptor { label: None, layout: None, module: &shader,
        entry_point: Some("accumulate"), compilation_options: Default::default(), cache: None });
    let reso = device.create_compute_pipeline(&wgpu::ComputePipelineDescriptor { label: None, layout: None, module: &shader,
        entry_point: Some("resolve"), compilation_options: Default::default(), cache: None });
    let acc_bgs: Vec<wgpu::BindGroup> = accs.iter().map(|a| device.create_bind_group(&wgpu::BindGroupDescriptor { label: None,
        layout: &comp.get_bind_group_layout(0), entries: &[
            wgpu::BindGroupEntry { binding: 0, resource: a.as_entire_binding() },
            wgpu::BindGroupEntry { binding: 1, resource: wgpu::BindingResource::TextureView(&sub_v) },
            wgpu::BindGroupEntry { binding: 2, resource: sum.as_entire_binding() }] })).collect();
    let res_bg = device.create_bind_group(&wgpu::BindGroupDescriptor { label: None, layout: &reso.get_bind_group_layout(0), entries: &[
        wgpu::BindGroupEntry { binding: 0, resource: accs[0].as_entire_binding() },
        wgpu::BindGroupEntry { binding: 2, resource: sum.as_entire_binding() },
        wgpu::BindGroupEntry { binding: 3, resource: colpx.as_entire_binding() }] });

    let cs = wgpu::ShaderStages::COMPUTE;
    let enc_l = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor { label: None, entries: &[
        wgpu::BindGroupLayoutEntry { binding: 0, visibility: cs, ty: wgpu::BindingType::Buffer { ty: wgpu::BufferBindingType::Uniform, has_dynamic_offset: false, min_binding_size: None }, count: None },
        wgpu::BindGroupLayoutEntry { binding: 4, visibility: cs, ty: wgpu::BindingType::Texture { sample_type: wgpu::TextureSampleType::Float { filterable: false }, view_dimension: wgpu::TextureViewDimension::D2, multisampled: false }, count: None },
        wgpu::BindGroupLayoutEntry { binding: 5, visibility: cs, ty: wgpu::BindingType::Texture { sample_type: wgpu::TextureSampleType::Float { filterable: false }, view_dimension: wgpu::TextureViewDimension::D2, multisampled: false }, count: None },
        wgpu::BindGroupLayoutEntry { binding: 6, visibility: cs, ty: wgpu::BindingType::Buffer { ty: wgpu::BufferBindingType::Storage { read_only: false }, has_dynamic_offset: false, min_binding_size: None }, count: None },
        wgpu::BindGroupLayoutEntry { binding: 7, visibility: cs, ty: wgpu::BindingType::Buffer { ty: wgpu::BufferBindingType::Storage { read_only: false }, has_dynamic_offset: false, min_binding_size: None }, count: None }] });
    let encp = device.create_compute_pipeline(&wgpu::ComputePipelineDescriptor { label: None,
        layout: Some(&device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor { label: None, bind_group_layouts: &[Some(&enc_l)], immediate_size: 0 })),
        module: &shader, entry_point: Some("encode"), compilation_options: Default::default(), cache: None });
    let enc_bg = device.create_bind_group(&wgpu::BindGroupDescriptor { label: None, layout: &enc_l, entries: &[
        wgpu::BindGroupEntry { binding: 0, resource: accs[0].as_entire_binding() },
        wgpu::BindGroupEntry { binding: 4, resource: wgpu::BindingResource::TextureView(&id_v) },
        wgpu::BindGroupEntry { binding: 5, resource: wgpu::BindingResource::TextureView(&dat_v) },
        wgpu::BindGroupEntry { binding: 6, resource: idpx.as_entire_binding() },
        wgpu::BindGroupEntry { binding: 7, resource: datpx.as_entire_binding() }] });
    let pass_bytes = npx * 4;
    let readback: Vec<wgpu::Buffer> = (0..2).map(|_| empty(pass_bytes * 4, wgpu::BufferUsages::MAP_READ | wgpu::BufferUsages::COPY_DST)).collect();
    let t_setup = t_start.elapsed().as_secs_f64() - t_load;

    // --- frames
    let (mut t_gpu, mut t_write) = (0.0, 0.0);
    let t_frames = Instant::now();
    rayon::scope(|scope| {
        for fr in 0..nframes {
            let t0 = Instant::now();
            let ff = &frame_files[fr];
            queue.write_buffer(&b_pos, 0, &ff[..bv * 12]);
            queue.write_buffer(&b_nrm, 0, &ff[bv * 12..bv * 12 + bl * 12]);
            queue.write_buffer(&h_pos, 0, &ff[bv * 12 + bl * 12..bv * 12 + bl * 12 + hv * 12]);
            let mut enc = device.create_command_encoder(&Default::default());
            let draw = |enc: &mut wgpu::CommandEncoder, view: &wgpu::TextureView, f: &dyn Fn(&mut wgpu::RenderPass)| {
                let mut rp = enc.begin_render_pass(&wgpu::RenderPassDescriptor { label: None,
                    color_attachments: &[Some(wgpu::RenderPassColorAttachment { view, resolve_target: None, depth_slice: None,
                        ops: wgpu::Operations { load: wgpu::LoadOp::Clear(wgpu::Color::TRANSPARENT), store: wgpu::StoreOp::Store } })],
                    depth_stencil_attachment: Some(wgpu::RenderPassDepthStencilAttachment { view: &dep_v,
                        depth_ops: Some(wgpu::Operations { load: wgpu::LoadOp::Clear(1.0), store: wgpu::StoreOp::Discard }), stencil_ops: None }),
                    timestamp_writes: None, occlusion_query_set: None, multiview_mask: None });
                f(&mut rp);
            };
            let body = |rp: &mut wgpu::RenderPass, p: &wgpu::RenderPipeline, bg: &wgpu::BindGroup| {
                rp.set_pipeline(p);
                rp.set_bind_group(0, bg, &[]);
                for &(m, s, e) in &ranges { rp.set_bind_group(1, &mat_bgs[m], &[]); rp.draw(s * 3..e * 3, 0..1); }
            };
            for s in 0..AA {
                draw(&mut enc, &sub_v, &|rp| body(rp, &p_color, &body_bgs[s + 1]));
                let mut cp = enc.begin_compute_pass(&Default::default());
                cp.set_pipeline(&comp); cp.set_bind_group(0, &acc_bgs[s], &[]);
                cp.dispatch_workgroups(w.div_ceil(16), h.div_ceil(16), 1);
            }
            {
                let mut cp = enc.begin_compute_pass(&Default::default());
                cp.set_pipeline(&reso); cp.set_bind_group(0, &res_bg, &[]);
                cp.dispatch_workgroups(w.div_ceil(16), h.div_ceil(16), 1);
            }
            draw(&mut enc, &id_v, &|rp| body(rp, &p_id, &body_bgs[0]));
            draw(&mut enc, &dat_v, &|rp| body(rp, &p_data, &body_bgs[0]));
            draw(&mut enc, &hul_v, &|rp| {
                rp.set_bind_group(0, &hull_bg, &[]); rp.set_bind_group(1, &mat_bgs[0], &[]);
                rp.set_pipeline(&p_hold); rp.draw(0..n_hold * 3, 0..1);
                rp.set_pipeline(&p_shell); rp.draw(n_hold * 3..ht as u32 * 3, 0..1);
            });
            {
                let mut cp = enc.begin_compute_pass(&Default::default());
                cp.set_pipeline(&encp); cp.set_bind_group(0, &enc_bg, &[]);
                cp.dispatch_workgroups(w.div_ceil(16), h.div_ceil(16), 1);
            }
            let rb = &readback[fr % 2];
            for (i, b) in [&colpx, &idpx, &datpx].iter().enumerate() {
                enc.copy_buffer_to_buffer(b, 0, rb, (i * pass_bytes) as u64, pass_bytes as u64);
            }
            enc.copy_texture_to_buffer(hul.as_image_copy(), wgpu::TexelCopyBufferInfo { buffer: rb, layout: wgpu::TexelCopyBufferLayout {
                offset: (3 * pass_bytes) as u64, bytes_per_row: Some(w * 4), rows_per_image: Some(h) } }, size);
            queue.submit([enc.finish()]);
            let slice = rb.slice(..);
            slice.map_async(wgpu::MapMode::Read, |r| r.unwrap());
            device.poll(wgpu::PollType::wait_indefinitely()).unwrap();
            let data = slice.get_mapped_range().unwrap().to_vec();
            rb.unmap();
            t_gpu += t0.elapsed().as_secs_f64();
            if write {
                let out = out.clone();
                let t1 = Instant::now();
                scope.spawn(move |_| {
                    for (i, kind) in ["color", "id", "data", "hull"].iter().enumerate() {
                        tga(&out.join(format!("{kind}_{:04}.tga", fr + 1)), w as usize, h as usize, &data[i * pass_bytes..(i + 1) * pass_bytes], *kind == "hull");
                    }
                });
                t_write += t1.elapsed().as_secs_f64();
            }
        }
    });
    let t_all = t_frames.elapsed().as_secs_f64();
    println!("{}", serde_json::json!({"load": t_load, "setup": t_setup, "gpu_and_readback": t_gpu, "frames_total": t_all,
        "frames": nframes, "adapter": adapter.get_info().name}));
}
