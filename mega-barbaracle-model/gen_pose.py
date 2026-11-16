"""Write pose / motion for Mega Barbaracle into the config.

The eight arms are separate root chains (children of `origin`, not of the body), laid out in a row
in front of the model in the bind pose. Each is turned to its art direction about its shoulder head
and moved so its base sits in its socket on the rock body (the `closed_arm` caps). Bends after that
use axes computed here from that turn (the RIG.md rest axes no longer hold once an arm is turned).
Body motion goes on `origin` last, so body and arms move as one; the ankles are planted.

Run: /usr/local/bin/python3 gen_pose.py [KEY=value ...]   (keeps existing params, prints changes)
"""
import json
import math
import sys
from pathlib import Path

CFG = Path(__file__).with_name("mega_barbaracle_front.json")
cfg = json.loads(CFG.read_text())

DEFAULTS = {
    "AZIMUTH": 75, "ELEVATION": 10, "FOV": 30,
    # arm directions: degrees from straight up, outward in the picture; Y lean (+ = back)
    "TH_a": 22, "TH_b": 52, "TH_c": 82, "TH_d": 116,
    "YL_a": 0.35, "YL_b": 0.15, "YL_c": -0.30, "YL_d": -0.30,
    "INSET": 0.04,
    # rest bends (deg, + = further out / down in the spread plane)
    "E_a": 0, "E_b": 0, "E_c": 0, "E_d": 0,
    "H_a": 0, "H_b": 0, "H_c": 0, "H_d": 0,
    # motion
    "S0": 6, "S1": 10, "S2": -12, "S3": -10,
    "A1": 4, "WPH": 0.8, "ARMPH": 1.1, "SIDEPH": 2.4,
    "CROSS_L": 11, "CROSS_R": 4, "FWD_L": 5, "FWD_R": 3,
    "KNEE": 8, "DIP": 0.022, "SWAY": 0.6, "AS": 1.2, "AE": 1.8, "AH": 2.6, "AF": 4.0, "RIP": 0.25,
}
SOCKET = {"a": (0.105, 0.215, 1.70), "b": (0.25, 0.08, 1.645),
          "c": (0.34, -0.205, 1.39), "d": (0.18, -0.23, 1.26)}
ARMY = {"a": -0.40, "b": -0.60, "c": -0.80, "d": -1.00}

P = dict(cfg.get("pose_params", {}))
before = dict(P)
for k, v in DEFAULTS.items():
    P.setdefault(k, v)
for kv in sys.argv[1:]:
    k, v = kv.split("=")
    P[k] = float(v)
for k in sorted(set(P) | set(before)):
    if before.get(k) != P.get(k):
        print(f"  {k}: {before.get(k)} -> {P.get(k)}")


def norm(v):
    n = math.sqrt(sum(x * x for x in v))
    return tuple(x / n for x in v)


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def rot(v, axis, deg):  # Rodrigues
    a = math.radians(deg)
    k = axis
    c, s = math.cos(a), math.sin(a)
    kv = cross(k, v)
    kd = sum(x * y for x, y in zip(k, v))
    return tuple(v[i] * c + kv[i] * s + k[i] * kd * (1 - c) for i in range(3))


def ax(v):
    return "A:" + ",".join(f"{x:.4f}" for x in v)


