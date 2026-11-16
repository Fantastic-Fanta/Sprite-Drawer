// Vertex pulling from the bake: triangle (via order[]) -> loop -> vertex; positions/normals per frame.
struct Cam { mvp: mat4x4<f32>, view: mat4x4<f32> };
@group(0) @binding(0) var<uniform> cam: Cam;
@group(0) @binding(1) var<storage, read> pos: array<f32>;
@group(0) @binding(2) var<storage, read> nrm: array<f32>;
@group(0) @binding(3) var<storage, read> uvs: array<f32>;
@group(0) @binding(4) var<storage, read> tri_loops: array<u32>;
@group(0) @binding(5) var<storage, read> loop_vert: array<u32>;
@group(0) @binding(6) var<storage, read> order: array<u32>;

struct Mat { color: vec4<f32>, flags: vec4<u32> }; // flags: textured, group, alpha cutoff, premultiplied
@group(1) @binding(0) var<uniform> mat: Mat;
@group(1) @binding(1) var tex: texture_2d<f32>;
@group(1) @binding(2) var smp: sampler;

struct VOut { @builtin(position) p: vec4<f32>, @location(0) n: vec3<f32>, @location(1) uv: vec2<f32> };

fn loop_of(vi: u32) -> u32 {
    let tri = order[vi / 3u];
    return tri_loops[tri * 3u + vi % 3u];
}
fn vpos(v: u32) -> vec4<f32> { return vec4<f32>(pos[v * 3u], pos[v * 3u + 1u], pos[v * 3u + 2u], 1.0); }

@vertex fn vs_body(@builtin(vertex_index) vi: u32) -> VOut {
    let l = loop_of(vi);
    var o: VOut;
    o.p = cam.mvp * vpos(loop_vert[l]);
    o.n = vec3<f32>(nrm[l * 3u], nrm[l * 3u + 1u], nrm[l * 3u + 2u]);
    o.uv = vec2<f32>(uvs[l * 2u], uvs[l * 2u + 1u]);
    return o;
}

@vertex fn vs_hull(@builtin(vertex_index) vi: u32) -> @builtin(position) vec4<f32> {
    return cam.mvp * vpos(loop_vert[loop_of(vi)]);
}

// colour: Workbench flat texture colour (workbench_image_color: texture alpha < 0.1 cut), alpha = coverage
@fragment fn fs_color(i: VOut) -> @location(0) vec4<f32> {
    if (mat.flags.x == 0u) { return vec4<f32>(mat.color.rgb, 1.0); }
    var c = textureSample(tex, smp, i.uv);
    if (mat.flags.w == 1u && c.a != 0.0 && c.a != 1.0) { c = vec4<f32>(c.rgb / c.a, c.a); }
    if (mat.flags.z == 1u && c.a < 0.1) { discard; }
    return vec4<f32>(c.rgb, 1.0);
}

@fragment fn fs_id(i: VOut) -> @location(0) vec4<f32> { return vec4<f32>(f32(mat.flags.y), 0.0, 0.0, 0.0); }

// data: camera-space shading normal (flipped toward the viewer on back faces) * 0.5 + 0.5 in R/G
@fragment fn fs_data(i: VOut, @builtin(front_facing) ff: bool) -> @location(0) vec4<f32> {
    var n = normalize(i.n);
    if (!ff) { n = -n; }
    let c = (cam.view * vec4<f32>(n, 0.0)).xyz;
    return vec4<f32>(c.x * 0.5 + 0.5, c.y * 0.5 + 0.5, 0.0, 1.0);
}

@fragment fn fs_hold() -> @location(0) vec4<f32> { return vec4<f32>(0.0); }
@fragment fn fs_shell() -> @location(0) vec4<f32> { return vec4<f32>(1.0); }

// --- colour AA: each jittered sub-frame added to its 3x3 neighbours with Blackman-Harris weights
struct Acc { w0: vec4<f32>, w1: vec4<f32>, w2: vec4<f32>, size: vec4<u32>, crop: vec4<i32> };
@group(0) @binding(0) var<uniform> acc: Acc;
@group(0) @binding(1) var sub: texture_2d<f32>;
@group(0) @binding(2) var<storage, read_write> sum: array<vec4<f32>>;
@group(0) @binding(3) var<storage, read_write> outpx: array<u32>;
@group(0) @binding(10) var<uniform> reg: vec4<u32>; // this frame's colour region: x0, y0, w, h (the rest is empty)

fn wt(k: u32) -> f32 {
    if (k < 4u) { return acc.w0[k]; }
    if (k < 8u) { return acc.w1[k - 4u]; }
    return acc.w2[0];
}

