"""Write pose / pose_params / motion into mega_crabominable_front.json.

Run: /usr/local/bin/python3 mega-crabominable-model/gen_pose.py [NAME=value ...] [--reset]
Params already in the config keep their values (new names get the defaults below);
NAME=value changes one; --reset takes every default again. Prints before -> after for every
change. Entries are sorted deepest bone first, so each "A:" bend (a world axis through the bone
head) uses the bone's rest axes from RIG.md before its parents move it.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = HERE / "mega_crabominable_front.json"

DEFAULTS = {
    "AZIMUTH": 70, "ELEVATION": 12, "FOV": 30,
    # rest pose (deg)
    "LEAN": 0, "TURN": 0, "NOD": 0,
    "SH_UP": 10, "SH_FWD": 15, "ELB": 75, "ELB_FWD": 0, "WR": 0, "WR_TWIST": 0,
    # motion
    "DIP": 0.0, "BR": 0.0, "HD": 0.0, "ARM": 0.0, "CLAW": 0.0, "FUR": 0.0, "TUFT": 0.0,
    "FEEL": 0.0, "LEGA": 0.0, "JAW": 0.0, "ANT": 0.0, "KNEE": 0, "KD": 0,
    # v2 (redo): growl face, out-of-step fist arcs, body sway
    "JAW0": 0.0, "JR": 0.0, "HTURN": 0.0, "ARF": 0.0, "ELA": 0.0, "WRA": 0.0,
    "PHR": 0.4, "AMR": 0.85, "SW": 0.0, "SK": 0.1,
}

depth, axes = {}, {}
for line in (HERE / "RIG.md").read_text().splitlines():
    m = re.match(r"^( *)(\w+)  head=.*axes x=\(([^)]*)\) y=\(([^)]*)\) z=\(([^)]*)\)", line)
    if m:
        depth[m.group(2)] = len(m.group(1)) // 2
        axes[m.group(2)] = [tuple(float(v) for v in m.group(i).split(",")) for i in (3, 4, 5)]

NOTE = 'Crabby abomination squaring up on its two planted ice shards: a slow growling breath per loop drives the body (dips ~1-2 px, the legs bend under it, the chest rocks). The head is held low and turned to the camera, the jaw held open in a snarl that opens wider a beat after the breath with a quick growl rumble on top. Each huge pincer swings on its own eased loop (up/down plus forward/back a quarter cycle later), the right one 0.4 of a loop behind the left and a little smaller; shoulder, upper arm, forearm, wrist and claw each lag the one before, the dark fur fringe trails last, and the body turns slightly toward the rising fist. Back mane, chest feelers, leg spikes and the yellow antenna follow the breath.'

pose = []


def A(bone, axis, expr):
    pose.append([bone, "A:" + ",".join(f"{c:g}" for c in axis), expr])


def own(bone, i, sign=1):
    return tuple(sign * c for c in axes[bone][i])


def B(lag):
    return f"B(t-{lag:g})"


# --- body: one slow growling breath; the body dips on planted ice legs -------------
A("waist", (1, 0, 0), f"LEAN + BR*{B(0.04)}")
# the body turns a little toward whichever fist is rising (follows the fists' average)
A("waist", (0, 0, 1), "TURN + SW*(F(t-0.06) - F(t-PHR-0.06))/2")
pose.append(["origin", "LOCZ", "-DIP*(0.5+0.5*B(t))"])
# head held low (NOD) and turned toward the camera; dips on the breath a beat later
A("head", (1, 0, 0), f"NOD - HD*{B(0.12)}")
A("head", (0, 0, 1), "HTURN")
# growl: jaw held open, opens wider on the breath, with a quick snarl rumble on top
A("jaw", own("jaw", 1, -1), f"JAW0 + JAW*(0.5+0.5*{B(0.16)}) + JR*sin(12*pi*t)")

# --- arms: boxer guard, pincers high; each fist on its own eased arc ----------------
# F(p): the fist's up/down arc (wave: lingers high, drops through quickly); G(p): its
# forward/back component a quarter cycle later, so the fist traces a loop, not a line.
# The right fist runs PHR of a loop behind the left, at AMR of its size. Joints lag outward.
for s, sg in (("left", 1), ("right", -1)):
    up, fwd = (0, -sg, 0), (0, 0, -sg)
    ph = "0" if s == "left" else "PHR"
    am = "1" if s == "left" else "AMR"
    def F(lag, ph=ph):
        return f"F(t-{ph}-{lag:g})"
    def G(lag, ph=ph):
        return f"G(t-{ph}-{lag:g})"
    A(f"{s}_shoulder", up, f"{am}*0.5*ARM*{F(0.0)}")
    A(f"{s}_arm_01", up, f"SH_UP + {am}*ARM*{F(0.05)}")
    A(f"{s}_arm_01", fwd, f"SH_FWD + {am}*ARF*{G(0.05)}")
    A(f"{s}_arm_02", up, f"ELB + {am}*ELA*{F(0.13)}")
    A(f"{s}_arm_02", fwd, f"ELB_FWD + {am}*0.6*ARF*{G(0.13)}")
    A(f"{s}_hand", up, f"WR + {am}*WRA*{F(0.21)}")
    A(f"{s}_index", up, f"CLAW*{F(0.29)}")
    A(f"{s}_index", (sg, 0, 0), "WR_TWIST")
    for k in "abcdefghi":                       # dark fur fringe on the pincer trails the fist
        A(f"{s}_skirt_{k}", own(f"{s}_skirt_{k}", 2), f"TUFT*{F(0.37)}")
    for k in "abcdefgh":                        # small chest feelers on the shoulder
        A(f"{s}_feeler_{k}", own(f"{s}_feeler_{k}", 2), f"FEEL*{B(0.22)}")
    for k in "ij":
        A(f"{s}_feeler_{k}", own(f"{s}_feeler_{k}", 2), f"FEEL*{B(0.2)}")
    A(f"{s}_leg_b_01", own(f"{s}_leg_b_01", 2), "KNEE - KD*(0.5+0.5*B(t))")      # pre-bent knee: the plant can bend it
    A(f"{s}_leg_b_02", own(f"{s}_leg_b_02", 2), "-2*KNEE + 2*KD*(0.5+0.5*B(t))")
    A(f"{s}_leg_a_01", own(f"{s}_leg_a_01", 2), f"LEGA*{B(0.16)}")
    A(f"{s}_leg_a_02", own(f"{s}_leg_a_02", 2), f"0.6*LEGA*{B(0.2)}")

for b in ("feeler_a_01", "feeler_b", "feeler_c"):
    A(b, own(b, 2), f"FEEL*{B(0.2)}")
A("feeler_a_02", own("feeler_a_02", 2), f"0.6*FEEL*{B(0.26)}")

# --- fur: back mane and head fur lag behind the breath -----------------------------
for b in depth:
    m = re.match(r"(hair_[a-k]|cloth|left_cloth_[ab]|right_cloth_[ab]|horn_[a-f])_0(\d)$", b)
    if m:
        n = int(m.group(2))
        A(b, own(b, 2), f"{0.5 + 0.25 * n:g}*FUR*{B(0.18 + 0.05 * n)}")
# antenna (yellow strand on top): lag plus its own faster flutter
for i, b in enumerate(("left_hair_01", "left_hair_02", "left_hair_03")):
    A(b, (0, 1, 0), f"{0.6 + 0.3 * i:g}*ANT*{B(0.2 + 0.06 * i)} + 0.25*ANT*sin(4*pi*(t-{0.1 * i:g}))")
for i, b in enumerate(("right_hair_01", "right_hair_02", "right_hair_03")):
    A(b, (0, 1, 0), f"{0.6 + 0.3 * i:g}*ANT*{B(0.2 + 0.06 * i)} + 0.25*ANT*sin(4*pi*(t-{0.1 * i:g}))")

pose.sort(key=lambda e: -depth[e[0]])           # stable: deepest bone first

cfg = json.loads(CFG.read_text())
old = cfg.get("pose_params", {})
reset = "--reset" in sys.argv
params = dict(DEFAULTS) if reset else {**DEFAULTS, **{k: v for k, v in old.items() if k in DEFAULTS}}
for a in sys.argv[1:]:
    if "=" in a:
        k, v = a.split("=", 1)
        params[k] = float(v)
for k in params:
    if old.get(k) != params[k]:
        print(f"  {k}: {old.get(k)} -> {params[k]}")
cfg["pose_params"] = params
cfg["pose"] = pose
cfg.setdefault("motion", {})["functions"] = {
    "B": "sin(2*pi*t)", "F": "wave(t, SK)", "G": "cos(2*pi*t)"}
cfg["style"]["height"] = 200
cfg["render"].setdefault("hull", {})["cap_each_frame"] = True
cfg["motion"]["note"] = NOTE
cfg["motion"]["plant"] = ["left_foot_b", "right_foot_b"]
CFG.write_text(json.dumps(cfg, indent=2) + "\n")
print(f"{len(pose)} pose entries")
