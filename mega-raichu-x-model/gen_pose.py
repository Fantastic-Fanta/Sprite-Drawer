"""Write pose / pose_params / motion into mega_raichu_x_front.json.

Run: /usr/local/bin/python3 mega-raichu-x-model/gen_pose.py [NAME=value ...]
Params already in the config keep their values (only new names get the defaults below);
NAME=value changes one. Prints before -> after for every change.
Entries are sorted deepest bone first, so each bend uses the bone's own rest axes (RIG.md)
before its parents move it. Axes: RIG.md world axes; the right side's axes there are already
the mirror of the left's, so both sides take the same value.
"""
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = HERE / "mega_raichu_x_front.json"

DEFAULTS = {
    "AZIMUTH": 70, "ELEVATION": 8, "FOV": 30,
    # rest pose (deg) -- HOME render / official art: floating, arms out, right knee up,
    # the two bolt tails pointing down and apart like an X's lower half, broad side to the viewer
    "TAIL_SPLAY": 26, "TAIL_BACK": 14, "TAIL_FLIP": 1, "TAIL_LEAN": 0, "TAIL_SEP": 0,
    "ARM_UP": 12, "ARM_FWD": 8, "ELB": -10,
    "RTHIGH": -95, "RKNEE": 105, "RFOOT": -30, "RABD": 18,
    "LTHIGH": -15, "LKNEE": 25, "LFOOT": 45,
    "NOD": 4, "TILT": 5, "LEAN": 0,
    "EAR_OUT": 0,
    # motion: one hover cycle per loop
    "BOB": 0.022, "BR": 1.5, "HD": 1.5, "EAR": 2.5, "WH": 6.0,
    "ARM": 3.0, "LEG": 4.0, "TAILA": 1.6, "TAILF": 0.8,
}

depth = {}
for line in (HERE / "RIG.md").read_text().splitlines():
    m = re.match(r"^( *)(\w+)  head=", line)
    if m:
        depth[m.group(2)] = len(m.group(1)) // 2

cli = dict(a.split("=", 1) for a in sys.argv[1:])
cfg = json.loads(CFG.read_text())
old = cfg.get("pose_params", {})
P = {}
for k, v in DEFAULTS.items():
    P[k] = float(cli[k]) if k in cli else old.get(k, v)
for k, v in old.items():
    P.setdefault(k, v)

NOTE = ("Light electric mouse floating on the magnetic field between its two bolt tails (official art: "
        "airborne, right knee up, arms spread, tails in an X below). One slow hover bob per loop drives "
        "everything: the body rises and sinks ~2 px; spine and head nod a beat later; the spread arms rise "
        "as the body sinks, like balancing; the long ears flop after the head and the curly whiskers flutter "
        "last; the dangling left leg and the tucked right leg trail the bob; the big flat bolt tails "
        "scissor open and closed a beat behind, tips most, with a small faster flutter at the ends.")

pose = []


def A(bone, axis, expr):
    pose.append([bone, "A:" + ",".join(f"{c:g}" for c in axis), expr])


def B(lag):
    """the hover driver, `lag` of a loop later (body up at B = 1)"""
    return f"B(t-{lag:g})"


# --- vector helpers for the tail orientation (fixed rest pose, computed here) ----------------
def norm(v):
    n = math.sqrt(sum(c * c for c in v))
    return [c / n for c in v]


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def frame(d, n):
    d = norm(d)
    n = norm([n[i] - dot(n, d) * d[i] for i in range(3)])
    return [d, n, cross(d, n)]


