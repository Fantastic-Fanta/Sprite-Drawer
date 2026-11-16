"""Blender side of prep_model.py: import a model, save it as a .blend with relative texture paths,
and describe it for the config (rig, materials, texture colours, size) plus rest-pose views.

Run (prep_model.py does):  Blender -b --python prep_scene.py -- MODEL.fbx|.glb OUT.blend OUT_DIR
Writes OUT_DIR/scene.json and OUT_DIR/rest_{front,side,top}.png.
"""
import bpy, sys, json, math, os, random
import numpy as np
from pathlib import Path
from mathutils import Vector

src, out_blend, out_dir = sys.argv[sys.argv.index("--") + 1:][:3]
out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
ext = Path(src).suffix.lower()
if ext == ".fbx":
    bpy.ops.import_scene.fbx(filepath=src)
elif ext in (".glb", ".gltf"):
    bpy.ops.import_scene.gltf(filepath=src)
else:
    raise SystemExit(f"can't import {ext}")
bpy.ops.wm.save_as_mainfile(filepath=out_blend)
bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_as_mainfile(filepath=out_blend)

scene = bpy.context.scene
arms = [o for o in scene.objects if o.type == "ARMATURE"]
meshes = [o for o in scene.objects if o.type == "MESH" and not o.name.startswith("Icosphere")]
arm = arms[0] if arms else None
info = {"source": Path(src).name, "warnings": []}
if len(arms) != 1:
    info["warnings"].append(f"{len(arms)} armatures (the pipeline expects exactly one)")

# --- size (rest pose, deformed meshes) ----------------------------------------
dg = bpy.context.evaluated_depsgraph_get()
pts = []
for o in meshes:
    e = o.evaluated_get(dg); me = e.to_mesh()
    pts += [o.matrix_world @ v.co for v in me.vertices]
    e.to_mesh_clear()
lo = Vector([min(p[i] for p in pts) for i in range(3)]); hi = Vector([max(p[i] for p in pts) for i in range(3)])
info["bbox"] = {"min": [round(v, 4) for v in lo], "max": [round(v, 4) for v in hi]}

# --- rig ----------------------------------------------------------------------
weight = {}
for o in meshes:
    names = {vg.index: vg.name for vg in o.vertex_groups}
    for v in o.data.vertices:
        for ge in v.groups:
            n = names.get(ge.group)
            if n:
                weight[n] = weight.get(n, 0) + ge.weight
bones = []
if arm:
    mw = arm.matrix_world
    for b in arm.data.bones:
        m = (mw @ b.matrix_local).to_3x3().normalized()
        bones.append({"name": b.name, "parent": b.parent.name if b.parent else None,
                      "head": [round(c, 3) for c in mw @ b.head_local],
                      "tail": [round(c, 3) for c in mw @ b.tail_local],
                      "children": [c.name for c in b.children],
                      "weight": round(weight.get(b.name, 0), 1),
                      # the bone's own axes in world space at rest: bend axes for "A:x,y,z" pose entries
                      "axes": {k: [round(c, 3) for c in m.col[i]] for i, k in enumerate("xyz")}})
info["bones"] = bones
info["actions"] = [a.name for a in bpy.data.actions]

# --- materials, textures, colour samples ---------------------------------------
def base_image(mat):
    """the albedo image of a material: the image feeding Base Color, else one named like an albedo"""
    if not mat or not mat.node_tree:
        return None
    nodes = mat.node_tree.nodes
    for n in nodes:
        if n.type == "BSDF_PRINCIPLED":
            stack = [l.from_node for l in n.inputs["Base Color"].links]
            seen = set()
            while stack:
                x = stack.pop()
                if x in seen:
                    continue
                seen.add(x)
                if x.type == "TEX_IMAGE" and x.image:
                    return x.image
                stack += [l.from_node for i in x.inputs for l in i.links]
    imgs = [n.image for n in nodes if n.type == "TEX_IMAGE" and n.image]
    for key in ("alb", "col", "diff", "base"):
        for im in imgs:
            if key in im.name.lower():
                return im
    return imgs[0] if imgs else None

