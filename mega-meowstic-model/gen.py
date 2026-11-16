"""Write palette / parts / camera / pose / pose_params / motion for Mega Meowstic.
Keeps existing pose_params unless overridden: python3 gen.py [KEY=value ...] [--out PATH].
Prints every change. Note: "A:x,y,z" rotates about a WORLD axis at the bone's posed head, in list order."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = HERE / "mega_meowstic_front.json"
out = CFG
args = sys.argv[1:]
reset = "--reset" in args
if reset:
    args.remove("--reset")
if "--out" in args:
    i = args.index("--out"); out = Path(args[i + 1]); del args[i:i + 2]

DEFAULTS = {
    "AZIMUTH": 70, "ELEVATION": 12, "FOV": 30,
    "TX": 0.0, "TZ": 0.42, "OS": 2.0,
    # rest pose
    "ARMD": 55, "ARMF": 30, "ELBF": 35, "ELBD": 0, "HDT": 4, "HDU": 4,
    "LEGB": 6, "LEGS": 4, "FOOTP": 25,
    "TAD": 95, "TAC": 14, "TAS": -10,   # thin tail (tail_a): down, curl per joint, side swing
    "TBD": 100, "TBC": 22, "TBS": 18,   # fluffy tail (tail_b)
    "EARO": 0,
    # idle
    "BOB": 0.025, "SPB": 1.5, "HB": 2.0, "EB": 2.5, "EB2": 3.0, "AB": 4.0, "EBW": 4.0,
    "LB": 3.0, "LB2": 3.0, "HRB": 3.0, "HRB2": 3.0, "CB": 3.0, "SKB": 3.0,
    "TS1": 3.0, "TS2": 2.5, "TF": 1.5, "TAM": 0.75, "TBM": 1.3,
}
cfg = json.loads(CFG.read_text())
old = dict(cfg.get("pose_params", {}))
params = dict(DEFAULTS)
if not reset:
    params.update({k: v for k, v in old.items()})
for a in args:
    k, v = a.split("=", 1)
    params[k] = float(v)
for k in sorted(set(params) | set(old)):
    if old.get(k) != params.get(k):
        print(f"  {k}: {old.get(k)} -> {params.get(k)}")

W = "2*pi*t"          # one hover bob per loop (3.6 s)

# --- palette: every part its own shades (shiny swap) ---
cfg["palette"] = {
    "outline": "#091019",
    "parts": {
        "silver": ["#afafae", "#c5c5c4", "#d0d0d0", "#dbdcdb", "#e7e7e6"],
        "blue": ["#2c4b74", "#3f5f89", "#496994", "#52739e", "#5c7ea9"],
        "mark": ["#8e9250", "#b1b67d", "#d2d672", "#eff070", "#fcfc6d"],
        "eye": ["#4f9fb4", "#62b4c8", "#72c3d7", "#86d0e1", "#9cdcea"],
    },
}
cfg["parts"] = {
    "materials": {
        "l_eye_a": "eye",
        "r_eye_a": "eye",
        "eye_b": "mark",
        "body_b": "silver|blue",
        "body_a": "silver|blue",
    },
    "default_material": "body_a",
    "albedo": {"silver": "#c6c6c6", "blue": "#40608a", "mark": "#d2d672", "eye": "#72c3d7"},
}
cfg["camera"]["target"] = ["TX", 0.0, "TZ"] if False else [params["TX"], 0.0, params["TZ"]]
cfg["camera"]["ortho_scale"] = params["OS"]

pose = [
    # --- rest pose (Z-A render): floating, legs dangling, arms in, tails hanging and curling ---
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
    ["left_leg_01", "A:1,0,0", "LEGB"],
    ["right_leg_01", "A:1,0,0", "LEGB"],
    ["left_leg_01", "A:0,1,0", "-LEGS"],
    ["right_leg_01", "A:0,1,0", "LEGS"],
    ["left_foot", "A:1,0,0", "FOOTP"],
    ["right_foot", "A:1,0,0", "FOOTP"],
    ["left_ear_01", "A:0,1,0", "EARO"],
    ["right_ear_01", "A:0,1,0", "-EARO"],
    # tails: base points back (+Y); bend down about X, swing sideways, then curl about Y
    ["tail_a_01", "A:1,0,0", "-TAD"],
    ["tail_a_01", "A:0,1,0", "TAS"],
] + [[f"tail_a_0{i}", "A:0,1,0", f"TAC*{k}"] for i, k in zip(range(3, 8), (0.2, 0.5, 0.8, 1.0, 1.2))] + [
    ["tail_b_01", "A:1,0,0", "-TBD"],
    ["tail_b_01", "A:0,1,0", "TBS"],
] + [[f"tail_b_0{i}", "A:0,1,0", f"TBC*{k}"] for i, k in zip(range(2, 6), (0.2, 0.6, 1.0, 1.4))] + [
    # --- idle: psychic hover bob drives; chest, head, arms, ears, hair, collar, skirt and
    #     the two tails follow a beat later, the tail tips lagging most ---
    ["waist", "LOCZ", f"BOB*sin({W})"],
    ["spine", "A:-1,0,0", f"SPB*sin({W} - 0.6)"],
    ["head", "A:-1,0,0", f"-HB*sin({W} - 1.0)"],
    ["left_ear_01", "A:-1,0,0", f"EB*sin({W} - 1.4)"],
    ["right_ear_01", "A:-1,0,0", f"EB*sin({W} - 1.6)"],
    ["left_ear_02", "A:-1,0,0", f"EB2*sin({W} - 1.9)"],
    ["right_ear_02", "A:-1,0,0", f"EB2*sin({W} - 2.1)"],
    ["left_arm_01", "A:0.03,-1.00,0", f"AB*sin({W} - 1.0)"],
    ["right_arm_01", "A:-0.03,-1.00,0", f"-AB*sin({W} - 1.0)"],
    ["left_arm_02", "A:0,0,1", f"-EBW*sin({W} - 1.4)"],
    ["right_arm_02", "A:0,0,-1", f"-EBW*sin({W} - 1.4)"],
    # dangling legs swing a little after the bob
    ["left_leg_01", "A:1,0,0", f"LB*sin({W} - 1.2)"],
    ["right_leg_01", "A:1,0,0", f"LB*sin({W} - 1.5)"],
    ["left_foot", "A:1,0,0", f"LB2*sin({W} - 1.8)"],
    ["right_foot", "A:1,0,0", f"LB2*sin({W} - 2.1)"],
    # hair strands over the face (light)
    ["feeler_i", "A:-1,0,0", f"HRB*sin({W} - 1.5)"],
    ["feeler_j_02", "A:-1,0,0", f"HRB2*sin({W} - 2.0)"],
    ["feeler_k_02", "A:0,1,0", f"HRB2*sin({W} - 2.0)"],
    ["feeler_l_02", "A:0,0,1", f"HRB2*sin({W} - 2.1)"],
    ["feeler_g_02", "A:0,0,1", f"HRB2*sin({W} - 1.9)"],
    ["feeler_h_02", "A:0,0,1", f"HRB2*sin({W} - 2.0)"],
    ["feeler_b_04", "A:0,0,1", f"-HRB2*sin({W} - 2.0)"],
    # collar flaps
    ["feeler_c_01", "A:-1,0,0", f"CB*sin({W} - 1.3)"],
    ["feeler_d_01", "A:-1,0,0", f"CB*sin({W} - 1.4)"],
    ["feeler_e_02", "A:0,1,0", f"CB*sin({W} - 1.5)"],
    # hip skirt flaps
    ["feeler_m", "A:0,1,0", f"-SKB*sin({W} - 1.3)"],
    ["feeler_n", "A:0,1,0", f"-SKB*sin({W} - 1.5)"],
    ["feeler_o", "A:0,1,0", f"SKB*sin({W} - 1.4)"],
    # tails: slow sway, each joint later; tips also get a small flutter
    ["tail_a_01", "A:0,1,0", f"TAM*TS1*sin({W} - 1.2)"],
    ["tail_a_03", "A:0,1,0", f"TAM*TS2*sin({W} - 1.7)"],
    ["tail_a_05", "A:0,1,0", f"TAM*TS2*sin({W} - 2.2)"],
    ["tail_a_07", "A:0,1,0", f"TAM*TF*sin(2*{W} - 2.6)"],
    ["tail_b_01", "A:0,1,0", f"TBM*-TS1*sin({W} - 1.0)"],
    ["tail_b_02", "A:1,0,0", f"TBM*TS2*sin({W} - 1.5)"],
    ["tail_b_03", "A:0,1,0", f"TBM*-TS2*sin({W} - 2.0)"],
    ["tail_b_05", "A:0,1,0", f"TBM*-TF*sin(2*{W} - 2.5)"],
]
cfg["pose_params"] = params
cfg["pose"] = pose
cfg.setdefault("motion", {})
cfg["motion"] = {
    "frames": 120,
    "note": ("Mega Meowstic floats on its psychic power (Z-A render: legs dangling, two long tails "
             "hanging and curling below): nothing touches the ground, so nothing is planted. One "
             "driver: a slow hover bob, one per 3.6 s loop. The chest and head follow a beat later, "
             "then the big ears, arms and dangling legs; the light hair strands, collar and hip "
             "flaps lag more, and the two tails sway slowest and most, their tips last with a "
             "small flutter."),
}
cfg["reference"] = None
cfg["reference_source"] = "reference/mega_male.png, mega_female.png (Legends Z-A in-game renders, rotomlabs.net)"
out.write_text(json.dumps(cfg, indent=2) + "\n")
print("wrote", out)
