"""Give the fin-mesh faces skinned to the horn bones their own material ("kelp_horns"), so they can be
their own part (Mega Dragalge's olive horns share the fins' flat purple texture).
Run:  Blender -b --factory-startup --python kelp_mat.py -- IN.blend OUT.blend
"""
import bpy, sys
args = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.open_mainfile(filepath=args[0])
o = bpy.data.objects["pm0710_51_00_hair_mesh"]; me = o.data
names = {g.index: g.name for g in o.vertex_groups}
src = me.materials[0]
kelp = src.copy(); kelp.name = "kelp_horns"
me.materials.append(kelp); k = len(me.materials) - 1
n = 0
for p in me.polygons:
    w = {}
    for vi in p.vertices:
        for g in me.vertices[vi].groups:
            w[names[g.group]] = w.get(names[g.group], 0) + g.weight
    if w and "horn" in max(w, key=w.get):
        p.material_index = k; n += 1
print("KELP faces", n, "of", len(me.polygons))
bpy.ops.wm.save_as_mainfile(filepath=args[1], relative_remap=True)