@compute @workgroup_size(16, 16) fn accumulate(@builtin(global_invocation_id) gi: vec3<u32>) {
    let W = acc.size.x; let H = acc.size.y;
    if (gi.x >= reg.z || gi.y >= reg.w) { return; }
    let g = gi.xy + reg.xy;
    var s = vec4<f32>(0.0);
    for (var k = 0u; k < 9u; k++) {
        // neighbour (x, y) in GL pixels (y up; our rows go down), edge-clamped; colour in log2(c + 1)
        let x = clamp(i32(g.x) + i32(k / 3u) - 1, 0, i32(W) - 1);
        let y = clamp(i32(g.y) - (i32(k % 3u) - 1), 0, i32(H) - 1);
        let c = textureLoad(sub, vec2<i32>(x, y), 0);
        s += wt(k) * vec4<f32>(log2(c.rgb + 1.0), c.a);
    }
    let i = g.y * W + g.x;
    if (acc.size.z == 1u) { sum[i] = s; } else { sum[i] += s; }
}

// Blender's 8-bit write: dither_random_value (iqint3 hash, triangle pdf) * 0.0033 added to RGB, then
// unit_float_to_uchar_clamp. x, y in ImBuf coordinates (row 0 at the bottom).
fn dither(x: u32, y: u32) -> f32 {
    let qx = 1103515245u * ((x >> 1u) ^ y);
    let qy = 1103515245u * ((y >> 1u) ^ x);
    let n = 1103515245u * (qx ^ (qy >> 3u));
    var v = f32(n) * (1.0 / 4294967296.0);
    v = v * 2.0 - 1.0;
    return sign(v) * (1.0 - sqrt(1.0 - abs(v))) * 0.0033;
}
fn to_u8(v: f32) -> u32 {
    if (v <= 0.0) { return 0u; }
    if (v > 1.0 - 0.5 / 255.0) { return 255u; }
    return u32(255.0 * v + 0.5);
}
fn pack(c: vec3<f32>, a: f32, g: vec2<u32>) -> u32 {
    let d = dither(g.x, acc.size.y - 1u - g.y);
    return to_u8(c.r + d) | (to_u8(c.g + d) << 8u) | (to_u8(c.b + d) << 16u) | (to_u8(a) << 24u);
}

fn oetf(c: f32) -> f32 {
    let x = clamp(c, 0.0, 1.0);
    if (x <= 0.0031308) { return 12.92 * x; }
    return 1.055 * pow(x, 1.0 / 2.4) - 0.055;
}

@compute @workgroup_size(16, 16) fn resolve(@builtin(global_invocation_id) gi: vec3<u32>) {
    let W = acc.size.x; let H = acc.size.y;
    if (gi.x >= reg.z || gi.y >= reg.w) { return; }
    let g = gi.xy + reg.xy;
    let i = g.y * W + g.x;
    var v = sum[i] / bitcast<f32>(acc.size.w);
    v = vec4<f32>(exp2(v.rgb) - 1.0, v.a);
    var a = clamp(v.a, 0.0, 1.0);
    if (a > 0.999) { a = 1.0; }
    var rgb = vec3<f32>(0.0);
    if (a > 0.0) { rgb = v.rgb / v.a; }      // straight alpha, as Blender writes 8-bit files
    outpx[i] = pack(vec3<f32>(oetf(rgb.r), oetf(rgb.g), oetf(rgb.b)), a, g);
    if (to_u8(a) > 8u) {
        atomicMax(&box[0], W - g.x); atomicMax(&box[1], H - g.y); atomicMax(&box[2], g.x + 1u); atomicMax(&box[3], g.y + 1u);
    }
}
@group(0) @binding(8) var<storage, read_write> box: array<atomic<u32>, 4>; // W - x0, H - y0, x1, y1

// the crop (size.zw at crop.xy, image px) as colour RGBA, then (data R, data G (Raw, dithered 8-bit), group, hull)
@group(0) @binding(4) var idf: texture_2d<f32>;
@group(0) @binding(5) var datf: texture_2d<f32>;
@group(0) @binding(9) var hulf: texture_2d<f32>;
@group(0) @binding(6) var<storage, read_write> crop: array<u32>;
@compute @workgroup_size(16, 16) fn encode(@builtin(global_invocation_id) g: vec3<u32>) {
    let cw = acc.size.z; let ch = acc.size.w;
    if (g.x >= cw || g.y >= ch) { return; }
    let p = vec2<i32>(g.xy) + acc.crop.xy;
    var col = 0u; var aux = 0u;
    if (p.x >= 0 && p.y >= 0 && p.x < i32(acc.size.x) && p.y < i32(acc.size.y)) {
        let q = vec2<u32>(p);
        if (all(q >= reg.xy) && all(q < reg.xy + reg.zw)) { col = outpx[q.y * acc.size.x + q.x]; }
        let d = textureLoad(datf, p, 0);
        let dy = dither(q.x, acc.size.y - 1u - q.y);
        aux = to_u8(d.r + dy) | (to_u8(d.g + dy) << 8u) | (u32(textureLoad(idf, p, 0).r) << 16u)
            | (select(0u, 255u, textureLoad(hulf, p, 0).r > 0.5) << 24u);
    }
    crop[g.y * cw + g.x] = col;
    crop[cw * ch + g.y * cw + g.x] = aux;
}
