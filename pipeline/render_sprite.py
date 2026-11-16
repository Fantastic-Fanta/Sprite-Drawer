"""Inside Blender (blender.py's worker, JOB = {config, out, frames}): render each frame's passes as TGA:
color_ (flat texture), id_ (material group), data_ (camera-space normal), hull_ (inverted-hull lines)."""
import bpy, sys, math
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
r.film_transparent, r.resolution_percentage, r.use_file_extension = True, 100, False
r.resolution_x, r.resolution_y = cfg["render"]["width"], cfg["render"]["height"]
r.image_settings.file_format, r.image_settings.color_mode, r.image_settings.color_depth = "TARGA_RAW", "RGBA", "8"
shading = scene.display.shading
shading.light, shading.show_object_outline, shading.show_specular_highlight = "FLAT", False, False

# id pass: one flat colour per material group (parts.materials {name fragment: "part|part"})
ID_ORDER = [PM["default_material"]] + sorted(set(PM.get("materials", {}).values()))
ID_RGB = [(1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0), (1, 0, 1), (0, 1, 1), (1, 1, 1),
          (0.5, 0, 0), (0, 0.5, 0), (0, 0, 0.5), (0.5, 0.5, 0), (0.5, 0, 0.5), (0, 0.5, 0.5)]
assert len(ID_ORDER) <= len(ID_RGB), f"{len(ID_ORDER)} material groups: at most {len(ID_RGB)}"
for mat in bpy.data.materials:
    images = [n.image.name for n in (mat.node_tree.nodes if mat.node_tree else []) if n.type == "TEX_IMAGE" and n.image]
    group = PM["default_material"]
    for key, name in PM.get("materials", {}).items():
        if any(key in i for i in images) or key in mat.name:
            group = name
    mat.diffuse_color = (*ID_RGB[ID_ORDER.index(group)], 1)

# data pass: EEVEE, one emission material: camera-space normal * 0.5 + 0.5 in R/G
data_mat = bpy.data.materials.new("SpriteData")
data_mat.use_nodes = True
nt = data_mat.node_tree
nt.nodes.clear()
N, L = nt.nodes.new, nt.links.new
geo, vt = N("ShaderNodeNewGeometry"), N("ShaderNodeVectorTransform")
vt.vector_type, vt.convert_from, vt.convert_to = "NORMAL", "WORLD", "CAMERA"
half = N("ShaderNodeVectorMath"); half.operation = "MULTIPLY_ADD"
half.inputs[1].default_value = half.inputs[2].default_value = (0.5, 0.5, 0.5)
sep, comb, emit, outn = N("ShaderNodeSeparateXYZ"), N("ShaderNodeCombineColor"), N("ShaderNodeEmission"), N("ShaderNodeOutputMaterial")
L(geo.outputs["Normal"], vt.inputs["Vector"]); L(vt.outputs["Vector"], half.inputs[0]); L(half.outputs["Vector"], sep.inputs["Vector"])
L(sep.outputs["X"], comb.inputs[0]); L(sep.outputs["Y"], comb.inputs[1])
L(comb.outputs["Color"], emit.inputs["Color"]); L(emit.outputs["Emission"], outn.inputs["Surface"])
meshes = [o for o in scene.objects if o.type == "MESH" and not o.hide_render]


# hull pass: each mesh's solidify shell (flipped normals, back faces culled) in white, the body a holdout:
# what shows is the line. render.hull: thickness_px (sprite px) or thickness (world), even, spike, cap_each_frame
def flat_mat(name, node):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.node_tree.nodes.clear()
    n = m.node_tree.nodes.new(node)
    if node == "ShaderNodeEmission":
        n.inputs["Color"].default_value = (1, 1, 1, 1)
    m.node_tree.links.new(n.outputs[0], m.node_tree.nodes.new("ShaderNodeOutputMaterial").inputs["Surface"])
    return m


hull_mat, hull_hold = flat_mat("SpriteHull", "ShaderNodeEmission"), flat_mat("SpriteHullHold", "ShaderNodeHoldout")
hull_mat.use_backface_culling = True
HULL_MODS, HULL_MATS, HULL_T = [], {}, None
for o in meshes:
    me = o.data
    if len(me.materials) == 0:
        me.materials.append(None)
    HULL_MATS[me.name] = list(me.materials)
    n_slots = len(me.materials)
    me.materials.append(hull_mat)
    s = o.modifiers.new("SpriteHull", "SOLIDIFY")
    s.use_flip_normals, s.use_rim, s.offset = True, False, 1.0
    s.use_even_offset, s.use_quality_normals, s.material_offset = HULL.get("even", True), True, n_slots
    s.show_render = s.show_viewport = False
    HULL_MODS.append(s)


def hull_on(on):
    for m in HULL_MODS:
        m.show_render = m.show_viewport = on
    for o in meshes:
        for i, m in enumerate(HULL_MATS[o.data.name]):
            o.data.materials[i] = hull_hold if on else m
    upd()


def set_hull_thickness():
    """thickness_px sprite px in world units, from frame 0's projected height = style.height px"""
    global HULL_T
    if "thickness" in HULL:
        HULL_T = HULL["thickness"]
    else:
        import numpy as np
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
    import numpy as np
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


def use_pass(kind):
    vl = bpy.context.view_layer
    r.use_freestyle = False
    if kind in ("color", "id"):
        r.engine, vl.material_override, scene.view_settings.view_transform = "BLENDER_WORKBENCH", None, "Standard"
        r.filter_size = 1.5 if kind == "color" else 0.01
        shading.color_type = "TEXTURE" if kind == "color" else "MATERIAL"
        scene.display.render_aa = "8" if kind == "color" else "OFF"
        return
    r.engine = "BLENDER_EEVEE"
    for a in ("use_shadows", "use_raytracing", "use_volumetric_shadows", "use_gtao"):
        if hasattr(scene.eevee, a):
            setattr(scene.eevee, a, False)
    scene.eevee.taa_render_samples, r.filter_size = 1, 0.01
    vl.material_override = None if kind == "hull" else data_mat
    scene.view_settings.view_transform = "Standard" if kind == "hull" else "Raw"


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


plant()
for f in JOB["frames"]:
    if HULL_T is None:
        set_hull_thickness()
    pose_at(f / FRAMES)
    for kind in ("color",) + (("id",) if len(ID_ORDER) > 1 else ()) + ("data", "hull"):
        use_pass(kind)
        if kind == "hull":
            hull_on(True)
            if HULL.get("cap_each_frame"):
                cap_spikes()
        r.filepath = f"{out_dir}/{kind}_{f + 1:04d}.tga"
        bpy.ops.render.render(write_still=True)
        if kind == "hull":
            hull_on(False)
