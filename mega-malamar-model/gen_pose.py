"""Write pose / motion for Mega Malamar into mega_malamar_front.json.

Run: /usr/local/bin/python3 mega-malamar-model/gen_pose.py [KEY=value ...]
Keeps existing pose_params (defaults only fill missing keys); KEY=value overrides; prints every change.
"""
import json, sys, os

CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mega_malamar_front.json")
c = json.load(open(CFG))
pp = c.setdefault("pose_params", {})

DEFAULTS = {
    "AZIMUTH": 72, "ELEVATION": 10, "FOV": 30,
    # rest pose (degrees)
    "HDT": 0.0,      # head tilt (nod, + = chin down)
    "SPL": 8.0,      # tentacle splay at the shoulder (outward)
    "HANG": -6.0,    # upper tentacle drawn back in under the wing (per joint 02..04)
    "C5": 14, "C6": 24, "C7": 30, "C8": 32, "C9": 34, "C10": 34, "C11": 30,  # loop curl per joint
    "FWD": 4.0,      # tentacle lower half swept slightly toward the camera
    "TL1": 0.0, "TL2": 0.0, "TL3": 0.0,  # tail side lean
    # motion
    "BOB": 0.045,    # body hover (world units)
    "DRIFT": 0.012,  # tiny side drift
    "HN": 1.2,       # head nod
    "WG": 3.0,       # wing (feeler_a) lift
    "BF": 4.0,       # back feeler
    "TS": 2.0,       # tail sway per joint
    "AS": 2.2,       # tentacle sway per joint (base)
    "AL": 0.32,      # phase lag per tentacle joint (rad)
    "FL": 2.0,       # tip flutter per joint (fast)
    "FB": 6.0,       # fin (feeler_b) flutter
}
for k, v in DEFAULTS.items():
    if k not in pp:
        pp[k] = v
        print(f"default {k} = {v}")
for arg in sys.argv[1:]:
    k, v = arg.split("=")
    old = pp.get(k)
    pp[k] = float(v)
    print(f"set {k}: {old} -> {pp[k]}")

Z = "A:0,-1,0"   # bend in the front plane (left: + = outward / toward +X)
Y = "A:1,0,0"    # bend toward / away from camera for the vertical chains
T = "2*pi*t"
pose = []
# ---- rest pose
pose.append(["head", "A:1,0,0", "HDT"])
for side, sg in (("left", 1), ("right", -1)):
    s = "" if sg > 0 else "-"
    pose.append([f"{side}_arm_01", Z, f"{s}SPL"])
    for j in (2, 3, 4):
        pose.append([f"{side}_arm_{j:02d}", Z, f"{s}HANG"])
    for j in range(5, 12):
        pose.append([f"{side}_arm_{j:02d}", Z, f"{s}C{j}"])
    pose.append([f"{side}_arm_06", Y, "-FWD"])
    pose.append([f"{side}_arm_08", Y, "-FWD"])
for j in (1, 2, 3):
    pose.append([f"tail_{j:02d}", Z, f"TL{j}"])

# ---- motion: one driver = the hover bob (1 cycle per loop). Everything else follows later.
pose.append(["waist", "LOCZ", f"BOB*sin({T})"])
pose.append(["waist", "LOCX", f"DRIFT*sin({T} - 1.2)"])
pose.append(["head", "A:1,0,0", f"HN*sin({T} - 0.6)"])
for side, sg in (("left", 1), ("right", -1)):
    s = "" if sg > 0 else "-"
    po = 0.0 if sg > 0 else 0.35          # the two sides a touch apart
    pose.append([f"{side}_feeler_a", Z, f"{s}WG*sin({T} - {0.9 + po:.2f})"])
    # tentacle chain: each joint bends a little, later and more toward the tip
    for j in range(1, 12):
        amp = f"AS*{0.5 + 0.08 * j:.2f}"
        pose.append([f"{side}_arm_{j:02d}", Z, f"{s}{amp}*sin({T} - {0.8 + po:.2f} - AL*{j})"])
        if j >= 4:
            pose.append([f"{side}_arm_{j:02d}", Y, f"{amp}*0.5*sin({T} - {1.6 + po:.2f} - AL*{j})"])
    # tip flutter on top, faster
    for j in (9, 10, 11):
        pose.append([f"{side}_arm_{j:02d}", Z, f"{s}FL*sin(2*{T} - {2.0 + po:.2f} - 0.6*{j - 9})"])
    pose.append([f"{side}_feeler_b", Z, f"{s}FB*sin(2*{T} - {3.0 + po:.2f})"])
    pose.append([f"{side}_feeler_c", Z, f"{s}FB*0.5*sin(2*{T} - {2.6 + po:.2f})"])
    pose.append([f"{side}_feeler_d", Z, "FB*0.3*sin(2*2*pi*t - 2.4)"])   # tail fin halves move as one (no open/close: they overlap)
pose.append(["back_feeler_01", "A:1,0,0", f"BF*0.5*sin({T} - 1.0)"])
pose.append(["back_feeler_02", "A:1,0,0", f"BF*sin({T} - 1.5)"])
for j in (1, 2, 3):
    pose.append([f"tail_{j:02d}", Z, f"TS*{0.6 + 0.3 * j:.1f}*sin({T} - {0.7 + 0.4 * j:.1f})"])
    pose.append([f"tail_{j:02d}", Y, f"TS*0.4*sin({T} - {1.0 + 0.4 * j:.1f})"])

old_n = len(c.get("pose", []))
c["pose"] = pose
c["motion"] = c.get("motion", {})
c["motion"]["frames"] = 120
c["motion"].pop("plant", None)   # floats: nothing touches the ground
json.dump(c, open(CFG, "w"), indent=2)
print(f"pose: {old_n} -> {len(pose)} entries")
