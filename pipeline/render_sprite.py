"""Render a posed model as frame sequences for the sprite pipeline.

Run:
  Blender -b MODEL.blend --python render_sprite.py -- CONFIG.json OUT_DIR [--test 0,0.5] [--frames 0:60 | 0,5,9]
(render_parallel.py runs several of these at once, one slice of the loop each)
Writes these images per frame (see SPRITE_PIPELINE.md), read by sprite_style.py:
  color_NNNN  flat texture colours (Workbench), transparent background
  id_NNNN     which material group each pixel shows (only with parts.materials)
  data_NNNN   camera-space normal in R/G (EEVEE), for the shade bands
  hull_NNNN   where the inverted hull shows, i.e. the lines
Everything model-specific (bones, camera, material groups) comes from CONFIG.json.
Other scripts (fit_pose.py) exec this file with --setup-only to reuse the scene setup.
"""
import bpy, sys, math, json, os
from pathlib import Path
from mathutils import Matrix, Vector

# motion.py (shared expression helpers / motion functions) sits next to this script; when another
# script exec()s this file there is no __file__, so use the --python script's folder
sys.path.insert(0, str(Path(globals()["__file__"]).parent if "__file__" in globals()
                       else Path(sys.argv[sys.argv.index("--python") + 1]).resolve().parent))
import motion

args = sys.argv[sys.argv.index("--") + 1:]
cfg = json.loads(Path(args[0]).read_text())
out_dir = args[1]
test_ts = [float(t) for t in args[args.index("--test") + 1].split(",")] if "--test" in args else None
setup_only = "--setup-only" in args

P = dict(cfg["pose_params"])          # fit_pose.py updates this dict in place
FRAMES = cfg["motion"]["frames"]
CAM = cfg["camera"]


def num(v):
    """config value: a number, or the name of / expression over a pose parameter"""
    return eval(v, {"__builtins__": {}}, P) if isinstance(v, str) else v


scene = bpy.context.scene
arm = next(o for o in scene.objects if o.type == "ARMATURE")
for o in scene.objects:
    if o.name.startswith("Icosphere"):   # bone-display helper the glTF importer adds
        o.hide_render = True

# --- Texture swap (render.texture_swap {"name fragment": "new file"}): e.g. the shiny textures,
# same UV layout as the normal ones (make_shiny.py writes this)
for img in bpy.data.images:
    for frag, new in cfg["render"].get("texture_swap", {}).items():
        if frag in img.filepath or frag in img.name:
            img.filepath = "//" + new
            img.reload()
            break

# --- Shared render settings ---------------------------------------------------
scene.render.film_transparent = True
scene.render.resolution_x = cfg["render"]["width"]
scene.render.resolution_y = cfg["render"]["height"]
scene.render.resolution_percentage = 100
# pass files: uncompressed Targa (default: ~5% faster to render and ~2x faster to load than PNG,
# same pixels, ~7x the disk space), or SPRITE_RENDER_FORMAT=PNG
RAW = os.environ.get("SPRITE_RENDER_FORMAT", "TGA").upper() == "TGA"
EXT = ".tga" if RAW else ".png"
scene.render.image_settings.file_format = "TARGA_RAW" if RAW else "PNG"
scene.render.use_file_extension = False
scene.render.image_settings.color_mode = "RGBA"
scene.render.image_settings.color_depth = "8"

shading = scene.display.shading
shading.light = "FLAT"
shading.show_object_outline = False
shading.show_specular_highlight = False

# --- ID pass: which material group each pixel shows (parts.materials {"texture or material name
# fragment": "part" or "part|part"}), one flat colour per group, for sprite_style.py to keep each
# group to its parts (a shell that has no texture colour of its own, a wing side the game colours
# in its shader). Only rendered when the config maps any material.
ID_ORDER = [cfg["parts"]["default_material"]] + sorted(set(cfg["parts"].get("materials", {}).values()))
ID_RGB = [(1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0), (1, 0, 1), (0, 1, 1), (1, 1, 1),
          (0.5, 0, 0), (0, 0.5, 0), (0, 0, 0.5), (0.5, 0.5, 0), (0.5, 0, 0.5), (0, 0.5, 0.5)]
