"""Copy of MegaRaichuY_clip.blend with the clip's mouth damped. The game's battlewait holds the
mouth bones (lower_jaw_01 ~27 deg, the lower-lip _01 bones ~10-25 deg) pushed up past closed all
loop: the lower lip folds under the upper one and the hull draws stacked jagged lines under the
mouth (a 'beard'). Each mouth bone's keyed rotation is slerped from rest toward the clip's by F
(0 = rest, mouth open with the tongue showing; 1 = the clip). Locations untouched.
Run: blender_slot.py --timeout 300 -- -b MegaRaichuY/MegaRaichuY_clip.blend --python shut_mouth.py -- OUT.blend F [FL]
(FL: a separate factor for the lip bones, left_/right_*_jaw_* and teeth; default F)."""
import sys, bpy
from pathlib import Path
from mathutils import Quaternion
argv = sys.argv[sys.argv.index("--") + 1:]
out, F = argv[0], float(argv[1])
FL = float(argv[2]) if len(argv) > 2 else F   # lip bones (*_jaw_a..d): their own factor
LIP = lambda n: n.startswith(("left_", "right_"))
MOUTH = lambda n: ("jaw" in n or "teeth" in n) and not n.endswith("_end")


def fcurves(act):
    if getattr(act, "fcurves", None) and len(act.fcurves):
        return list(act.fcurves)
    return [fc for l in act.layers for s in l.strips for cb in s.channelbags for fc in cb.fcurves]


for act in bpy.data.actions:
    groups = {}
    for fc in fcurves(act):
        p = fc.data_path
        if p.startswith('pose.bones["') and p.endswith("rotation_quaternion") and MOUTH(p.split('"')[1]):
            groups.setdefault(p, {})[fc.array_index] = fc
    for p, fcs in groups.items():
        if len(fcs) != 4:
            print("SKIP", p, sorted(fcs)); continue
        n = len(fcs[0].keyframe_points)
        assert all(len(fc.keyframe_points) == n for fc in fcs.values())
        for i in range(n):
            q = Quaternion([fcs[j].keyframe_points[i].co[1] for j in range(4)])
            d = Quaternion().slerp(q.normalized(), FL if LIP(p.split('"')[1]) else F)
            for j in range(4):
                k = fcs[j].keyframe_points[i]
                k.co[1] = k.handle_left[1] = k.handle_right[1] = d[j]
        for fc in fcs.values():
            fc.update()
    print("DAMPED", act.name, len(groups), "bones: jaw", F, "lips", FL)
bpy.ops.wm.save_as_mainfile(filepath=str(Path(out).resolve()), copy=True)
print("saved", out)
