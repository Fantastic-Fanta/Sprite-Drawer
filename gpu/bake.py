"""Inside Blender: pose every frame with pipeline/render_sprite.py's own setup and dump the geometry the
GPU renderer draws. JOB = {"config": cfg (model path absolute), "out": dir}; run via gpu/run.py.
Out: meta.json, static.bin (topology, UVs, materials), frames.bin (per-frame positions/normals), tex_*.rgba."""
import bpy, json, sys, time
from pathlib import Path
import numpy as np

t0 = time.time()
BAKE = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text())
out = Path(BAKE["out"]); out.mkdir(parents=True, exist_ok=True)
src = Path(BAKE["pipeline"]) / "render_sprite.py"
G = {"__name__": "__main__", "__file__": str(src), "JOB": {"config": BAKE["config"], "out": str(out), "frames": []}}
exec(compile(src.read_text(), str(src), "exec"), G)
pose_at, hull_on, cap_spikes, cam, meshes = G["pose_at"], G["hull_on"], G["cap_spikes"], G["cam"], G["meshes"]
FRAMES, HULL, r = G["FRAMES"], G["HULL"], G["r"]
G["set_hull_thickness"]()
t_setup = time.time() - t0


def image_of(mat):
    """the image Workbench's texture colour uses: the active image node, else the first one"""
    if not mat or not mat.node_tree:
        return None
    nodes = [n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image]
    act = mat.node_tree.nodes.active
    return act if act in nodes else (nodes[0] if nodes else None)


mats, mat_index, textures, tex_index = [], {}, [], {}
def material(m):
    key = m.name if m else None
    if key in mat_index:
        return mat_index[key]
    node = image_of(m)
    tex = None
    if node:
        im = node.image
        if im.name not in tex_index:
            w, h = im.size
            px = np.empty(w * h * 4, np.float32)
            im.pixels.foreach_get(px)
            srgb = im.colorspace_settings.name.lower().startswith("srgb")
            (out / f"tex_{len(textures)}.rgba").write_bytes(np.round(np.clip(px, 0, 1) * 255).astype(np.uint8).tobytes())
            tex_index[im.name] = len(textures)
            textures.append({"name": im.name, "w": w, "h": h, "srgb": srgb})
        tex = tex_index[im.name]
    dc = list(m.diffuse_color) if m else [0.8, 0.8, 0.8, 1]
    mats.append({"name": key, "tex": tex, "nearest": bool(node and node.interpolation == "Closest"),
                 "id": dc[:3], "color": dc[:3],
                 "blend": getattr(m, "surface_render_method", None) if m else None})
    mat_index[key] = len(mats) - 1
    return len(mats) - 1


def grab(o, dg, with_static):
    me = o.evaluated_get(dg).to_mesh()
    nv, nl = len(me.vertices), len(me.loops)
    co = np.empty(nv * 3, np.float32); me.vertices.foreach_get("co", co)
    M = np.array(o.matrix_world, np.float64)
    pos = (co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]).astype(np.float32)
    nrm = np.empty(nl * 3, np.float32); me.corner_normals.foreach_get("vector", nrm)
    if not bpy.context.scene.render.use_high_quality_normals:   # GPU_PackedNormal: 10-bit, truncated
        nrm = np.clip(np.trunc(np.clip(nrm, -1, 1) * 511), -512, 511).astype(np.float32) / 511
    nrm = nrm.reshape(-1, 3) @ np.linalg.inv(M[:3, :3]).astype(np.float32)   # (M^-T n) as rows
    # not renormalised: EEVEE interpolates M^-T n as is and normalises per pixel
    st = None
    if with_static:
        me.calc_loop_triangles()
        nt = len(me.loop_triangles)
        tl = np.empty(nt * 3, np.int32); me.loop_triangles.foreach_get("loops", tl)
        mi = np.empty(nt, np.int32); me.loop_triangles.foreach_get("material_index", mi)
        lv = np.empty(nl, np.int32); me.loops.foreach_get("vertex_index", lv)
        uvl = next((l for l in me.uv_layers if l.active_render), me.uv_layers.active)
        uv = np.zeros(nl * 2, np.float32)
        if uvl:
            uvl.data.foreach_get("uv", uv)
        st = {"tl": tl, "mi": mi, "lv": lv, "uv": uv}
    o.evaluated_get(dg).to_mesh_clear()
    return pos, nrm.astype(np.float32), st


