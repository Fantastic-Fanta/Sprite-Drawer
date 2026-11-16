"""Write pose / pose_params / motion for Mega Delphox. Keeps existing pose_params unless
overridden: python3 gen.py [KEY=value ...] [--out PATH]. Prints every change."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = HERE / "mega_delphox_front.v1.json"
out = CFG
args = sys.argv[1:]
if "--out" in args:
    i = args.index("--out"); out = Path(args[i + 1]); del args[i:i + 2]

DEFAULTS = {
    "AZIMUTH": 70, "ELEVATION": 12, "FOV": 30,
    # rest pose
    "ARMD": 35, "ARMF": 15, "ELBF": 30, "ELBD": 15, "SLV": 65, "SLV2": 20,
    "HAIRD": 25, "HAIRB": 15, "HDT": 0, "HDU": 10,
    "SBX": 0.85, "SBY": -0.1, "SBZ": 1.9, "SBTX": -90, "SBTY": 45,
    "BIGT": 0, "BDF": 6,
    # idle
    "BOB": 0.03, "SPB": 1.5, "HB": 2.0, "AB": 3.0, "EB": 3.0, "SB": 6.0, "SB2": 5.0,
    "HRB": 4.0, "HRB2": 3.0, "TB": 4.0, "TB2": 4.0, "FB": 2.0,
    "WBOB": 0.04, "WROT": 4.0, "FLK": 6.0, "FLKS": 0.04,
}
cfg = json.loads(CFG.read_text())
old = dict(cfg.get("pose_params", {}))
params = dict(DEFAULTS)
params.update({k: v for k, v in old.items()})
for a in args:
    k, v = a.split("=", 1)
    params[k] = float(v)
for k in sorted(set(params) | set(old)):
    if old.get(k) != params.get(k):
        print(f"  {k}: {old.get(k)} -> {params.get(k)}")

W = "2*pi*t"          # one bob per loop (3.6 s)
pose = [
    # --- rest pose (from the Z-A render) ---
    ["head", "A:0,-1,0", "HDT"],
    ["head", "A:-1,0,0", "HDU"],
    ["left_arm_01", "A:0.03,-1.00,0", "-ARMD"],
    ["right_arm_01", "A:-0.03,-1.00,0", "ARMD"],
    ["left_arm_01", "A:0,0,1", "-ARMF"],
    ["right_arm_01", "A:0,0,-1", "-ARMF"],
    ["left_arm_02", "A:0,0,1", "-ELBF"],
    ["right_arm_02", "A:0,0,-1", "-ELBF"],
    ["left_arm_02", "A:-0.03,-1.00,0", "-ELBD"],
    ["right_arm_02", "A:0.03,-1.00,0", "ELBD"],
    ["left_feeler_c_01", "A:1,0,0", "-SLV"],
    ["right_feeler_c_01", "A:1,0,0", "-SLV"],
    ["left_feeler_c_02", "A:1,0,0", "-SLV2"],
    ["right_feeler_c_02", "A:1,0,0", "-SLV2"],
    ["left_hair_e_01", "A:0.26,-0.97,0", "-HAIRD"],
    ["right_hair_e_01", "A:-0.26,-0.97,0", "HAIRD"],
    ["left_hair_e_01", "A:0,0,1", "HAIRB"],
    ["right_hair_e_01", "A:0,0,-1", "HAIRB"],
    ["feeler_a", "A:0,0,1", "BIGT"],
    ["feeler_d_01", "A:-1,0,0", "BDF"],
    # small branches: up to head height either side, stick out and up, flame below
    ["feeler_b", "X", "SBTX"], ["feeler_b", "Y", "SBTY"],
    ["feeler_c", "X", "SBTX"], ["feeler_c", "Y", "-SBTY"],
    ["feeler_b", "LOCX", "SBX"], ["feeler_b", "LOCY", "SBY"], ["feeler_b", "LOCZ", "SBZ"],
    ["feeler_c", "LOCX", "-SBX"], ["feeler_c", "LOCY", "SBY"], ["feeler_c", "LOCZ", "SBZ+0.4"],
    # --- idle: hover bob drives; chest, head, arms, sleeves, hair, tail follow ---
    ["waist", "LOCZ", f"BOB*sin({W})"],
    ["spine_02", "A:-1,0,0", f"SPB*sin({W} - 0.6)"],
    ["head", "A:-1,0,0", f"-HB*sin({W} - 1.0)"],
    ["left_arm_01", "A:0.03,-1.00,0", f"AB*sin({W} - 1.0)"],
    ["right_arm_01", "A:-0.03,-1.00,0", f"-AB*sin({W} - 1.0)"],
    ["left_arm_02", "A:-0.03,-1.00,0", f"EB*sin({W} - 1.4)"],
    ["right_arm_02", "A:0.03,-1.00,0", f"-EB*sin({W} - 1.4)"],
    ["left_feeler_c_01", "A:1,0,0", f"SB*sin({W} - 1.6)"],
    ["right_feeler_c_01", "A:1,0,0", f"SB*sin({W} - 1.6)"],
    ["left_feeler_c_02", "A:1,0,0", f"SB2*sin({W} - 2.1)"],
    ["right_feeler_c_02", "A:1,0,0", f"SB2*sin({W} - 2.1)"],
    ["left_hair_e_01", "A:0.26,-0.97,0", f"HRB*sin({W} - 1.5)"],
    ["right_hair_e_01", "A:-0.26,-0.97,0", f"-HRB*sin({W} - 1.5)"],
    ["left_hair_e_03", "A:0.26,-0.97,0", f"HRB2*sin({W} - 2.0)"],
    ["right_hair_e_03", "A:-0.26,-0.97,0", f"-HRB2*sin({W} - 2.0)"],
    ["tail_01", "A:1,0,0", f"TB*sin({W} - 1.2)"],
    ["tail_02", "A:1,0,0", f"TB2*sin({W} - 1.7)"],
    ["feeler_d_01", "A:-1,0,0", f"FB*sin({W} - 1.2)"],
    # small branches drift on their own, half a beat apart
    ["feeler_b", "LOCZ", f"WBOB*sin({W} - 1.8)"],
    ["feeler_c", "LOCZ", f"WBOB*sin({W} - 0.6)"],
    ["feeler_b", "Y", f"WROT*sin({W} - 2.2)"],
    ["feeler_c", "Y", f"-WROT*sin({W} - 1.0)"],
    # flames: a light flicker, faster (3 per loop) on the flame wisps
    ["horn_a_01", "A:0,0,1", f"FLK*sin(3*{W})"],
    ["horn_a_02", "A:1,0,0", f"FLK*sin(3*{W} - 1.0)"],
    ["horn_d_01", "A:0,0,1", f"FLK*sin(3*{W} - 2.0)"],
    ["horn_e_01", "A:0,0,1", f"FLK*sin(3*{W} - 0.5)"],
]
cfg["pose_params"] = params
cfg["pose"] = pose
cfg["motion"] = {
    "frames": 120,
    "note": ("Floating witch on a flaming broom-branch (Z-A render): no feet touch anything, so "
             "nothing is planted. One driver: a slow hover bob of the body and its branch, one per "
             "3.6 s loop. The chest, head, then arms follow a beat later; the wizard sleeves, ear "
             "fur strands and robe tail lag most and move most. The two small wands drift on their "
             "own, offset, and the three flame tips flicker lightly at 3x the bob."),
}
out.write_text(json.dumps(cfg, indent=2) + "\n")
print("wrote", out)
