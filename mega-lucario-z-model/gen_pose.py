"""Write pose / pose_params / motion into mega_lucario_z_front.json.

Run: /usr/local/bin/python3 mega-lucario-z-model/gen_pose.py
Params already in the config keep their values (only new names get the defaults below);
pass NAME=value on the command line to change one. Prints before -> after for every change.
Entries are sorted deepest bone first, so each bend uses the bone's own rest axes (RIG.md)
before its parents move it.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = HERE / "mega_lucario_z_front.json"

DEFAULTS = {
    "AZIMUTH": 62, "ELEVATION": 8, "FOV": 30,
    # rest pose (deg)
    "LEAN": 6, "NOD": 8, "HDTURN": 6,
    "UA_DOWN_L": 55, "UA_FWD_L": 40, "ELB_L": 105,
    "UA_DOWN_R": 62, "UA_FWD_R": 30, "ELB_R": 95,
    "FA_DROOP": 50, "FA_CURL": 7, "FA_SPLAY": 12,
    "FB_DROOP": 40, "FB_CURL": 9,
    "TAIL_DROOP": 30, "TAIL_SIDE": 25,
    "HAIR_DROOP": 62, "HAIR_BACK": 20,
    # motion
    "DIP": 0.010, "BR": 1.6, "ARM": 2.5, "EAR": 2.0,
    "FA": 2.2, "FAF": 1.2, "FB": 3.0, "FBF": 2.0,
    "TAILA": 2.5, "HAIRA": 3.0, "CLOTH": 3.0,
}

# deg of each bone in the tree, from RIG.md indentation
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


# --- body -------------------------------------------------------------------
A("spine_01", (1, 0, 0), f"LEAN + 0.4*BR*{B(0)}")
A("spine_02", (1, 0, 0), f"BR*{B(0.04)}")
A("neck", (1, 0, 0), f"0.5*NOD + 0.6*BR*{B(0.10)}")
A("head", (1, 0, 0), f"0.5*NOD - 0.4*BR*{B(0.14)}")
A("head", (0, 0, 1), "HDTURN")

# ears: small lagging nod
for s in ("left", "right"):
    A(f"{s}_ear_01", (1, 0, 0), f"EAR*{B(0.18)}")
    A(f"{s}_ear_02", (1, 0, 0), f"EAR*{B(0.24)}")

# --- arms: fighter's guard (world axes: +X arm lowers about +Y, swings forward about -Z) ---
for s, sg in (("left", 1), ("right", -1)):
    S = "L" if s == "left" else "R"
    A(f"{s}_arm_02", (0, 0, -sg), f"ELB_{S} + ARM*{B(0.16)}")
    A(f"{s}_arm_01", (0, sg, 0), f"UA_DOWN_{S} - 0.6*ARM*{B(0.12)}")
    A(f"{s}_arm_01", (0, 0, -sg), f"UA_FWD_{S} + 0.5*ARM*{B(0.12)}")
    A(f"{s}_shoulder", (0, 1 * sg, 0), f"-0.5*ARM*{B(0.08)}")

# --- head feelers ---------------------------------------------------------------
# big paddles (feeler_a): droop about the bone's horizontal y axis, curl along, splay out
FA_AX = {"left": (-0.94, 0.34, 0), "right": (-0.94, -0.34, 0)}
FB_AX = {"left": (-0.98, 0.17, 0), "right": (-0.98, -0.17, 0)}
for s, sg in (("left", 1), ("right", -1)):
    ax = FA_AX[s]
    for i in range(8, 1, -1):
        lag = 0.20 + 0.035 * i
        w = 0.4 + 0.12 * i
        flut = f" + FAF*{0.15 * max(0, i - 5):g}*sin(4*pi*(t-{lag + 0.05:g}))" if i >= 6 else ""
        A(f"{s}_feeler_a_{i:02d}", ax, f"FA_CURL + {w:g}*FA*{B(lag)}{flut}")
    A(f"{s}_feeler_a_01", ax, f"FA_DROOP + FA*{B(0.20)}")
    A(f"{s}_feeler_a_01", (0, 0, 1), f"{sg}*(-FA_SPLAY) + {sg}*0.5*FA*{B(0.22)}")
    ax = FB_AX[s]
    for i in range(10, 1, -1):
        lag = 0.22 + 0.03 * i
        w = 0.4 + 0.1 * i
        flut = f" + FBF*{0.12 * max(0, i - 6):g}*sin(4*pi*(t-{lag + 0.04:g}))" if i >= 7 else ""
        A(f"{s}_feeler_b_{i:02d}", ax, f"FB_CURL + {w:g}*FB*{B(lag)}{flut}")
    A(f"{s}_feeler_b_01", ax, f"FB_DROOP + FB*{B(0.22)}")

# chest fur / cloth: light, lags the chest
for b in ("center_root_cloth", "left_root_cloth", "right_root_cloth"):
    A(b, (1, 0, 0), f"CLOTH*{B(0.12)}")
for b in ("center_cloth", "left_cloth_a", "right_cloth_a", "left_cloth_b", "right_cloth_b",
          "left_cloth_c", "right_cloth_c", "left_cloth_d", "right_cloth_d", "left_cloth_e", "right_cloth_e"):
    A(b, (1, 0, 0), f"1.3*CLOTH*{B(0.18)}")

# --- hips: tail fin, yellow tail tuft ("hair"), skirt ---------------------------------
A("tail_04", (0, 0, 1), f"1.6*TAILA*{B(0.36)}")
A("tail_03", (0, 0, 1), f"1.2*TAILA*{B(0.31)}")
A("tail_02", (0, 0, 1), f"TAILA*{B(0.26)}")
A("tail_01", (-1, 0, 0), f"TAIL_DROOP + 0.5*TAILA*{B(0.22)}")
A("tail_01", (0, 0, 1), f"-TAIL_SIDE + TAILA*{B(0.22)}")

A("hair_03", (0, 1, 0), f"1.5*HAIRA*{B(0.32)}")
A("hair_02", (0, 1, 0), f"1.2*HAIRA*{B(0.27)}")
A("hair_01", (0, -1, 0), f"HAIR_DROOP + 0.7*HAIRA*{B(0.22)}")
A("hair_01", (0, 0, 1), "HAIR_BACK")

for b in ("front_skirt", "back_skirt", "left_skirt_a", "right_skirt_a", "left_skirt_b",
          "right_skirt_b", "left_skirt_c", "right_skirt_c"):
    A(b, (1, 0, 0), f"0.8*CLOTH*{B(0.2)}")

# --- whole body: the dip (feet planted at the ankles) ----------------------------
pose.sort(key=lambda e: -depth.get(e[0], 0))
pose.append(["waist", "LOCZ", f"0.5*DIP*{B(0.02)}"])

cfg = json.loads(CFG.read_text())
old = cfg.get("pose_params", {})
cli = dict(a.split("=", 1) for a in sys.argv[1:])
new = {}
for k, v in DEFAULTS.items():
    new[k] = float(cli[k]) if k in cli else old.get(k, v)
for k, v in old.items():
    new.setdefault(k, v)
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
