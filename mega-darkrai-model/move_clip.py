"""Move the game idle from the animation pack onto the textured MegaDarkrai .blend (a copy).

Run (from the repo root):
  /usr/local/bin/python3 pipeline/blender_slot.py --timeout 600 -- -b \
    mega-darkrai-model/MegaDarkrai/MegaDarkrai.blend \
    --python mega-darkrai-model/move_clip.py -- [inspect|save]

inspect: import the pack FBX (same importer settings as pipeline/import_fbx.py), print the idle's
         range and channels, and compare every shared bone's rest matrix (world space) and the
         armature object transforms with the model's own, then quit without saving.
save:    also keep only the battlewait01_loop action (plain name below), delete everything else the
         import brought in, and save MegaDarkrai/MegaDarkrai_idle.blend (the original is untouched).
"""
import re
import sys
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
FBX = HERE / "pack/source/MegaDarkrai.fbx"
OUT = HERE / "MegaDarkrai/MegaDarkrai_idle.blend"
NAME = "pm0491_51_00_20001_battlewait01_loop"
mode = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else "inspect"

arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
before = {k: set(getattr(bpy.data, k)) for k in
          ("objects", "actions", "meshes", "materials", "images", "armatures", "collections", "textures")}
bpy.ops.import_scene.fbx(filepath=str(FBX))
new = {k: [d for d in getattr(bpy.data, k) if d not in before[k]] for k in before}
src = next(o for o in new["objects"] if o.type == "ARMATURE")
acts = new["actions"]
print("imported objects", len(new["objects"]), "actions", len(acts), "scene fps", bpy.context.scene.render.fps)
for a in acts:
    if "battlewait" in a.name:
        print(f"  {a.name}  range={tuple(a.frame_range)}")
idle = [a for a in acts if a.name.endswith(NAME) or NAME in a.name]
print("idle candidates", [a.name for a in idle])
act = idle[0]


def fcurves(a):
    if hasattr(a, "fcurves") and len(a.fcurves):
        return list(a.fcurves)
    out = []
    for layer in getattr(a, "layers", []):
        for strip in layer.strips:
            for bag in strip.channelbags:
                out += list(bag.fcurves)
    return out


fcs = fcurves(act)
bones_keyed = sorted({re.search(r'pose\.bones\["(.+?)"\]', f.data_path).group(1)
                      for f in fcs if f.data_path.startswith("pose.bones")})
other = sorted({f.data_path for f in fcs if not f.data_path.startswith("pose.bones")})
print("fcurves", len(fcs), "bones keyed", len(bones_keyed), "non-bone paths", other)
missing = [b for b in bones_keyed if b not in arm.data.bones]
print("keyed bones missing on target:", missing)
kinds = sorted({f.data_path.split(".")[-1] for f in fcs})
print("channel kinds", kinds)
# loop seam: first vs last key value per curve
s, e = act.frame_range
worst = max(fcs, key=lambda f: abs(f.evaluate(s) - f.evaluate(e)))
print(f"seam worst |v(start)-v(end)| = {abs(worst.evaluate(s) - worst.evaluate(e)):.5f} on {worst.data_path}[{worst.array_index}]")
for f in fcs:
    if not f.data_path.startswith("pose.bones"):
        vals = [f.evaluate(x) for x in range(int(s), int(e) + 1)]
        print(f"  object channel {f.data_path}[{f.array_index}] min {min(vals):.5f} max {max(vals):.5f}")
# rig match
print("src obj matrix", [[round(v, 4) for v in r] for r in src.matrix_world])
print("tgt obj matrix", [[round(v, 4) for v in r] for r in arm.matrix_world])
worst_t, worst_r, n = (0, ""), (0, ""), 0
for b in arm.data.bones:
    if b.name not in src.data.bones:
        continue
    n += 1
    ms = src.matrix_world @ src.data.bones[b.name].matrix_local
    mt = arm.matrix_world @ b.matrix_local
    dt = (ms.translation - mt.translation).length
    dr = ms.to_quaternion().rotation_difference(mt.to_quaternion()).angle * 57.2958
    dr = min(dr, 360 - dr)                      # q and -q are the same rotation
    worst_t = max(worst_t, (dt, b.name))
    worst_r = max(worst_r, (dr, b.name))
print(f"shared bones {n}/{len(arm.data.bones)} (src {len(src.data.bones)}); worst head offset "
      f"{worst_t[0]:.5f} ({worst_t[1]}), worst rest rotation diff {worst_r[0]:.3f} deg ({worst_r[1]})")

if mode == "save":
    act.name = NAME
    act.use_fake_user = True
    for a in acts:
        if a is not act:
            bpy.data.actions.remove(a)
    for o in new["objects"]:
        bpy.data.objects.remove(o, do_unlink=True)
    for k in ("meshes", "materials", "images", "armatures", "collections", "textures"):
        coll = getattr(bpy.data, k)
        for d in new[k]:
            if d.name in coll:
                coll.remove(d)
    ad = arm.animation_data or arm.animation_data_create()
    ad.action = None
    bpy.ops.outliner.orphans_purge(do_recursive=True) if False else None
    print("kept", act.name, tuple(act.frame_range), "actions now", [a.name for a in bpy.data.actions])
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT), copy=True)
    print("saved", OUT)
