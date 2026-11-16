"""Write pose / motion / palette into mega_golurk_front.json.

Run:  /usr/local/bin/python3 mega-golurk-model/gen.py [KEY=value ...] [--out PATH]
Keeps existing pose_params (only DEFAULTS missing from the config are added); KEY=value overrides
one; every change is printed.
"""
import json, sys
from pathlib import Path

here = Path(__file__).parent
cfg_path = here / "mega_golurk_front.json"
out_path = cfg_path
args = sys.argv[1:]
if "--out" in args:
    i = args.index("--out"); out_path = Path(args[i + 1]); del args[i:i + 2]
cfg = json.loads(cfg_path.read_text())

DEFAULTS = {
    "AZIMUTH": 70, "ELEVATION": 8, "FOV": 30,
    # rest pose (HOME): right fist raised in front of the chest, left arm hanging
    "RSF": 30, "RSO": 10, "REB": 60, "RHT": 0, "RTW": 30, "RFC": 75, "LFC": 35,
    "LSO": 12, "LSF": 8, "LEB": 15,
    "LEGO": 5, "KNE": 12,
    "TRN": 0, "LEAN": 4,
    # motion amplitudes
    "BR": 1.2, "DIP": 0.03, "HB": 1.5, "AB": 2.0, "EB": 2.5, "FL": 3.0, "FL2": 2.0, "HN": 1.5,
}
pp = cfg.setdefault("pose_params", {})
for k, v in DEFAULTS.items():
    if k not in pp:
        print(f"add {k} = {v}"); pp[k] = v
for a in args:
    k, v = a.split("="); v = float(v)
    print(f"set {k}: {pp.get(k)} -> {v}"); pp[k] = v

cfg["model"] = "MegaGolurk/MegaGolurk_sprite.blend"   # copy without the rocket-punch fists
cfg["reference"] = "reference/home_render.png"
cfg["reference_source"] = "HOME render (rotomlabs) + Z-A official art (Poképedia), in reference/"
cfg["palette"]["parts"] = {
    "teal":   ["#386968", "#4c7d7d", "#699b9a", "#73a6a4", "#7fb1b0"],
    "purple": ["#7d4587", "#92599d", "#9d63a8", "#a86eb3", "#b378be"],
    "gold":   ["#cba25b", "#e2b871", "#eec37c", "#f9cf87", "#ffda92"],
    "glow":   ["#cfa45d", "#e5ba73", "#f0c57e", "#fbd189", "#ffdc95"],
    "bronze": ["#775d3a", "#8c724e", "#9a7f5c", "#a58a66", "#b09570"],
    "mark":   ["#2b2d31", "#393c40", "#484b50"],
}
cfg["parts"] = {
    "materials": {
        "body_a_00": "teal|mark", "body_b_00": "teal|mark",
        "body_a_01": "gold|bronze", "body_b_02": "gold",
        "body_a_02": "bronze|mark", "body_b_01": "bronze",
        "body_c": "purple|glow", "eye": "mark",
    },
    "default_material": "body_c",
    "albedo": {"teal": "#649695", "purple": "#92599d", "gold": "#e3b972", "glow": "#e4b46c",
               "bronze": "#937955", "mark": "#3c3c3c"},
}
cfg["camera"]["target"] = [0.0, 0.0, 2.05]
cfg.setdefault("style", {})["flat_parts"] = ["mark"]