def rot_to_axis_angle(F0, F1):
    # R = sum_i F1[i] (x) F0[i]
    R = [[sum(F1[k][i] * F0[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    ang = math.acos(max(-1, min(1, (R[0][0] + R[1][1] + R[2][2] - 1) / 2)))
    ax = [R[2][1] - R[1][2], R[0][2] - R[2][0], R[1][0] - R[0][1]]
    return norm(ax), math.degrees(ang)


sp, bk = math.radians(P["TAIL_SPLAY"]), math.radians(P["TAIL_BACK"])
d0 = [0.0, 0.93, 0.38]                  # tail_02 x axis at rest: back and up
n0 = [1.0, 0.0, 0.0]                    # the flat bolt's normal at rest
for s, sg in (("left", 1), ("right", -1)):
    d1 = [sg * math.sin(sp), math.sin(bk), -math.cos(sp) * math.cos(bk)]
    n1 = [0.0, -P["TAIL_FLIP"], 0.0]    # broad side to the viewer
    F0 = frame(d0, [sg * c for c in n0])
    F1 = frame(d1, n1)
    ax, ang = rot_to_axis_angle(F0, F1)
    A(f"{s}_tail_01", [round(c, 4) for c in ax], f"{ang:.2f}")
    A(f"{s}_tail_01", (0, 1, 0), f"{sg}*TAIL_LEAN")
    pose.append([f"{s}_tail_01", "LOCX", f"{sg}*TAIL_SEP"])

# tail sway: an in-plane scissor (the X opening and closing) a beat after the bob, more
# toward the tips, plus a small faster flutter on the light tip segment
for s in ("left", "right"):
    A(f"{s}_tail_04", (-1, 0, 0), f"1.6*TAILA*{B(0.34)} + TAILF*sin(4*pi*(t-0.40))")
    A(f"{s}_tail_03", (-1, 0, 0), f"1.3*TAILA*{B(0.28)}")
    A(f"{s}_tail_02", (-1, 0, 0), f"TAILA*{B(0.22)}")

# --- body ------------------------------------------------------------------------------
A("spine_01", (1, 0, 0), f"LEAN + 0.5*BR*{B(0.05)}")
A("spine_02", (1, 0, 0), f"0.7*BR*{B(0.08)}")
A("head", (1, 0, 0), f"NOD + HD*{B(0.14)}")
A("head", (0, 1, 0), "TILT")

# ears (long, heavy-ish): flop forward/back after the head; whisker spirals flutter last
EAR_Y = {"left": (-0.42, -0.76, 0.49), "right": (-0.42, 0.76, -0.49)}
EAR_Z = {"left": (0.86, -0.50, -0.03), "right": (-0.86, -0.50, -0.03)}
HORN_Z = {"left": (0.82, -0.57, 0.02), "right": (-0.82, -0.57, 0.02)}
for s in ("left", "right"):
    A(f"{s}_ear_01", EAR_Z[s], f"EAR_OUT + 0.6*EAR*{B(0.20)}")
    A(f"{s}_ear_01", EAR_Y[s], f"EAR*{B(0.22)}")
    A(f"{s}_ear_02", EAR_Y[s], f"1.4*EAR*{B(0.28)}")
    A(f"{s}_horn_02", HORN_Z[s], f"WH*{B(0.30)} + 0.4*WH*sin(4*pi*(t-0.36))")

# arms: held out; they rise as the body sinks (balancing), a beat late
ARM_Z = {"left": (-0.44, -0.90, 0.03), "right": (0.44, -0.90, 0.03)}
ARM_Y = {"left": (-0.02, 0.05, 1.00), "right": (-0.02, -0.05, -1.00)}
for s in ("left", "right"):
    A(f"{s}_arm_02", ARM_Y[s], f"ELB - 0.5*ARM*{B(0.20)}")
    A(f"{s}_hand", ARM_Z[s], f"-0.6*ARM*{B(0.24)}")
    A(f"{s}_arm_01", ARM_Z[s], f"ARM_UP - ARM*{B(0.16)}")
    A(f"{s}_arm_01", ARM_Y[s], f"-ARM_FWD")

# legs: right knee pulled up, left leg dangling; they trail the bob
A("right_foot", (1, 0, 0), f"RFOOT - 0.5*LEG*{B(0.26)}")
A("right_leg_02", (1, 0, 0), f"RKNEE + 0.5*LEG*{B(0.22)}")
A("right_leg_01", (1, 0, 0), f"RTHIGH - 0.4*LEG*{B(0.18)}")
A("right_leg_01", (0, 0, 1), "-RABD")
A("left_foot", (1, 0, 0), f"LFOOT + LEG*{B(0.30)}")
A("left_leg_02", (1, 0, 0), f"LKNEE + 0.8*LEG*{B(0.26)}")
A("left_leg_01", (1, 0, 0), f"LTHIGH - 0.6*LEG*{B(0.20)}")

pose.sort(key=lambda e: -depth.get(e[0], 0))
pose.append(["origin", "LOCZ", f"BOB*{B(0)}"])

for k in sorted(set(old) | set(P)):
    if old.get(k) != P.get(k):
        print(f"  {k}: {old.get(k)} -> {P.get(k)}")
cfg["pose_params"] = P
if cfg.get("pose") != pose:
    print(f"  pose: {len(cfg.get('pose', []))} -> {len(pose)} entries")
cfg["pose"] = pose
mo = cfg.setdefault("motion", {})
mo["functions"] = {"B": "sin(2*pi*t)"}
mo.pop("plant", None)
mo["note"] = NOTE
CFG.write_text(json.dumps(cfg, indent=2) + "\n")
print("wrote", CFG)
