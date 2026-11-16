"""Move the game idle from the animation pack (FBX) onto the textured model, saved as a copy.

Run (from the repo root):
  /usr/local/bin/python3 pipeline/blender_slot.py --timeout 900 -- -b \
    mega-eelektross-model/MegaEelektross/MegaEelektross.blend \
    --python mega-eelektross-model/move_clip.py -- inspect
  ... -- save pm0604_51_00_20001_battlewait01_loop

inspect: import the pack, list the battlewait actions, compare rest bones (world) and posed bones
         (model armature playing the action vs the pack's own armature) with no offset or scale.
save:    the same check for ACTION_NAME, then keep only that action, delete everything the import
         brought in, and save MegaEelektross/MegaEelektross_anim.blend (the original is untouched).
"""
import sys
from pathlib import Path
import bpy

HERE = Path(__file__).resolve().parent
FBX = HERE / "pack/source/Mega Eelektross.fbx"
OUT = HERE / "MegaEelektross/MegaEelektross_anim.blend"
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else ["inspect"]
mode = args[0]

arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
before = {k: set(getattr(bpy.data, k)) for k in ("objects", "actions", "meshes", "materials", "images", "armatures")}
bpy.ops.import_scene.fbx(filepath=str(FBX))
new_obj = [o for o in bpy.data.objects if o not in before["objects"]]
src = next(o for o in new_obj if o.type == "ARMATURE")
acts = [a for a in bpy.data.actions if a not in before["actions"]]
print("imported actions:", len(acts), "scene fps", bpy.context.scene.render.fps)
for a in acts:
    if "wait" in a.name:
        print(f"  ACT {a.name}  range={tuple(a.frame_range)}")
print("src bones", len(src.data.bones), "tgt bones", len(arm.data.bones),
      "missing in src:", [b.name for b in arm.data.bones if b.name not in src.data.bones][:10])
print("src obj", src.name, [[round(v, 3) for v in r] for r in src.matrix_world])
print("tgt obj", arm.name, [[round(v, 3) for v in r] for r in arm.matrix_world])
wp = wr = 0.0
for b in arm.data.bones:
    if b.name not in src.data.bones:
        continue
    ms = src.matrix_world @ src.data.bones[b.name].matrix_local
    mt = arm.matrix_world @ b.matrix_local
    wp = max(wp, (ms.translation - mt.translation).length)
    a = ms.to_quaternion().rotation_difference(mt.to_quaternion()).angle * 57.2958
    wr = max(wr, min(a, 360 - a))     # q and -q are the same rotation
print(f"REST worst head offset {wp:.6f}  worst rot diff {wr:.4f} deg")


def posed_check(act, frames):
    for o in (arm, src):
        ad = o.animation_data or o.animation_data_create()
        ad.action = act
        if act.slots:
            ad.action_slot = act.slots[0]
    sc = bpy.context.scene
    wp = ws = 0.0
    for f in frames:
        sc.frame_set(f)
        bpy.context.view_layer.update()
        for pb in arm.pose.bones:
            if pb.name not in src.pose.bones:
                continue
            ma = arm.matrix_world @ pb.matrix
            mb = src.matrix_world @ src.pose.bones[pb.name].matrix
            wp = max(wp, (ma.translation - mb.translation).length)
            ws = max(ws, max(abs(x - y) for x, y in zip(ma.to_scale(), mb.to_scale())))
        for n in ("waist", "head", "tail_08", "left_feeler_b_10", "right_feeler_b_10"):
            if n in arm.pose.bones:
                ma = arm.matrix_world @ arm.pose.bones[n].matrix
                print(f"  f{f} {n:18s} {tuple(round(v, 3) for v in ma.translation)} scale {tuple(round(v, 3) for v in ma.to_scale())}")
    print(f"POSED {act.name}: worst pos {wp:.6f}  worst scale {ws:.6f}")


if mode == "inspect":
    for a in acts:
        if "battlewait01_loop" in a.name:
            s, e = a.frame_range
            posed_check(a, [int(s), int((s + e) / 2), int(e)])
elif mode == "save":
    act = next(a for a in acts if a.name.endswith(args[1]))
    s, e = act.frame_range
    posed_check(act, [int(s + (e - s) * k / 6) for k in range(7)])
    act.name = args[1]          # plain name, as motion.clip refers to it
    act.use_fake_user = True
    arm.animation_data.action = None
    for a in acts:
        if a is not act:
            bpy.data.actions.remove(a)
    for o in new_obj:
        bpy.data.objects.remove(o, do_unlink=True)
    for k in ("meshes", "materials", "images", "armatures"):
        coll = getattr(bpy.data, k)
        for d in [d for d in coll if d not in before[k]]:
            coll.remove(d)
    print("ACTIONS kept:", [a.name for a in bpy.data.actions], "objects:", len(bpy.data.objects))
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT), copy=True)
    print("SAVED", OUT)
