import bpy, sys
from pathlib import Path
args = sys.argv[sys.argv.index("--") + 1:]
src, out = args[0], args[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=src)
for o in bpy.context.scene.objects:
    print("OBJ", o.type, o.name, tuple(round(v, 2) for v in o.dimensions), [m.name for m in getattr(o.data, "materials", [])] if o.type == "MESH" else "")
arm = next((o for o in bpy.context.scene.objects if o.type == "ARMATURE"), None)
if arm:
    print("BONES", len(arm.data.bones))
    for b in arm.data.bones:
        print("  BONE", b.name, "parent", b.parent.name if b.parent else None, tuple(round(v, 1) for v in (arm.matrix_world @ b.head_local)))
for m in bpy.data.materials:
    imgs = [n.image.name for n in (m.node_tree.nodes if m.node_tree else []) if n.type == "TEX_IMAGE" and n.image]
    print("MAT", m.name, imgs)
for a in bpy.data.actions:
    print("ACTION", a.name, a.frame_range[:])
bpy.ops.file.pack_all() if False else None
bpy.ops.wm.save_as_mainfile(filepath=out)
