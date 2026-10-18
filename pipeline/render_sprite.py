"""Render a posed model as frame sequences for the Showdown-style sprite pipeline.

Run:
  Blender -b MODEL.blend --python render_sprite.py -- CONFIG.json OUT_DIR [--test 0,0.5] [--frames 0:60 | 0,5,9]
(render_parallel.py runs several of these at once, one slice of the loop each)
Writes three images per frame (see SPRITE_PIPELINE.md):
  color_NNNN.png  flat texture colours (Workbench), transparent background
  id_NNNN.png     which part each pixel is: one solid colour per entry of config "parts.materials"
  data_NNNN.png   camera-space normal in R/G, depth in B (EEVEE), for shading + inner lines
  rest_NNNN.png   where on the unposed model each pixel is (EEVEE), for surface-attached lines
Everything model-specific (bones, camera, materials) comes from CONFIG.json.
Other scripts (fit_pose.py) exec this file with --setup-only to reuse the scene setup.
"""
import bpy, sys, math, json
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
DEPTH_RANGE = cfg["render"].get("depth_range", 250)   # +- model units around the target stored in the data pass
                                     # (about the model's size: Lapras ~200 units, a Switch rip ~3)


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

# --- Texture-space passes (per Pokemon): maps painted in the model's texture layout, rendered as
# the colour pass with those textures swapped in, so whatever they mark sits on the surface and
# moves with it exactly. render.texture_passes {"name": {"maps": {"texture name fragment": "file"},
# "nearest": bool}} -> NAME_####.png. Made by make_seams.py:
#   seams    plate edges / grooves (white) -> style.seam_lines
#   islands  one colour per UV island = which plate a pixel shows (nearest: ids must not blend)
#            -> style.plate_shading
# render.seams {...} is short for texture_passes {"seams": {"maps": {...}}}. Pokemon without any
# (Lapras: Showdown draws few inner lines) render no extra pass.
TEX_PASSES = dict(cfg["render"].get("texture_passes", {}))
if cfg["render"].get("seams"):
    TEX_PASSES.setdefault("seams", {"maps": cfg["render"]["seams"]})
TEX_SWAPS = {}
for pname, spec in TEX_PASSES.items():
    TEX_SWAPS[pname] = []
    for img in bpy.data.images:
        for frag, f in spec["maps"].items():
            if frag in img.filepath or frag in img.name:
                TEX_SWAPS[pname].append((img, img.filepath, "//" + f))
                break


def swap_texture_pass(pname, on):
    nearest = TEX_PASSES[pname].get("nearest", False)
    imgs = {img for img, _, _ in TEX_SWAPS[pname]}
    for img, orig, new in TEX_SWAPS[pname]:
        img.filepath = new if on else orig
        img.reload()
    if nearest:
        if hasattr(bpy.context.preferences.system, "use_mipmaps"):    # gone in newer Blender
            bpy.context.preferences.system.use_mipmaps = not on
        for mat in bpy.data.materials:
            for nd in (mat.node_tree.nodes if mat.node_tree else []):
                if nd.type == "TEX_IMAGE" and nd.image in imgs:
                    if on:
                        nd["_interp"] = nd.interpolation
                        nd.interpolation = "Closest"
                    else:
                        nd.interpolation = nd.get("_interp", "Linear")


# --- Shared render settings ---------------------------------------------------
scene.render.film_transparent = True
scene.render.resolution_x = cfg["render"]["width"]
scene.render.resolution_y = cfg["render"]["height"]
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.image_settings.color_depth = "8"

shading = scene.display.shading
shading.light = "FLAT"
shading.show_object_outline = False
shading.show_specular_highlight = False

# --- ID pass colours: one primary-ish colour per part name ---------------------
ID_ORDER = [cfg["parts"]["default_material"]] + sorted(set(cfg["parts"]["materials"].values()))
ID_RGB = [(1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0), (1, 0, 1), (0, 1, 1), (1, 1, 1)]
for mat in bpy.data.materials:
    images = [n.image.name for n in (mat.node_tree.nodes if mat.node_tree else [])
              if n.type == "TEX_IMAGE" and n.image]
    part = cfg["parts"]["default_material"]
    for key, name in cfg["parts"]["materials"].items():
        if any(key in i for i in images) or key in mat.name:
            part = name
    mat.diffuse_color = (*ID_RGB[ID_ORDER.index(part)], 1)

