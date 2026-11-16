"""Writes pose / motion into mega_scolipede_front.json (or OUT=path), keeps existing params,
takes KEY=value overrides, prints every param change.
Usage: python3 gen.py [OUT=scratch/x.json] [KEY=value ...]
v2 (redo): a reared centipede poised to strike, not a deer. v1 is scratch-free in
mega_scolipede_front.v1.json."""
import json, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "mega_scolipede_front.json")

DEFAULTS = {
    # camera / rest pose
    "AZIMUTH": 50, "ELEVATION": 12, "FOV": 30,
    "SPL": 18.0,     # legs splayed out sideways (thigh out, shin back in): low, spidery stance
    "KNF": 10.0,     # knees flexed (thigh forward/back, shin the other way): a crouch
    "CURVE": 8.0,    # static S-curve along the segments (yaw), the body never a straight bar
    "LEAN": 8.0,     # whole torso pitched forward (front end down)
    "NKX": 14.0,     # neck_01 pitched forward (+ = forward/down)
    "NK2X": 6.0,     # neck_02 forward
    "NK3X": -10.0,   # neck_03 back: S curve, head held up and over
    "HDX": 6.0,      # head pitch at rest (+ = nose down, aimed at prey)
    "TAILX": -10.0,  # tail raised (rear horns up, scorpion-like)
    # idle amplitudes (deg / model units)
    "WV": 3.0,       # driver: lateral wave travelling up the body (spine -> neck)
    "WP": 1.5,       # pitch wave riding with it (segments heave in turn)
    "HS": 4.0,       # head sway (counter to the neck: it stays aimed)
    "HP2": 1.5,      # head pitch bob with the heave
    "LG": 7.0,       # leg ripple: thigh swing per leg, planted feet bend the knee
    "SH": 4.0,       # neck shell plates ripple
    "HP": 4.0,       # hanging front plate
    "CL": 6.0,       # waist side plates
    "TL": 5.0,       # tail sway
    "TW": 5.0,       # tail horn twitch
    "AT": 3.0,       # antenna twitch (head flick)
    "DIP": 0.012,    # body dip
}

# world X = pitch (bones lie in the YZ plane; + = front end down), world Y = lateral for the
# upright neck, world Z = lateral (yaw) for the lying spine
P, LN, LS = "A:1,0,0", "A:0,1,0", "A:0,0,1"
W = "2*pi*t"
# twitches: decaying flicks (damp) at fixed loop times, zero (and eased) outside
TW1 = "damp(((t - 0.18) % 1) / 0.30, 3)"
TW2 = "damp(((t - 0.62) % 1) / 0.28, 3)"

