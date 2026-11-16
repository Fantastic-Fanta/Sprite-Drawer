"""import the pack glb, keep the idle action, check it lands on the model's rig with no offset or
scale (posed bones vs the pack's own armature), delete the rest, save *_anim.blend"""
import bpy, sys
args = sys.argv[sys.argv.index("--")+1:]
glb, keep, out = args
before = set(bpy.data.objects); acts_before = set(bpy.data.actions)
A = [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
bpy.ops.import_scene.gltf(filepath=glb)
new = [o for o in bpy.data.objects if o not in before]
B = [o for o in new if o.type == "ARMATURE"][0]
act = bpy.data.actions[keep]
for o in (A, B):
    ad = o.animation_data or o.animation_data_create()
    ad.action = act
    if act.slots: ad.action_slot = act.slots[0]
sc = bpy.context.scene
worst_p = worst_r = 0.0
for f in (1, 12, 24, 33, 47, 60, 64):
    sc.frame_set(f); bpy.context.view_layer.update()
    for pb in A.pose.bones:
        if pb.name not in B.pose.bones: continue
        ma = A.matrix_world @ pb.matrix; mb = B.matrix_world @ B.pose.bones[pb.name].matrix
        worst_p = max(worst_p, (ma.translation - mb.translation).length)
        worst_r = max(worst_r, max(abs(x - y) for ca, cb in zip(ma.to_3x3(), mb.to_3x3()) for x, y in zip(ca, cb)))
    if f in (1, 33):
        for n in ("waist", "head", "left_hand", "feeler_a", "horn_a_05", "feeler_b", "left_foot"):
            ma = A.matrix_world @ A.pose.bones[n].matrix; mb = B.matrix_world @ B.pose.bones[n].matrix
            print(f"POSE f{f} {n:9s} model {tuple(round(v,3) for v in ma.translation)} pack {tuple(round(v,3) for v in mb.translation)} scale {tuple(round(v,3) for v in ma.to_scale())}")
print(f"WORST over all bones/frames: pos {worst_p:.6f}  matrix elem {worst_r:.6f}")
# keep only the idle on the model's armature
A.animation_data.action = None
for o in new:
    bpy.data.objects.remove(o, do_unlink=True)
for a in list(bpy.data.actions):
    if a not in acts_before and a.name != keep:
        bpy.data.actions.remove(a)
act.use_fake_user = True
for blk in (bpy.data.meshes, bpy.data.armatures, bpy.data.materials, bpy.data.images):
    for d in list(blk):
        if d.users == 0: blk.remove(d)
print("ACTIONS kept:", [a.name for a in bpy.data.actions], "objects:", len(bpy.data.objects))
bpy.ops.wm.save_as_mainfile(filepath=out, copy=True)
print("SAVED", out)
