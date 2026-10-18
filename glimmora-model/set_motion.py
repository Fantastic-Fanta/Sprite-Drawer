"""Write Mega Glimmora's motion (round 9: float, drift, sway, shake, menacing spin) into configs.

Run:  python3 set_motion.py glimmora_front.json [glimmora_back.json ...]
Replaces pose_params' motion numbers, motion.functions, the motion part of pose, style.pixel_bob
and style.fast_frames; the camera / view numbers (AZIMUTH, ELEVATION, FOV, YAW, PITCH, ROLL,
petal rest pose, crown fit) are left as they are. The replaced values go to motion_previous.

Measured on Showdown's floating sprites (in-page, see SPRITE_PIPELINE.md round 9): base Glimmora
bobs 6.7 % of its height over 90 frames (2.7 s), drifts 5.5 px sideways a third of a cycle behind
the bob, hangs at the top and turns quicker at the bottom, rocks a few degrees; Bronzong 8.5 % /
79 frames, Claydol 7 % / 79, Cosmoem 13 % / 89 with a sideways orbit and +-20 deg rock.
"""
import json
import sys
from pathlib import Path

N = 270                  # 8.1 s at 30 ms: three 90-frame floats, one shake, one spin
SPIN_F0 = 150            # the spin event: frames 150-239, exactly one float cycle long, so the
                         # frames either side of it (stabilised as one loop) still match

PARAMS = {
    "NF": N, "CYC": 3,
    # float: crest at frame 0 (= Showdown's still, held on a whole pixel: 3.5 + 0.5 = 4)
    "FLOAT_A": 3.5, "FLOAT_C": 0.5, "SKEW": 0.18,
    "DRIFT_A": 2.5,                     # sideways, a quarter cycle behind: an egg-shaped orbit
    "TILT_DEG": 3.0,                    # pendulum rock: leans out at the ends of the drift
    "LAG_F": 2.5, "RIP_F": 0.25,        # petals trail the body (frames), a little more round the ring
    "BREATH_OPEN": 15, "BREATH_SCALE": 0.08,
    # shake (slow frames, hanging at the crest of the second float): whole-pixel rattle + bristle
    "SHAKE_F0": 78, "SHAKE_F": 26, "SHAKE_K": 13, "SHAKE_PX": 2,
    "BRISTLE_DEG": 6, "BRISTLE_OUT": 0.05,
    # spin: charge (crown clenches, petals tuck and wind back, body dips and trembles), release
    # (snap, petals fling out, crown flares, body rises and counter-rolls), coast, settle wobble
    "SPIN_F0": SPIN_F0, "CHARGE_F": 20, "RELEASE_F": 6,
    "WIND_DEG": 40, "SPIN_DEG": 720, "SPIN_F": 56, "SPIN_SNAP": 0.7,
    "OVER_DEG": 26, "OVER_F0": 64, "OVER_F": 25,
    "FLARE_HOLD": 46, "FLARE_FALL": 34,
    "LIFT_PX": 3, "DIP_PX": 2, "CLOSE_DEG": 8, "FLARE_DEG": 14, "FLING": 0.12, "TUCK": 0.08,
    "SPIN_ROLL": 4, "TREMBLE_PX": 1, "TREMBLE_K": 9,
}
OBSOLETE = ["SPIN_T0", "SPIN_LEN", "SPIN_DELAY", "WIND_LEN", "OVER_T0", "OVER_LEN", "LAG_PH",
            "RIPPLE", "FLOAT_PH", "FLOAT_PX"]

FUNCTIONS = {
    "rs": "t*NF - SPIN_F0",                                     # frames into the spin event
    "hover": "FLOAT_A*wave(CYC*t + 0.25, SKEW) + FLOAT_C",       # px, + = up
    "drift": "DRIFT_A*sin(2*pi*CYC*t)",                         # px, + = right
    "breath": "0.5 - 0.5*cos(2*pi*CYC*t)",                      # 0 at the crest, 1 at the trough
    "tense": "smoother(rs(t)/CHARGE_F) - smoother((rs(t) - CHARGE_F)/RELEASE_F)",
    "flare": "smoother((rs(t) - CHARGE_F + 2)/8)*(1 - smoother((rs(t) - FLARE_HOLD)/FLARE_FALL))",
    "spin": "-WIND_DEG*smoother(rs(t)/CHARGE_F) + (SPIN_DEG + WIND_DEG)*smoother(max(0, (rs(t) - CHARGE_F)/SPIN_F)**SPIN_SNAP)"
            " + OVER_DEG*damp((rs(t) - OVER_F0)/OVER_F, 3)",
    "shake_env": "bump((t*NF - SHAKE_F0)/SHAKE_F)",
    "jolt": "round(SHAKE_PX*jitter((t*NF - SHAKE_F0)/SHAKE_F, SHAKE_K)) + round(TREMBLE_PX*jitter((rs(t) - 3)/(CHARGE_F - 2), TREMBLE_K))",
    "FY": "hover(t) + LIFT_PX*flare(t) - DIP_PX*tense(t)",
    "FX": "drift(t)",
    "crown": "CLOSE_DEG*tense(t) - FLARE_DEG*flare(t) - BRISTLE_DEG*shake_env(t)",
    "pout": "PETAL_OUT + FLING*flare(t) - TUCK*tense(t) + BRISTLE_OUT*shake_env(t)",
    "tilt": "TILT_DEG*sin(2*pi*CYC*t) - SPIN_ROLL*flare(t)",
}

