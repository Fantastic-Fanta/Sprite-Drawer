"""Writes pose, motion, camera and style into the config. KEY=value overrides; prints every change.

Layout (redo, from the official Legends Z-A art, mirrored so the sprite faces left):
three Tatsugiri lie parallel on the platter, all facing the same way (model -Y), side by side across X
with a grass row between each pair. Nearest the camera (+X, camera on the model's left-front): Droopy
(pink, b); middle: Stretchy (yellow, a); far side: Curly (orange, c), the one posed differently: it
rears up from its rice ball, head curled forward, tail raised, wearing the roe.
"""
import json, sys
CFG = "mega-tatsugiri-original-color-model/mega_tatsugiri_original_color_front.json"
cfg = json.load(open(CFG))
P = dict(
    # placement (world units; LOC* are world axes)
    AX=-0.01, AY=0.05, AZ=0.0, BX=0.255, BY=0.02, BZ=0.0, CX=-0.235, CY=0.08, CZ=0.0, AL=0.0, BL=0.012, CL=0.0,
    # Curly's rear-up (degrees, + raises the head / tail)
    CS1=40, CS2=30, CS3=10, CH=-45, CT0=15, CT1=30, CT2=25, CT3=20, CT4=15, IK=1.0, RS=0.7, RD=0.06, CF=50,
    # camera
    AZIMUTH=55, ELEVATION=22, FOV=30,
    # motion: the plate's bob drives; fish wiggle a beat later, each out of phase; fins / tails trail
    BOB=0.006, ROLL=1.0, FL=1.0, GR=2.5, WIG=1.5, NOD=1.2, TS=2.5, FIN=3.0, FT=17,
)
for a in sys.argv[1:]:
    k, v = a.split("="); P[k] = float(v)

pp = cfg["pose_params"]
for k in list(pp):
    if k not in P:
        print(f"param {k}: {pp[k]} -> (removed)"); del pp[k]
for k, v in P.items():
    if pp.get(k) != v:
        print(f"param {k}: {pp.get(k)} -> {v}"); pp[k] = v


def setk(path, v):
    d = cfg
    for k in path[:-1]:
        d = d.setdefault(k, {})
    if d.get(path[-1]) != v:
        print(f"{'.'.join(path)}: {d.get(path[-1])} -> {v}"); d[path[-1]] = v


setk(("style", "height"), 200)
setk(("render", "hull", "cap_each_frame"), True)
setk(("camera", "target"), [0.0, 0.02, 0.17])
setk(("camera", "ortho_scale"), 1.25)
setk(("motion", "frames"), 96)

R = "-1,0,0"   # spine pitch axis: + raises the head


def w(lag, skew=0.0):   # loop wave lagging the driver by `lag` of a cycle
    return f"wave(t-{lag:.3f},{skew})"


# each fish's wiggle starts a beat after the plate's bob, the three a third of a cycle apart
PH = {"b": 0.12, "a": 0.12 + 1 / 3, "c": 0.12 + 2 / 3}
pose = []
# 1) side-to-side wiggle about world Z (before pitch bends / placement carry the bones):
#    a wave travelling head -> tail, growing toward the tail tip; fins paddle behind it
for f in ("a", "b", "c"):
    ph = PH[f]
    pose += [[f"head_{f}", "Z", f"-WIG*0.5*{w(ph)}"], [f"spine_{f}_03", "Z", f"WIG*0.3*{w(ph+0.04)}"],
             [f"spine_{f}_02", "Z", f"WIG*0.4*{w(ph+0.08)}"], [f"spine_{f}_01", "Z", f"WIG*0.4*{w(ph+0.12)}"]]
    for i, (lag, amp) in enumerate(((0.16, 0.4), (0.20, 0.7), (0.24, 1.0), (0.28, 1.3)), start=1):
        pose.append([f"tail_{f}_0{i}", "Z", f"TS*{amp}*{w(ph+lag)}"])
    for side, sg in (("left", 1), ("right", -1)):
        pose.append([f"{side}_arm_{f}_01", "Z", f"{sg}*(FT + FIN*{w(ph+0.18)})"])   # FT: fold toward the tail
        pose.append([f"{side}_arm_{f}_02", "Z", f"{sg}*FIN*0.6*{w(ph+0.24)}"])
