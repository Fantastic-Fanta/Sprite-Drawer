"""Writes pose / motion into mega_chandelure_front.json. Keeps existing pose_params values
(only adds missing ones) unless named in OVERRIDE; prints every change."""
import json, sys
from pathlib import Path

CFG = Path(__file__).parent / "mega_chandelure_front.json"
cfg = json.loads(CFG.read_text())

DEFAULTS = {
    "AZIMUTH": 70, "ELEVATION": 12, "FOV": 30,
    # pose: S-curved top flame, from the references
    "S_LO": 5.0, "S_HI": -7.0, "S_TIP": 5.0, "S_FB": 0.0,
    # motion
    "NF": 120, "PX_U": 0.033,
    "HOVER_PX": 2.0, "SKEW": 0.18,          # body bob, sprite px, 1 cycle / loop
    "DRIFT_PX": 0.8,                        # sideways drift, sprite px
    "ROCK_DEG": 1.2,                        # pendulum rock about the waist
    "ARM_DEG": 2.5, "ARM_LAG": 0.06, "ARM_RIP": 0.03,   # arms trail the bob
    "LEG_DEG": 2.0, "LEG_LAG": 0.09,                     # lower arms trail more
    "FLAME_DEG": 1.6, "FLAME_LAG": 0.08, "FLAME_RIP": 0.035,  # top flame trails the rock
    "FLICK_DEG": 1.2, "FLICK_C": 3, "FLICK_RIP": 0.06,       # top flame's own flutter
    "CANDLE_DEG": 4.0, "CANDLE_C": 3,                       # candle flames flutter
    "PEND_DEG": 4.0, "PEND_LAG": 0.12,                      # hanging pendant swings
}
OVERRIDE = {k.split("=")[0]: float(k.split("=")[1]) for k in sys.argv[1:]}

pp = cfg.setdefault("pose_params", {})
for k, v in DEFAULTS.items():
    if k in OVERRIDE:
        v = OVERRIDE[k]
        if pp.get(k) != v:
            print(f"  {k}: {pp.get(k)} -> {v}")
        pp[k] = v
    elif k not in pp:
        print(f"  {k}: (new) {v}")
        pp[k] = v

cfg["motion"]["functions"] = {
    # hover: crest broad, trough quick (wave skew), +y = up, sprite px
    "FY": "HOVER_PX*wave(t + 0.25, SKEW)",
    "FX": "DRIFT_PX*sin(2*pi*t)",
    "hn": "wave(t + 0.25, SKEW)",           # normalised bob, -1..1
    "rk": "sin(2*pi*(t - 0.05))",           # normalised rock (follows drift)
}

pose = []
# whole body: pixel bob (fraction rendered, whole px shifted by style.pixel_bob) + rock
pose += [["origin", "LOCCAM", "PX_U*(FY(t) - round(FY(t)))"],
         ["origin", "LOCCAMX", "PX_U*(FX(t) - round(FX(t)))"],
         ["waist", "ROLLCAM", "-ROCK_DEG*rk(t)"]]

# top flame: S curve (sideways = own z axis) + trailing sway + travelling flutter
Z, Y = "A:0,-1,0", "A:-1,0,0"
for i in range(1, 13):
    b = f"feeler_a_{i:02d}"
    rest = "S_LO" if 2 <= i <= 5 else ("S_HI" if 7 <= i <= 11 else ("S_TIP" if i == 12 else "0"))
    w = 0.5 + i / 12          # further up: more
    lag = f"(FLAME_LAG + {i}*FLAME_RIP)"
    pose.append([b, Z, f"{rest} + FLAME_DEG*{w:.3f}*rk(t - {lag}) + FLICK_DEG*{w:.3f}*sin(2*pi*(FLICK_C*t - {i}*FLICK_RIP))"])
    pose.append([b, Y, f"S_FB + 0.6*FLAME_DEG*{w:.3f}*hn(t - {lag}) + 0.7*FLICK_DEG*{w:.3f}*cos(2*pi*(FLICK_C*t - {i}*FLICK_RIP + 0.13))"])