# --- Data pass: EEVEE with one emission material on everything -----------------
data_mat = bpy.data.materials.new("SpriteData")
data_mat.use_nodes = True
nt = data_mat.node_tree
nt.nodes.clear()
N = nt.nodes.new
geo, vt = N("ShaderNodeNewGeometry"), N("ShaderNodeVectorTransform")
vt.vector_type, vt.convert_from, vt.convert_to = "NORMAL", "WORLD", "CAMERA"
half = N("ShaderNodeVectorMath"); half.operation = "MULTIPLY_ADD"
half.inputs[1].default_value = (0.5, 0.5, 0.5); half.inputs[2].default_value = (0.5, 0.5, 0.5)
sep, cam_node, depth = N("ShaderNodeSeparateXYZ"), N("ShaderNodeCameraData"), N("ShaderNodeMapRange")
depth.inputs["To Min"].default_value, depth.inputs["To Max"].default_value = 1.0, 0.0   # brighter = nearer
comb, emit, out = N("ShaderNodeCombineColor"), N("ShaderNodeEmission"), N("ShaderNodeOutputMaterial")
L = nt.links.new
L(geo.outputs["Normal"], vt.inputs["Vector"]); L(vt.outputs["Vector"], half.inputs[0])
L(half.outputs["Vector"], sep.inputs["Vector"])
L(cam_node.outputs["View Z Depth"], depth.inputs["Value"])
L(sep.outputs["X"], comb.inputs[0]); L(sep.outputs["Y"], comb.inputs[1]); L(depth.outputs["Result"], comb.inputs[2])
L(comb.outputs["Color"], emit.inputs["Color"]); L(emit.outputs["Emission"], out.inputs["Surface"])


# --- Rest pass: each pixel's position on the *unposed* model, so lines can be attached to the
# surface (sprite_style.anchor_lines) instead of re-detected every frame. Stored as a colour
# attribute (vertex rest position, normalised to the model's bounding box), drawn by emission.
meshes = [o for o in scene.objects if o.type == "MESH" and not o.hide_render]
lo = Vector((min(v.co[i] for o in meshes for v in o.data.vertices) for i in range(3)))
hi = Vector((max(v.co[i] for o in meshes for v in o.data.vertices) for i in range(3)))
for o in meshes:
    me = o.data
    attr = me.color_attributes.get("RestPos") or me.color_attributes.new("RestPos", "FLOAT_COLOR", "POINT")
    for v, c in zip(me.vertices, attr.data):
        c.color = (*((v.co[i] - lo[i]) / max(1e-6, hi[i] - lo[i]) for i in range(3)), 1.0)
rest_mat = bpy.data.materials.new("SpriteRest")
rest_mat.use_nodes = True
rt = rest_mat.node_tree
rt.nodes.clear()
ra, re_, ro = rt.nodes.new("ShaderNodeAttribute"), rt.nodes.new("ShaderNodeEmission"), rt.nodes.new("ShaderNodeOutputMaterial")
ra.attribute_type, ra.attribute_name = "GEOMETRY", "RestPos"
rt.links.new(ra.outputs["Color"], re_.inputs["Color"]); rt.links.new(re_.outputs["Emission"], ro.inputs["Surface"])


# --- Lines pass (Freestyle): creases, inner contours and borders traced from the mesh itself,
# so inner lines move with the model instead of being re-detected from pixels every frame.
# The body renders transparent (holdout); only the strokes are drawn, in white.
FS = cfg["render"].get("freestyle", {})
hold_mat = bpy.data.materials.new("SpriteHoldout")
hold_mat.use_nodes = True
hn = hold_mat.node_tree
hn.nodes.clear()
hn.links.new(hn.nodes.new("ShaderNodeHoldout").outputs[0], hn.nodes.new("ShaderNodeOutputMaterial").inputs["Surface"])
fs = bpy.context.view_layer.freestyle_settings
fs.crease_angle = math.radians(FS.get("crease_angle", 140))
fs.use_culling = True           # skip edges outside the view: the model is always fully in view (same lines, faster)
lset = fs.linesets[0] if len(fs.linesets) else fs.linesets.new("SpriteLines")
lset.select_by_visibility, lset.visibility = True, "VISIBLE"
lset.select_by_edge_types = True
for k in ("silhouette", "crease", "border", "contour", "external_contour", "material_boundary", "ridge_valley",
          "suggestive_contour", "edge_mark"):
    setattr(lset, "select_" + k, k in FS.get("edges", ["silhouette", "crease", "border"]))
if lset.linestyle is None:
    lset.linestyle = bpy.data.linestyles.new("SpriteLineStyle")
lset.linestyle.color = (1, 1, 1)
lset.linestyle.thickness = FS.get("thickness", 3.0)
lset.linestyle.alpha = 1.0
scene.render.line_thickness_mode = "ABSOLUTE"
scene.render.line_thickness = 1.0


