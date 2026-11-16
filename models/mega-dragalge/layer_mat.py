"""Give the faces of one material that fall inside a texture layer mask their own material, so they
can be their own part. Game models colour some surfaces in the shader from layer masks
(..._lym_R/G/B/A.png) instead of the albedo: Mega Dragalge's wings are thin shells whose outer
side (layer G) is crimson and inner side (layer R) purple, while the albedo is one flat purple.
A face goes to the new material when the mask is white at its UV centre.
Run:  Blender -b --factory-startup --python layer_mat.py -- IN.blend OUT.blend OBJECT MATERIAL MASK.png NEW_MATERIAL
(MASK.png relative to IN.blend's folder)
"""
import bpy, sys
args = sys.argv[sys.argv.index("--") + 1:]
src_blend, out_blend, obj, mat_name, mask_file, new_name = args[:6]
bpy.ops.wm.open_mainfile(filepath=src_blend)
o = bpy.data.objects[obj]; me = o.data
src = next(i for i, m in enumerate(me.materials) if m and m.name == mat_name)
mask = bpy.data.images.load(bpy.path.abspath("//" + mask_file))
w, h = mask.size
px = mask.pixels[:]
ch = mask.channels
new = me.materials[src].copy(); new.name = new_name
me.materials.append(new); k = len(me.materials) - 1
uv = me.uv_layers.active.data
n = 0
for p in me.polygons:
    if p.material_index != src:
        continue
    u = sum(uv[i].uv[0] for i in p.loop_indices) / p.loop_total
    v = sum(uv[i].uv[1] for i in p.loop_indices) / p.loop_total
    x, y = min(w - 1, int(u % 1 * w)), min(h - 1, int(v % 1 * h))
    if px[(y * w + x) * ch] > 0.5:
        p.material_index = k; n += 1
print("LAYER faces", n, "->", new_name)
bpy.ops.wm.save_as_mainfile(filepath=out_blend, relative_remap=True)
