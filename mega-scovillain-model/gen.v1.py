"""Mega Scovillain pose + idle generator. Writes pose / motion into mega_scovillain_front.json.
Run: python3 gen.py [KEY=value ...]   (overrides P below; prints every change to pose/motion)

The bind pose has both heads floating in front of the body, apart from their necks (the game
places them with its animations). The pose assembles them: each neck chain is stretched by LOC
(pure translations, so positions add up) to a target collar point, and each head is moved onto
its collar. head_a (green) is on left_neck (+X), head_b (red) on right_neck (-X)."""
import json, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "mega_scovillain_front.json")

P = dict(
    AZ=145, EL=12,
    RARM=-30, LARM=0, TAILUP=5,
    # red head on top: collar target and head bone offset from it
    RCX=-0.03, RCY=-0.10, RCZ=1.02, RHX=0.0, RHY=-0.03, RHZ=0.10, RNOD=0, RTURN=-25,
    # green head out to its left side
    GCX=0.60, GCY=-0.40, GCZ=0.76, GHX=-0.02, GHY=0.06, GHZ=0.04, GTURN=-60, GNOD=10, GROLL=0,
    GBULGE=0.06,     # green neck arches up in the middle
    RTONGUE=0.2,     # red head tongue scale (pulled into the mouth)
    GZIG=25,         # green tongue zigzag bend per joint
    GJAW=25, RJAW=6,
    # motion
    BREATH=0.015,    # body dip (model units, LOCZ on waist; feet planted)
    SPINE=0.8,       # chest bend with the breath (deg)
    NECK=0.7,        # neck sway per joint (deg)
    NOD=1.6,         # head nods (deg)
    LOOK=1.5,        # green head's slow look about (deg)
    JAWA=2.0,
    TONGUE=4.0,      # green tongue flutter per joint (deg)
    STREAK=2.0,      # red chest streak sway (deg)
    TAIL=1.0,        # tail sway per joint (deg)
    ARM=1.5, CLOTH=2.5,
    LAG=0.05,
)
for a in sys.argv[1:]:
    k, v = a.split("=")
    P[k] = float(v)

REST = {  # bind heads (RIG.md)
    "left_neck": [(0.01, 0.02, 0.69), (0.03, 0.01, 0.80), (0.07, -0.02, 0.88), (0.11, -0.06, 0.94), (0.17, -0.11, 0.97)],
    "right_neck": [(-0.01, 0.02, 0.69), (-0.03, 0.01, 0.80), (-0.07, -0.02, 0.88), (-0.11, -0.06, 0.94), (-0.17, -0.11, 0.97)],
    "head_a": (0.00, -0.56, 0.86), "head_b": (0.00, -0.56, 0.23),
}


import math


def lat(deg):
    """a head's own lateral axis once turned deg about Z (the bind lateral is world X)"""
    g = math.radians(deg)
    return f"A:{math.cos(g):.3f},{math.sin(g):.3f},0"


def ph(lag):
    return f"sin(2*pi*(t-{lag:.3f}))"


pose = []


def f(v):
    return f"{v:.4f}"


def assemble(side, head, collar, hoff, bulge):
    rest = REST[side]
    base = rest[0]
    cum = [0.0, 0.0, 0.0]
    for i in range(1, 5):
        fr = i / 4
        want = [base[k] + (collar[k] - base[k]) * fr for k in range(3)]
        want[2] += bulge * 4 * fr * (1 - fr)
        tot = [want[k] - rest[i][k] for k in range(3)]
        d = [tot[k] - cum[k] for k in range(3)]
        for k, ax in enumerate("XYZ"):
            if abs(d[k]) > 1e-4:
                pose.append([f"{side}_0{i + 1}", f"LOC{ax}", f(d[k])])
        cum = tot
    hw = [collar[k] + hoff[k] for k in range(3)]
    for k, ax in enumerate("XYZ"):
        d = hw[k] - (REST[head][k] + cum[k])
        if abs(d) > 1e-4:
            pose.append([head, f"LOC{ax}", f(d)])


assemble("right_neck", "head_b", (P["RCX"], P["RCY"], P["RCZ"]), (P["RHX"], P["RHY"], P["RHZ"]), 0.0)
assemble("left_neck", "head_a", (P["GCX"], P["GCY"], P["GCZ"]), (P["GHX"], P["GHY"], P["GHZ"]), P["GBULGE"])
# head facing (about each head bone, at the back of the head)
if P["GTURN"]: pose.append(["head_a", "Z", f"{P['GTURN']}"])
if P["GNOD"]: pose.append(["head_a", lat(P['GTURN']), f"{P['GNOD']}"])
if P["GROLL"]: pose.append(["head_a", "Y", f"{P['GROLL']}"])
if P["RTURN"]: pose.append(["head_b", "Z", f"{P['RTURN']}"])
if P["RNOD"]: pose.append(["head_b", lat(P['RTURN']), f"{P['RNOD']}"])
lat_a, lat_b = lat(P["GTURN"]), lat(P["RTURN"])
# mouths and tongues
pose.append(["jaw_a_01", lat_a, f"{P['GJAW']}"])
pose.append(["jaw_b_01", lat_b, f"{P['RJAW']}"])
pose.append(["tongue_b_01", "SCALE", f"{P['RTONGUE']}"])
for i in range(1, 7):
    sgn = 1 if i % 2 else -1
    amt = P["GZIG"] * (1.6 if i == 1 else 1.0) * (sgn if i > 1 else 1)
    pose.append([f"tongue_a_0{i}", lat_a, f"{amt:.1f}"])

