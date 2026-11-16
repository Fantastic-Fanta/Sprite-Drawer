"""Inside Blender (blender.py's worker, JOB = {config, out, frames}): pose each frame and write the geometry the
GPU renderer (sprite/) draws: frame_NNNN.bin (body positions and corner normals, hull positions); the worker
with frame 0 also writes meta.json (camera, materials, sizes), static.bin (topology, UVs, materials), tex_*.rgba."""
import bpy, json, math, sys
import numpy as np
from pathlib import Path
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).parent))
import motion

cfg, out_dir = JOB["config"], JOB["out"]
P = dict(cfg["pose_params"])
FRAMES, CAM, HULL = cfg["motion"]["frames"], cfg["camera"], cfg["render"].get("hull", {})
CLIP, PM = cfg["motion"].get("clip"), cfg["parts"]
num = lambda v: eval(v, {"__builtins__": {}}, P) if isinstance(v, str) else v
upd = lambda: bpy.context.view_layer.update()

scene = bpy.context.scene
arm = next(o for o in scene.objects if o.type == "ARMATURE")
for o in scene.objects:
    if o.name.startswith("Icosphere"):          # the glTF importer's bone-display helper
        o.hide_render = True
r = scene.render
r.resolution_percentage, r.resolution_x, r.resolution_y = 100, cfg["render"]["width"], cfg["render"]["height"]

# material groups (parts.materials {name fragment: "part|part"}), in sprite/'s order; a material without a
# texture is drawn in its group's colour here (it was the id pass's diffuse colour)
GROUPS = [PM["default_material"]] + sorted(set(PM.get("materials", {}).values()))
GROUP_RGB = [(1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0), (1, 0, 1), (0, 1, 1), (1, 1, 1),
             (0.5, 0, 0), (0, 0.5, 0), (0, 0, 0.5), (0.5, 0.5, 0), (0.5, 0, 0.5), (0, 0.5, 0.5)]
assert len(GROUPS) <= len(GROUP_RGB), f"{len(GROUPS)} material groups: at most {len(GROUP_RGB)}"


def group_of(mat):
    images = [n.image.name for n in (mat.node_tree.nodes if mat and mat.node_tree else []) if n.type == "TEX_IMAGE" and n.image]
    group = PM["default_material"]
    for key, name in PM.get("materials", {}).items():
        if any(key in i for i in images) or (mat and key in mat.name):
            group = name
    return GROUPS.index(group)


meshes = [o for o in scene.objects if o.type == "MESH" and not o.hide_render]


# hull: each mesh's solidify shell (flipped normals; its faces take the extra material slot). render.hull:
# thickness_px (sprite px) or thickness (world), even, spike, cap_each_frame
HULL_MODS, N_SLOTS, HULL_T = [], {}, None
for o in meshes:
    me = o.data
    if len(me.materials) == 0:
        me.materials.append(None)
    n_slots = N_SLOTS[o.name] = len(me.materials)
    me.materials.append(None)
    s = o.modifiers.new("SpriteHull", "SOLIDIFY")
    s.use_flip_normals, s.use_rim, s.offset = True, False, 1.0
    s.use_even_offset, s.use_quality_normals, s.material_offset = HULL.get("even", True), True, n_slots
    s.show_render = s.show_viewport = False
    HULL_MODS.append(s)


def hull_on(on):
    for m in HULL_MODS:
        m.show_render = m.show_viewport = on
    upd()


