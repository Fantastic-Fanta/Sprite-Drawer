//! bake.py's posed geometry -> the four passes Blender used to render, on the GPU (wgpu: Metal, Vulkan, DX12):
//! colour (Workbench flat texture, 8x TAA), material group, camera-space normal (EEVEE), inverted-hull lines.
//! Blender's own sampling, filter and 8-bit dither are reproduced, so the sprites match its renders.
use serde_json::Value;
use std::{fs, path::{Path, PathBuf}};
use wgpu::util::DeviceExt;

const AA: usize = 8; // Workbench render_aa "8"

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
fn e(i: u32, b: &wgpu::Buffer) -> wgpu::BindGroupEntry<'_> { wgpu::BindGroupEntry { binding: i, resource: b.as_entire_binding() } }
fn tv(i: u32, v: &wgpu::TextureView) -> wgpu::BindGroupEntry<'_> { wgpu::BindGroupEntry { binding: i, resource: wgpu::BindingResource::TextureView(v) } }
fn mat_of(v: &Value) -> [[f64; 4]; 4] { [0, 1, 2, 3].map(|i| [0, 1, 2, 3].map(|j| v[i][j].as_f64().unwrap())) }

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
                let (mut vx, mut vy) = (j[k][0] - x - 1.0, j[k][1] - y - 1.0);
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
                let (mut vx, mut vy) = (j[k][0] - x - 1.0, j[k][1] - y - 1.0);
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
    let (mut ci, mut cd) = (0, 1.0f32);
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

#[repr(C)]
#[derive(Clone, Copy, bytemuck::Pod, bytemuck::Zeroable)]
struct Cam { mvp: [f32; 16], view: [f32; 16] }
#[repr(C)]
#[derive(Clone, Copy, bytemuck::Pod, bytemuck::Zeroable)]
struct Mat { color: [f32; 4], flags: [u32; 4] } // flags: textured, group, alpha cutoff, premultiplied
#[repr(C)]
#[derive(Clone, Copy, bytemuck::Pod, bytemuck::Zeroable)]
struct Acc { w: [f32; 12], size: [u32; 4], crop: [i32; 4] }

pub struct Gpu {
    bake: PathBuf, pub w: u32, pub h: u32, sizes: [usize; 3], ht: u32, n_hold: u32, ranges: Vec<(usize, u32, u32)>,
    device: wgpu::Device, queue: wgpu::Queue, b_pos: wgpu::Buffer, b_nrm: wgpu::Buffer, h_pos: wgpu::Buffer,
    body_bgs: Vec<wgpu::BindGroup>, hull_bg: wgpu::BindGroup, mat_bgs: Vec<wgpu::BindGroup>,
    sub_v: wgpu::TextureView, id_v: wgpu::TextureView, dat_v: wgpu::TextureView, hul_v: wgpu::TextureView, dep_v: wgpu::TextureView,
    p_color: wgpu::RenderPipeline, p_id: wgpu::RenderPipeline, p_data: wgpu::RenderPipeline, p_hold: wgpu::RenderPipeline, p_shell: wgpu::RenderPipeline,
    comp: wgpu::ComputePipeline, reso: wgpu::ComputePipeline, encp: wgpu::ComputePipeline,
    acc_bgs: Vec<wgpu::BindGroup>, res_bg: wgpu::BindGroup, colpx: wgpu::Buffer, bbox: wgpu::Buffer, crop_u: wgpu::Buffer, reg: wgpu::Buffer, vp: [[f64; 4]; 4],
}

