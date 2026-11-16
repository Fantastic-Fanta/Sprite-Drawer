"""Write pose / motion / palette into mega_scrafty_front.json.
Run: python3 gen.py [KEY=value ...]   keeps existing pose_params, overrides from argv, prints changes.
Bone axes come from RIG.md (world axes at rest): ax(bone, 'x'|'y'|'z') -> "A:..".
"""
import json, re, sys
from pathlib import Path

HERE = Path(__file__).parent
CFG = HERE / "mega_scrafty_front.json"
cfg = json.loads(CFG.read_text())

AX = {}
for line in (HERE / "RIG.md").read_text().splitlines():
    m = re.match(r"\s*(\S+)\s+head=.*axes x=\(([^)]*)\) y=\(([^)]*)\) z=\(([^)]*)\)", line)
    if m:
        AX[m.group(1)] = {k: m.group(i) for k, i in (("x", 2), ("y", 3), ("z", 4))}


def ax(bone, k):
    return "A:" + ",".join(v.strip().lstrip("+") for v in AX[bone][k].split(","))


DEFAULTS = {
    # camera
    "AZIMUTH": 55, "ELEVATION": 10, "FOV": 30,
    # static pose
    "SPX": 8.0,      # spine_01 lean forward (slouch)
    "SP2": 4.0,      # spine_02 hunch
    "NKX": -6.0,     # neck back up (keep the face forward)
    "HDX": 4.0,      # head chin down
    "HDR": 7.0,      # head cock (roll)
    "HDT": -8.0,     # head turn toward the camera's left
    "ARMIN": 18.0,   # upper arms in toward the body
    "ARMFW": 22.0,   # upper arms forward
    "ELB": 25.0,     # forearms bent forward to the waistband
    "LEGOUT": 9.0,   # stance wider
    "KNEE": 0.0,     # knee bend (thigh forward)
    "TAILX": 0.0,
    # motion
    "CYC": 2,        # breaths per loop
    "LAG": 0.04,     # lag per step down a chain (loop fraction)
    "DIP": 0.010,    # body dip (model units, ~1.2 px)
    "SWAY": 0.006,   # weight shift side to side, once per loop
    "BRX": 1.6,      # spine breath bend (deg)
    "NOD": 2.0,      # head nod (deg)
    "ARMT": 4.0,     # pants tug: upper arm lift (deg)
    "ELBT": 5.0,     # pants tug: forearm (deg)
    "HOOD": 2.0,     # hood follow (deg)
    "STRIP": 5.0,    # trailing strips swing per joint (deg)
    "FLUT": 2.0,     # strips' faster flutter (deg)
    "FLAP": 4.0,     # hood side flaps
    "CREST": 3.0,    # crest / hair follow
    "TAILS": 5.0,    # tail sway
    "PFLAP": 2.5,    # pants front/back flaps
}

old = dict(cfg.get("pose_params", {}))
params = dict(DEFAULTS)
params.update({k: v for k, v in old.items() if k in DEFAULTS})
for a in sys.argv[1:]:
    k, v = a.split("=")
    params[k] = float(v) if "." in v else int(v)
for k in sorted(set(old) | set(params)):
    if old.get(k) != params.get(k):
        print(f"  {k}: {old.get(k)} -> {params.get(k)}")

P = []
add = lambda b, a, e: P.append([b, a, e])

# ---- static pose -------------------------------------------------------
add("spine_01", ax("spine_01", "y"), "-SPX")
add("spine_02", ax("spine_02", "y"), "-SP2")
add("neck", ax("neck", "y"), "-NKX")
add("head", ax("head", "y"), "-HDX")
add("head", ax("head", "z"), "HDR")
add("head", ax("head", "x"), "HDT")
# the hood hangs off spine_02, not the head: turn it with the head so the crest stays inside
add("cloth_sub", ax("head", "y"), "-HDX")
add("cloth_sub", ax("head", "z"), "HDR")
add("cloth_sub", ax("head", "x"), "HDT")
for side, s in (("left", 1), ("right", -1)):
    add(f"{side}_arm_01", "Y", f"{s}*ARMIN")
    add(f"{side}_arm_01", "X", "-ARMFW")
    add(f"{side}_arm_02", ax(f"{side}_arm_02", "y"), f"{s}*ELB")
    add(f"{side}_leg_01", "Y", f"{-s}*LEGOUT")
    add(f"{side}_leg_01", "X", "-KNEE")
    add(f"{side}_leg_02", "X", "KNEE")
    add(f"{side}_foot", "Y", f"{s}*LEGOUT")
