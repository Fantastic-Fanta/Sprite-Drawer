"""Move a game idle from the animation pack onto the textured sprite body (no glow shell).

Run (from the repo root):
  /usr/local/bin/python3 pipeline/blender_slot.py --timeout 900 -- -b \
    mega-raichu-x-model/MegaRaichuX/MegaRaichuX_sprite.blend \
    --python mega-raichu-x-model/move_clip.py -- MODE [OUT.blend] [KEEP ...]

inspect:      import the FBX, list its actions, compare rest matrices and the posed bone
              positions (source armature vs. our armature playing the same action), quit.
save OUT K..: keep the actions whose names contain each K (renamed to their plain names),
              delete everything else the import brought in, save a copy at OUT.
"""
import sys
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
FBX = HERE / "pack/source/inner/source/Mega Raichu X.fbx"
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else ["inspect"]
mode = argv[0]

scene = bpy.context.scene
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
before = {k: set(getattr(bpy.data, k)) for k in
          ("objects", "actions", "meshes", "materials", "images", "armatures", "collections", "textures")}
fps_before = (scene.render.fps, scene.render.fps_base)
bpy.ops.import_scene.fbx(filepath=str(FBX), use_anim=True)
print("scene fps before", fps_before, "after", (scene.render.fps, scene.render.fps_base))
new_obj = [o for o in bpy.data.objects if o not in before["objects"]]
src = next(o for o in new_obj if o.type == "ARMATURE")
acts = [a for a in bpy.data.actions if a not in before["actions"]]
print("imported actions:", len(acts))
for a in acts:
    if "wait" in a.name:
        print(f"  {a.name}  range={tuple(a.frame_range)}")
print("src bones", len(src.data.bones), "tgt bones", len(arm.data.bones),
      "missing in tgt", [b.name for b in src.data.bones if b.name not in arm.data.bones][:10])
r3 = lambda v: tuple(round(x, 3) for x in v)
print("src obj", r3(src.matrix_world.translation), r3(src.matrix_world.to_scale()), "tgt obj",
      r3(arm.matrix_world.translation), r3(arm.matrix_world.to_scale()))
BONES = ("origin", "waist", "head", "left_hand", "left_foot", "left_tail_04", "right_ear_02")
for b in BONES:
    ms = src.matrix_world @ src.data.bones[b].matrix_local
    mt = arm.matrix_world @ arm.data.bones[b].matrix_local
    print(f"rest {b:14s} src {r3(ms.translation)} tgt {r3(mt.translation)}"
          f"  rot diff {ms.to_quaternion().rotation_difference(mt.to_quaternion()).angle * 57.3:.2f} deg")

waits = [a for a in acts if "battlewait" in a.name]


def play(obj, act, f):
    ad = obj.animation_data or obj.animation_data_create()
    ad.action = act
    if getattr(act, "slots", None):
        ad.action_slot = act.slots[0]
    scene.frame_set(int(f), subframe=f - int(f))


if mode == "inspect":
    for act in waits:
        s, e = act.frame_range
        worst = 0.0
        for f in (s, (s + e) / 2, s + (e - s) * 0.3):
            play(src, act, f)
            play(arm, act, f)
            bpy.context.view_layer.update()
            for b in BONES:
                ps = (src.matrix_world @ src.pose.bones[b].matrix).translation
                pt = (arm.matrix_world @ arm.pose.bones[b].matrix).translation
                worst = max(worst, (ps - pt).length)
        print(f"posed {act.name}: worst bone gap src vs tgt {worst:.4f} (units; model is ~1.9 tall)")
    sys.exit(0)

out, keys = argv[1], argv[2:]
keep = []
for k in keys:
    act = next(a for a in waits if k in a.name)
    act.name = next(n for n in [act.name.split("|")[-1]])
    act.use_fake_user = True
    keep.append(act)
    print("keep", act.name, tuple(act.frame_range))
for a in acts:
    if a not in keep:
        bpy.data.actions.remove(a)
for o in new_obj:
    bpy.data.objects.remove(o, do_unlink=True)
for k, b in before.items():
    coll = getattr(bpy.data, k)
    for d in [d for d in coll if d not in b]:
        if k != "actions":
            coll.remove(d)
ad = arm.animation_data or arm.animation_data_create()
ad.action = None
scene.render.fps, scene.render.fps_base = fps_before
bpy.ops.wm.save_as_mainfile(filepath=str(Path(out).resolve()), copy=True)
print("saved", out, "actions", [a.name for a in bpy.data.actions])
