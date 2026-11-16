"""Move the game idle from the Z-A animation pack onto the textured model copy.

Run (from the repo root):
  /usr/local/bin/python3 pipeline/blender_slot.py --timeout 600 -- -b \
    mega-malamar-model/MegaMalamar/MegaMalamar_noglow.blend \
    --python mega-malamar-model/move_clip.py -- [inspect|save]

inspect: import the pack FBX, list its actions, compare rest bones and the posed bones of the
         model's armature against the pack's own armature over the whole clip (offset / scale),
         then quit without saving.
save:    the same, then keep only the idle action, delete everything the import brought in
         (the pack is the shiny version: none of its meshes, materials or images are kept) and
         save a copy as MegaMalamar/MegaMalamar_anim.blend. The source .blend is not changed.
"""
import sys
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
FBX = HERE / "pack/source/Mega Malamar (ZA).fbx"
OUT = HERE / "MegaMalamar/MegaMalamar_anim.blend"
NAME = "pm0727_51_00_20001_battlewait01_loop"
mode = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else "inspect"

scene = bpy.context.scene
fps_before = (scene.render.fps, scene.render.fps_base)
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
before = {name: set(getattr(bpy.data, name)) for name in
          ("objects", "actions", "meshes", "materials", "images", "armatures", "textures",
           "node_groups", "collections", "cameras", "lights")}
bpy.ops.import_scene.fbx(filepath=str(FBX))
new = {name: [d for d in getattr(bpy.data, name) if d not in s] for name, s in before.items()}
print("scene fps before", fps_before, "after import", (scene.render.fps, scene.render.fps_base))
src = next(o for o in new["objects"] if o.type == "ARMATURE")
print("imported objects", len(new["objects"]), "actions", len(new["actions"]))
for a in new["actions"]:
    print(f"  ACTION {a.name}  range={tuple(a.frame_range)}")
act = next(a for a in new["actions"] if NAME in a.name)
print("idle:", act.name, tuple(act.frame_range))

missing = [b.name for b in arm.data.bones if b.name not in src.data.bones]
extra = [b.name for b in src.data.bones if b.name not in arm.data.bones]
print("bones model", len(arm.data.bones), "pack", len(src.data.bones),
      "missing in pack", missing[:10], "extra in pack", extra[:10])
print("model obj matrix", [[round(v, 4) for v in r] for r in arm.matrix_world])
print("pack  obj matrix", [[round(v, 4) for v in r] for r in src.matrix_world])
worst = 0.0
for b in arm.data.bones:
    if b.name in src.data.bones:
        mt = arm.matrix_world @ b.matrix_local
        ms = src.matrix_world @ src.data.bones[b.name].matrix_local
        worst = max(worst, (mt.translation - ms.translation).length)
print(f"REST worst bone head offset {worst:.6f}")

# play the idle on both armatures, compare every posed bone in world space
for o in (arm, src):
    ad = o.animation_data or o.animation_data_create()
    ad.action = act
    if act.slots:
        ad.action_slot = act.slots[0]
s, e = (int(round(v)) for v in act.frame_range)
worst_p = worst_m = 0.0
scales = []
for f in range(s, e + 1, 5):
    scene.frame_set(f)
    bpy.context.view_layer.update()
    for pb in arm.pose.bones:
        if pb.name not in src.pose.bones:
            continue
        ma = arm.matrix_world @ pb.matrix
        mb = src.matrix_world @ src.pose.bones[pb.name].matrix
        worst_p = max(worst_p, (ma.translation - mb.translation).length)
        worst_m = max(worst_m, max(abs(x - y) for ra, rb in zip(ma.to_3x3(), mb.to_3x3())
                                   for x, y in zip(ra, rb)))
    for n in ("waist", "head", "left_arm_11", "tail_03"):
        if f in (s, (s + e) // 2):
            m = arm.matrix_world @ arm.pose.bones[n].matrix
            r = arm.matrix_world @ arm.data.bones[n].matrix_local
            print(f"POSE f{f} {n:12s} posed {tuple(round(v, 3) for v in m.translation)} "
                  f"rest {tuple(round(v, 3) for v in r.translation)} scale {tuple(round(v, 3) for v in m.to_scale())}")
    scales += [pb.matrix.to_scale() for pb in arm.pose.bones]
smin = min(min(v) for v in scales)
smax = max(max(v) for v in scales)
print(f"POSED vs pack, all bones every 5th frame: pos {worst_p:.6f}  matrix elem {worst_m:.6f}")
print(f"posed bone scale range {smin:.4f} .. {smax:.4f}")
# loop seam: first vs last frame on the model's own armature
seam = 0.0
scene.frame_set(s); bpy.context.view_layer.update()
first = {pb.name: (arm.matrix_world @ pb.matrix).translation.copy() for pb in arm.pose.bones}
scene.frame_set(e); bpy.context.view_layer.update()
for pb in arm.pose.bones:
    seam = max(seam, ((arm.matrix_world @ pb.matrix).translation - first[pb.name]).length)
print(f"SEAM first vs last frame, worst bone {seam:.6f}")

if mode == "save":
    act.name = NAME
    act.use_fake_user = True
    arm.animation_data.action = None
    for o in new["objects"]:
        bpy.data.objects.remove(o, do_unlink=True)
    for a in new["actions"]:
        if a is not act:
            bpy.data.actions.remove(a)
    for name in ("meshes", "materials", "images", "armatures", "textures", "node_groups",
                 "cameras", "lights", "collections"):
        coll = getattr(bpy.data, name)
        for d in new[name]:
            if d.name in coll:
                coll.remove(d)
    scene.render.fps, scene.render.fps_base = fps_before
    print("kept actions", [a.name for a in bpy.data.actions], "objects", len(bpy.data.objects),
          "images", len(bpy.data.images), "materials", len(bpy.data.materials))
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT), copy=True)
    print("SAVED", OUT)