assert len(ID_ORDER) <= len(ID_RGB), f"{len(ID_ORDER)} material groups: at most {len(ID_RGB)}"
USE_ID = len(ID_ORDER) > 1
for mat in bpy.data.materials:
    images = [n.image.name for n in (mat.node_tree.nodes if mat.node_tree else [])
              if n.type == "TEX_IMAGE" and n.image]
    group = cfg["parts"]["default_material"]
    for key, name in cfg["parts"].get("materials", {}).items():
        if any(key in i for i in images) or key in mat.name:
            group = name
    mat.diffuse_color = (*ID_RGB[ID_ORDER.index(group)], 1)

# --- Data pass: EEVEE with one emission material on everything: the camera-space normal ------
data_mat = bpy.data.materials.new("SpriteData")
data_mat.use_nodes = True
nt = data_mat.node_tree
nt.nodes.clear()
N = nt.nodes.new
geo, vt = N("ShaderNodeNewGeometry"), N("ShaderNodeVectorTransform")
vt.vector_type, vt.convert_from, vt.convert_to = "NORMAL", "WORLD", "CAMERA"
half = N("ShaderNodeVectorMath"); half.operation = "MULTIPLY_ADD"
half.inputs[1].default_value = (0.5, 0.5, 0.5); half.inputs[2].default_value = (0.5, 0.5, 0.5)
sep = N("ShaderNodeSeparateXYZ")
comb, emit, out = N("ShaderNodeCombineColor"), N("ShaderNodeEmission"), N("ShaderNodeOutputMaterial")
L = nt.links.new
L(geo.outputs["Normal"], vt.inputs["Vector"]); L(vt.outputs["Vector"], half.inputs[0])
L(half.outputs["Vector"], sep.inputs["Vector"])
L(sep.outputs["X"], comb.inputs[0]); L(sep.outputs["Y"], comb.inputs[1])
L(comb.outputs["Color"], emit.inputs["Color"]); L(emit.outputs["Emission"], out.inputs["Surface"])

meshes = [o for o in scene.objects if o.type == "MESH" and not o.hide_render]


# --- Hull pass: an inverted hull - a copy of every mesh pushed out along its normals, normals
# flipped, back faces culled - in white, with the body as a holdout. What shows is the line:
# around the silhouette, and inside wherever a nearer part sits more than the hull's thickness in
# front of what's behind it. The modifiers stay off except during this pass.
# render.hull (optional): {"thickness_px": 1.15, "thickness": world units, "even": true, "weld": false,
#   "spike": 2.0}
#   thickness_px  line width in sprite px; turned into world units from frame 0's size on screen
#                 and style.height (set_hull_thickness), so every model gets the same line width
#   thickness     world units instead (overrides thickness_px)
#   even          solidify's even thickness (keeps the shell the same width round sharp corners)
#   spike         largest offset of a hull vertex, in thicknesses: even offset at a needle tip is
#                 capped to it (cap_spikes)
#   cap_each_frame  cap spikes for every frame's pose, not only frame 0's (cap_spikes_now)
#   weld          join split (hard-edge) vertices first: closes cracks at hard edges, but smooths
#                 the shell's normals across them, which draws extra lines along creases
HULL = cfg["render"].get("hull", {})
HULL_MODS, HULL_MATS = [], {}


def _flat_mat(name, node):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    t = m.node_tree
    t.nodes.clear()
    n = t.nodes.new(node)
    if node == "ShaderNodeEmission":
        n.inputs["Color"].default_value = (1, 1, 1, 1)
    t.links.new(n.outputs[0], t.nodes.new("ShaderNodeOutputMaterial").inputs["Surface"])
    return m


hull_mat, hull_hold = _flat_mat("SpriteHull", "ShaderNodeEmission"), _flat_mat("SpriteHullHold", "ShaderNodeHoldout")
hull_mat.use_backface_culling = True
for o in meshes:
    me = o.data
    if len(me.materials) == 0:
        me.materials.append(None)
    HULL_MATS[me.name] = list(me.materials)
    n_slots = len(me.materials)
    me.materials.append(hull_mat)             # extra slot: only the hull's faces use it
    if HULL.get("weld"):
        wd = o.modifiers.new("SpriteHullWeld", "WELD")
        wd.merge_threshold = 1e-4 / max(o.matrix_world.to_scale())
        HULL_MODS.append(wd)
    s = o.modifiers.new("SpriteHull", "SOLIDIFY")
    s.use_flip_normals, s.use_rim, s.offset = True, False, 1.0
    s.use_even_offset = HULL.get("even", True)
    s.use_quality_normals = True
    s.material_offset = n_slots
    HULL_MODS.append(s)