POSE = [
    # rest pose: crouched, torso leaning in, neck in an S, head aimed down at the prey
    # legs splayed out to the sides and the knees flexed; the foot bone takes the net turn
    # back so the soles stay flat (plant then holds them on the ground)
    ["left_arm_01", "A:0,1,0", "-SPL"], ["left_arm_02", "A:0,1,0", "0.6*SPL"],
    ["left_hand", "A:0,1,0", "0.4*SPL"],
    ["right_arm_01", "A:0,1,0", "SPL"], ["right_arm_02", "A:0,1,0", "-0.6*SPL"],
    ["right_hand", "A:0,1,0", "-0.4*SPL"],
    ["left_leg_01", "A:0,1,0", "-SPL"], ["left_leg_02", "A:0,1,0", "0.6*SPL"],
    ["left_foot_index", "A:0,1,0", "0.4*SPL"],
    ["right_leg_01", "A:0,1,0", "SPL"], ["right_leg_02", "A:0,1,0", "-0.6*SPL"],
    ["right_foot_index", "A:0,1,0", "-0.4*SPL"],
    ["left_arm_01", "A:1,0,0", "-KNF"], ["left_arm_02", "A:1,0,0", "2*KNF"], ["left_hand", "A:1,0,0", "-KNF"],
    ["right_arm_01", "A:1,0,0", "-KNF"], ["right_arm_02", "A:1,0,0", "2*KNF"], ["right_hand", "A:1,0,0", "-KNF"],
    ["left_leg_01", "A:1,0,0", "KNF"], ["left_leg_02", "A:1,0,0", "-2*KNF"], ["left_foot_index", "A:1,0,0", "KNF"],
    ["right_leg_01", "A:1,0,0", "KNF"], ["right_leg_02", "A:1,0,0", "-2*KNF"], ["right_foot_index", "A:1,0,0", "KNF"],
    ["spine_01", P, "LEAN"],
    ["neck_01", P, "NKX"],
    ["neck_02", P, "NK2X"],
    ["neck_03", P, "NK3X"],
    ["head", P, "HDX"],
    ["tail", P, "TAILX"],
    ["hips", LS, "0.6*CURVE"],
    ["spine_02", LS, "-0.6*CURVE"],
    ["spine_03", LS, "-0.6*CURVE"],
    ["neck_02", LN, "0.8*CURVE"],
    # driver: a lateral wave travels from the rear segments up the neck (each a beat later)
    ["hips", LS, f"-0.6*WV*sin({W})"],
    ["spine_01", LS, f"0.5*WV*sin({W} - 0.5)"],
    ["spine_02", LS, f"0.6*WV*sin({W} - 1.0)"],
    ["spine_03", LS, f"0.7*WV*sin({W} - 1.5)"],
    ["neck_01", LN, f"WV*sin({W} - 2.0)"],
    ["neck_02", LN, f"WV*sin({W} - 2.5)"],
    ["neck_03", LN, f"0.8*WV*sin({W} - 3.0)"],
    # pitch wave rides with it: segments heave in turn, twice a loop
    ["spine_02", P, f"WP*sin(2*{W} - 0.6)"],
    ["spine_03", P, f"WP*sin(2*{W} - 1.2)"],
    ["neck_01", P, f"-WP*sin(2*{W} - 1.8)"],
    ["neck_02", P, f"-WP*sin(2*{W} - 2.4)"],
    ["waist", "LOCZ", f"DIP*sin(2*{W} - 0.3)"],
    # head: sways against the neck so it stays aimed, poised; antennae flick with it
    ["head", LN, f"-HS*sin({W} - 3.4) + AT*({TW1} - 0.7*{TW2})"],
    ["head", P, f"-HP2*sin(2*{W} - 3.0) + 0.6*AT*{TW2}"],
    # legs ripple back to front: each pair a quarter loop after the one behind it
    ["right_leg_01", "A:1,0,0", f"LG*sin({W})"],
    ["left_leg_01", "A:1,0,0", f"LG*sin({W} - 1.57)"],
    ["right_arm_01", "A:1,0,0", f"LG*sin({W} - 3.14)"],
    ["left_arm_01", "A:1,0,0", f"LG*sin({W} - 4.71)"],
    # the feet keep their orientation (flat, toes put): undo what the bends above turned them by
    *[[f, LS, f"-(0.5*WV*sin({W} - 0.5) + 0.6*WV*sin({W} - 1.0) + 0.7*WV*sin({W} - 1.5))"]
      for f in ("left_hand", "right_hand")],
    *[[f, P, f"-(WP*sin(2*{W} - 0.6) + WP*sin(2*{W} - 1.2))"] for f in ("left_hand", "right_hand")],
    *[[f, LS, f"0.6*WV*sin({W})"] for f in ("left_foot_index", "right_foot_index")],
    ["right_foot_index", "A:1,0,0", f"-LG*sin({W})"],
    ["left_foot_index", "A:1,0,0", f"-LG*sin({W} - 1.57)"],
    ["right_hand", "A:1,0,0", f"-LG*sin({W} - 3.14)"],
    ["left_hand", "A:1,0,0", f"-LG*sin({W} - 4.71)"],
    # shell plates ripple up the neck, waist plates, front plate
    ["feeler_a", P, f"SH*sin({W} - 2.2)"],
    ["feeler_b", P, f"SH*sin({W} - 2.7)"],
    ["feeler_c", P, f"0.6*SH*sin({W} - 3.2)"],
    ["horn", P, f"HP*sin({W} - 3.4)"],
    ["left_cloth", "A:0,1,0", f"CL*sin({W} - 0.8)"],
    ["right_cloth", "A:0,1,0", f"-CL*sin({W} - 2.4)"],
    # tail horns: sway against the wave, plus a twitch of their own
    ["tail", LS, f"TL*sin({W} + 1.0)"],
    ["tail", P, f"0.6*TL*sin(2*{W} + 0.6) - TW*{TW2}"],
    ["tail", LS, f"TW*damp(((t - 0.40) % 1) / 0.28, 3)"],
]

NOTE = ("giant venomous centipede reared to strike, menacing not graceful: crouched low on its "
        "legs, torso leaning in, the neck in an S and the head held over it aimed down at prey. "
        "Driver: a slow lateral wave travels up the segmented body from the hips through the "
        "spine to the neck, with a heave riding along it; the legs ripple back to front, each a "
        "quarter loop after the one behind (planted feet, the knees take it); the head sways "
        "against the neck so it stays aimed, poised; the neck plates and waist plates ripple a "
        "beat later; the antennae (head) and the tail horns twitch in short decaying flicks")


def main():
    args = sys.argv[1:]
    out = SRC
    over = {}
    for a in args:
        k, v = a.split("=", 1)
        if k == "OUT":
            out = v if os.path.isabs(v) else os.path.join(HERE, v)
        else:
            over[k] = float(v)
    c = json.load(open(SRC))
    old = c.get("pose_params", {})
    new = dict(DEFAULTS)
    if c.get("motion", {}).get("note") == NOTE:   # keep params a v2 run already tuned
        new.update({k: v for k, v in old.items() if k in DEFAULTS})
    new.update(over)
    for k in sorted(set(old) | set(new)):
        if old.get(k) != new.get(k):
            print(f"  {k}: {old.get(k)} -> {new.get(k)}")
    c["pose_params"] = new
    c["pose"] = POSE
    c["reference"] = None
    c["reference_source"] = ("official Mega Scolipede art (reference/mega_scolipede_official_art.jpg); "
                             "v2 pose: crouched, neck in an S, head aimed to strike")
    c["motion"] = {"frames": 120, "note": NOTE,
                   "plant": ["left_hand", "right_hand", "left_foot_index", "right_foot_index"]}
    c["render"].setdefault("hull", {})["cap_each_frame"] = True
    c["style"]["height"] = 200
    # v2 stance throws the antennae forward: frame further forward so the tips never leave it
    c["camera"]["target"] = [0.0, -0.45, 1.45]
    c["camera"]["ortho_scale"] = 5.0
    if out != SRC:
        c["model"] = os.path.relpath(os.path.join(HERE, "MegaScolipede/MegaScolipede.blend"),
                                     os.path.dirname(out))
    json.dump(c, open(out, "w"), indent=2)
    print("wrote", out)


if __name__ == "__main__":
    main()