W = "4*pi*t"          # two breaths per loop (120 f = 3.6 s)
def ph(p): return f"sin({W} - {p} - pi/2)"   # phase: frame 0 = lowest dip (deepest knee bend), so the hull spike cap (measured on frame 0) covers it
L, R = "left", "right"
pose = [
    # whole body: turn and a slight forward lean of the torso
    ["waist", "Z", "TRN"],
    ["waist_sub", "A:1,0,0", "LEAN"],
    # right arm raised, fist up in front of the chest
    ["right_arm_01", "A:0,0,1", "RTW"],
    ["right_arm_01", "A:1,0,0", "-RSF"],
    ["right_arm_01", "A:0,1,0", "RSO"],
    ["right_arm_02", "A:1,0,0", "-REB"],
    ["right_hand", "A:0,0,1", "RHT"],
    # fists: right clenched, left loosely curled
    *[[f"right_{f}_0{j}", "A:0,1,0", f"-RFC*{0.9 if j == 1 else 1.0}"] for f in ("index", "middle", "ring", "pinky") for j in (1, 2)],
    *[[f"left_{f}_0{j}", "A:0,1,0", f"LFC*{0.9 if j == 1 else 1.0}"] for f in ("index", "middle", "ring", "pinky") for j in (1, 2)],
    # left arm hanging a little out and forward
    ["left_arm_01", "A:0,1,0", "-LSO"],
    ["left_arm_01", "A:1,0,0", "-LSF"],
    ["left_arm_02", "A:1,0,0", "-LEB"],
    # wide stance
    ["left_leg_01", "A:0,1,0", "-LEGO"],
    ["right_leg_01", "A:0,1,0", "LEGO"],
    ["left_foot", "A:0,1,0", "LEGO"],
    # knees a little bent (a heavy stance; lets the planted legs take the breath)
    *[[f"{sd}_leg_01", "A:1,0,0", "-KNE"] for sd in ("left", "right")],
    *[[f"{sd}_leg_02", "A:1,0,0", "2*KNE"] for sd in ("left", "right")],
    *[[f"{sd}_foot", "A:1,0,0", "-KNE"] for sd in ("left", "right")],
    ["right_foot", "A:0,1,0", "-LEGO"],
    # --- idle: one driver (a slow heavy breath), the rest follows ---
    ["waist", "LOCZ", f"DIP*{ph(0.0)}"],
    ["waist_sub", "A:1,0,0", f"-BR*{ph(0.3)}"],
    ["head", "A:1,0,0", f"HB*{ph(0.8)}"],
    ["right_arm_01", "A:1,0,0", f"AB*{ph(0.7)}"],
    ["right_arm_02", "A:1,0,0", f"-EB*{ph(1.1)}"],
    ["left_arm_01", "A:0,1,0", f"AB*{ph(0.7)}"],
    ["left_arm_02", "A:1,0,0", f"-EB*{ph(1.1)}"],
    # gold glow orbs (horns) sway a beat later
    ["left_horn_a", "A:0,1,0", f"-HN*{ph(1.0)}"],
    ["right_horn_a", "A:0,1,0", f"HN*{ph(1.0)}"],
    ["left_horn_b", "A:0,1,0", f"-HN*{ph(1.4)}"],
    ["right_horn_b", "A:0,1,0", f"HN*{ph(1.4)}"],
]
# ghost flames: each joint of the flame chain bends a little, the free end lagging, plus a faster
# small flutter on top (light strands)
for side, sgn in ((L, 1), (R, -1)):
    for i, b in enumerate(range(4, 12)):
        lag = 1.2 + 0.35 * i
        pose.append([f"{side}_hair_a_{b:02d}", f"A:{0.12*sgn:.2f},-0.99,-0.07",
                     f"{'' if sgn > 0 else '-'}(FL*{ph(lag)} + FL2*sin(8*pi*t - {lag*1.6:.2f}))*{0.6 + 0.08*i:.2f}"])
    pose.append([f"{side}_hair_c", f"A:{0.66*sgn:.2f},-0.02,-0.75", f"FL*{ph(1.6)}"])
    for i, b in enumerate(range(1, 4)):
        pose.append([f"{side}_hair_c_{b:02d}", f"A:{-1*sgn:.2f},-0.05,-0.03",
                     f"{'' if sgn > 0 else '-'}(FL*0.6*{ph(1.0 + 0.4*i)} + FL2*0.6*sin(8*pi*t - {2 + i:.1f}))"])
    pose.append([f"{side}_hair_d", f"A:{-1*sgn:.2f},-0.09,-0.02", f"FL*0.5*{ph(1.3)}"])
cfg["pose"] = pose
cfg["motion"] = {
    "frames": 120,
    "note": ("Mega Golurk, a giant ghost golem: a slow, heavy, guarded idle. Rest pose = HOME render "
             "(right fist raised in front of the chest, left arm hanging, wide stance, flame wings "
             "spread). One driver: a slow breath, 2 per loop (120 f = 3.6 s): the body sinks and "
             "lifts ~1 px on bending legs (feet planted), the torso pitches, the head and both arms "
             "follow a beat later. The light ghost flames (wing chains, head flames) sway with a "
             "growing lag up the chain and flicker faster on top; the gold glow orbs bob after "
             "the body."),
    "plant": ["left_foot", "right_foot"],
}
out_path.write_text(json.dumps(cfg, indent=2) + "\n")
print("wrote", out_path)