for m in HULL_MODS:
    m.show_render = m.show_viewport = False
HULL_T = None                                 # world units, set before the first frame


def hull_on(on):
    """switch the hull shell on (body a holdout) or off (the model as it was)"""
    for m in HULL_MODS:
        m.show_render = m.show_viewport = on
    for o in meshes:
        for i, m in enumerate(HULL_MATS[o.data.name]):
            o.data.materials[i] = hull_hold if on else m
    bpy.context.view_layer.update()


def set_hull_thickness():
    """render.hull.thickness, or thickness_px sprite px in world units: frame 0's height on screen
    (its posed vertices projected) is style.height sprite px, and the camera gives the world size
    of a render px at the target. Same in every render process, so the slices of a loop match."""
    global HULL_T
    if "thickness" in HULL:
        HULL_T = HULL["thickness"]
    else:
        import numpy as np
        pose_at(0.0)
        dg = bpy.context.evaluated_depsgraph_get()
        W, H = scene.render.resolution_x, scene.render.resolution_y
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
        height_px = (ys.max() - ys.min()) / 2 * H              # NDC -1..1 -> render px
        if cam_data.type == "ORTHO":
            world_px = cam_data.ortho_scale / max(W, H)
        else:
            world_px = 2 * (cam.location - Vector(CAM["target"])).length * math.tan(cam_data.angle / 2) / max(W, H)
        HULL_T = HULL.get("thickness_px", 1.15) * height_px / cfg["style"]["height"] * world_px
    for o in meshes:
        for m in o.modifiers:
            if m.name == "SpriteHull":
                m.thickness = HULL_T / max(o.matrix_world.to_scale())
    print(f"hull thickness {HULL_T:.5g} world units")
    cap_spikes()


def cap_spikes():
    """Even offset pushes a vertex out by thickness / cos(its corner angle): at a needle-sharp tip
    (Golisopod's claws) that is a spike many times the line width, drawn as a long strand. Measure
    each vertex's offset at frame 0 and scale any beyond render.hull.spike x the thickness back to
    it (a solidify vertex-group weight); every other vertex keeps its even offset."""
    import numpy as np
    limit = HULL.get("spike", 2.0)
    pose_at(0.0)
    hull_on(True)
    dg = bpy.context.evaluated_depsgraph_get()
    capped = 0
    for o in meshes:
        s = o.modifiers.get("SpriteHull")
        n = len(o.data.vertices)
        if s is None or n == 0:
            continue
        me = o.evaluated_get(dg).to_mesh()
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        o.evaluated_get(dg).to_mesh_clear()
        if len(co) != 6 * n:                          # a weld changed the vertex count
            continue
        co = co.reshape(2, n, 3)
        w = np.clip(limit * s.thickness / np.maximum(np.linalg.norm(co[1] - co[0], axis=1), 1e-12), 0, 1)
        far = np.nonzero(w < 1)[0]
        if not len(far):
            continue
        vg = o.vertex_groups.new(name="SpriteHullCap")
        vg.add(np.nonzero(w >= 1)[0].tolist(), 1.0, "REPLACE")
        for i in far:
            vg.add([int(i)], float(w[i]), "REPLACE")
        s.vertex_group, s.thickness_vertex_group = vg.name, 0.0
        capped += len(far)
    hull_on(False)
    print(f"hull spikes capped at {capped} vertices")