SKIRTS = [("upper_skirt_01", "A:-1,0,0", "CS_U", True), ("lower_skirt_01", "A:1,0,0", "CS_D", True),
          ("left_skirt_a_01", "A:-0.45,0,0.89", "CS_LA", False), ("right_skirt_a_01", "A:-0.45,0,-0.89", "CS_RA", False),
          ("left_skirt_b_01", "A:0.45,0,0.89", "CS_LB", False), ("right_skirt_b_01", "A:0.45,0,-0.89", "CS_RB", False)]
FEELERS = [("upper_feeler_02", [("LOCZ", 1)]), ("lower_feeler_02", [("LOCZ", -1)]),
           ("left_feeler_a_02", [("LOCX", 0.857), ("LOCZ", 0.514)]), ("right_feeler_a_02", [("LOCX", -0.857), ("LOCZ", 0.514)]),
           ("left_feeler_b_02", [("LOCX", 0.857), ("LOCZ", -0.514)]), ("right_feeler_b_02", [("LOCX", -0.857), ("LOCZ", -0.514)])]
RING = ["upper_feeler_02", "left_feeler_a_02", "left_feeler_b_02", "lower_feeler_02", "right_feeler_b_02", "right_feeler_a_02"]


def pose():
    p = []
    for bone, *_ in SKIRTS:
        p.append([bone, "SCALE", "1 + BREATH_SCALE*breath(t)"])
    for bone, axis, cs, breathes in SKIRTS:
        p.append([bone, axis, f"CROWN_SWEEP + {cs} + crown(t)" + (" - BREATH_OPEN*breath(t)" if breathes else "")])
    for bone, locs in FEELERS:
        p.append([bone, "SCALE", "PETAL_SCALE"])
        for ax, k in locs:
            p.append([bone, ax, f"{k}*pout(t)"])
    p += [["root_feeler", "Y", "- PETAL_SWAY*(0.5 - 0.5*cos(4*pi*ts)) + spin(t)"],
          ["waist", "Z", "YAW"], ["waist", "X", "PITCH"], ["waist", "Y", "ROLL"],
          ["waist", "ROLLCAM", "tilt(t)"],
          ["origin", "LOCZ", "BOB*c"],
          # whole pixels are style.pixel_bob's shift of the finished sprite; only the fraction is rendered
          ["origin", "LOCCAM", "PX_U*(FY(t) - round(FY(t)))"],
          ["origin", "LOCCAMX", "PX_U*(FX(t) - round(FX(t)))"]]
    for k, bone in enumerate(RING):
        p.append([bone, "LOCCAM", f"PX_U*(FY(t - (LAG_F + {k}*RIP_F)/NF) - FY(t))"])
    return p


NOTE = ("round 9 (ours; Showdown has no Mega Glimmora animation). 270 frames = 8.1 s. Float measured on Showdown's "
        "floaters (base Glimmora, Bronzong, Claydol, Cosmoem, Nihilego): 3 floats of 90 frames (2.7 s), 7 px travel "
        "(~7 % of the height, base Glimmora 6.7 %), crest broad / trough quick (wave skew), a sideways drift a quarter "
        "cycle behind (egg-shaped orbit) and a pendulum rock of TILT_DEG; petals trail the body by LAG_F frames. "
        "Whole pixels of FY / FX are style.pixel_bob's shift, the fraction is rendered (origin LOCCAM / LOCCAMX). "
        "Crown breathes on the float (open at the trough). Shake, frames 78-104 (slow frames, hanging at a crest): "
        "a whole-pixel rattle +-2 px held 2 frames per swing, crown and petals bristle. Spin, frames 150-239 "
        "(fast frames, one float cycle long): charge 20 frames (crown clenches, petals tuck and wind back 40 deg, "
        "body dips 2 px and trembles 1 px), snap release (peak 24.6 deg/frame, under the ~30 at which the ring "
        "seems to turn backwards), two turns coasting down, crown flared, petals flung out, body lifted 3 px and "
        "counter-rolled 4 deg, then overshoots ~6 deg, recoils ~7 and settles. Frame 0 is the fitted rest pose on a whole pixel.")


def apply(path):
    cfg = json.loads(path.read_text())
    prev = {"pose_params": {k: cfg["pose_params"][k] for k in OBSOLETE + list(PARAMS) if k in cfg["pose_params"]},
            "pose": cfg["pose"], "motion": cfg["motion"],
            "pixel_bob": cfg["style"].get("pixel_bob"), "fast_frames": cfg["style"].get("fast_frames")}
    cfg.setdefault("motion_previous", prev)
    for k in OBSOLETE:
        cfg["pose_params"].pop(k, None)
    cfg["pose_params"].update(PARAMS)
    cfg["pose"] = pose()
    cfg["motion"] = {"frames": N, "functions": FUNCTIONS, "note": NOTE}
    cfg["style"]["pixel_bob"] = {"y": "FY(t)", "x": "FX(t) + jolt(t)"}
    cfg["style"]["fast_frames"] = [[SPIN_F0, SPIN_F0 + 89]]
    path.write_text(json.dumps(cfg, indent=2) + "\n")
    print("wrote", path)


if __name__ == "__main__":
    for a in sys.argv[1:]:
        apply(Path(a))