# arms and tail (rest pose)
if P["RARM"]: pose.append(["right_arm_01", "A:0.01,-1.00,0.01", f"{P['RARM']}"])
if P["LARM"]: pose.append(["left_arm_01", "A:-0.01,-1.00,0.01", f"{P['LARM']}"])
for i in range(3, 7):
    pose.append([f"tail_0{i}", "A:1,0,0", f"{P['TAILUP'] * (i - 2) / 2.5:.2f}"])

# ---------------- motion: one driver (a slow breath: the body dips and the chest swells),
# everything else follows a beat later, light and far-out parts later and more
import math
B = P["BREATH"]
pose.append(["waist", "LOCZ", f"{-B:.4f}*{ph(0.0)}"])
pose.append(["spine_02", "A:-1,0,0", f"{P['SPINE']:.2f}*{ph(0.05)}"])
# necks: a sway that climbs the chain; the green neck is longer and lags more
for side, sx, extra in (("right_neck", -1, 0.0), ("left_neck", 1, 0.05)):
    lat = f"A:-0.64,{-0.77 * sx:.2f},0"          # each neck's own y axis (mirrored)
    for i in range(2, 6):
        pose.append([f"{side}_0{i}", lat, f"{P['NECK'] * (0.6 + 0.2 * i):.2f}*{ph(0.08 + extra + P['LAG'] * i)}"])
# heads: nods a beat after the neck; the green head also looks about slowly
pose.append(["head_b", lat_b, f"{P['NOD']:.2f}*{ph(0.30)}"])
pose.append(["head_a", lat_a, f"{P['NOD'] * 1.2:.2f}*{ph(0.40)}"])
pose.append(["head_a", "Z", f"{P['LOOK']:.2f}*{ph(0.55)}"])
pose.append(["jaw_a_01", lat_a, f"{P['JAWA']:.2f}*{ph(0.45)}"])
pose.append(["jaw_b_01", lat_b, f"{P['JAWA'] * 0.6:.2f}*{ph(0.35)}"])
for i in range(1, 7):
    pose.append([f"tongue_a_0{i}", lat_a,
                 f"{P['TONGUE'] * (0.5 + 0.15 * i):.2f}*{ph(0.45 + 0.04 * i)} + {P['TONGUE'] * 0.3:.2f}*sin(4*pi*(t-{0.2 + 0.03 * i:.2f}))"])
# red streak down the chest: hangs, swings a beat after the chest
for b, k, lag in (("cloth_a_01", 0.6, 0.15), ("cloth_a_02", 1.0, 0.22), ("feeler_a_01", 0.8, 0.18), ("feeler_a_02", 1.2, 0.26)):
    pose.append([b, "A:1,0,0", f"{P['STREAK'] * k:.2f}*{ph(lag)}"])
# tail: slow side sway, the tip lagging most; feelers on it trail
for i in range(1, 7):
    pose.append([f"tail_0{i}", "A:0,0,1", f"{P['TAIL'] * (0.4 + 0.2 * i):.2f}*{ph(0.10 + P['LAG'] * i)}"])
for b, lag in (("feeler_b", 0.35), ("feeler_c", 0.40), ("feeler_d", 0.45)):
    pose.append([b, "A:1,0,0", f"{P['CLOTH'] * 0.3:.2f}*{ph(lag)}"])
# arms drift with the breath; hands trail
for side, sx in (("left", 1), ("right", -1)):
    pose.append([f"{side}_arm_01", f"A:{0.01 * sx:.2f},-1.00,0.01", f"{P['ARM'] * sx:.2f}*{ph(0.12)}"])
    pose.append([f"{side}_hand_sub", f"A:{0.01 * sx:.2f},-1.00,0.01", f"{P['ARM'] * 1.5 * sx:.2f}*{ph(0.22)}"])
    # black cloth flaps and leg feelers: light, lag most, small faster flutter
    for b, lag in ((f"{side}_cloth_a", 0.25), (f"{side}_cloth_b", 0.28), (f"{side}_cloth_c_01", 0.20),
                   (f"{side}_cloth_c_02", 0.26), (f"{side}_cloth_c_03", 0.32), (f"{side}_feeler_a", 0.3), (f"{side}_feeler_b", 0.34)):
        pose.append([b, "A:1,0,0", f"{P['CLOTH']:.2f}*{ph(lag)} + {P['CLOTH'] * 0.25:.2f}*sin(4*pi*(t-{lag:.2f}))"])

c = json.load(open(CFG))
c["motion"]["plant"] = ["left_foot", "right_foot"]
c["pose_params"].update(AZIMUTH=P["AZ"], ELEVATION=P["EL"])
old = {(p[0], p[1]): p[2] for p in c.get("pose", [])}
new = {(p[0], p[1]): p[2] for p in pose}
for k in sorted(set(old) | set(new)):
    if old.get(k) != new.get(k):
        print(f"  {k}: {old.get(k)} -> {new.get(k)}")
c["pose"] = pose
json.dump(c, open(CFG, "w"), indent=2)
print("params:", P)