# arms: bend about own y (+ = up); trail the bob, joints further out lag more
AXY = {"left_arm_a": "-0.71,-0.71,0", "right_arm_a": "-0.71,0.71,0",
       "left_arm_b": "0.71,-0.71,0", "right_arm_b": "0.71,0.71,0"}
for k, (arm, ax) in enumerate(AXY.items()):
    ph = 0.04 * k   # each arm a little off the others
    for j, wgt in [(1, 1.0), (5, 0.6)]:
        pose.append([f"{arm}_{j:02d}", f"A:{ax}", f"ARM_DEG*{wgt}*hn(t - ARM_LAG - {j}*ARM_RIP/4 - {ph:.2f})"])
    hand = arm.replace("arm", "hand")
    pose.append([f"{hand}_01", f"A:{ax}", f"ARM_DEG*0.35*hn(t - ARM_LAG - 3*ARM_RIP - {ph:.2f})"])
    # candle flame on the hand: flutter about both own side axes
    idx = arm.replace("arm", "index")
    zax = {"left_arm_a": "0.71,-0.71,0", "right_arm_a": "-0.71,-0.71,0",
           "left_arm_b": "0.71,0.71,0", "right_arm_b": "-0.71,0.71,0"}[arm]
    for j in (1, 2, 3):
        pose.append([f"{idx}_{j:02d}", f"A:{ax}", f"CANDLE_DEG*{0.4 + 0.3*j:.2f}*sin(2*pi*(CANDLE_C*t - {0.1*j + 0.27*k:.2f}))"])
        pose.append([f"{idx}_{j:02d}", f"A:{zax}", f"0.7*CANDLE_DEG*{0.4 + 0.3*j:.2f}*cos(2*pi*(CANDLE_C*t - {0.1*j + 0.27*k + 0.1:.2f}))"])

# lower arms (legs) + their little flames (foot_01/02): trail a beat more, flutter
LEGY = {"left_leg_a": "-0.92,-0.38,0", "right_leg_a": "-0.92,0.38,0", "left_leg_b": "-0.38,-0.92,0",
        "right_leg_b": "-0.38,0.92,0", "left_leg_c": "0.38,-0.92,0", "right_leg_c": "0.38,0.92,0",
        "left_leg_d": "0.92,-0.38,0", "right_leg_d": "0.92,0.38,0"}
LEGX = {"left_leg_a": "0.38,-0.92,0", "right_leg_a": "-0.38,-0.92,0", "left_leg_b": "0.92,-0.38,0",
        "right_leg_b": "-0.92,-0.38,0", "left_leg_c": "0.92,0.38,0", "right_leg_c": "-0.92,0.38,0",
        "left_leg_d": "0.38,0.92,0", "right_leg_d": "-0.38,0.92,0"}
for k, (leg, ax) in enumerate(LEGY.items()):
    ph = 0.03 * k
    pose.append([leg, f"A:{ax}", f"LEG_DEG*hn(t - LEG_LAG - {ph:.2f})"])
    foot = leg.replace("leg", "foot")
    for j in (1, 2):
        pose.append([f"{foot}_{j:02d}", f"A:{ax}", f"CANDLE_DEG*{0.5*j:.2f}*sin(2*pi*(CANDLE_C*t - {0.1*j + 0.19*k:.2f}))"])
        pose.append([f"{foot}_{j:02d}", f"A:{LEGX[leg]}", f"0.6*CANDLE_DEG*{0.5*j:.2f}*cos(2*pi*(CANDLE_C*t - {0.1*j + 0.19*k + 0.1:.2f}))"])

# pendant below: hangs, swings after the rock and bob
pose.append(["feeler_b", "A:0,-1,0", "PEND_DEG*rk(t - PEND_LAG)"])
pose.append(["feeler_b", "A:1,0,0", "0.5*PEND_DEG*hn(t - PEND_LAG)"])

old = len(cfg.get("pose", []))
cfg["pose"] = pose
cfg["style"]["pixel_bob"] = {"y": "FY(t)", "x": "FX(t)"}
print(f"pose: {old} -> {len(pose)} entries")
CFG.write_text(json.dumps(cfg, indent=2) + "\n")