def cap_spikes_now():
    """render.hull.cap_each_frame: cap_spikes for the current pose (call with the hull on). A
    corner that only turns needle-sharp later in the loop (a deep bend, a squashed joint) would
    otherwise draw a long black strand in those frames. Offsets are measured with the cap off, so
    each frame's weights depend on its pose alone, whichever process renders it."""
    import numpy as np
    limit = HULL.get("spike", 2.0)
    mods = [(o, o.modifiers.get("SpriteHull")) for o in meshes if len(o.data.vertices)]
    mods = [(o, s) for o, s in mods if s is not None]
    for o, s in mods:
        s.vertex_group = ""
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    for o, s in mods:
        n = len(o.data.vertices)
        me = o.evaluated_get(dg).to_mesh()
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        o.evaluated_get(dg).to_mesh_clear()
        if len(co) != 6 * n:                          # a weld changed the vertex count
            continue
        co = co.reshape(2, n, 3)
        w = np.clip(limit * s.thickness / np.maximum(np.linalg.norm(co[1] - co[0], axis=1), 1e-12), 0, 1)
        if (w >= 1).all():
            continue
        vg = o.vertex_groups.get("SpriteHullCap") or o.vertex_groups.new(name="SpriteHullCap")
        vg.add(np.nonzero(w >= 1)[0].tolist(), 1.0, "REPLACE")
        for i in np.nonzero(w < 1)[0]:
            vg.add([int(i)], float(w[i]), "REPLACE")
        s.vertex_group, s.thickness_vertex_group = vg.name, 0.0
    bpy.context.view_layer.update()


def use_pass(kind):
    """color: flat texture colours (Workbench); id: material group colours (Workbench, exact);
    data: normals (unlit EEVEE, no anti-aliasing); hull: the inverted hull (unlit EEVEE, no
    anti-aliasing)"""
    view_layer = bpy.context.view_layer
    scene.render.use_freestyle = False
    if kind in ("color", "id"):
        scene.render.engine = "BLENDER_WORKBENCH"
        view_layer.material_override = None
        scene.view_settings.view_transform = "Standard"
        scene.render.filter_size = 1.5 if kind == "color" else 0.01
        shading.color_type = "TEXTURE" if kind == "color" else "MATERIAL"
        scene.display.render_aa = "8" if kind == "color" else "OFF"
        return
    scene.render.engine = "BLENDER_EEVEE"
    for a in ("use_shadows", "use_raytracing", "use_volumetric_shadows", "use_gtao"):
        if hasattr(scene.eevee, a):
            setattr(scene.eevee, a, False)
    scene.eevee.taa_render_samples = 1          # no anti-aliasing: don't blend normals
    scene.render.filter_size = 0.01
    if kind == "hull":
        view_layer.material_override = None
        scene.view_settings.view_transform = "Standard"
    else:
        view_layer.material_override = data_mat
        scene.view_settings.view_transform = "Raw"   # store values as-is, no sRGB curve


# --- Camera -------------------------------------------------------------------
cam_data = bpy.data.cameras.new("SpriteCam")
cam = bpy.data.objects.new("SpriteCam", cam_data)
scene.collection.objects.link(cam)
cam_data.clip_end = 100000
scene.camera = cam


def place_camera():
    az, el = math.radians(num(CAM["azimuth"])), math.radians(num(CAM["elevation"]))
    fov = num(CAM.get("perspective_fov", 0)) or 0
    direction = Vector((math.cos(az) * math.cos(el), -math.sin(az) * math.cos(el), math.sin(el)))
    target = Vector(CAM["target"])
    if fov > 0.5:   # perspective, framed to cover the same area as the orthographic view
        cam_data.type = "PERSP"
        cam_data.angle = math.radians(fov)
        dist = CAM["ortho_scale"] / 2 / math.tan(cam_data.angle / 2)
    else:
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = CAM["ortho_scale"]
        dist = CAM["distance"]
    cam.location = target + direction * dist
    # "-Z" looks along the view; "Y" is this camera's up axis, kept toward world Z
    cam.rotation_euler = (-direction).to_track_quat("-Z", CAM.get("up", "Y")).to_euler()


place_camera()

# --- Pose ---------------------------------------------------------------------
AXES = {"X": Vector((1, 0, 0)), "Y": Vector((0, 1, 0)), "Z": Vector((0, 0, 1))}
to_arm = arm.matrix_world.inverted().to_3x3()


def rotate_world(name, axis, degrees):
    """Rotate a pose bone about a world axis through its head (children follow)."""
    pb = arm.pose.bones[name]
    a = (to_arm @ AXES[axis]).normalized()
    m = pb.matrix.copy()
    rot = Matrix.Rotation(math.radians(degrees), 4, a)
    head = m.translation.copy()
    pb.matrix = Matrix.Translation(head) @ rot @ Matrix.Translation(-head) @ m
    bpy.context.view_layer.update()


