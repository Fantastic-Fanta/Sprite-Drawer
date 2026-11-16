"""Write pose / pose_params / motion into mega_zeraora_front.json.

Run: /usr/local/bin/python3 mega-zeraora-model/gen_pose.py [NAME=value ...]
Params already in the config keep their values (only new names get the defaults below);
NAME=value on the command line changes one. Prints before -> after for every change.
Entries are sorted deepest bone first, so each bend uses the bone's rest axes (RIG.md, world
space at rest) before its parents move it.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = HERE / "mega_zeraora_front.json"

DEFAULTS = {
    "AZIMUTH": 60, "ELEVATION": 10, "FOV": 30,
    # rest pose (deg; world units for CROUCH)
    "CROUCH": 0.10, "LEAN": 14, "TWIST": 0, "NOD": 10, "HDTURN": 10, "HDTILT": 0,
    "THIGH_L": 50, "KNEE_L": 60, "FOOT_L": 20, "SPREAD_L": 18,
    "THIGH_R": 30, "KNEE_R": 55, "FOOT_R": 20, "SPREAD_R": 22,
    "UA_DOWN_L": 45, "UA_FWD_L": 55, "ELB_L": 110,
    "UA_DOWN_R": 30, "UA_FWD_R": -25, "ELB_R": 25,
    "ELBUP_L": 0, "ELBUP_R": 0,
    "TAIL_UP": 55, "TAIL_UPD": 0, "TAIL_YAW": 0, "TAIL_CURL": 8, "TAIL_SPLAY": 12,
    # motion
    "DIP": 0.012, "BR": 1.6, "ARM": 3.0, "EAR": 3.0, "FEEL": 4.0,
    "TAILA": 2.2, "TAILF": 1.2, "HAIRA": 3.0,
}

depth = {}
for line in (HERE / "RIG.md").read_text().splitlines():
    m = re.match(r"^( *)(\w+)  head=", line)
    if m:
        depth[m.group(2)] = len(m.group(1)) // 2

pose = []


def A(bone, axis, expr):
    pose.append([bone, "A:" + ",".join(f"{c:g}" for c in axis), expr])


def B(lag):
    """the breath driver, `lag` of a loop later"""
    return f"B(t-{lag:g})"


# --- body: lean into the crouch, breath in the chest --------------------------
A("spine_01", (1, 0, 0), f"LEAN + 0.4*BR*{B(0)}")
A("spine_01", (0, 0, 1), "TWIST")
A("spine_02", (1, 0, 0), f"BR*{B(0.04)}")
A("neck", (1, 0, 0), f"0.5*NOD + 0.5*BR*{B(0.10)}")
A("head", (1, 0, 0), f"0.5*NOD - 0.5*BR*{B(0.14)}")
A("head", (0, 0, 1), "HDTURN")
A("head", (0, 1, 0), "HDTILT")

# ears, cheek feelers, head hair: light, lag the head
for s, sg in (("left", 1), ("right", -1)):
    A(f"{s}_ear", (1, 0, 0), f"EAR*{B(0.20)}")
    A(f"{s}_feeler_a", (1, 0, 0), f"FEEL*{B(0.22)}")
    A(f"{s}_feeler_b", (1, 0, 0), f"FEEL*{B(0.18)}")
    A(f"{s}_hair_a", (1, 0, 0), f"HAIRA*{B(0.24)}")
    A(f"{s}_hair_b", (1, 0, 0), f"HAIRA*{B(0.26)}")
    A(f"{s}_hair_c", (1, 0, 0), f"HAIRA*{B(0.24)}")
    A(f"{s}_hair_d", (1, 0, 0), f"HAIRA*{B(0.20)}")
for b, lag in (("hair_a", 0.22), ("hair_b", 0.25), ("hair_c", 0.27), ("hair_d", 0.22)):
    A(b, (1, 0, 0), f"HAIRA*{B(lag)}")
A("hair_e", (1, 0, 0), f"HAIRA*{B(0.24)}")

# --- arms (world axes: +X arm lowers about +Y, swings forward about -Z) ---------
for s, sg in (("left", 1), ("right", -1)):
    S = "L" if s == "left" else "R"
    A(f"{s}_arm_02", (0, 0, -sg), f"ELB_{S}")  # elbow fold held: a changing fold spikes the hull
    A(f"{s}_arm_02", (0, -sg, 0), f"ELBUP_{S}")
    A(f"{s}_arm_01", (0, sg, 0), f"UA_DOWN_{S} - 0.6*ARM*{B(0.12)}")
    A(f"{s}_arm_01", (0, 0, -sg), f"UA_FWD_{S} + 0.5*ARM*{B(0.12)}")
    A(f"{s}_shoulder", (0, sg, 0), f"-0.5*ARM*{B(0.08)}")
    A(f"{s}_feeler_c", (1, 0, 0), f"0.35*FEEL*{B(0.24)}")
    # horns on the shoulders: small lag
    A(f"{s}_horn_a_01", (1, 0, 0), f"0.5*EAR*{B(0.14)}")

# --- legs: crouched stance (thigh forward about -X, knee back about +X) ---------
for s, sg in (("left", 1), ("right", -1)):
    S = "L" if s == "left" else "R"
    A(f"{s}_foot", (1, 0, 0), f"-FOOT_{S}")
    A(f"{s}_leg_02", (1, 0, 0), f"KNEE_{S}")
    A(f"{s}_leg_01", (-1, 0, 0), f"THIGH_{S}")
    A(f"{s}_leg_01", (0, -sg, 0), f"SPREAD_{S}")

# --- tails: two long tails raised in an arc, slow wave from base to tip ----------
TAIL_AX = {"left": (-0.98, 0.17, -0.04), "right": (-0.98, -0.17, 0.04)}
for s, sg in (("left", 1), ("right", -1)):
    ax = TAIL_AX[s]
    for i in range(8, 1, -1):
        lag = 0.18 + 0.04 * i
        w = 0.4 + 0.15 * i
        flut = f" + TAILF*{0.3 * max(0, i - 5):g}*sin(4*pi*(t-{lag + 0.05:g}))" if i >= 6 else ""
        # negative about the tail's -X-ish axis lifts it
        A(f"{s}_tail_{i:02d}", ax, f"-TAIL_CURL - {w:g}*TAILA*{B(lag)}{flut}")
    A(f"{s}_tail_01", ax, f"-TAIL_UP - {sg}*TAIL_UPD - TAILA*{B(0.18)}")
    A(f"{s}_tail_01", (0, 0, 1), f"{sg}*TAIL_SPLAY + TAIL_YAW + 0.5*TAILA*{B(0.20)}")

pose.sort(key=lambda e: -depth.get(e[0], 0))
pose.append(["waist", "LOCZ", f"-CROUCH + 0.5*DIP*{B(0.02)}"])

cfg = json.loads(CFG.read_text())
old = cfg.get("pose_params", {})
cli = dict(a.split("=", 1) for a in sys.argv[1:])
new = {}
for k, v in DEFAULTS.items():
    new[k] = float(cli[k]) if k in cli else old.get(k, v)
for k, v in old.items():
    new.setdefault(k, float(cli[k]) if k in cli else v)
for k in sorted(set(old) | set(new)):
    if old.get(k) != new.get(k):
        print(f"  {k}: {old.get(k)} -> {new.get(k)}")
cfg["pose_params"] = new
if cfg.get("pose") != pose:
    print(f"  pose: {len(cfg.get('pose', []))} -> {len(pose)} entries")
cfg["pose"] = pose
mo = cfg.setdefault("motion", {})
mo["functions"] = {"B": "sin(2*pi*t)"}
mo["plant"] = ["left_foot", "right_foot"]
CFG.write_text(json.dumps(cfg, indent=2) + "\n")
print("wrote", CFG)