def set_hull_thickness():
    """thickness_px sprite px in world units, from frame 0's projected height = style.height px"""
    global HULL_T
    if "thickness" in HULL:
        HULL_T = HULL["thickness"]
    else:
        pose_at(0.0)
        dg = bpy.context.evaluated_depsgraph_get()
        W, H = r.resolution_x, r.resolution_y
        Pm = np.array(cam.calc_matrix_camera(dg, x=W, y=H)) @ np.array(cam.matrix_world.inverted())
        ys = []
        for o in meshes:
            me = o.evaluated_get(dg).to_mesh()
            co = np.empty(len(me.vertices) * 3)
            me.vertices.foreach_get("co", co)
            o.evaluated_get(dg).to_mesh_clear()
            v = np.c_[co.reshape(-1, 3), np.ones(len(co) // 3)] @ (Pm @ np.array(o.matrix_world)).T
            ys.append(v[:, 1] / v[:, 3])
        ys = np.concatenate(ys)
        height_px = (ys.max() - ys.min()) / 2 * H
        if cam_data.type == "ORTHO":
            world_px = cam_data.ortho_scale / max(W, H)
        else:
            world_px = 2 * (cam.location - Vector(CAM["target"])).length * math.tan(cam_data.angle / 2) / max(W, H)
        HULL_T = HULL.get("thickness_px", 1.15) * height_px / cfg["style"]["height"] * world_px
    for o in meshes:
        for m in o.modifiers:
            if m.name == "SpriteHull":
                m.thickness = HULL_T / max(o.matrix_world.to_scale())
    pose_at(0.0)
    hull_on(True)
    cap_spikes()
    hull_on(False)


def cap_spikes():
    """scale back any hull vertex offset beyond render.hull.spike (default 2) thicknesses (needle tips),
    via a solidify vertex-group weight measured with the cap off, from the current pose alone"""
    limit = HULL.get("spike", 2.0)
    mods = [(o, o.modifiers.get("SpriteHull")) for o in meshes if len(o.data.vertices)]
    mods = [(o, s) for o, s in mods if s is not None]
    for o, s in mods:
        s.vertex_group = ""
    upd()
    dg = bpy.context.evaluated_depsgraph_get()
    for o, s in mods:
        n = len(o.data.vertices)
        me = o.evaluated_get(dg).to_mesh()
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        o.evaluated_get(dg).to_mesh_clear()
        if len(co) != 6 * n:
            continue
        co = co.reshape(2, n, 3)
        w = np.clip(limit * s.thickness / np.maximum(np.linalg.norm(co[1] - co[0], axis=1), 1e-12), 0, 1)
        far = np.nonzero(w < 1)[0]
        if not len(far):
            continue
        vg = o.vertex_groups.get("SpriteHullCap") or o.vertex_groups.new(name="SpriteHullCap")
        vg.add(np.nonzero(w >= 1)[0].tolist(), 1.0, "REPLACE")
        for i in far:
            vg.add([int(i)], float(w[i]), "REPLACE")
        s.vertex_group, s.thickness_vertex_group = vg.name, 0.0
    upd()


cam_data = bpy.data.cameras.new("SpriteCam")
cam = bpy.data.objects.new("SpriteCam", cam_data)
scene.collection.objects.link(cam)
cam_data.clip_end, scene.camera = 100000, cam
az, el = math.radians(num(CAM["azimuth"])), math.radians(num(CAM["elevation"]))
fov = num(CAM.get("perspective_fov", 0)) or 0
direction = Vector((math.cos(az) * math.cos(el), -math.sin(az) * math.cos(el), math.sin(el)))
if fov > 0.5:                                    # perspective, covering the orthographic view's area
    cam_data.type, cam_data.angle = "PERSP", math.radians(fov)
    dist = CAM["ortho_scale"] / 2 / math.tan(cam_data.angle / 2)
else:
    cam_data.type, cam_data.ortho_scale, dist = "ORTHO", CAM["ortho_scale"], CAM["distance"]
cam.location = Vector(CAM["target"]) + direction * dist
cam.rotation_euler = (-direction).to_track_quat("-Z", CAM.get("up", "Y")).to_euler()

AXES = {"X": Vector((1, 0, 0)), "Y": Vector((0, 1, 0)), "Z": Vector((0, 0, 1))}
to_arm = arm.matrix_world.inverted().to_3x3()


def rotate(pb, world_axis, degrees):
    m = pb.matrix.copy()
    head = m.translation.copy()
    rot = Matrix.Rotation(math.radians(degrees), 4, (to_arm @ world_axis).normalized())
    pb.matrix = Matrix.Translation(head) @ rot @ Matrix.Translation(-head) @ m


def move(pb, world_offset):
    pb.matrix = Matrix.Translation(to_arm @ world_offset) @ pb.matrix


cam_axis = lambda i: (cam.matrix_world.to_3x3() @ Vector([float(i == k) for k in range(3)])).normalized()


def apply_clip(t):
    """motion.clip: the model's own action, t in [0, 1) over its frame range once"""
    action = bpy.data.actions[CLIP]
    ad = arm.animation_data or arm.animation_data_create()
    if ad.action != action:
        ad.action = action
        if action.slots:
            ad.action_slot = action.slots[0]
    start, end = action.frame_range
    frame = start + (t % 1.0) * (end - start)
    scene.frame_set(int(frame), subframe=frame - int(frame))
    upd()
    if cfg.get("pose"):                          # pose offsets on top: freeze this frame, unbind the action
        basis = {pb.name: pb.matrix_basis.copy() for pb in arm.pose.bones}
        ad.action = None
        for pb in arm.pose.bones:
            pb.matrix_basis = basis[pb.name]
        upd()


def batched(pose):
    """pose entries as (bone, axis, compiled expr, update after it): an entry reads its bone's and ancestors' pose
    matrices and writes its bone (SCALEW: its chain), so it goes in a batch after every earlier entry that wrote
    what it reads or writes, and not before one that read what it writes: same values, one update per batch"""
    up = lambda b: {b.name} | (up(b.parent) if b.parent else set())
    rw, level = [], []
    for bone, axis, _ in pose:
        b = arm.data.bones[bone]
        rw.append((up(b), {bone} | ({c.name for c in b.children_recursive} if axis == "SCALEW" else set())))
    for i, (r, w) in enumerate(rw):
        level.append(max([level[j] + 1 for j in range(i) if rw[j][1] & (r | w)] +
                         [level[j] for j in range(i) if rw[j][0] & w] + [0]))
    order = sorted(range(len(pose)), key=lambda i: (level[i], i))
    return [(*pose[i][:2], compile(pose[i][2], "pose", "eval"), k + 1 == len(order) or level[order[k + 1]] != level[i])
            for k, i in enumerate(order)]


POSE = batched(cfg.get("pose") or [])
DEFORM = [m for o in scene.objects for m in o.modifiers if m.type == "ARMATURE" and m.show_viewport]


def pose_at(t):
    """config "pose" at loop position t; the meshes deform once, after it (armature modifiers off till then)"""
    for m in DEFORM:
        m.show_viewport = False
    pose_bones(t)
    for m in DEFORM:
        m.show_viewport = True
    upd()


def pose_bones(t):
    """config "pose" [bone, axis, expr] at loop position t (s/c: one sine cycle, ts: slow time; motion.py)"""
    if CLIP:
        apply_clip(t)
    else:
        for pb in arm.pose.bones:
            pb.rotation_mode = "QUATERNION"
            pb.matrix_basis = Matrix.Identity(4)
        upd()
    if not POSE:
        return
    env = motion.env(cfg, P)
    env.update(s=math.sin(2 * math.pi * t), c=math.cos(2 * math.pi * t), t=t,
               ts=motion.slow_t(t * FRAMES, FRAMES, cfg["style"].get("fast_frames", [])))
    for bone, axis, expr, flush in POSE:
        value, pb = eval(expr, env), arm.pose.bones[bone]
        if axis == "SCALE":
            pb.scale = (value, value, value)
        elif axis == "SCALEW":                   # widen a chain without lengthening it (own axes, no inherited scale)
            axis_of = {}
            for q in [pb] + list(pb.children_recursive):
                b = arm.data.bones[q.name]
                kids = [c for c in b.children if not c.name.endswith("_end")]
                if kids:
                    d = b.matrix_local.to_3x3().inverted() @ (kids[0].head_local - b.head_local)
                    axis_of[q.name] = max(range(3), key=lambda i: abs(d[i]))
                else:
                    axis_of[q.name] = axis_of.get(b.parent.name, 1) if b.parent else 1
                b.inherit_scale = "NONE"
                q.scale = tuple(1.0 if i == axis_of[q.name] else value for i in range(3))
        elif axis.startswith("A:"):              # about any world axis through the bone head
            rotate(pb, Vector([float(c) for c in axis[2:].split(",")]).normalized(), value)
        elif axis in ("LOCCAM", "LOCCAMX"):      # along the camera's up / right
            move(pb, cam_axis(1 if axis == "LOCCAM" else 0) * value)
        elif axis == "ROLLCAM":                  # about the view axis (+ = counter-clockwise)
            rotate(pb, cam_axis(2), value)
        elif axis.startswith("LOC"):
            move(pb, AXES[axis[3]] * value)
        else:
            rotate(pb, AXES[axis], value)
        if flush:
            upd()
    if PLANT:
        hold_planted()


PLANT = {}


def plant():
    """motion.plant: bones held at their mean head position over the loop; the two bones above bend"""
    bones = cfg["motion"].get("plant", [])
    if not bones:
        return
    acc = {b: Vector() for b in bones}
    for i in range(8):
        pose_at(i / 8)
        for b in bones:
            acc[b] += arm.pose.bones[b].head
    PLANT.update({b: v / 8 for b, v in acc.items()})


def hold_planted():
    """cyclic coordinate descent on each planted bone's parent and grandparent; the foot keeps its angle"""
    legs = []
    for name, target in PLANT.items():
        foot = arm.pose.bones[name]
        chain = [foot.parent.parent, foot.parent]
        pts = [chain[0].head.copy(), chain[1].head.copy(), foot.head.copy()]
        D = [Matrix.Identity(4), Matrix.Identity(4)]
        for _ in range(12):
            if (pts[2] - target).length < 1e-6:
                break
            for j in (1, 0):
                q = (pts[2] - pts[j]).rotation_difference(target - pts[j])
                M = Matrix.Translation(pts[j]) @ q.to_matrix().to_4x4() @ Matrix.Translation(-pts[j])
                for k in range(j + 1, 3):
                    pts[k] = M @ pts[k]
                for k in range(j, 2):
                    D[k] = M @ D[k]
        legs.append((chain, D, foot, foot.matrix.copy(), pts[2] - foot.head, [b.matrix.copy() for b in chain]))
    for level in (0, 1):
        for chain, D, _, _, _, M0 in legs:
            chain[level].matrix = D[level] @ M0[level]
        upd()
    for _, _, foot, Mf, shift, _ in legs:
        foot.matrix = Matrix.Translation(shift) @ Mf
    upd()




# --- the geometry dump
out = Path(out_dir)


def image_of(mat):
    """the image node Workbench's texture colour uses: the active one, else the first"""
    nodes = [n for n in (mat.node_tree.nodes if mat and mat.node_tree else []) if n.type == "TEX_IMAGE" and n.image]
    return (mat.node_tree.nodes.active if mat.node_tree.nodes.active in nodes else nodes[0]) if nodes else None


MATS, TEXTURES = {}, {}


def material(m):
    """index of m in meta materials (texture, sampler, colour, group)"""
    if m not in MATS:
        node, tex = image_of(m), None
        if node:
            im = node.image
            if im.name not in TEXTURES:
                w, h = im.size
                px = np.empty(w * h * 4, np.float32)
                im.pixels.foreach_get(px)
                (out / f"tex_{len(TEXTURES)}.rgba").write_bytes(np.round(np.clip(px, 0, 1) * 255).astype(np.uint8).tobytes())
                TEXTURES[im.name] = {"w": w, "h": h, "srgb": im.colorspace_settings.name.lower().startswith("srgb"),
                                     "cutoff": im.alpha_mode not in ("NONE", "CHANNEL_PACKED"), "premul": im.alpha_mode == "PREMUL"}
            tex = list(TEXTURES).index(im.name)
        t = TEXTURES[node.image.name] if node else {"cutoff": False, "premul": False}
        MATS[m] = {"tex": tex, "nearest": bool(node and node.interpolation == "Closest"), "extension": node.extension if node else "REPEAT",
                   "cutoff": t["cutoff"], "premul": t["premul"], "group": group_of(m),
                   "color": GROUP_RGB[group_of(m)] if m else (0.8, 0.8, 0.8)}
    return list(MATS).index(m)


def grab(o, dg, static):
    """world positions, corner normals (as EEVEE gets them) and, with static, topology / UVs / slots"""
    me = o.evaluated_get(dg).to_mesh()
    co = np.empty(len(me.vertices) * 3, np.float32); me.vertices.foreach_get("co", co)
    M = np.array(o.matrix_world, np.float64)
    pos = (co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]).astype(np.float32)
    nrm = np.empty(len(me.loops) * 3, np.float32); me.corner_normals.foreach_get("vector", nrm)
    if not r.use_high_quality_normals:           # GPU_PackedNormal: 10-bit, truncated
        nrm = np.clip(np.trunc(np.clip(nrm, -1, 1) * 511), -512, 511).astype(np.float32) / 511
    nrm = (nrm.reshape(-1, 3) @ np.linalg.inv(M[:3, :3]).astype(np.float32)).astype(np.float32)  # M^-T n, not renormalised
    st = None
    if static:
        me.calc_loop_triangles()
        get = lambda seq, attr, n: (lambda a: (seq.foreach_get(attr, a), a)[1])(np.empty(n, np.int32))
        nt = len(me.loop_triangles)
        uvl = next((l for l in me.uv_layers if l.active_render), me.uv_layers.active)
        uv = np.zeros(len(me.loops) * 2, np.float32)
        if uvl:
            uvl.data.foreach_get("uv", uv)
        st = (get(me.loop_triangles, "loops", nt * 3), get(me.loops, "vertex_index", len(me.loops)), uv,
              get(me.loop_triangles, "material_index", nt))
    o.evaluated_get(dg).to_mesh_clear()
    return pos, nrm, st


def frame(f, static=False):
    """body (hull off) and body + shell (hull on) of frame f"""
    pose_at(f / FRAMES)
    body = [grab(o, bpy.context.evaluated_depsgraph_get(), static) for o in meshes]
    hull_on(True)
    if HULL.get("cap_each_frame"):
        cap_spikes()
    hull = [grab(o, bpy.context.evaluated_depsgraph_get(), static) for o in meshes]
    hull_on(False)
    return body, hull


def write_static(body, hull):
    def concat(parts):
        tl, lv, uv, mi, vo, lo = [], [], [], [], 0, 0
        for pos, nrm, (t, l, u, m) in parts:
            tl.append(t + lo); lv.append(l + vo); uv.append(u); mi.append(m); vo += len(pos); lo += len(nrm)
        return np.concatenate(tl), np.concatenate(lv), np.concatenate(uv), mi
    slots = [[s.material for s in o.material_slots] or [None] for o in meshes]
    btl, blv, buv, bmi = concat(body)
    bmat = np.concatenate([np.array([material(m) for m in sm], np.int32)[np.minimum(mi, len(sm) - 1)] for mi, sm in zip(bmi, slots)])
    htl, hlv, _, hmi = concat(hull)
    shell = np.concatenate([(mi >= N_SLOTS[o.name]).astype(np.int32) for mi, o in zip(hmi, meshes)])
    with open(out / "static.bin", "wb") as fh:
        for a in (btl, blv, buv, bmat, htl, hlv, shell):
            fh.write(np.ascontiguousarray(a).tobytes())
    dg = bpy.context.evaluated_depsgraph_get()
    W, H = r.resolution_x, r.resolution_y
    count = lambda parts, tl, lv: {"verts": sum(len(p) for p, _, _ in parts), "loops": len(lv), "tris": len(tl) // 3}
    (out / "meta.json").write_text(json.dumps({
        "width": W, "height": H, "persp": cam_data.type == "PERSP", "materials": list(MATS.values()),
        "proj": np.array(cam.calc_matrix_camera(dg, x=W, y=H)).tolist(), "view": np.array(cam.matrix_world.inverted()).tolist(),
        "body": count(body, btl, blv), "hull": count(hull, htl, hlv), "textures": list(TEXTURES.values())}))


out.mkdir(parents=True, exist_ok=True)
plant()
for f in JOB["frames"]:
    if HULL_T is None:
        set_hull_thickness()
    body, hull = frame(f, f == 0)
    if f == 0:
        write_static(body, hull)
    with open(out / f"frame_{f:04d}.bin", "wb") as fh:
        for a in [p for p, _, _ in body] + [n for _, n, _ in body] + [p for p, _, _ in hull]:
            fh.write(a.tobytes())