add("tail_01", ax("tail_01", "y"), "TAILX")

# ---- idle --------------------------------------------------------------
# driver: br(t) one breath; everything else reads br at a later time
add("waist", "LOCZ", "-DIP*0.5*(1-cos(2*pi*CYC*t))")
add("waist", "LOCX", "SWAY*sin(2*pi*t)")
add("spine_01", ax("spine_01", "y"), "-BRX*br(t-LAG)")
add("spine_02", ax("spine_02", "y"), "-0.6*BRX*br(t-2*LAG)")
add("head", ax("head", "y"), "-NOD*br(t-3*LAG)")
add("head", ax("head", "z"), "0.6*NOD*sin(2*pi*(t-3*LAG))")
add("cloth_sub", ax("head", "y"), "-NOD*br(t-3*LAG)")
add("cloth_sub", ax("head", "z"), "0.6*NOD*sin(2*pi*(t-3*LAG))")
for side, s in (("left", 1), ("right", -1)):
    add(f"{side}_arm_01", "Y", f"{s}*ARMT*br(t-2*LAG)")
    add(f"{side}_arm_02", ax(f"{side}_arm_02", "y"), f"{s}*ELBT*br(t-3*LAG)")
    add(f"{side}_cloth_b", ax(f"{side}_cloth_b", "y"), f"FLAP*br(t-4*LAG)")
    add(f"{side}_cloth_d", ax(f"{side}_cloth_d", "y"), f"0.7*FLAP*br(t-4*LAG)")
    for i in (1, 2, 3):
        add(f"{side}_cloth_a_0{i}", ax(f"{side}_cloth_a_0{i}", "y"),
            f"{s}*STRIP*(0.6+0.3*{i})*br(t-(3+{i})*LAG) + {s}*FLUT*sin(2*pi*(2*CYC*t-{i}*0.15))*0.3*{i}")
        add(f"{side}_feeler_a_0{i}", ax(f"{side}_feeler_a_0{i}", "y"),
            f"{s}*STRIP*(0.5+0.3*{i})*br(t-(3+{i})*LAG) + {s}*FLUT*sin(2*pi*(2*CYC*t-{i}*0.15+0.3))*0.3*{i}")
add("left_cloth_e", ax("left_cloth_e", "y"), "FLAP*br(t-5*LAG)")
add("left_cloth_c", ax("left_cloth_c", "y"), "FLAP*br(t-5*LAG)")
add("right_cloth_a", ax("right_cloth_a", "y"), "-FLAP*br(t-5*LAG)")
add("cloth_a_01", ax("cloth_a_01", "y"), "-HOOD*br(t-4*LAG)")
add("cloth_a_03", ax("cloth_a_03", "y"), "-0.6*HOOD*br(t-5*LAG)")
add("feeler_a", ax("feeler_a", "y"), "-2*HOOD*br(t-6*LAG)")
add("cloth_b_01", ax("cloth_b_01", "y"), "HOOD*br(t-4*LAG)")
add("cloth_b_02", ax("cloth_b_02", "y"), "HOOD*br(t-5*LAG)")
add("hair_c_02", ax("hair_c_02", "y"), "-CREST*br(t-4*LAG)")
add("tail_01", ax("tail_01", "z"), "TAILS*0.5*sin(2*pi*(t-2*LAG))")
add("tail_02", ax("tail_02", "z"), "TAILS*0.7*sin(2*pi*(t-3*LAG))")
add("tail_03", ax("tail_03", "z"), "TAILS*sin(2*pi*(t-4*LAG))")
add("feeler_b", ax("feeler_b", "y"), "PFLAP*br(t-3*LAG)")
add("feeler_c", ax("feeler_c", "y"), "-PFLAP*br(t-3*LAG)")
for side in ("left", "right"):
    add(f"{side}_feeler_b", ax(f"{side}_feeler_b", "z"), "PFLAP*br(t-3*LAG)")

cfg["pose_params"] = params
cfg["pose"] = P
mo = cfg.setdefault("motion", {})
mo["frames"] = 120
mo["functions"] = {"br": "0.5*(1-cos(2*pi*CYC*t))"}
mo["plant"] = ["left_foot", "right_foot"]
CFG.write_text(json.dumps(cfg, indent=2) + "\n")
print(f"wrote {CFG.name}: {len(P)} pose entries")
