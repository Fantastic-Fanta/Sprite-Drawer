"""Write pose / pose_params / motion / palette into mega_absol_z_front.json.
Run: python3 gen.py [KEY=value ...]   Keeps existing pose_params unless overridden; prints changes."""
import json
import sys
from pathlib import Path

CFG = Path(__file__).with_name("mega_absol_z_front.json")
cfg = json.loads(CFG.read_text())

DEFAULTS = {
    "AZIMUTH": 62, "ELEVATION": 12, "FOV": 30,
    # rest pose (from HOME / official art: low, wide, wary stance, head down and turned)
    "FSPL": 12, "RSPL": 10,          # front / rear legs splayed out (deg)
    "FK": 16, "RK": 10,              # front / rear knee bend (deg)
    "BODYZ": -0.03,                  # body lowered to keep the paws on the ground
    "NK": 14, "HD": 6,               # neck / head lowered
    "HYAW": 12, "HROLL": 8,          # head turned to the viewer, tilted
    "WING": 0, "TAILR": 0,
    # motion
    "CYC": 2,                        # breaths per loop
    "DIP": 0.008, "BR": 1.5, "NB": 1.2, "HB": 1.0,
    "SW": 0.006,                     # weight shift side to side, once a loop
    "WB": 2.5, "WB2": 2.0, "WB3": 2.0, "WF": 1.5, "WC": 0.0, "CLAW": 0.0, "GRIP": 0.0,   # mane wing: root..tip lag, tip flutter
    "TB": 3.0,                       # tail blade
    "FB": 3.0,                       # feelers / hair strands
    "HN": 1.0, "HR": 1.5, "CF": 1.0,                       # horn follows the head
}

params = dict(DEFAULTS)
params.update({k: v for k, v in cfg.get("pose_params", {}).items() if k in DEFAULTS})
for arg in sys.argv[1:]:
    k, v = arg.split("=", 1)
    params[k] = float(v)
old = cfg.get("pose_params", {})
for k in params:
    if old.get(k) != params[k]:
        print(f"  {k}: {old.get(k)} -> {params[k]}")

NOTE = ("wary dark predator crouched low on four planted paws: slow, tense breathing (2 breaths a loop) drives everything; the body dips a little and shifts its weight side to side once a loop, the legs bend under it; neck, head and horn follow the chest a beat later; the big crimson mane-wing lags further, root to tip, its feather tips adding a faster small flutter; the bladed tail sways a beat after the hips; feelers and hair strands trail last")
W = "2*pi*CYC*t"  # breath phase
def br(amp, lag):
    return f"{amp}*sin({W} - {lag})"

ax = lambda v: "A:" + ",".join(f"{c:.2f}" for c in v)
X, mX = ax((1, 0, 0)), ax((-1, 0, 0))
pose = [
    # --- rest pose ---
    ["waist", "LOCZ", "BODYZ + DIP*sin(" + W + " - 0.3) "],
    ["waist", "LOCX", "SW*sin(2*pi*t)"],
    # front legs: upper arm forward, elbow back; splay outward; paw kept flat
    ["left_arm_01", X, "FK"], ["left_arm_02", X, "-2*FK"], ["left_hand", X, "FK"],
    ["right_arm_01", X, "FK"], ["right_arm_02", X, "-2*FK"], ["right_hand", X, "FK"],
    ["left_arm_01", ax((0, -1, 0)), "FSPL"], ["left_hand", ax((0, -1, 0)), "-FSPL"],
    ["right_arm_01", ax((0, -1, 0)), "-FSPL"], ["right_hand", ax((0, -1, 0)), "FSPL"],
    # rear legs
    ["left_leg_01", X, "-RK"], ["left_leg_02", X, "2*RK"], ["left_foot", X, "-RK"],
    ["right_leg_01", X, "-RK"], ["right_leg_02", X, "2*RK"], ["right_foot", X, "-RK"],
    ["left_leg_01", ax((0, -1, 0)), "RSPL"], ["left_toe", ax((0, -1, 0)), "-RSPL"],
    ["right_leg_01", ax((0, -1, 0)), "-RSPL"], ["right_toe", ax((0, -1, 0)), "RSPL"],
    # neck and head
    ["neck_01", X, "NK + " + br("NB", 0.8)],
    ["head", X, "HD + " + br("HB", 1.3)],
    ["head", ax((0, 0, 1)), "HYAW"],
    ["head", ax((0, -1, 0)), "HROLL"],
    # chest breath
    ["spine_02", X, "-" + br("BR", 0.4)],
    # horn trails the head
    ["horn", ax((-0.88, 0.41, 0.24)), br("HN", 1.8)],
    # tail blade: sways a beat after the hips
    ["tail", ax((0, 0, 1)), "TAILR + TB*sin(2*pi*t - 0.9)"],
    ["tail", X, br("TB*0.5", 1.2)],
]
# mane wing: root -> tip, each joint later and a bit bigger, tip strands flutter faster
wing_axis = ax((-0.43, -0.53, -0.73))
# a feathery claw (Cobblemon / HOME): it sways like fur, slow and soft - one wave per loop that
# travels root -> tip and across the feathers (each a little later), the tips curling on the second
# axis, plus a light faster ripple; not the breath's 2-per-loop beat.
# It is a claw: every feather is curled to one side (CLAW per joint, more toward the tip, about
# -wing_axis: the hooks arch over like fingers), and the curl tightens and opens a little once a
# loop (GRIP) as if reaching to grab. curl_axis is the feathers' other bend axis (not x: that
# twists them along their length).
curl_axis = ax((-0.06, 0.82, -0.56))
for i, (b, amp) in enumerate([("right_wing_01", "WB*0.4"), ("right_wing_02", "WB*0.6"),
                              ("right_wing_03", "WB2"), ("right_wing_04", "WB3")]):
    lag = 0.6 + 0.5 * i
    pose.append([b, wing_axis, ("WING + " if i == 0 else "") + f"{amp}*sin(2*pi*t - {lag:.2f})"])
    pose.append([b, curl_axis, f"0.5*WC*sin(2*pi*t - {lag + 0.9:.2f})"])
