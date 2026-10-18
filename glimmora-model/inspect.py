import bpy
for m in bpy.data.materials:
    imgs = [n.image.name for n in (m.node_tree.nodes if m.node_tree else []) if n.type == "TEX_IMAGE" and n.image]
    print("MAT", m.name, imgs)
for a in bpy.data.actions:
    print("ACTION", a.name, tuple(a.frame_range))
arm = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
print("ARM rot", tuple(arm.rotation_euler), "scale", tuple(arm.scale))
for o in bpy.context.scene.objects:
    if o.type == "MESH":
        import mathutils
        bb = [o.matrix_world @ mathutils.Vector(c) for c in o.bound_box]
        lo = [round(min(v[i] for v in bb), 2) for i in range(3)]; hi = [round(max(v[i] for v in bb), 2) for i in range(3)]
        print("MESH", o.name, lo, hi, len(o.data.vertices))
for i in bpy.data.images:
    print("IMG", i.name, i.filepath, i.size[:])
