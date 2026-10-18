"""The lines pass without Freestyle: the mesh's own edges (border, silhouette between front- and
back-facing faces, creases sharper than the crease angle), kept where nothing is in front of
them, drawn as strokes `thickness` render px wide. Same kinds of lines as the Freestyle setup in
render_sprite.py, ~20x faster; render.freestyle.engine "freestyle" brings Freestyle back.

render_sprite.py calls trace() inside Blender (posed meshes -> projected arrays -> lines PNG).
The work is done by the Rust core (rustcore.trace_lines) when it is built, else by trace_numpy()
below, which gives the same pixels.
"""
import math
import struct
import zlib

import numpy as np

SS = 4                                             # supersampling per render px for stroke coverage


def export(scene, meshes):
    """the posed meshes as arrays: world vertices, screen x / y (render px), NDC depth, camera
    position, triangles, polygons (loops + (start, count)) and edges, all meshes concatenated"""
    import bpy
    dg = bpy.context.evaluated_depsgraph_get()
    W, H = scene.render.resolution_x, scene.render.resolution_y
    cam = scene.camera
    P = np.array(cam.calc_matrix_camera(dg, x=W, y=H)) @ np.array(cam.matrix_world.inverted())
    V, tris, loops, poly, edges = [], [], [], [], []
    base = nloop = 0
    for o in meshes:
        e = o.evaluated_get(dg)
        m = e.to_mesh()
        co = np.empty(len(m.vertices) * 3, np.float32); m.vertices.foreach_get("co", co)
        Mw = np.array(o.matrix_world)
        V.append(co.reshape(-1, 3).astype(np.float64) @ Mw[:3, :3].T + Mw[:3, 3])
        m.calc_loop_triangles()
        tv = np.empty(len(m.loop_triangles) * 3, np.int32); m.loop_triangles.foreach_get("vertices", tv)
        tris.append(tv.reshape(-1, 3) + base)
        lv = np.empty(len(m.loops), np.int32); m.loops.foreach_get("vertex_index", lv)
        ls = np.empty(len(m.polygons), np.int32); m.polygons.foreach_get("loop_start", ls)
        lt = np.empty(len(m.polygons), np.int32); m.polygons.foreach_get("loop_total", lt)
        loops.append(lv + base); poly.append(np.stack([ls + nloop, lt], 1))
        ev = np.empty(len(m.edges) * 2, np.int32); m.edges.foreach_get("vertices", ev)
        edges.append(ev.reshape(-1, 2) + base)
        base += len(m.vertices); nloop += len(m.loops)
        e.to_mesh_clear()
    V = np.concatenate(V)
    h = np.c_[V, np.ones(len(V))] @ P.T
    ndc = h[:, :3] / h[:, 3:4]
    return {"V": V, "sx": (ndc[:, 0] + 1) / 2 * W, "sy": (1 - (ndc[:, 1] + 1) / 2) * H, "z": ndc[:, 2].copy(),
            "campos": np.array(cam.matrix_world.translation, np.float64), "tris": np.concatenate(tris),
            "loops": np.concatenate(loops), "poly": np.concatenate(poly), "edges": np.concatenate(edges), "W": W, "H": H}


KINDS = {"border": 1, "silhouette": 2, "contour": 2, "external_contour": 2, "crease": 4}


def kinds_of(edge_types):
    """Freestyle edge types -> the tracer's bits; None if one of them can't be traced"""
    if any(e not in KINDS for e in edge_types):
        return None
    return sum({KINDS[e] for e in edge_types})


def trace(scene, meshes, crease_deg, thickness, kinds, eps=2e-5):
    """the lines pass's alpha (H x W, uint8) for the scene as posed"""
    import rustcore
    m = export(scene, meshes)
    fn = rustcore.trace_lines if rustcore.lib is not None else trace_numpy
    return fn(m, math.cos(math.radians(180 - crease_deg)), thickness, eps, kinds)


def write_tga(path, alpha):
    """as write_png, uncompressed Targa (render.SPRITE_RENDER_FORMAT=TGA)"""
    h, w = alpha.shape
    px = np.empty((h, w, 4), np.uint8); px[..., :3] = 255; px[..., 3] = alpha        # BGRA: white either way
    with open(path, "wb") as f:
        f.write(struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, w, h, 32, 0x28) + px.tobytes())


def write_png(path, alpha):
    """white strokes with this alpha, as an RGBA PNG (what the Freestyle pass looks like)"""
    h, w = alpha.shape
    px = np.empty((h, w, 4), np.uint8); px[..., :3] = 255; px[..., 3] = alpha
    raw = b"".join(b"\x00" + row.tobytes() for row in px)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b""))