for j, s in enumerate("nopqrstuv"):
    for k in (1, 2, 3):
        lag = 2.0 + 0.55 * k + 0.22 * j
        e = (f"-CLAW*{k} - GRIP*{0.5 * k:.2f}*(0.5 + 0.5*sin(2*pi*t - {lag + 0.4:.2f}))"
             f" + WF*{0.5 + 0.35 * k:.2f}*sin(2*pi*t - {lag:.2f})"
             f" + 0.3*WF*sin(4*pi*t - {lag + 0.8:.2f})")
        pose.append([f"right_feeler_{s}_0{k}", wing_axis, e])
        pose.append([f"right_feeler_{s}_0{k}", curl_axis, f"WC*{0.4 * k:.2f}*sin(2*pi*t - {lag + 1.1:.2f})"])
# left small wing and feelers
for b, a, lag in [("left_wing_a", (0.41, -0.88, -0.23), 1.1), ("left_wing_b", (0.34, -0.93, -0.13), 1.6),
                  ("left_wing_c", (0.29, -0.95, -0.07), 1.6), ("left_wing_d", (0.55, -0.76, -0.35), 1.8)]:
    pose.append([b, ax(a), br("FB", lag)])
for b in ["left_feeler_a_01", "left_feeler_b", "left_feeler_c", "left_feeler_d", "left_feeler_e",
          "left_feeler_f", "left_feeler_h", "right_feeler_d", "right_feeler_f", "right_feeler_g",
          "right_feeler_h", "right_feeler_k", "right_feeler_l", "right_feeler_m",
          "right_feeler_a_01", "right_feeler_b", "right_feeler_c"]:
    pose.append([b, X, br("FB", 1.4)])
# hair strands hanging off the head, centre ruff
pose += [
    ["left_hair_01", ax((0.62, -0.78, 0.05)), br("HR*0.5", 1.6)], ["left_hair_02", ax((0.62, -0.78, 0.05)), br("HR*0.7", 1.9)],
    ["left_hair_03", ax((0.62, -0.78, 0.05)), br("HR", 2.2)], ["right_hair", X, br("HR", 1.8)],
    ["center_feeler_01", X, br("CF*0.5", 1.2)], ["center_feeler_02", X, br("CF*0.8", 1.5)],
]

cfg["pose"] = pose
cfg["pose_params"] = params
cfg["camera"]["azimuth"], cfg["camera"]["elevation"] = "AZIMUTH", "ELEVATION"
cfg["palette"]["parts"] = {
    "navy": ["#17243f", "#22355a", "#2f4870", "#405f8a"],   # HOME's mid navy, softer ramp
    "steel": ["#2f3a5e", "#4a5a88", "#6a7cad", "#93a3cf"],
    "red": ["#7a0a32", "#b50044", "#db2e62", "#f45a84"],
    "eye": ["#9a9a9a", "#c4c4c4", "#e2e2e2", "#ffffff"],
    "iris": ["#5e0012", "#9a0022", "#c8102e", "#e8455c"],
}
cfg["parts"] = {
    "materials": {"body_a": "navy|red|steel", "body_b": "navy|steel", "r_eye": "eye|iris|navy"},
    "default_material": "body_b_00",
    "match": "albedo",
    "albedo": {"navy": "#132f47", "steel": "#5e6683", "red": "#d81f5c", "eye": "#d2d2d2", "iris": "#b30027"},
}
cfg["reference"] = None
cfg["reference_source"] = "reference/home_sprite.png, reference/official_art.png (Poképédia)"
cfg["motion"]["frames"] = 120
cfg["motion"]["note"] = NOTE
cfg["motion"]["plant"] = ["left_hand", "right_hand", "left_toe", "right_toe"]
CFG.write_text(json.dumps(cfg, indent=2))
print("wrote", CFG, len(pose), "pose entries")
