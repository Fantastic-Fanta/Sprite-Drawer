"""Write pose / pose_params / motion / palette into mega_pyroar_front.json.
Run: python3 gen.py [KEY=value ...]   Keeps existing pose_params unless overridden; prints changes."""
import json
import sys
from pathlib import Path

CFG = Path(__file__).with_name("mega_pyroar_front.json")
cfg = json.loads(CFG.read_text())

DEFAULTS = {
    "AZIMUTH": 70, "ELEVATION": 12, "FOV": 30,
    # rest pose (HOME / official art: proud roar, head up, mane tip swept back, tail curled up)
    "FK": 6, "RK": 6,                # front / rear knee bend (deg), kept shallow (hull spikes)
    "FSPL": 4, "RSPL": 3,            # legs splayed a little
    "BODYZ": -0.01,
    "NK": -10, "HD": -6,             # neck / head raised (negative = up)
    "HYAW": 14, "HROLL": 0,          # head turned to the viewer
    "JAW": 18,                       # mouth open (roar)
    "MB": 6, "MC": 9,                # mane spire swept back: root bend, curl per joint further out
    "TL": 22, "TC": 10,              # tail lifted, curl per joint
    # motion
    "CYC": 2, "PH": 2.77,            # breaths per loop, breath phase at frame 0
    "DIP": 0.006, "BR": 1.2, "NB": 1.0, "HB": 0.8, "JB": 2.0,
    "SW": 0.004,                     # weight shift side to side, once a loop
    "MS": 1.2,                       # mane spire sway (follows the head)
    "FL": 1.6, "TW": 1.3,            # mane flame flicker (fast, small); spire side twist
    "TB": 4.0,                       # tail sway
    "FB": 3.0, "FA": 1.5,             # fur tufts (thigh/rump, wrist)
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

NOTE = ("proud fire lion standing square on four planted paws, head up and mouth open as in the official art: "
        "slow deep breathing (2 breaths a loop) drives everything; the body dips a little and shifts its weight "
        "side to side once a loop, the legs bend under it; neck, head and jaw follow the chest a beat later; "
        "the tall flame-mane spire sways after the head, root to tip, and every mane flame adds a light fast "
        "flicker of its own; the curled tail sways a beat after the hips; fur tufts trail last")
W = "(2*pi*CYC*t + PH)"  # breath phase; PH puts frame 0 at the head-down extreme (hull spike cap is measured at frame 0)


def br(amp, lag):
    return f"{amp}*sin({W} - {lag})"


def fl(amp, k, lag):
    """flame flicker: k cycles a loop (integer, loops cleanly), plus a smaller 2k harmonic"""
    return f"{amp}*(sin({2*k}*pi*t - {lag}) + 0.4*sin({4*k}*pi*t - {lag*1.7:.2f}))"


ax = lambda v: "A:" + ",".join(f"{c:.2f}" for c in v)
X = ax((1, 0, 0))
pose = [
    ["waist", "LOCZ", "BODYZ + DIP*sin(" + W + " - 0.3)"],
    ["waist", "LOCX", "SW*sin(2*pi*t)"],
    # front legs (shallow bend so the elbow line stays clean)
    ["left_arm_01", X, "FK"], ["left_arm_02", X, "-2*FK"], ["left_hand", X, "FK"],
    ["right_arm_01", X, "FK"], ["right_arm_02", X, "-2*FK"], ["right_hand", X, "FK"],
    ["left_arm_01", ax((0, -1, 0)), "FSPL"], ["left_hand", ax((0, -1, 0)), "-FSPL"],
    ["right_arm_01", ax((0, -1, 0)), "-FSPL"], ["right_hand", ax((0, -1, 0)), "FSPL"],
    # rear legs
    ["left_leg_01", X, "-RK"], ["left_leg_02", X, "2*RK"], ["left_foot", X, "-RK"],
    ["right_leg_01", X, "-RK"], ["right_leg_02", X, "2*RK"], ["right_foot", X, "-RK"],
    ["left_leg_01", ax((0, -1, 0)), "RSPL"], ["left_toe", ax((0, -1, 0)), "-RSPL"],
    ["right_leg_01", ax((0, -1, 0)), "-RSPL"], ["right_toe", ax((0, -1, 0)), "RSPL"],
    # chest breath, neck and head follow
    ["spine_02", X, "-" + br("BR", 0.4)],
    ["neck_01", X, "NK"],
    ["neck_02", X, br("NB", 0.8)],  # breath on neck_02: on neck_01 it drew a hull spike (stray weight)
    ["head", X, "HD + " + br("HB", 1.2)],
    ["head", ax((0, 0, 1)), "HYAW"],
    ["head", ax((0, -1, 0)), "HROLL"],
    ["lower_jaw", X, "-JAW + " + br("JB", 1.571)],  # most open at frame 0 (hull spike cap is measured there)
    # tail: lifted and curled, sways after the hips
    ["tail_a_01", X, "TL + " + br("TB*0.3", 1.0)],
    ["tail_a_01", ax((0, 0, 1)), "TB*sin(2*pi*t - 0.9)"],
]
for i, b in enumerate(["tail_a_02", "tail_a_03", "tail_a_04", "tail_a_05", "tail_a_06", "tail_a_07"]):
    lag = 1.2 + 0.3 * i
    pose.append([b, X, f"TC*{(i + 1) / 3:.2f} + " + br(f"TB*{0.2 + 0.08 * i:.2f}", lag)])
    pose.append([b, ax((0, 0, 1)), f"TB*{0.3 + 0.1 * i:.2f}*sin(2*pi*t - {0.9 + 0.3 * (i + 1):.2f})"])
# mane spire: swept back root to tip, sways after the head, the tip flickers
for i, b in enumerate(["hair_a_01", "hair_a_02", "hair_a_03", "hair_a_04", "hair_a_05", "hair_a_06"]):
    rest = "MB" if i == 0 else f"MC*{i / 2.5:.2f}"
    pose.append([b, ax((-1, 0, 0)), f"{rest} + " + br(f"MS*{0.4 + 0.15 * i:.2f}", 1.5 + 0.3 * i)
                 + " + " + fl(f"FL*{0.15 * i:.2f}", 3, 0.5 + 0.6 * i)])
    pose.append([b, ax((0, -1, 0)), fl(f"TW*{0.1 + 0.1 * i:.2f}", 2, 1.1 + 0.5 * i)])
# side mane flames: each its own flicker (different phase), outer joint more
flames = [
    ("left_hair_a_01", "left_hair_a_02", (0, -1, 0), 0.0), ("right_hair_a_01", "right_hair_a_02", (0, -1, 0), 1.3),
    ("left_hair_b_01", "left_hair_b_02", (0.09, -1, -0.01), 2.1), ("right_hair_b_01", "right_hair_b_02", (-0.09, -1, -0.01), 3.4),
    ("left_hair_c_01", "left_hair_c_02", (0.22, -0.97, -0.02), 4.2), ("right_hair_c_01", "right_hair_c_02", (-0.22, -0.97, -0.02), 5.0),
    ("left_hair_d_01", "left_hair_d_02", (-0.01, -0.99, 0.10), 0.7), ("right_hair_d_01", "right_hair_d_02", (0.01, -0.99, 0.10), 2.6),
]
for b1, b2, a, ph in flames:
    pose.append([b1, ax(a), br("MS*0.5", 1.6) + " + " + fl("FL*0.6", 3, ph)])
    pose.append([b2, ax(a), br("MS*0.8", 1.9) + " + " + fl("FL", 3, ph + 0.6)])
# fur tufts (wrists, thighs, rump) trail last
pose += [
    ["left_feeler_a", ax((0, -1, 0)), br("FA", 1.6)], ["right_feeler_a", ax((0, -1, 0)), br("-FA", 1.7)],
    ["left_feeler_b", ax((0, -1, 0)), br("FB", 1.4)], ["right_feeler_b", ax((0, -1, 0)), br("-FB", 1.5)],
    ["feeler", X, br("FB", 1.3)],
]

cfg["pose"] = pose
cfg["pose_params"] = params
cfg["camera"]["azimuth"], cfg["camera"]["elevation"] = "AZIMUTH", "ELEVATION"
parts = cfg["palette"]["parts"]
if "tan2" in parts:  # eye whites / iris: rename
    parts["eye"] = parts.pop("tan2")
    cfg["parts"]["albedo"]["eye"] = cfg["parts"]["albedo"].pop("tan2")
    for m, v in cfg["parts"]["materials"].items():
        cfg["parts"]["materials"][m] = v.replace("tan2", "eye")
# material groups keyed so they also match the texture names (make_shiny matches groups to texture
# files): with no group the eye texture's dark pupils counted as brown and turned the shiny body orange.
# General keys first: render_sprite takes the last key that matches, so body_a_0x / l_eye still win.
mats = cfg["parts"]["materials"]
new = {"body_a": "brown|tan|red", "eye": "eye"}  # "eye": the eye texture only (l_eye / r_eye keys below win in the render)
new.update({k: v for k, v in mats.items() if k not in new and k != "body_b"})  # body_b = default (mane)
cfg["parts"]["materials"] = new
cfg["reference"] = None
cfg["reference_source"] = ("reference/home_render.png (serebii HOME 668-m), reference/official_art.jpg (pokemondb): "
                           "facing right, head up roaring, mane spire swept back, tail curled up")
cfg["motion"]["frames"] = 120
cfg["motion"]["note"] = NOTE
cfg["motion"]["plant"] = ["left_hand", "right_hand", "left_toe", "right_toe"]
CFG.write_text(json.dumps(cfg, indent=2))
print("wrote", CFG, len(pose), "pose entries")