impl Gpu {
    pub fn new(bake: &Path) -> Gpu {
        let meta: Value = serde_json::from_str(&fs::read_to_string(bake.join("meta.json")).unwrap()).unwrap();
        let (w, h) = (meta["width"].as_u64().unwrap() as u32, meta["height"].as_u64().unwrap() as u32);
        let g = |k: &str, f: &str| meta[k][f].as_u64().unwrap() as usize;
        let (bv, bl, bt, hv, hl, ht) = (g("body", "verts"), g("body", "loops"), g("body", "tris"), g("hull", "verts"), g("hull", "loops"), g("hull", "tris"));
        let st = fs::read(bake.join("static.bin")).unwrap();
        let mut off = 0;
        let mut take = |n: usize| { let v: Vec<u32> = bytemuck::pod_collect_to_vec(&st[off..off + n * 4]); off += n * 4; v };
        let (btl, blv, buv, bmat, htl, hlv, hshell) = (take(bt * 3), take(bl), take(bl * 2), take(bt), take(ht * 3), take(hl), take(ht));

        // triangle draw order: body by material (one draw per material), hull body tris then shell tris
        let mats = meta["materials"].as_array().unwrap();
        let (mut border, mut ranges) = (vec![], vec![]);
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
        let f0 = fs::read(bake.join("frame_0000.bin")).unwrap();
        let p0: Vec<f32> = bytemuck::pod_collect_to_vec(&f0[..bv * 12]);
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
            let (dx, dy) = (ox / w as f64, oy / h as f64); // NDC (y up)
            let mut m = vp;
            for c in 0..4 { m[0][c] += dx * vp[3][c]; m[1][c] += dy * vp[3][c]; }
            Cam { mvp: col_major(&m), view: col_major(&view) }
        };