PROF = [0.0, 0.0, 0.0]


def frame(f, first):
    """(body pos, body normals) with the hull off, (hull pos) with it on, as render_sprite.py renders them"""
    a = time.time()
    pose_at(f / FRAMES)
    b = time.time()
    dg = bpy.context.evaluated_depsgraph_get()
    body = [grab(o, dg, first) for o in meshes]
    c = time.time()
    hull_on(True)
    if HULL.get("cap_each_frame"):
        cap_spikes()
    dg = bpy.context.evaluated_depsgraph_get()
    hull = [grab(o, dg, first) for o in meshes]
    hull_on(False)
    PROF[0] += b - a; PROF[1] += c - b; PROF[2] += time.time() - c
    return body, hull


def concat(parts, slots_of):
    """meshes -> one: triangles (loop ids), loop -> vertex, UVs, global material per triangle, slot count"""
    tl, lv, uv, mi, vo, lo = [], [], [], [], 0, 0
    for (pos, nrm, st), slots in zip(parts, slots_of):
        tl.append(st["tl"] + lo); lv.append(st["lv"] + vo); uv.append(st["uv"]); mi.append(st["mi"])
        vo += len(pos); lo += len(nrm)
    return np.concatenate(tl), np.concatenate(lv), np.concatenate(uv), mi


body, hull = frame(0, True)
slot_mats = [[s.material for s in o.material_slots] or [None] for o in meshes]
n_slots = [len(G["HULL_MATS"][o.data.name]) for o in meshes]
btl, blv, buv, bmi = concat(body, slot_mats)
bmat = np.concatenate([np.array([material(m) for m in sm], np.int32)[np.minimum(mi, len(sm) - 1)] for mi, sm in zip(bmi, slot_mats)])
htl, hlv, _, hmi = concat(hull, slot_mats)
hshell = np.concatenate([(mi >= n).astype(np.int32) for mi, n in zip(hmi, n_slots)])
static = [btl, blv, buv, bmat, htl, hlv, hshell]
with open(out / "static.bin", "wb") as fh:
    for a in static:
        fh.write(np.ascontiguousarray(a).tobytes())

dg = bpy.context.evaluated_depsgraph_get()
W, H = r.resolution_x, r.resolution_y
meta = {"width": W, "height": H, "frames": FRAMES,
        "proj": np.array(cam.calc_matrix_camera(dg, x=W, y=H)).tolist(),
        "view": np.array(cam.matrix_world.inverted()).tolist(),
        "persp": cam.data.type == "PERSP",
        "body": {"verts": int(sum(len(p) for p, _, _ in body)), "loops": int(len(blv)), "tris": int(len(btl) // 3)},
        "hull": {"verts": int(sum(len(p) for p, _, _ in hull)), "loops": int(len(hlv)), "tris": int(len(htl) // 3)},
        "static": [[a.dtype.str, int(a.size)] for a in static],
        "materials": mats, "textures": textures}

t1 = time.time()
mine = BAKE.get("frames", list(range(FRAMES)))
for f in mine:                                   # this worker's share of the loop: frame_NNNN.bin each
    if f != 0:
        body, hull = frame(f, False)
    with open(out / f"frame_{f:04d}.bin", "wb") as fh:
        for a in [p for p, _, _ in body] + [n for _, n, _ in body] + [p for p, _, _ in hull]:
            fh.write(a.tobytes())
    body = None
meta["time"] = {"pose": PROF[0], "body": PROF[1], "hull": PROF[2], "setup": t_setup, "static": t1 - t0 - t_setup, "frames": time.time() - t1}
if BAKE.get("worker", 0) == 0:
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
print("@@BAKE", json.dumps(meta["time"]), meta["body"], meta["hull"], flush=True)