pix_cache = {}
def pixels(img):
    if img.name not in pix_cache:
        if not img.has_data:
            try:
                img.reload()
            except Exception:
                pass
        w, h = img.size
        if w == 0:
            pix_cache[img.name] = None
        else:
            a = np.empty(w * h * 4, dtype=np.float32); img.pixels.foreach_get(a)
            pix_cache[img.name] = a.reshape(h, w, 4)
    return pix_cache[img.name]

mats, samples = {}, []
rng = random.Random(1)
for o in meshes:
    e = o.evaluated_get(dg); me = e.to_mesh()
    me.calc_loop_triangles()
    uv = me.uv_layers.active.data if me.uv_layers.active else None
    for t in me.loop_triangles:
        mat = o.material_slots[t.material_index].material if o.material_slots else None
        mname = mat.name if mat else "(none)"
        img = base_image(mat)
        d = mats.setdefault(mname, {"image": img.filepath if img else None, "image_name": img.name if img else None,
                                    "area": 0.0, "missing": False})
        a = t.area
        d["area"] += a
        if img is None or uv is None:
            continue
        px = pixels(img)
        if px is None:
            d["missing"] = True
            continue
        h, w = px.shape[:2]
        # a few points per triangle, more on big ones
        n = 1 + int(a * 400)
        for _ in range(min(n, 6)):
            r1, r2 = rng.random(), rng.random()
            if r1 + r2 > 1:
                r1, r2 = 1 - r1, 1 - r2
            u = uv[t.loops[0]].uv * (1 - r1 - r2) + uv[t.loops[1]].uv * r1 + uv[t.loops[2]].uv * r2
            x, y = int((u.x % 1) * w) % w, int((u.y % 1) * h) % h
            c = px[y, x]
            if c[3] > 0.5:
                samples.append([mname, round(float(c[0]), 4), round(float(c[1]), 4), round(float(c[2]), 4), round(a / n, 6)])
    e.to_mesh_clear()
for m, d in mats.items():
    if d["image"] and not d["missing"] and d["image_name"] and not bpy.data.images[d["image_name"]].has_data:
        d["missing"] = True
    if d["missing"]:
        info["warnings"].append(f"material {m}: texture {d['image']} missing or unreadable")
info["materials"] = mats
if len(samples) > 40000:
    samples = rng.sample(samples, 40000)
info["samples_linear_rgb"] = samples             # [material, r, g, b, area weight]; 8-bit textures: sRGB-encoded

# --- rest views (Workbench, a few seconds) -------------------------------------
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "TEXTURE"
scene.render.film_transparent = False
scene.world = scene.world or bpy.data.worlds.new("W"); scene.world.color = (0.55, 0.55, 0.55)
scene.view_settings.view_transform = "Standard"
scene.render.resolution_x = scene.render.resolution_y = 420
for o in scene.objects:
    if o.name.startswith("Icosphere"):
        o.hide_render = True
cd = bpy.data.cameras.new("C"); cd.type = "ORTHO"; cam = bpy.data.objects.new("C", cd)
scene.collection.objects.link(cam); scene.camera = cam
centre = (lo + hi) / 2; size = max(hi - lo) * 1.15
cd.ortho_scale = size; cd.clip_end = size * 20
for name, az, el in (("front", 90, 5), ("side", 0, 5), ("top", 90, 85)):
    a, e = math.radians(az), math.radians(el)
    d = Vector((math.cos(a) * math.cos(e), -math.sin(a) * math.cos(e), math.sin(e)))
    cam.location = centre + d * size * 5
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = str(out_dir / f"rest_{name}.png")
    bpy.ops.render.render(write_still=True)

(out_dir / "scene.json").write_text(json.dumps(info))
print("PREP_SCENE_OK")
