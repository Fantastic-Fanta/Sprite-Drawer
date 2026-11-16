"""Ease out the one-frame jumps baked into the game idle (run after pipeline/move_clip.py).

The pack's battlewait01_loop has single-frame rotation steps on three spike chains
(left_horn_b_04 f89, right_horn_b_04 f78/f105, horn_a_04 f55/f96/f181/f232): a 5-9 deg pop of the
spike between two 60 fps frames, which reads as a 4-7 sprite px twitch at the spike tip.
Each step is spread over 2*W frames with a smoothstep (all four quaternion components of the bone,
same window), everything else is untouched. Saves MegaDarkrai_idle.blend in place (a copy; the
original MegaDarkrai.blend is untouched).

Run: /usr/local/bin/python3 pipeline/blender_slot.py --timeout 600 -- -b \
       mega-darkrai-model/MegaDarkrai/MegaDarkrai_idle.blend --python mega-darkrai-model/smooth_steps.py
"""
import bpy

NAME, W = "pm0491_51_00_20001_battlewait01_loop", 4
act = bpy.data.actions[NAME]
F = [c for l in act.layers for s in l.strips for b in s.channelbags for c in b.fcurves]
byb = {}
for f in F:
    if f.data_path.startswith("pose.bones") and f.data_path.endswith("rotation_quaternion"):
        byb.setdefault(f.data_path.split('"')[1], []).append(f)


def steps(vals):
    d = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
    out = set()
    for k in range(len(d)):
        nb = sorted(abs(d[(k + j) % len(d)]) for j in (-3, -2, -1, 1, 2, 3))
        if abs(d[k]) > 0.02 and abs(d[k]) > 5 * max(nb[3], 1e-4):
            out.add(k)
    return out


ease = lambda x: 0.0 if x <= 0 else 1.0 if x >= 1 else x * x * (3 - 2 * x)
for bone, fcs in byb.items():
    vals = {f.array_index: [f.evaluate(x) for x in range(1, 242)] for f in fcs}
    ks = sorted(set().union(*(steps(v) for v in vals.values())))
    if not ks:
        continue
    for f in fcs:
        v = vals[f.array_index]
        new = v[:]
        for k in ks:                       # step between index k and k+1
            S = v[k + 1] - v[k]
            for i in range(len(v)):
                h = 1.0 if i > k else 0.0
                new[i] += S * (ease((i - (k - W + 0.5)) / (2 * W)) - h)
        assert len(f.keyframe_points) == 241
        for kp, x in zip(f.keyframe_points, new):
            kp.co[1] = x; kp.handle_left[1] = x; kp.handle_right[1] = x
        f.update()
    print(f"eased {bone}: steps after frames {[k + 1 for k in ks]}")
bpy.ops.wm.save_mainfile()
print("saved", bpy.data.filepath)