def trace_numpy(m, cos_lim, thickness, eps, kinds=7):
    """reference version (the Rust one does the same operations in the same order).
    kinds: 1 = borders, 2 = silhouettes, 4 = creases"""
    W, H = int(m["W"]), int(m["H"])
    V, sx, sy, z = m["V"], m["sx"], m["sy"], m["z"]
    loops, poly, campos = m["loops"], m["poly"], m["campos"]
    # depth buffer: nearest NDC depth per pixel centre
    zb = np.full((H, W), np.inf)
    for a, b, c in m["tris"].tolist():
        xs = (float(sx[a]), float(sx[b]), float(sx[c])); ys = (float(sy[a]), float(sy[b]), float(sy[c]))
        x0, x1 = max(math.floor(min(xs) - 0.5), 0), min(math.ceil(max(xs) - 0.5), W - 1)
        y0, y1 = max(math.floor(min(ys) - 0.5), 0), min(math.ceil(max(ys) - 0.5), H - 1)
        if x1 < x0 or y1 < y0:
            continue
        den = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
        if abs(den) < 1e-12:
            continue
        px, py = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        l0 = ((ys[1] - ys[2]) * (px - xs[2]) + (xs[2] - xs[1]) * (py - ys[2])) / den
        l1 = ((ys[2] - ys[0]) * (px - xs[2]) + (xs[0] - xs[2]) * (py - ys[2])) / den
        l2 = 1 - l0 - l1
        zz = l0 * float(z[a]) + l1 * float(z[b]) + l2 * float(z[c])
        sub = zb[y0:y1 + 1, x0:x1 + 1]
        np.minimum(sub, np.where((l0 >= 0) & (l1 >= 0) & (l2 >= 0), zz, np.inf), out=sub)
    # faces: normal (Newell), facing the camera or not; edges -> their faces
    nf = len(poly)
    nrm = np.zeros((nf, 3)); front = np.zeros(nf, bool)
    adj = {}
    for k, (ls, lt) in enumerate(poly.tolist()):
        vi = loops[ls:ls + lt].tolist()
        n0 = n1 = n2 = c0 = c1 = c2 = 0.0
        for i in range(lt):
            p, q = V[vi[i]], V[vi[(i + 1) % lt]]
            n0 += (float(p[1]) - float(q[1])) * (float(p[2]) + float(q[2]))
            n1 += (float(p[2]) - float(q[2])) * (float(p[0]) + float(q[0]))
            n2 += (float(p[0]) - float(q[0])) * (float(p[1]) + float(q[1]))
            c0 += float(p[0]); c1 += float(p[1]); c2 += float(p[2])
            e = (min(vi[i], vi[(i + 1) % lt]), max(vi[i], vi[(i + 1) % lt]))
            adj.setdefault(e, []).append(k)
        ln = math.sqrt(n0 * n0 + n1 * n1 + n2 * n2) + 1e-20
        nrm[k] = (n0 / ln, n1 / ln, n2 / ln)
        c0, c1, c2 = c0 / lt - float(campos[0]), c1 / lt - float(campos[1]), c2 / lt - float(campos[2])
        front[k] = n0 * c0 + n1 * c1 + n2 * c2 < 0
    # lines: borders, silhouettes, creases; visible samples stamped as stroke-wide discs
    r = thickness / 2 * SS
    R = math.ceil(r)
    disc = [(dy, dx) for dy in range(-R, R + 1) for dx in range(-R, R + 1) if dx * dx + dy * dy <= r * r]
    cov = np.zeros((H * SS, W * SS), bool)
    for a, b in m["edges"].tolist():
        fs = adj.get((min(a, b), max(a, b)), [])
        if len(fs) == 2:
            f0, f1 = fs
            d = nrm[f0, 0] * nrm[f1, 0] + nrm[f0, 1] * nrm[f1, 1] + nrm[f0, 2] * nrm[f1, 2]
            if not ((kinds & 2 and front[f0] != front[f1]) or (kinds & 4 and d < cos_lim)):
                continue
        elif len(fs) != 1 or not kinds & 1:
            continue
        xa, ya, za = float(sx[a]), float(sy[a]), float(z[a])
        dxe, dye, dze = float(sx[b]) - xa, float(sy[b]) - ya, float(z[b]) - za
        n = max(int(math.hypot(dxe, dye) * 2) + 1, 2)
        step = 1 / (n - 1)
        for i in range(n):
            t = 1.0 if i == n - 1 else i * step
            X, Y, Z = xa + dxe * t, ya + dye * t, za + dze * t
            ix, iy = math.floor(X), math.floor(Y)
            if not (0 <= ix < W and 0 <= iy < H) or not Z <= zb[iy, ix] + eps:
                continue
            cx, cy = int(X * SS), int(Y * SS)
            for dy, dx in disc:
                if 0 <= cx + dx < W * SS and 0 <= cy + dy < H * SS:
                    cov[cy + dy, cx + dx] = True
    k = cov.reshape(H, SS, W, SS).sum((1, 3))
    return np.round(k / (SS * SS) * 255).astype(np.uint8)