# --- Shadow pass (optional, config render.shadow): white diffuse lit by one hard sun, no ambient.
# Compared with the sun's N.L (from the data pass) it tells which pixels are in a *cast* shadow:
# facing the light but blocked by another part (petals under the crown, a chin over a neck).
# Normal-based shading (matcap) can't produce those, and they're what makes the game's shadows
# read as big dark masses. render.shadow.light_cam = direction toward the light in camera space
# (x right, y up, z toward the viewer).
SH = cfg["render"].get("shadow")
shadow_mat = bpy.data.materials.new("SpriteShadow")
shadow_mat.use_nodes = True
sn = shadow_mat.node_tree
sn.nodes.clear()
sdif = sn.nodes.new("ShaderNodeBsdfDiffuse"); sdif.inputs["Color"].default_value = (1, 1, 1, 1)
sn.links.new(sdif.outputs[0], sn.nodes.new("ShaderNodeOutputMaterial").inputs["Surface"])
sun_data = bpy.data.lights.new("SpriteSun", "SUN")
sun_data.energy = 0.0
sun_data.angle = 0.0                      # hard shadow edge, like the game's
sun_data.use_shadow = True
sun = bpy.data.objects.new("SpriteSun", sun_data)
scene.collection.objects.link(sun)
if scene.world is None:
    scene.world = bpy.data.worlds.new("SpriteWorld")
scene.world.use_nodes = True
bg = next((n for n in scene.world.node_tree.nodes if n.type == "BACKGROUND"), None)
if bg is not None:
    bg.inputs["Strength"].default_value = 0.0         # no ambient light: only sun + shadow


def aim_sun(light_cam):
    """point the sun so light comes from light_cam (camera space)"""
    v = cam.matrix_world.to_3x3() @ Vector(light_cam)
    v.normalize()
    sun.rotation_euler = (-v).to_track_quat("-Z", "Y").to_euler()
    bpy.context.view_layer.update()


# EEVEE settings that only matter for lit passes: only the shadow pass is lit; data / rest are
# emission and the lines pass a holdout + unlit strokes, so they skip them (same pixels, faster)
EEVEE_LIT = {a: getattr(scene.eevee, a) for a in ("use_shadows", "use_raytracing", "use_volumetric_shadows", "use_gtao")
             if hasattr(scene.eevee, a)}


def use_pass(kind):
    view_layer = bpy.context.view_layer
    for a, v in EEVEE_LIT.items():
        setattr(scene.eevee, a, v if kind == "shadow" else False)
    if kind in ("color", "id") or kind in TEX_PASSES:
        scene.render.engine = "BLENDER_WORKBENCH"
        view_layer.material_override = None
        scene.view_settings.view_transform = "Standard"
        exact = kind == "id" or TEX_PASSES.get(kind, {}).get("nearest", False)
        scene.render.filter_size = 0.01 if exact else 1.5
        shading.color_type = "MATERIAL" if kind == "id" else "TEXTURE"
        scene.display.render_aa = "OFF" if exact else "8"
    scene.render.use_freestyle = kind == "lines"
    if kind == "lines":
        scene.render.engine = "BLENDER_EEVEE"
        scene.eevee.taa_render_samples = 8
        scene.render.filter_size = 1.5
        view_layer.material_override = hold_mat
        scene.view_settings.view_transform = "Standard"
    elif kind in ("color", "id") or kind in TEX_PASSES:
        pass
    else:
        scene.render.engine = "BLENDER_EEVEE"
        scene.eevee.taa_render_samples = 1          # no anti-aliasing: don't blend normals
        scene.render.filter_size = 0.01
        view_layer.material_override = {"rest": rest_mat, "shadow": shadow_mat}.get(kind, data_mat)
        scene.view_settings.view_transform = "Raw"   # store values as-is, no sRGB curve
    sun_data.energy = math.pi if kind == "shadow" else 0.0   # pi: a lit white surface facing the sun = 1.0


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
    cam.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
    depth.inputs["From Min"].default_value = dist - DEPTH_RANGE
    depth.inputs["From Max"].default_value = dist + DEPTH_RANGE


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
    during them). Same function in sprite_style.py / check_loop.py."""
    total = sum(b - a for a, b in fast)
    lost = 0
    for a, b in sorted(fast):
        if f >= b:
            lost += b - a
        elif f > a:
            return (a - lost) / (n - total)
    return (f - lost) / (n - total)


def pose_at(t):
    """Apply config "pose" at loop position t in [0, 1); s/c are one sine cycle (the idle)."""
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
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


def render_frame(t, name):
    pose_at(t)
    if SH:
        aim_sun(SH["light_cam"])
    for kind in ("color", "id", "data", "rest") + (("lines",) if FS else ()) + (("shadow",) if SH else ()) + tuple(TEX_PASSES):
        use_pass(kind)
        if kind in TEX_PASSES:
            swap_texture_pass(kind, True)
        scene.render.filepath = f"{out_dir}/{kind}_{name}.png"
        bpy.ops.render.render(write_still=True)
        if kind in TEX_PASSES:
            swap_texture_pass(kind, False)


if setup_only:
    pass
elif "--shadow-dirs" in args:
    # fitting the sun: frame 0's shadow pass for each candidate direction ("x,y,z;x,y,z;...")
    pose_at(0.0)
    for k, d in enumerate(args[args.index("--shadow-dirs") + 1].split(";")):
        aim_sun([float(v) for v in d.split(",")])
        use_pass("shadow")
        scene.render.filepath = f"{out_dir}/shadowdir{k:03d}.png"
        bpy.ops.render.render(write_still=True)
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