pose, motion_pose = [], []
# Arms are tentacles: each chain (shoulder, arm_01, arm_02, hand) holds an S-curve in its spread
# plane (bends about kax) and a wave travels root to tip (phase grows toward the tip, amplitude
# too), each arm out of phase with its neighbours; the claws flex last.
CHAIN = ("shoulder_{k}", "arm_{k}_01", "arm_{k}_02", "hand_{k}")
S_REST = ("S0", "S1", "S2", "S3")      # rest S bends (deg) per joint, sign flips per arm
W_AMP = ("AS", "A1", "AE", "AH")       # wave amplitude (deg) per joint
for side, sx in (("left", 1), ("right", -1)):
    for i, k in enumerate("abcd"):
        th = math.radians(P[f"TH_{k}"])
        d = norm((sx * math.sin(th), P[f"YL_{k}"], math.cos(th)))
        kax = norm(cross((0, 0, 1), d))          # turn +Z onto d about kax
        ang = math.degrees(math.acos(max(-1, min(1, d[2]))))
        head = (0.2 * sx, ARMY[k], -0.2)
        base = tuple(head[j] + 0.2 * d[j] for j in range(3))
        sock = (SOCKET[k][0] * sx, SOCKET[k][1], SOCKET[k][2])
        tgt = tuple(sock[j] - P["INSET"] * d[j] for j in range(3))
        sh = f"{side}_shoulder_{k}"
        pose.append([sh, ax(kax), f"{ang:.3f}"])
        for j, L in enumerate("XYZ"):
            pose.append([sh, "LOC" + L, f"{tgt[j] - base[j]:.4f}"])
        sgn = 1 if i % 2 == 0 else -1           # alternate the S so neighbours don't nest
        for j, b in enumerate(CHAIN):
            pose.append([f"{side}_{b.format(k=k)}", ax(kax), f"{sgn}*{S_REST[j]}"])
        pose.append([f"{side}_arm_{k}_02", ax(kax), f"E_{k}"])
        pose.append([f"{side}_hand_{k}", ax(kax), f"H_{k}"])
        # claw spread axis: rest +Y turned with the arm and its rest S
        tot = ang + sgn * sum(P[s] for s in S_REST) + P[f"E_{k}"] + P[f"H_{k}"]
        sp = norm(rot((0, 1, 0), kax, tot))
        # arm phase: ripple top to bottom, the right side half a beat behind the left
        ph = f"(ARMPH*{i} + {0 if sx > 0 else 1}*SIDEPH)"
        for j, b in enumerate(CHAIN):
            motion_pose.append([f"{side}_{b.format(k=k)}", ax(kax),
                                f"-{W_AMP[j]}*cos(4*pi*t - 0.5 - WPH*{j} - {ph})"])
        fl = f"0.5 - WPH*4 - {ph}"
        motion_pose += [
            [f"{side}_thumb_{k}", ax(sp), f"{sx}*AF*sin(4*pi*t - {fl})"],
            [f"{side}_middle_{k}", ax(sp), f"{-sx}*AF*sin(4*pi*t - {fl})"],
            [f"{side}_index_{k}", ax(kax), f"-0.6*AF*cos(4*pi*t - {fl})"],
        ]

# legs: knee bend (as v1), then semi-crossed like HOME: each leg swings in about world Y at the
# hip (left = the near/viewer-right leg crosses more and steps forward, right steps back), and
# the foot turns back flat.
legs = []
for side, sx in (("left", 1), ("right", -1)):
    C, F = ("CROSS_L", "FWD_L") if sx > 0 else ("CROSS_R", "FWD_R")
    legs += [[f"{side}_leg_01", "A:1,0,0", "-KNEE"], [f"{side}_leg_02", "A:1,0,0", "2*KNEE"],
             [f"{side}_foot", "A:1,0,0", "-KNEE"],
             [f"{side}_leg_01", "A:0,1,0", f"{sx}*{C}"], [f"{side}_leg_01", "A:1,0,0", f"{-sx}*{F}"],
             [f"{side}_foot", "A:1,0,0", f"{sx}*{F}"], [f"{side}_foot", "A:0,1,0", f"{-sx}*{C}"]]

# body: two slow breaths a loop (dip), one weight shift side to side; ankles planted
body = [
    ["origin", "LOCZ", "-DIP*(1 - cos(4*pi*t))/2"],
    ["origin", "A:0,1,0", "SWAY*sin(2*pi*t)"],
]
cfg["pose_params"] = P
cfg["pose"] = pose + legs + motion_pose + body
CFG.write_text(json.dumps(cfg, indent=2) + "\n")
print(f"wrote {len(cfg['pose'])} pose entries")
