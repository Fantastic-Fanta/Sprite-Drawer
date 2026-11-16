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
    "AZIMUTH": 60, "ELEVATION": 10, "FOV": 30,
    # rest pose: both arms hanging, mirrored (v2: no raised fist)
    "LSO": 14, "LSF": 6, "LEB": 14, "LFC": 35, "HTN": 0,
    "LEGO": 5, "KNE": 10,
    "TRN": 0, "LEAN": 3,
    # motion amplitudes (v2: small and heavy)
    "BR": 0.6, "DIP": 0.0, "HB": 1.0, "HY": 0.6, "AB": 1.2, "EB": 1.4, "FL": 1.8, "FL2": 0.8,
    "HN": 1.0, "OP": 0.02, "HG": 4.0, "LC": 1.0,
}
OBSOLETE = ["RSF", "RSO", "REB", "RHT", "RTW", "RFC"]   # v1 raised right arm
pp = cfg.setdefault("pose_params", {})
for k in OBSOLETE:
    if k in pp: print(f"drop {k} = {pp.pop(k)}")
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

W = "2*pi*t"          # one slow breath per loop (120 f = 3.6 s)
def ph(p): return f"sin({W} - {p} - pi/2)"   # frame 0 = bottom of the breath
L, R = "left", "right"
pose = [
    # whole body: turn and a slight forward lean of the torso
    ["waist", "Z", "TRN"],
    ["waist_sub", "A:1,0,0", "LEAN"],
    ["head", "Z", "HTN"],
    # both arms hanging a little out and forward, mirrored
    ["left_arm_01", "A:0,1,0", "-LSO"],
    ["right_arm_01", "A:0,1,0", "LSO"],
    *[[f"{sd}_arm_01", "A:1,0,0", "-LSF"] for sd in (L, R)],
    *[[f"{sd}_arm_02", "A:1,0,0", "-LEB"] for sd in (L, R)],
    # fists loosely curled, mirrored
    *[[f"left_{f}_0{j}", "A:0,1,0", f"LFC*{0.9 if j == 1 else 1.0}"] for f in ("index", "middle", "ring", "pinky") for j in (1, 2)],
    *[[f"right_{f}_0{j}", "A:0,1,0", f"-LFC*{0.9 if j == 1 else 1.0}"] for f in ("index", "middle", "ring", "pinky") for j in (1, 2)],
    # wide stance, feet levelled
    ["left_leg_01", "A:0,1,0", "-LEGO"],
    ["right_leg_01", "A:0,1,0", "LEGO"],
    ["left_foot", "A:0,1,0", "LEGO"],
    ["right_foot", "A:0,1,0", "-LEGO"],
    # knees a little bent; the foot bend cancels the leg bends so the soles stay flat
    *[[f"{sd}_leg_01", "A:1,0,0", "-KNE"] for sd in (L, R)],
    *[[f"{sd}_leg_02", "A:1,0,0", "2*KNE"] for sd in (L, R)],
    *[[f"{sd}_foot", "A:1,0,0", "-KNE"] for sd in (L, R)],
    # --- idle: one driver (a slow heavy breath / hum), the rest follows late ---
    ["waist", "LOCZ", f"DIP*{ph(0.0)}"],
    ["waist_sub", "A:1,0,0", f"-BR*{ph(0.0)}"],
    # legs take back the chest pitch so the feet stay put
    *[[f"{sd}_leg_01", "A:1,0,0", f"LC*BR*{ph(0.0)}"] for sd in (L, R)],
    ["head", "A:1,0,0", f"HB*{ph(0.6)}"],
    ["head", "Z", f"HY*sin({W} - 1.2)"],
    # arms: a small, late, heavy sway (shoulder, then elbow later)
    ["left_arm_01", "A:1,0,0", f"AB*{ph(0.9)}"],
    ["right_arm_01", "A:1,0,0", f"AB*{ph(1.0)}"],
    ["left_arm_02", "A:1,0,0", f"-EB*{ph(1.5)}"],
    ["right_arm_02", "A:1,0,0", f"-EB*{ph(1.6)}"],
    # gold glow orbs: sway a beat later and pulse a little (the glow)
    ["left_horn_a", "A:0,1,0", f"-HN*{ph(1.0)}"],
    ["right_horn_a", "A:0,1,0", f"HN*{ph(1.0)}"],
    ["left_horn_b", "A:0,1,0", f"-HN*{ph(1.4)}"],
    ["right_horn_b", "A:0,1,0", f"HN*{ph(1.4)}"],
    # hip flames (hair_g) drift a little after the body
    ["left_hair_g", "A:0,1,0", f"-HG*{ph(1.2)}"],
    ["right_hair_g", "A:0,1,0", f"HG*{ph(1.2)}"],
    ["left_horn_b", "SCALE", f"1 + OP*{ph(0.4)}"],
    ["right_horn_b", "SCALE", f"1 + OP*{ph(0.4)}"],
]
# ghost flames: each joint of the flame chain bends a little, the free end lagging, plus a faster
# small flutter on top (light strands)
for side, sgn in ((L, 1), (R, -1)):
    for i, b in enumerate(range(4, 12)):
        lag = 1.2 + 0.35 * i
        pose.append([f"{side}_hair_a_{b:02d}", f"A:{0.12*sgn:.2f},-0.99,-0.07",
                     f"{'' if sgn > 0 else '-'}(FL*{ph(lag)} + FL2*sin(6*pi*t - {lag*1.6:.2f}))*{0.6 + 0.08*i:.2f}"])
    pose.append([f"{side}_hair_c", f"A:{0.66*sgn:.2f},-0.02,-0.75", f"FL*{ph(1.6)}"])
    for i, b in enumerate(range(1, 4)):
        pose.append([f"{side}_hair_c_{b:02d}", f"A:{-1*sgn:.2f},-0.05,-0.03",
                     f"{'' if sgn > 0 else '-'}(FL*0.6*{ph(1.0 + 0.4*i)} + FL2*0.6*sin(6*pi*t - {2 + i:.1f}))"])
    pose.append([f"{side}_hair_d", f"A:{-1*sgn:.2f},-0.09,-0.02", f"FL*0.5*{ph(1.3)}"])
cfg["pose"] = pose
cfg["motion"] = {
    "frames": 120,
    "note": ("Mega Golurk, a huge rocky ghost mech: it barely moves. Rest pose = official art with "
             "the raised fist lowered: both arms hang, mirrored; wide stance, both feet flat and "
             "planted on one ground plane. One driver: one slow breath/hum per loop (120 f = 3.6 s): "
             "the chest pitches a fraction of a degree (the legs take it back, feet still), the head "
             "nods and turns slightly a beat later, the heavy arms sway late (shoulder, then elbow), "
             "the gold glow orbs pulse and sway after the body, the ghost flames drift slowly with a "
             "lag up the chain."),
    "plant": ["left_foot", "right_foot"],
}
cfg["style"]["height"] = 200
cfg["render"].setdefault("hull", {})["cap_each_frame"] = True
out_path.write_text(json.dumps(cfg, indent=2) + "\n")
print("wrote", out_path)
