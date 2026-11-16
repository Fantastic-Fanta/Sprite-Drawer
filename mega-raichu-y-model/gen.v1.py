"""Write pose / motion into mega_raichu_y_front.json. Keeps existing pose_params unless
overridden: python3 gen.py KEY=value ... (prints every change)."""
import json, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "mega_raichu_y_front.json")
cfg = json.load(open(CFG))

DEFAULTS = {
    "AZIMUTH": 80, "ELEVATION": 10, "FOV": 30,
    # rest pose (deg)
    "BODY": 0, "SPX": 0, "HDX": 0, "HDZ": 0,
    "LAU": 0, "LAB": 0, "LEL": 0, "RAU": 0, "RAB": 0, "REL": 0,
    "LTH": 0, "LKN": 0, "RTH": 0, "RKN": 0,
    "T1": 0, "TC": 0, "TY": 0, "T9": 0, "T10": 0, "TS": 0, "T9S": 0, "TR": 0,
    "LFE": 0, "JAW": 0, "RFE": 0,
    # motion amplitudes
    "BOB": 0.0, "BR": 0, "HB": 0, "AB": 0, "LB": 0, "TB": 0, "TB2": 0, "FB": 0, "FB2": 0, "EB": 0,
}
pp = cfg.get("pose_params", {})
for k, v in DEFAULTS.items():
    pp.setdefault(k, v)
for a in sys.argv[1:]:
    k, v = a.split("=")
    old = pp.get(k)
    pp[k] = float(v)
    print(f"{k}: {old} -> {pp[k]}")
cfg["pose_params"] = pp

W = "2*pi*t"   # one hover cycle per loop
pose = [
    # whole body lean (floating)
    ["waist", "X", "BODY"],
    ["spine_01", "A:0,-1,0", "SPX"],
    ["head", "A:-1,0,0", "HDX"],
    ["head", "Z", "HDZ"],
    # arms: up (about own forward axis), back (about up), elbow
    ["left_shoulder", "A:-0.58,-0.81,-0.13", "LAU"],
    ["left_shoulder", "A:-0.22,0,0.97", "LAB"],
    ["left_arm_02_roll", "A:-0.42,-0.91,0.03", "LEL"],
    ["right_shoulder", "A:0.58,-0.81,-0.13", "-RAU"],
    ["right_shoulder", "A:-0.22,0,-0.97", "RAB"],
    ["right_arm_02_roll", "A:0.42,-0.91,0.03", "-REL"],
    # legs: thigh lift / knee about lateral axis
    ["left_crotch", "A:1,0,0", "LTH"],
    ["left_leg_02", "A:1,0,0", "LKN"],
    ["right_crotch", "A:1,0,0", "RTH"],
    ["right_leg_02", "A:1,0,0", "RKN"],
    # tail: down at the root, curl along the cord, swing sideways, bolt
    ["tail_01", "A:1,0,0", "T1"],
    ["tail_01", "A:0,0,1", "TY"],
    ["tail_02", "A:1,0,0", "TC"], ["tail_03", "A:1,0,0", "TC"], ["tail_04", "A:1,0,0", "TC"],
    ["tail_05", "A:1,0,0", "TC"], ["tail_06", "A:1,0,0", "TC"], ["tail_07", "A:1,0,0", "TC"],
    ["tail_08", "A:1,0,0", "TC"],
    *[[f"tail_0{i}", "A:0,0,1", "TS"] for i in range(2, 9)],
    ["tail_09", "A:0,0,1", "T9S"],
    ["tail_10", "A:0,1,0", "TR"],
    ["tail_09", "A:1,0,0", "T9"],
    ["tail_10", "A:1,0,0", "T10"],
    ["lower_jaw_01", "A:1,0,0", "JAW"],
    # big bolt feelers on the head
    ["left_feeler_a_01", "A:0.17,-0.98,0.03", "LFE"],
    ["right_feeler_a_01", "A:-0.17,-0.98,0.03", "-RFE"],
    # ---- motion: hover bob drives; everything else follows a beat later ----
    ["waist", "LOCZ", f"BOB*sin({W})"],
    ["spine_01", "A:0,-1,0", f"-BR*sin({W} - 0.4)"],
    ["head", "A:-1,0,0", f"HB*sin({W} - 0.8)"],
    ["left_shoulder", "A:-0.58,-0.81,-0.13", f"-AB*sin({W} - 0.9)"],
    ["right_shoulder", "A:0.58,-0.81,-0.13", f"AB*sin({W} - 0.9)"],
    ["left_arm_02_roll", "A:-0.42,-0.91,0.03", f"-EB*sin({W} - 1.3)"],
    ["right_arm_02_roll", "A:0.42,-0.91,0.03", f"EB*sin({W} - 1.3)"],
    ["left_leg_01", "A:1,0,0", f"LB*sin({W} - 1.0)"],
    ["right_leg_01", "A:1,0,0", f"LB*sin({W} - 1.2)"],
    ["left_leg_02", "A:1,0,0", f"LB*sin({W} - 1.5)"],
    ["right_leg_02", "A:1,0,0", f"LB*sin({W} - 1.7)"],
    ["tail_01", "A:1,0,0", f"TB*sin({W} - 1.0)"],
    ["tail_03", "A:1,0,0", f"TB*sin({W} - 1.4)"],
    ["tail_05", "A:1,0,0", f"TB*sin({W} - 1.8)"],
    ["tail_07", "A:1,0,0", f"TB*sin({W} - 2.2)"],
    ["tail_09", "A:1,0,0", f"TB2*sin({W} - 2.6)"],
    ["tail_10", "A:0,0,1", f"TB2*sin({W} - 3.0) + 0.3*TB2*sin(2*{W} - 3.4)"],
    ["left_feeler_a_01", "A:0.17,-0.98,0.03", f"FB*sin({W} - 1.2)"],
    ["left_feeler_a_03", "A:0.17,-0.99,0.03", f"FB2*sin({W} - 1.7) + 0.3*FB2*sin(2*{W} - 2.0)"],
    ["right_feeler_a_01", "A:-0.17,-0.98,0.03", f"-FB*sin({W} - 1.2)"],
    ["right_feeler_a_03", "A:-0.17,-0.99,0.03", f"-FB2*sin({W} - 1.7) - 0.3*FB2*sin(2*{W} - 2.0)"],
    ["left_ear_01", "A:0.38,-0.92,0.11", f"0.6*FB*sin({W} - 1.0)"],
    ["right_ear_01", "A:-0.38,-0.92,0.11", f"-0.6*FB*sin({W} - 1.0)"],
    ["left_feeler_d_01", "A:-0.18,-0.86,0.48", f"FB*sin({W} - 1.4)"],
    ["right_feeler_d_01", "A:0.18,-0.86,0.48", f"-FB*sin({W} - 1.4)"],
]
# "A:" rotates about a fixed world axis at the moment the entry runs, so a rest-pose bone axis is
# only the bone's own axis while its parents are still at rest: apply the deepest bones first.
depth = {}
for line in open(os.path.join(HERE, "RIG.md")):
    if "head=(" in line and "axes" in line:
        depth[line.split()[0]] = len(line) - len(line.lstrip())
order = sorted(range(len(pose)), key=lambda i: -depth.get(pose[i][0], 0))
pose = [pose[i] for i in order]
cfg["pose"] = pose
json.dump(cfg, open(CFG, "w"), indent=2)
print("wrote", CFG)