def slow_t(f, n, fast):
    """frame f of n -> 0..1 position in the loop with the fast frame ranges removed (held still
    during them)."""
    total = sum(b - a for a, b in fast)
    lost = 0
    for a, b in sorted(fast):
        if f >= b:
            lost += b - a
        elif f > a:
            return (a - lost) / (n - total)
    return (f - lost) / (n - total)


CLIP = cfg.get("motion", {}).get("clip")


def apply_clip(t):
    """Play one of the model's own actions. t in [0, 1) covers its frame range once, so a
    looping clip's last frame (a copy of the first) is not drawn twice."""
    action = bpy.data.actions[CLIP]
    ad = arm.animation_data or arm.animation_data_create()
    if ad.action != action:
        ad.action = action
        if action.slots:
            ad.action_slot = action.slots[0]
    start, end = action.frame_range
    frame = start + (t % 1.0) * (end - start)
    scene.frame_set(int(frame), subframe=frame - int(frame))
    bpy.context.view_layer.update()
    if cfg.get("pose"):
        # config "pose" offsets on top of the clip: freeze the clip's pose for this frame and unbind
        # the action, or rendering re-evaluates the action and drops the offsets
        basis = {pb.name: pb.matrix_basis.copy() for pb in arm.pose.bones}
        ad.action = None
        for pb in arm.pose.bones:
            pb.matrix_basis = basis[pb.name]
        bpy.context.view_layer.update()