        // --- device
        let instance = wgpu::Instance::new(wgpu::InstanceDescriptor::new_without_display_handle());
        let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
            power_preference: wgpu::PowerPreference::HighPerformance, ..Default::default() })).expect("no GPU adapter");
        let (device, queue) = pollster::block_on(adapter.request_device(&wgpu::DeviceDescriptor::default())).unwrap();
        let shader = device.create_shader_module(wgpu::ShaderModuleDescriptor { label: None, source: wgpu::ShaderSource::Wgsl(include_str!("shader.wgsl").into()) });
        let st_ro = wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_DST;
        let buf = |data: &[u8], usage| device.create_buffer_init(&wgpu::util::BufferInitDescriptor { label: None, contents: data, usage });
        let empty = |size: usize, usage| device.create_buffer(&wgpu::BufferDescriptor { label: None, size: size as u64, usage, mapped_at_creation: false });
        let (b_pos, b_nrm, h_pos) = (empty(bv * 12, st_ro), empty(bl * 12, st_ro), empty(hv * 12, st_ro));
        let cast = |v: &[u32]| buf(bytemuck::cast_slice(v), st_ro);
        let (b_uv, b_tl, b_lv, b_ord, h_tl, h_lv, h_ord) = (cast(&buv), cast(&btl), cast(&blv), cast(&border), cast(&htl), cast(&hlv), cast(&horder));
        let uni = wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST;
        // Workbench TAA (workbench_effect_antialiasing.cc): sample offset o in [-1, 1] moves the image by o / 2 px,
        // weights are Blackman-Harris(|(x, y) - o|, 2.0) over 3x3.
        let jit: Vec<(f64, f64)> = workbench_taa_samples(AA).iter().map(|p| (p[0] as f64, p[1] as f64)).collect();
        let cams: Vec<wgpu::Buffer> = std::iter::once((0.0, 0.0)).chain(jit.iter().cloned())
            .map(|(x, y)| buf(bytemuck::bytes_of(&cam_for(x, y)), uni)).collect();

        let vis = wgpu::ShaderStages::VERTEX_FRAGMENT;
        let sto = |b| wgpu::BindGroupLayoutEntry { binding: b, visibility: vis, ty: wgpu::BindingType::Buffer {
            ty: wgpu::BufferBindingType::Storage { read_only: true }, has_dynamic_offset: false, min_binding_size: None }, count: None };
        let unif = |b, vis| wgpu::BindGroupLayoutEntry { binding: b, visibility: vis, ty: wgpu::BindingType::Buffer {
            ty: wgpu::BufferBindingType::Uniform, has_dynamic_offset: false, min_binding_size: None }, count: None };
        let geo_l = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor { label: None,
            entries: &[unif(0, vis), sto(1), sto(2), sto(3), sto(4), sto(5), sto(6)] });
        let mat_l = device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor { label: None, entries: &[unif(0, vis),
            wgpu::BindGroupLayoutEntry { binding: 1, visibility: vis, ty: wgpu::BindingType::Texture {
                sample_type: wgpu::TextureSampleType::Float { filterable: true }, view_dimension: wgpu::TextureViewDimension::D2, multisampled: false }, count: None },
            wgpu::BindGroupLayoutEntry { binding: 2, visibility: vis, ty: wgpu::BindingType::Sampler(wgpu::SamplerBindingType::Filtering), count: None }] });
        let geo_bg = |cam: &wgpu::Buffer, pos: &wgpu::Buffer, tl: &wgpu::Buffer, lv: &wgpu::Buffer, ord: &wgpu::Buffer| device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: None, layout: &geo_l, entries: &[e(0, cam), e(1, pos), e(2, &b_nrm), e(3, &b_uv), e(4, tl), e(5, lv), e(6, ord)] });
        let body_bgs: Vec<wgpu::BindGroup> = cams.iter().map(|c| geo_bg(c, &b_pos, &b_tl, &b_lv, &b_ord)).collect();
        let hull_bg = geo_bg(&cams[0], &h_pos, &h_tl, &h_lv, &h_ord);

        // textures (bottom row first, as Blender stores them, so UV v samples directly) and per-material groups
        let tex = |tw, th, fmt, data: &[u8]| device.create_texture_with_data(&queue, &wgpu::TextureDescriptor { label: None,
            size: wgpu::Extent3d { width: tw, height: th, depth_or_array_layers: 1 }, mip_level_count: 1, sample_count: 1,
            dimension: wgpu::TextureDimension::D2, format: fmt, usage: wgpu::TextureUsages::TEXTURE_BINDING | wgpu::TextureUsages::COPY_DST, view_formats: &[] },
            wgpu::util::TextureDataOrder::LayerMajor, data);
        let texs: Vec<wgpu::Texture> = meta["textures"].as_array().unwrap().iter().enumerate().map(|(i, t)| {
            let fmt = if t["srgb"].as_bool().unwrap() { wgpu::TextureFormat::Rgba8UnormSrgb } else { wgpu::TextureFormat::Rgba8Unorm };
            tex(t["w"].as_u64().unwrap() as u32, t["h"].as_u64().unwrap() as u32, fmt, &fs::read(bake.join(format!("tex_{i}.rgba"))).unwrap())
        }).collect();
        let white = tex(1, 1, wgpu::TextureFormat::Rgba8Unorm, &[255; 4]);
        let mat_bgs: Vec<wgpu::BindGroup> = mats.iter().map(|m| {
            let c = m["color"].as_array().unwrap();
            let t = m["tex"].as_u64();
            let flags = [t.is_some() as u32, m["group"].as_u64().unwrap() as u32, m["cutoff"].as_bool().unwrap() as u32, m["premul"].as_bool().unwrap() as u32];
            let u = buf(bytemuck::bytes_of(&Mat { color: [0, 1, 2, 3].map(|i| c.get(i).map_or(1.0, |v| v.as_f64().unwrap() as f32)), flags }), uni);
            let view = t.map(|t| &texs[t as usize]).unwrap_or(&white).create_view(&Default::default());
            let filter = if m["nearest"].as_bool().unwrap() { wgpu::FilterMode::Nearest } else { wgpu::FilterMode::Linear };
            let mode = match m["extension"].as_str().unwrap() {
                "EXTEND" | "CLIP" => wgpu::AddressMode::ClampToEdge, "MIRROR" => wgpu::AddressMode::MirrorRepeat, _ => wgpu::AddressMode::Repeat };
            let sampler = device.create_sampler(&wgpu::SamplerDescriptor { address_mode_u: mode, address_mode_v: mode, mag_filter: filter, min_filter: filter, ..Default::default() });
            device.create_bind_group(&wgpu::BindGroupDescriptor { label: None, layout: &mat_l, entries: &[e(0, &u),
                wgpu::BindGroupEntry { binding: 1, resource: wgpu::BindingResource::TextureView(&view) },
                wgpu::BindGroupEntry { binding: 2, resource: wgpu::BindingResource::Sampler(&sampler) }] })
        }).collect();

        // --- targets
        let size = wgpu::Extent3d { width: w, height: h, depth_or_array_layers: 1 };
        let target = |fmt| device.create_texture(&wgpu::TextureDescriptor { label: None, size, mip_level_count: 1, sample_count: 1,
            dimension: wgpu::TextureDimension::D2, format: fmt, usage: wgpu::TextureUsages::RENDER_ATTACHMENT | wgpu::TextureUsages::TEXTURE_BINDING, view_formats: &[] })
            .create_view(&Default::default());
        let (sub_v, id_v, dat_v, hul_v) = (target(wgpu::TextureFormat::Rgba16Float), target(wgpu::TextureFormat::R32Float),
            target(wgpu::TextureFormat::Rgba32Float), target(wgpu::TextureFormat::R32Float));
        let dep_v = target(wgpu::TextureFormat::Depth32Float);

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
        let p_id = pipe("vs_body", "fs_id", wgpu::TextureFormat::R32Float, None);
        let p_data = pipe("vs_body", "fs_data", wgpu::TextureFormat::Rgba32Float, None);
        let p_hold = pipe("vs_hull", "fs_hold", wgpu::TextureFormat::R32Float, None);
        let p_shell = pipe("vs_hull", "fs_shell", wgpu::TextureFormat::R32Float, Some(wgpu::Face::Back));

        // colour AA accumulation, resolve (+ alpha box), encode of the crop (compute)
        let npx = (w * h) as usize;
        let rw = wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_SRC | wgpu::BufferUsages::COPY_DST;
        let (sum, colpx, bbox, reg) = (empty(npx * 16, rw), empty(npx * 4, rw), empty(16, rw), empty(16, uni));
        let mut wsum = 0.0;
        let mut accs: Vec<Acc> = jit.iter().enumerate().map(|(s, &(jx, jy))| {
            let mut a = Acc { w: [0.0; 12], size: [w, h, (s == 0) as u32, 0], crop: [0; 4] };
            for k in 0..9 {
                let (nx, ny) = ((k / 3) as f64 - 1.0, (k % 3) as f64 - 1.0); // Blender's order: x outer, y inner
                let wk = blackman_harris(((nx - jx).powi(2) + (ny - jy).powi(2)).sqrt(), 2.0);
                a.w[k] = wk as f32; wsum += wk;
            }
            a
        }).collect();
        for a in &mut accs { a.size[3] = (wsum as f32).to_bits(); }
        let accs: Vec<wgpu::Buffer> = accs.iter().map(|a| buf(bytemuck::bytes_of(a), uni)).collect();
        let cpipe = |entry: &str| device.create_compute_pipeline(&wgpu::ComputePipelineDescriptor { label: None, layout: None, module: &shader,
            entry_point: Some(entry), compilation_options: Default::default(), cache: None });
        let (comp, reso, encp) = (cpipe("accumulate"), cpipe("resolve"), cpipe("encode"));
        let acc_bgs: Vec<wgpu::BindGroup> = accs.iter().map(|a| device.create_bind_group(&wgpu::BindGroupDescriptor { label: None,
            layout: &comp.get_bind_group_layout(0), entries: &[e(0, a), tv(1, &sub_v), e(2, &sum), e(10, &reg)] })).collect();
        let res_bg = device.create_bind_group(&wgpu::BindGroupDescriptor { label: None, layout: &reso.get_bind_group_layout(0),
            entries: &[e(0, &accs[0]), e(2, &sum), e(3, &colpx), e(8, &bbox), e(10, &reg)] });
        let crop_u = empty(std::mem::size_of::<Acc>(), uni);
        Gpu { bake: bake.into(), w, h, sizes: [bv * 12, bl * 12, hv * 12], ht: ht as u32, n_hold, ranges, device, queue,
              b_pos, b_nrm, h_pos, body_bgs, hull_bg, mat_bgs, sub_v, id_v, dat_v, hul_v, dep_v, p_color, p_id, p_data, p_hold, p_shell,
              comp, reso, encp, acc_bgs, res_bg, colpx, bbox, crop_u, reg, vp }
    }

    /// record frame f: its colour pass (alpha box in self.bbox) and, given an encode bind group, the crop
    fn encode(&self, f: usize, crop: Option<(&wgpu::BindGroup, u32, u32)>) -> wgpu::CommandEncoder {
        let ff = fs::read(self.bake.join(format!("frame_{f:04}.bin"))).unwrap();
        let [a, b, c] = self.sizes;
        self.queue.write_buffer(&self.b_pos, 0, &ff[..a]);
        self.queue.write_buffer(&self.b_nrm, 0, &ff[a..a + b]);
        self.queue.write_buffer(&self.h_pos, 0, &ff[a + b..a + b + c]);
        // the colour pass only covers the body's projected box (+ 3 px: sample jitter and the 3x3 filter)
        let (mut lo, mut hi) = ([f64::MAX; 2], [f64::MIN; 2]);
        for v in bytemuck::cast_slice::<u8, f32>(&ff[..a]).chunks(3) {
            let p = self.vp.map(|r| r[0] * v[0] as f64 + r[1] * v[1] as f64 + r[2] * v[2] as f64 + r[3]);
            let q = [(p[0] / p[3] + 1.0) / 2.0 * self.w as f64, (1.0 - p[1] / p[3]) / 2.0 * self.h as f64];
            for i in 0..2 { lo[i] = lo[i].min(q[i]); hi[i] = hi[i].max(q[i]); }
        }
        let (x0, y0) = ((lo[0].floor() - 3.0).max(0.0) as u32, (lo[1].floor() - 3.0).max(0.0) as u32);
        let (x1, y1) = (((hi[0].ceil() + 3.0) as u32).min(self.w), ((hi[1].ceil() + 3.0) as u32).min(self.h));
        let (rw, rh) = (x1.saturating_sub(x0), y1.saturating_sub(y0));
        self.queue.write_buffer(&self.reg, 0, bytemuck::cast_slice(&[x0, y0, rw, rh]));
        let mut enc = self.device.create_command_encoder(&Default::default());
        enc.clear_buffer(&self.bbox, 0, None);
        let draw = |enc: &mut wgpu::CommandEncoder, view: &wgpu::TextureView, f: &dyn Fn(&mut wgpu::RenderPass)| {
            let mut rp = enc.begin_render_pass(&wgpu::RenderPassDescriptor { label: None,
                color_attachments: &[Some(wgpu::RenderPassColorAttachment { view, resolve_target: None, depth_slice: None,
                    ops: wgpu::Operations { load: wgpu::LoadOp::Clear(wgpu::Color::TRANSPARENT), store: wgpu::StoreOp::Store } })],
                depth_stencil_attachment: Some(wgpu::RenderPassDepthStencilAttachment { view: &self.dep_v,
                    depth_ops: Some(wgpu::Operations { load: wgpu::LoadOp::Clear(1.0), store: wgpu::StoreOp::Discard }), stencil_ops: None }),
                timestamp_writes: None, occlusion_query_set: None, multiview_mask: None });
            f(&mut rp);
        };
        let body = |rp: &mut wgpu::RenderPass, p: &wgpu::RenderPipeline, bg: &wgpu::BindGroup| {
            rp.set_pipeline(p);
            rp.set_bind_group(0, bg, &[]);
            for &(m, s, e) in &self.ranges { rp.set_bind_group(1, &self.mat_bgs[m], &[]); rp.draw(s * 3..e * 3, 0..1); }
        };
        let compute = |enc: &mut wgpu::CommandEncoder, p: &wgpu::ComputePipeline, bg: &wgpu::BindGroup, x: u32, y: u32| {
            let mut cp = enc.begin_compute_pass(&Default::default());
            cp.set_pipeline(p); cp.set_bind_group(0, bg, &[]); cp.dispatch_workgroups(x.div_ceil(16), y.div_ceil(16), 1);
        };
        for s in 0..AA {
            draw(&mut enc, &self.sub_v, &|rp| body(rp, &self.p_color, &self.body_bgs[s + 1]));
            compute(&mut enc, &self.comp, &self.acc_bgs[s], rw, rh);
        }
        compute(&mut enc, &self.reso, &self.res_bg, rw, rh);
        if let Some((bg, cw, ch)) = crop {
            draw(&mut enc, &self.id_v, &|rp| body(rp, &self.p_id, &self.body_bgs[0]));
            draw(&mut enc, &self.dat_v, &|rp| body(rp, &self.p_data, &self.body_bgs[0]));
            draw(&mut enc, &self.hul_v, &|rp| {
                rp.set_bind_group(0, &self.hull_bg, &[]); rp.set_bind_group(1, &self.mat_bgs[0], &[]);
                rp.set_pipeline(&self.p_hold); rp.draw(0..self.n_hold * 3, 0..1);
                rp.set_pipeline(&self.p_shell); rp.draw(self.n_hold * 3..self.ht * 3, 0..1);
            });
            compute(&mut enc, &self.encp, bg, cw, ch);
        }
        enc
    }

    fn read(&self, rb: &wgpu::Buffer, idx: wgpu::SubmissionIndex) -> Vec<u8> {
        let slice = rb.slice(..);
        slice.map_async(wgpu::MapMode::Read, |r| r.unwrap());
        self.device.poll(wgpu::PollType::Wait { submission_index: Some(idx), timeout: None }).unwrap();
        let data = slice.get_mapped_range().unwrap().to_vec();
        rb.unmap();
        data
    }

    fn buffer(&self, size: u64, usage: wgpu::BufferUsages) -> wgpu::Buffer {
        self.device.create_buffer(&wgpu::BufferDescriptor { label: None, size, usage, mapped_at_creation: false })
    }

    /// each frame's colour alpha box [x0, y0, x1, y1] (8-bit alpha > 8, as PIL's getbbox); None if empty
    pub fn boxes(&self, n: usize) -> Vec<Option<[i64; 4]>> {
        let rb = self.buffer(16 * n as u64, wgpu::BufferUsages::MAP_READ | wgpu::BufferUsages::COPY_DST);
        let mut idx = None;
        for f in 0..n {
            let mut enc = self.encode(f, None);
            enc.copy_buffer_to_buffer(&self.bbox, 0, &rb, 16 * f as u64, 16);
            idx = Some(self.queue.submit([enc.finish()]));
        }
        let (w, h) = (self.w as i64, self.h as i64);
        self.read(&rb, idx.unwrap()).chunks(16).map(|c| {
            let b: [u32; 4] = bytemuck::pod_read_unaligned(c);
            (b[2] > 0).then(|| [w - b[0] as i64, h - b[1] as i64, b[2] as i64, b[3] as i64])
        }).collect()
    }

    /// every frame's crop [x0, y0, x1, y1] as colour (RGBA) then aux (normal x, normal y, material group, hull)
    /// bytes, zero outside the image, handed to `sink` in order; the GPU draws the next frame meanwhile
    pub fn passes(&self, n: usize, crop: [i64; 4], mut sink: impl FnMut(usize, Vec<u8>)) {
        let (cw, ch) = ((crop[2] - crop[0]) as u32, (crop[3] - crop[1]) as u32);
        let u = Acc { w: [0.0; 12], size: [self.w, self.h, cw, ch], crop: [crop[0] as i32, crop[1] as i32, 0, 0] };
        self.queue.write_buffer(&self.crop_u, 0, bytemuck::bytes_of(&u));
        let bytes = (cw * ch * 8) as u64;
        let slots: Vec<_> = (0..2).map(|_| {
            let o = self.buffer(bytes, wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_SRC);
            let bg = self.device.create_bind_group(&wgpu::BindGroupDescriptor { label: None, layout: &self.encp.get_bind_group_layout(0),
                entries: &[e(0, &self.crop_u), e(3, &self.colpx), tv(4, &self.id_v), tv(5, &self.dat_v), tv(9, &self.hul_v), e(6, &o), e(10, &self.reg)] });
            (o, self.buffer(bytes, wgpu::BufferUsages::MAP_READ | wgpu::BufferUsages::COPY_DST), bg)
        }).collect();
        let mut pending = None;
        for f in 0..=n {
            let next = (f < n).then(|| {
                let (o, rb, bg) = &slots[f % 2];
                let mut enc = self.encode(f, Some((bg, cw, ch)));
                enc.copy_buffer_to_buffer(o, 0, rb, 0, bytes);
                (f, self.queue.submit([enc.finish()]))
            });
            if let Some((g, idx)) = pending { sink(g, self.read(&slots[g % 2].1, idx)); }
            pending = next;
        }
    }
}