# grass blades: trail the bob most, each blade its own phase, plus a quicker flutter
for side in ("left", "right"):
    for j, b in enumerate("acegi"):
        ph = 0.03 * j + (0.05 if side == "right" else 0)
        pose.append([f"{side}_feeler_{b}_02", "X", f"-GR*1.2*{w(0.30+ph)} + 0.6*sin(4*pi*(t-{ph:.3f}))"])
        pose.append([f"{side}_feeler_{b}_01", "X", f"-GR*{w(0.22+ph)}"])
# plate edges flex a beat behind the bob
pose += [["feeler_a_02", "A:0,-1,0", f"-FL*{w(0.15)}"], ["feeler_b_02", "A:0,1,0", f"-FL*{w(0.18)}"],
         ["feeler_a_01", "A:0,-1,0", f"-FL*0.4*{w(0.10)}"], ["feeler_b_01", "A:0,1,0", f"-FL*0.4*{w(0.12)}"]]
# Curly's roe: full size (the art shows a clear cluster), a soft jiggle after its head
# the two loose balls (feeler_m / _n) stand in a column above the pile; the art shows a compact pile
pose += [["feeler_m", "SCALE", "RS"], ["feeler_n", "SCALE", "RS"]]
pose += [["feeler_k", "SCALE", "IK"], ["feeler_k", "A:" + R, f"-2.0*{w(PH['c']+0.10)}"]]
# 2) pitch: the two lying fish breathe a small nod / tail lift; Curly rears up
for f in ("a", "b"):
    ph = PH[f]
    pose += [[f"head_{f}", "A:" + R, f"-NOD*{w(ph+0.06)}"], [f"tail_{f}_03", "A:1,0,0", f"-1.5*{w(ph+0.22)}"],
             [f"tail_{f}_01", "A:1,0,0", f"-1.0*{w(ph+0.14)}"]]
ph = PH["c"]
pose += [
    ["head_c", "A:" + R, f"CH - NOD*{w(ph+0.10)}"],
    ["spine_c_03", "A:" + R, f"CS3 - NOD*0.5*{w(ph+0.07)}"], ["spine_c_02", "A:" + R, f"CS2 - NOD*0.5*{w(ph+0.04)}"],
    ["spine_c_01", "A:" + R, f"CS1 - NOD*0.4*{w(ph)}"],
    ["tail_c_04", "A:1,0,0", f"CT4 - 2.0*{w(ph+0.28)}"], ["tail_c_03", "A:1,0,0", f"CT3 - 1.5*{w(ph+0.22)}"],
    ["tail_c_02", "A:1,0,0", f"CT2 - 1.0*{w(ph+0.16)}"], ["tail_c_01", "A:1,0,0", f"CT1 - 0.6*{w(ph+0.10)}"],
    ["hips_c", "A:1,0,0", "CT0"],
    # the rear-up carries Curly's fins down through the plate: tip them back up along the body
    ["left_arm_c_01", "A:" + R, "-CF"], ["right_arm_c_01", "A:" + R, "-CF"],
]
# sink the two loose roe balls into the pile (world LOC, after the head's pitch)
pose += [["feeler_m", "LOCZ", "-RD"], ["feeler_n", "LOCZ", "-RD"]]
# 3) placement: move the stacked forms apart (world LOC), all facing -Y
for f in ("a", "b", "c"):
    U = f.upper()
    pose += [[f"root_waist_{f}", "Z", f"{U}Z"], [f"root_waist_{f}", "LOCX", f"{U}X"],
             [f"root_waist_{f}", "LOCY", f"{U}Y"], [f"root_waist_{f}", "LOCZ", f"{U}L"]]
# 4) driver: the whole platter bobs (buoyant wave) and rocks a little
pose += [["waist", "Y", f"ROLL*{w(0.25)}"], ["waist", "LOCZ", f"BOB*{w(0.0, 0.12)}"]]
if cfg["pose"] != pose:
    print(f"pose: {len(cfg['pose'])} -> {len(pose)} entries"); cfg["pose"] = pose
note = open("mega-tatsugiri-original-color-model/motion.note").read().strip()
setk(("motion", "note"), note)
json.dump(cfg, open(CFG, "w"), indent=2)