def pose_at(t):
    """Apply config "pose" at loop position t in [0, 1); s/c are one sine cycle (the idle).
    motion.clip plays that action instead of starting from the bind pose."""
    if CLIP:
        apply_clip(t)
    else:
        for pb in arm.pose.bones:
            pb.rotation_mode = "QUATERNION"
            pb.matrix_basis = Matrix.Identity(4)
        bpy.context.view_layer.update()
    if not cfg.get("pose"):
        return
    # s, c: one sine / cosine cycle per loop; t: loop position 0..1 (for timed events, e.g. a spin);
    # ts: "slow time" - loop position with the fast frames (style.fast_frames) cut out, so the slow
    # motions pause during a fast event and the loop outside it stays seamless (see slow_t);
    # helpers (smooth, smoother, bump, damp, jitter, wave, ...) and motion.functions: motion.py
    ts = slow_t(t * FRAMES, FRAMES, cfg["style"].get("fast_frames", []))
    env = motion.env(cfg, P)
    env.update(s=math.sin(2 * math.pi * t), c=math.cos(2 * math.pi * t), t=t, ts=ts)
    for bone, axis, expr in cfg["pose"]:
        value = eval(expr, env)
        if axis == "SCALE":
            arm.pose.bones[bone].scale = (value, value, value)
            bpy.context.view_layer.update()
        elif axis == "SCALEW":                # widen a bone and the chain under it without lengthening them
            # (a strand thinner than a sprite pixel breaks into dashes). Each bone is widened in its
            # own axes and doesn't inherit its parent's scale: an inherited non-uniform scale would
            # also stretch the children along their length. The length axis is the bone axis
            # pointing at its child (FBX bones often run along X, not Blender's Y); a leaf bone, or
            # one whose only child is an exporter's "_end" marker (placed along any axis), uses its parent's
            axis_of = {}
            for pb in [arm.pose.bones[bone]] + list(arm.pose.bones[bone].children_recursive):
                b = arm.data.bones[pb.name]
                kids = [c for c in b.children if not c.name.endswith("_end")]
                if kids:
                    d = b.matrix_local.to_3x3().inverted() @ (kids[0].head_local - b.head_local)
                    axis_of[pb.name] = max(range(3), key=lambda i: abs(d[i]))
                else:
                    axis_of[pb.name] = axis_of.get(b.parent.name, 1) if b.parent else 1
                b.inherit_scale = "NONE"
                pb.scale = tuple(1.0 if i == axis_of[pb.name] else value for i in range(3))
            bpy.context.view_layer.update()
        elif axis.startswith("A:"):           # "A:x,y,z": rotate about any world axis through the bone head
            v = Vector([float(c) for c in axis[2:].split(",")]).normalized()
            pb = arm.pose.bones[bone]
            m = pb.matrix.copy(); head = m.translation.copy()
            pb.matrix = Matrix.Translation(head) @ Matrix.Rotation(math.radians(value), 4, (to_arm @ v).normalized()) @ Matrix.Translation(-head) @ m
            bpy.context.view_layer.update()
        elif axis in ("LOCCAM", "LOCCAMX"):   # move along the camera's up / right direction (model units):
            pb = arm.pose.bones[bone]           # screen-vertical / screen-horizontal
            d = (cam.matrix_world.to_3x3() @ Vector((0, 1, 0) if axis == "LOCCAM" else (1, 0, 0))).normalized()
            pb.matrix = Matrix.Translation(to_arm @ (d * value)) @ pb.matrix
            bpy.context.view_layer.update()
        elif axis == "ROLLCAM":               # rotate about the camera's view axis through the bone head:
            pb = arm.pose.bones[bone]           # an in-picture tilt (+ = counter-clockwise on screen)
            v = (cam.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
            m = pb.matrix.copy(); head = m.translation.copy()
            pb.matrix = Matrix.Translation(head) @ Matrix.Rotation(math.radians(value), 4, (to_arm @ v).normalized()) @ Matrix.Translation(-head) @ m
            bpy.context.view_layer.update()
        elif axis.startswith("LOC"):          # LOCX / LOCY / LOCZ: move along a world axis (model units)
            pb = arm.pose.bones[bone]
            pb.matrix = Matrix.Translation(to_arm @ (AXES[axis[3]] * value)) @ pb.matrix
            bpy.context.view_layer.update()
        else:
            rotate_world(bone, axis, value)
    if PLANT:
        hold_planted()


PLANT = {}          # motion.plant: bone -> armature-space point its head is held at (plant())


def plant():
    """motion.plant: bones (each ankle, say) that stay put while the body above them moves: a body
    dip or sway bends the two bones above each one (thigh and shin) instead of sliding or lifting
    the foot. Each is held at its head's mean position over the loop. Run again whenever pose /
    pose_params change (live_preview does)."""
    PLANT.clear()
    bones = cfg.get("motion", {}).get("plant", [])
    if not bones:
        return
    n, acc = 8, {b: Vector() for b in bones}
    for i in range(n):
        pose_at(i / n)
        for b in bones:
            acc[b] += arm.pose.bones[b].head
    PLANT.update({b: v / n for b, v in acc.items()})


def hold_planted():
    """bring each planted bone's head back to its PLANT point: cyclic coordinate descent on its
    parent and grandparent, each turned about its own head in armature space (the rig's bones are
    disconnected and point every which way, which Blender's IK solver can't take). The planted bone
    keeps its orientation, so a foot stays flat. 3 scene updates a frame, whatever the leg count."""
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
        bpy.context.view_layer.update()
    for _, _, foot, Mf, shift, _ in legs:
        foot.matrix = Matrix.Translation(shift) @ Mf
    bpy.context.view_layer.update()


plant()


def render_frame(t, name):
    if HULL_T is None:
        set_hull_thickness()
    pose_at(t)
    for kind in ("color",) + (("id",) if USE_ID else ()) + ("data", "hull"):
        use_pass(kind)
        if kind == "hull":
            hull_on(True)
            if HULL.get("cap_each_frame"):
                cap_spikes_now()
        scene.render.filepath = f"{out_dir}/{kind}_{name}{EXT}"
        bpy.ops.render.render(write_still=True)
        if kind == "hull":
            hull_on(False)


if setup_only:
    pass
elif test_ts is not None:
    for i, t in enumerate(test_ts):
        render_frame(t, f"{i + 1:04d}")
elif "--frames" in args:
    # a subset of the loop's frames, named as in the full loop (render_parallel.py splits the
    # loop across several Blender processes this way); "0,5,9" or "0:60" (end exclusive)
    spec = args[args.index("--frames") + 1]
    fs = range(*map(int, spec.split(":"))) if ":" in spec else [int(v) for v in spec.split(",")]
    for f in fs:
        render_frame(f / FRAMES, f"{f + 1:04d}")
else:
    for f in range(FRAMES):
        render_frame(f / FRAMES, f"{f + 1:04d}")
