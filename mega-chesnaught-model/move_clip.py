"""Move the game idle from the animation pack onto the textured body copy (no spear, no vines).

Run (from the repo root):
  /usr/local/bin/python3 pipeline/blender_slot.py --timeout 600 -- -b \
    mega-chesnaught-model/MegaChesnaught/MegaChesnaught_body.blend \
    --python mega-chesnaught-model/move_clip.py -- [inspect|save]

inspect: import the glb, print its actions and compare a few bones' rest matrices (world space)
         with the model's own armature, then quit without saving.
save:    keep the battlewait01_loop action (renamed to the plain name below), delete everything
         else the import brought in, and save MegaChesnaught/MegaChesnaught_anim.blend.
"""
import sys
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
GLB = HERE / "pack/source/Chesnaught.glb"
OUT = HERE / "MegaChesnaught/MegaChesnaught_anim.blend"
NAME = "pm0722_51_00_00001_battlewait01_loop"
mode = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else "inspect"

arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
before_obj = set(bpy.data.objects)
before_act = set(bpy.data.actions)
before_mesh, before_mat, before_img, before_arm = (set(bpy.data.meshes), set(bpy.data.materials),
                                                    set(bpy.data.images), set(bpy.data.armatures))
bpy.ops.import_scene.gltf(filepath=str(GLB), bone_heuristic="BLENDER")
new_obj = [o for o in bpy.data.objects if o not in before_obj]
src = next(o for o in new_obj if o.type == "ARMATURE")
acts = [a for a in bpy.data.actions if a not in before_act]
print("imported actions:", len(acts))
for a in acts:
    if "battlewait" in a.name or "wait" in a.name:
        print(f"  {a.name}  range={tuple(a.frame_range)}")
print("src bones", len(src.data.bones), "tgt bones", len(arm.data.bones))
print("src obj matrix", [list(map(lambda v: round(v, 3), r)) for r in src.matrix_world])
print("tgt obj matrix", [list(map(lambda v: round(v, 3), r)) for r in arm.matrix_world])
for b in ("waist", "spine_01", "head", "left_arm_01", "left_leg_01", "left_foot", "left_feeler_a"):
    if b in src.data.bones and b in arm.data.bones:
        ms = src.matrix_world @ src.data.bones[b].matrix_local
        mt = arm.matrix_world @ arm.data.bones[b].matrix_local
        print(f"{b:14s} head src {tuple(round(v, 3) for v in ms.translation)} tgt {tuple(round(v, 3) for v in mt.translation)}"
              f"  rot diff {ms.to_quaternion().rotation_difference(mt.to_quaternion()).angle * 57.3:.2f} deg")

if mode == "save":
    act = next(a for a in acts if "battlewait01_loop" in a.name)
    act.name = NAME
    act.use_fake_user = True
    for a in acts:
        if a is not act:
            bpy.data.actions.remove(a)
    for o in new_obj:
        bpy.data.objects.remove(o, do_unlink=True)
    for coll, before in ((bpy.data.meshes, before_mesh), (bpy.data.materials, before_mat),
                         (bpy.data.images, before_img), (bpy.data.armatures, before_arm)):
        for d in [d for d in coll if d not in before]:
            coll.remove(d)
    ad = arm.animation_data or arm.animation_data_create()
    ad.action = None
    print("kept", act.name, tuple(act.frame_range), "fcurves/groups",
          len(getattr(act, "fcurves", [])) if hasattr(act, "fcurves") else "layered")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT), copy=True)
    print("saved", OUT)
