"""Write pose / pose_params / motion into mega_chesnaught_front.json.

Run: /usr/local/bin/python3 mega-chesnaught-model/gen_pose.py [--reset] [NAME=value ...]
Params already in the config keep their values (only new names get the defaults below);
--reset drops every stored param first (the v2 redo started from scratch this way).
NAME=value changes one. Prints before -> after for every change. Entries are sorted deepest
bone first, so each "A:" bend (a world axis through the bone head at rest, applied in list
order) uses the bone's rest axes from RIG.md before its parents move it.

v2 stance (user feedback 2026-11-15): base Chesnaught's sumo guard. Feet wide and planted,
knees bent and pushed out, body low and upright, arms spread and raised in guard, the
shoulder shields up beside the head.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = HERE / "mega_chesnaught_front.json"

DEFAULTS = {
    "AZIMUTH": 60, "ELEVATION": 10, "FOV": 30,
    # body (deg / model units)
    "CROUCH": 0.10, "LEAN": 8, "LEAN_SIDE": 0, "TURN": 0, "NOD": -8, "HDTURN": 0, "HDTILT": 0,
    # legs: thigh flexed forward + abducted out, shin back under the knee, foot flat
    "THIGH_FWD": 20, "THIGH_OUT": 25, "SHIN_BACK": 35, "SHIN_IN": 20, "FOOT_FLAT": 15, "FOOT_IN": 5,
    # arms: upper arm out/up, elbow bent so the fists come up in guard
    "LA_FWD": 25, "LA_UP": 30, "LE_FWD": 40, "LE_UP": 20,
    "RA_FWD": 25, "RA_UP": 30, "RE_FWD": 40, "RE_UP": 20,
    "WRIST": 0,
    # shoulder shields
    "SH_FWD": 0, "SH_UP": 0, "SH_YAW": 0,
    "TAIL_DROOP": 0, "CAPE_BACK": 25, "CAPE_CURL": 0, "CAPE_OUT": 0,
    # motion (amplitudes)
    "DIP": 0.0, "BR": 0.0, "SWAY": 0.0, "ARM": 0.0, "SH": 0.0, "CAPE": 0.0, "TAILA": 0.0, "FUR": 0.0, "HD": 0.0,
}

depth = {}
for line in (HERE / "RIG.md").read_text().splitlines():
    m = re.match(r"^( *)(\w+)  head=", line)
    if m:
        depth[m.group(2)] = len(m.group(1)) // 2

pose = []


def A(bone, axis, expr):
    pose.append([bone, "A:" + ",".join(f"{c:g}" for c in axis), expr])


def B(lag):        # the breath: one slow sine per loop
    return f"B(t-{lag:g})"


def W(lag):        # the weight shift: one slow side-to-side per loop, a quarter out of phase
    return f"W(t-{lag:g})"


# --- body: low, nearly upright trunk; breath lifts the chest -------------------------
A("spine_01", (1, 0, 0), f"LEAN + 0.4*BR*{B(0.02)}")
A("spine_01", (0, 0, 1), f"TURN + 0.5*SWAY*{W(0.06)}")
A("spine_01", (0, 1, 0), f"LEAN_SIDE + SWAY*{W(0.04)}")
A("spine_02", (1, 0, 0), f"BR*{B(0.06)}")
A("head", (1, 0, 0), f"NOD - 0.5*BR*{B(0.14)} + HD*{B(0.16)}")
A("head", (0, 0, 1), "HDTURN")
A("head", (0, 1, 0), f"HDTILT - 0.8*SWAY*{W(0.12)}")

# --- arms: spread wide, forearms up (sign sg: +1 left, -1 right) -----------------------
# +X arm swings forward about -Z, raises about -Y. Bend arm_02 only: arm_02_roll is its child
# with the same head and carries the forearm mesh (bending both doubles the bend: v1 spikes).
for s, sg, S in (("left", 1, "L"), ("right", -1, "R")):
    A(f"{s}_hand_sub", (0, -sg, 0), f"WRIST + 0.6*ARM*{B(0.24)}")
    # raise (about the front-back axis) first, then swing forward (about vertical): the swing
    # keeps the elevation; the other order turns a raise into a twist
    A(f"{s}_arm_02", (0, -sg, 0), f"{S}E_UP + ARM*{B(0.20)}")
    A(f"{s}_arm_02", (0, 0, -sg), f"{S}E_FWD + 0.6*ARM*{B(0.20)}")
    for b in (f"{s}_arm_01", f"{s}_feeler_b"):
        A(b, (0, -sg, 0), f"{S}A_UP + 0.5*ARM*{B(0.14)}")
        A(b, (0, 0, -sg), f"{S}A_FWD")

# --- shoulder shields (heavy: ride the chest, a small late rock) ------------------------
for s, sg in (("left", 1), ("right", -1)):
    A(f"{s}_feeler_a", (0, 0, -sg), "SH_YAW")
    A(f"{s}_feeler_a", (0, -sg, 0), f"SH_UP + SH*{B(0.18)}")
    A(f"{s}_feeler_a", (1, 0, 0), "-SH_FWD")

# --- tail ------------------------------------------------------------------------------
for i in range(1, 5):
    A(f"tail_0{i}", (1, 0, 0), f"{'TAIL_DROOP + ' if i == 1 else ''}{0.6 + 0.3 * i:g}*TAILA*{B(0.18 + 0.05 * i)}")
    A(f"tail_0{i}", (0, 0, 1), f"{0.4 + 0.3 * i:g}*TAILA*{W(0.16 + 0.05 * i)}")

# --- fur cape: two strands from the back; swung back behind the legs, a wave runs down it ---
for s, sg in (("left", 1), ("right", -1)):
    for i in range(1, 6):
        rest = "CAPE_BACK + " if i == 1 else ("CAPE_CURL + " if i >= 3 else "")
        A(f"{s}_cloth_0{i}", (1, 0, 0), f"{rest}{0.5 + 0.25 * i:g}*CAPE*{B(0.14 + 0.06 * i)}")
        A(f"{s}_cloth_0{i}", (0, 0, 1), f"{0.3 + 0.2 * i:g}*CAPE*{W(0.12 + 0.06 * i)}")
    A(f"{s}_cloth_01", (0, -sg, 0), "CAPE_OUT")

# --- face fur ----------------------------------------------------------------------------
for s in ("left", "right"):
    A(f"{s}_hair_a", (1, 0, 0), f"FUR*{B(0.2)}")
    A(f"{s}_hair_b", (1, 0, 0), f"FUR*{B(0.22)}")
    A(f"{s}_hair_c", (1, 0, 0), f"FUR*{B(0.2)}")

# --- legs: sumo squat (sign sg: +1 left, -1 right) ----------------------------------------
for s, sg in (("left", 1), ("right", -1)):
    A(f"{s}_foot", (1, 0, 0), "FOOT_FLAT")
    A(f"{s}_foot", (0, sg, 0), "FOOT_IN")
    A(f"{s}_leg_02", (1, 0, 0), "SHIN_BACK")
    A(f"{s}_leg_02", (0, sg, 0), "SHIN_IN")
    A(f"{s}_leg_01", (1, 0, 0), "-THIGH_FWD")
    A(f"{s}_leg_01", (0, -sg, 0), "THIGH_OUT")

# --- root: crouch, breath dip and weight shift (planted ankles take it in the legs) ----------
pose.append(["waist", "LOCZ", f"-CROUCH - DIP*(0.5+0.5*{B(0)})"])
pose.append(["waist", "LOCX", f"0.012*SWAY*{W(0)}"])

pose = [e for e in pose if e[0] in depth or e[0] == "waist"]
order = {id(e): i for i, e in enumerate(pose)}
pose.sort(key=lambda e: (-depth.get(e[0], 0), order[id(e)]))

args = sys.argv[1:]
cfg = json.loads(CFG.read_text())
params = {} if "--reset" in args else dict(cfg.get("pose_params", {}))
old = dict(cfg.get("pose_params", {}))
over = dict(a.split("=", 1) for a in args if "=" in a)
new = {}
for k, v in DEFAULTS.items():
    new[k] = params.get(k, v)
for k, v in over.items():
    new[k] = float(v)
for k in sorted(set(new) | set(old)):
    if old.get(k) != new.get(k):
        print(f"  {k}: {old.get(k)} -> {new.get(k)}")
cfg["pose_params"] = new
if cfg.get("pose") != pose:
    print(f"  pose: {len(cfg.get('pose', []))} -> {len(pose)} entries")
cfg["pose"] = pose
mo = cfg.setdefault("motion", {})
mo["functions"] = {"B": "sin(2*pi*t)", "W": "sin(2*pi*t + pi/2)"}
mo["plant"] = ["left_foot", "right_foot"]
CFG.write_text(json.dumps(cfg, indent=2) + "\n")
