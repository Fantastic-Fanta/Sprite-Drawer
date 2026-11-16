"""Move the game idle from the animation pack onto the textured Mega Feraligatr .blend (a copy).

Run (from the repo root):
  /usr/local/bin/python3 pipeline/blender_slot.py --timeout 600 -- -b \
    mega-feraligatr-model/MegaFeraligatr/MegaFeraligatr.blend \
    --python mega-feraligatr-model/move_clip.py -- [inspect|save] [ACTION ...]

inspect: import the pack GLB, print each named idle's range and channels (scale and location ranges,
         loop seam), compare every shared bone's rest matrix (world space) and the armature object
         transforms with the model's own, then quit without saving.
save:    also keep only the named actions, delete everything else the import brought in, and save
         MegaFeraligatr/MegaFeraligatr_idle.blend (the original is untouched).
"""
import re
import sys
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
GLB = HERE / "pack/source/18916_autosave.glb"
OUT = HERE / "MegaFeraligatr/MegaFeraligatr_idle.blend"
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
mode = args[0] if args else "inspect"
NAMES = args[1:] or ["pm0160_51_00_00001_battlewait01_loop", "pm0160_51_00_10001_battlewait01_loop"]

arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
kinds = ("objects", "actions", "meshes", "materials", "images", "armatures", "collections", "textures")
before = {k: set(getattr(bpy.data, k)) for k in kinds}
bpy.ops.import_scene.gltf(filepath=str(GLB))
new = {k: [d for d in getattr(bpy.data, k) if d not in before[k]] for k in kinds}
src = next(o for o in new["objects"] if o.type == "ARMATURE")
print("imported objects", len(new["objects"]), "actions", len(new["actions"]), "scene fps", bpy.context.scene.render.fps)


def fcurves(a):
    if hasattr(a, "fcurves") and len(a.fcurves):
        return list(a.fcurves)
    out = []
    for layer in getattr(a, "layers", []):
        for strip in layer.strips:
            for bag in strip.channelbags:
                out += list(bag.fcurves)
    return out


keep = []
for name in NAMES:
    act = bpy.data.actions[name]
    keep.append(act)
    fcs = fcurves(act)
    s, e = act.frame_range
    keyed = sorted({re.search(r'pose\.bones\["(.+?)"\]', f.data_path).group(1)
                    for f in fcs if f.data_path.startswith("pose.bones")})
    other = sorted({f.data_path for f in fcs if not f.data_path.startswith("pose.bones")})
    print(f"{name}: range ({s:.3f}, {e:.3f}) fcurves {len(fcs)} bones keyed {len(keyed)} non-bone {other}")
    print("  keyed bones missing on target:", [b for b in keyed if b not in arm.data.bones])
    nkeys = sorted({len(f.keyframe_points) for f in fcs})
    print("  keys per curve", nkeys[:5], "...", nkeys[-1:], " interpolation", sorted({k.interpolation for f in fcs for k in f.keyframe_points}))
    worst = max(fcs, key=lambda f: abs(f.evaluate(s) - f.evaluate(e)))
    print(f"  seam worst |v(start)-v(end)| = {abs(worst.evaluate(s) - worst.evaluate(e)):.6f} on {worst.data_path}[{worst.array_index}]")
    steps = [s + (e - s) * i / 200 for i in range(201)]
    for kind in ("scale", "location"):
        lo, hi, who = 9e9, -9e9, ""
        for f in fcs:
            if f.data_path.endswith(kind):
                v = [f.evaluate(x) for x in steps]
                base = 1.0 if kind == "scale" else 0.0
                d = max(abs(x - base) for x in v)
                if d > max(abs(lo - base), abs(hi - base)):
                    who = f"{f.data_path}[{f.array_index}]"
                lo, hi = min(lo, min(v)), max(hi, max(v))
        print(f"  {kind}: min {lo:.4f} max {hi:.4f} (furthest from rest: {who})")
    for b in ("origin", "waist", "hips"):
        fl = [f for f in fcs if f.data_path == f'pose.bones["{b}"].location']
        if fl:
            print(f"  {b}.location at start", [round(f.evaluate(s), 4) for f in fl])

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
    worst_t = max(worst_t, (dt, b.name))
    worst_r = max(worst_r, (min(dr, 360 - dr), b.name))
print(f"shared bones {n}/{len(arm.data.bones)} (src {len(src.data.bones)}); worst head offset "
      f"{worst_t[0]:.6f} ({worst_t[1]}), worst rest rotation diff {worst_r[0]:.4f} deg ({worst_r[1]})")

if mode == "save":
    for a in new["actions"]:
        if a not in keep:
            bpy.data.actions.remove(a)
    for a in keep:
        a.use_fake_user = True
    for o in new["objects"]:
        bpy.data.objects.remove(o, do_unlink=True)
    for k in ("meshes", "materials", "images", "armatures", "collections", "textures"):
        coll = getattr(bpy.data, k)
        for d in new[k]:
            if d.name in coll:
                coll.remove(d)
    ad = arm.animation_data or arm.animation_data_create()
    ad.action = None
    print("kept", [(a.name, tuple(a.frame_range)) for a in keep], "actions now", [a.name for a in bpy.data.actions])
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT), copy=True)
    print("saved", OUT)
