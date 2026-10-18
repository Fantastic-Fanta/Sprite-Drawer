"""Write Mega Glimmora's motion (round 10: float, drift, sway, living petals, a hiss, menacing spin) into configs.

Run:  python3 set_motion.py glimmora_front.json [glimmora_back.json ...]
Replaces pose_params' motion numbers, motion.functions, the motion part of pose, style.pixel_bob
and style.fast_frames; the camera / view numbers (AZIMUTH, ELEVATION, FOV, YAW, PITCH, ROLL,
petal rest pose, crown fit) are left as they are. The replaced values go to motion_previous.

Measured on Showdown's floating sprites (in-page, see SPRITE_PIPELINE.md round 9): base Glimmora
bobs 6.7 % of its height over 90 frames (2.7 s), drifts 5.5 px sideways a third of a cycle behind
the bob, hangs at the top and turns quicker at the bottom, rocks a few degrees; Bronzong 8.5 % /
79 frames, Claydol 7 % / 79, Cosmoem 13 % / 89 with a sideways orbit and +-20 deg rock.

Round 10 (user: the shake wasn't what they expected; wanted a "hiss" with the petals' help, and
the floating petals more alive): the whole-pixel shake is gone. The hiss is a fast-frame event
inserted at the second float's crest, with the float clock (tf) stopped during it, so the frames
either side of it are the same pose. Each floating petal now bends along its own bone chain
(feeler_03 / _04, which the round-9 motion never moved) and sways and bobs on its own phase round
the ring, on the slow clock (tq: both events cut out, so the stabilised loop stays seamless).
"""
import json
import sys
from pathlib import Path

HISS_F0, HISS_F = 90, 60       # hiss event: frames 90-149, at the second float's crest (float held)
SPIN_F0, SPIN_W = 210, 90      # spin event: one float cycle long, starting at the same float phase as round 9
N = 270 + HISS_F               # 9.9 s at 30 ms: three 90-frame floats + the hiss

PARAMS = {
    "NF": N, "CYC": 3, "HISS_F0": HISS_F0, "HISS_F": HISS_F, "SPIN_W": SPIN_W,
    # float: crest at frame 0 (= Showdown's still, held on a whole pixel: 3.5 + 0.5 = 4)
    "FLOAT_A": 3.5, "FLOAT_C": 0.5, "SKEW": 0.18,
    "DRIFT_A": 2.5,                     # sideways, a quarter cycle behind: an egg-shaped orbit
    "TILT_DEG": 3.0,                    # pendulum rock: leans out at the ends of the drift
    "LAG_F": 2.5, "RIP_F": 0.25,        # petals trail the body (frames), a little more round the ring
    "BREATH_OPEN": 15, "BREATH_SCALE": 0.08,
    # living petals (slow clock tq: 180 frames a loop). Each petal: a bend that runs base -> tip
    # (feeler_03, then feeler_04 LIVE_LAG of a cycle later), a sideways sway about its own radial
    # axis, a small bob of its own; the phases step round the ring, so a ripple travels round it
    "CURL_A": 2.5, "CURL_A2": 2.0, "CURL_C": 3, "LIVE_LAG": 0.15,
    "SWAY_A": 1.5, "SWAY_C": 2,
    "PBOB_A": 0.5, "PBOB_C": 2,
    # hiss (frames into the event, hs): inhale HI_IN (rears up, leans back, crown clenches, petals
    # tuck, curl in and wind back), burst HI_BURST (crown and petals flare open like a hood, body
    # strikes down), hold to HI_HOLD hissing (petals buzz, neighbours opposite, 2-frame swings;
    # crown quivers), relax HI_RELAX with a small overshoot (HI_OVER, settling over HI_SETTLE)
    "HI_IN": 14, "HI_BURST": 5, "HI_HOLD": 38, "HI_RELAX": 12, "HI_SETTLE": 14, "HI_OVER": 0.3,
    "HI_REAR_PX": 2, "HI_LUNGE_PX": 1, "HI_LUNGE_F": 8, "HI_LEAN": 3, "HI_STRIKE": 2,
    "HI_CLENCH": 8, "HI_FLARE": 20, "HI_QUIVER": 2, "HI_TWIST": 6,
    "HOOD_OUT": 0.14, "COIL_IN": 0.08, "HOOD_FAN": 11, "HOOD_FAN2": 8, "COIL_CURL": 5,
    "HOOD_PX": 5, "COIL_PX": 1.5,       # and on screen, straight out from the ring centre (SPREAD)
    "BUZZ_F0": 17, "BUZZ_F": 24, "BUZZ_K": 12, "BUZZ_DEG": 2.5, "HI_SPIKE": 0.25,
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
            "RIPPLE", "FLOAT_PH", "FLOAT_PX",
            "SHAKE_F0", "SHAKE_F", "SHAKE_K", "SHAKE_PX", "BRISTLE_DEG", "BRISTLE_OUT"]

FUNCTIONS = {
    # clocks: float (hiss cut out: the float holds at its crest while hissing), slow (both events cut out)
    "tf": "(t*NF - min(HISS_F, max(0, t*NF - HISS_F0)))/(NF - HISS_F)",
    "tq": "(t*NF - min(HISS_F, max(0, t*NF - HISS_F0)) - min(SPIN_W, max(0, t*NF - SPIN_F0)))/(NF - HISS_F - SPIN_W)",
    "rs": "t*NF - SPIN_F0",                                     # frames into the spin event
    "hs": "t*NF - HISS_F0",                                     # frames into the hiss event
    "hover": "FLOAT_A*wave(CYC*tf(t) + 0.25, SKEW) + FLOAT_C",   # px, + = up
    "drift": "DRIFT_A*sin(2*pi*CYC*tf(t))",                     # px, + = right
    "breath": "0.5 - 0.5*cos(2*pi*CYC*tf(t))",                  # 0 at the crest, 1 at the trough
    # hiss envelopes
    "rear": "smoother(hs(t)/HI_IN)*(1 - smoother((hs(t) - HI_HOLD)/HI_RELAX))",
    "coil": "smoother(hs(t)/HI_IN) - smoother((hs(t) - HI_IN)/HI_BURST)",
    "hood": "smoother((hs(t) - HI_IN)/HI_BURST)*(1 - smoother((hs(t) - HI_HOLD)/HI_RELAX))"
            " - HI_OVER*damp((hs(t) - HI_HOLD - 0.6*HI_RELAX)/HI_SETTLE, 2)",
    "lunge": "bump((hs(t) - HI_IN + 1)/HI_LUNGE_F)",
    "buzz": "jitter((hs(t) - BUZZ_F0)/BUZZ_F, BUZZ_K)",         # +-1, 2-frame swings, sin^2 envelope
    # spin envelopes
    "tense": "smoother(rs(t)/CHARGE_F) - smoother((rs(t) - CHARGE_F)/RELEASE_F)",
    "flare": "smoother((rs(t) - CHARGE_F + 2)/8)*(1 - smoother((rs(t) - FLARE_HOLD)/FLARE_FALL))",
    "spin": "-WIND_DEG*smoother(rs(t)/CHARGE_F) + (SPIN_DEG + WIND_DEG)*smoother(max(0, (rs(t) - CHARGE_F)/SPIN_F)**SPIN_SNAP)"
            " + OVER_DEG*damp((rs(t) - OVER_F0)/OVER_F, 3)",
    "jolt": "round(TREMBLE_PX*jitter((rs(t) - 3)/(CHARGE_F - 2), TREMBLE_K))",
    "FY": "hover(t) + LIFT_PX*flare(t) - DIP_PX*tense(t) + HI_REAR_PX*rear(t) - HI_LUNGE_PX*lunge(t)",
    "FX": "drift(t)",
    "crown": "CLOSE_DEG*tense(t) - FLARE_DEG*flare(t) + HI_CLENCH*coil(t) - HI_FLARE*hood(t) + HI_QUIVER*buzz(t)",
    "pout": "PETAL_OUT + FLING*flare(t) - TUCK*tense(t) + HOOD_OUT*hood(t) - COIL_IN*coil(t)",
    "tilt": "TILT_DEG*sin(2*pi*CYC*tf(t)) - SPIN_ROLL*flare(t) - HI_LEAN*coil(t) + HI_STRIKE*lunge(t)",
}

SKIRTS = [("upper_skirt_01", "A:-1,0,0", "CS_U", True), ("lower_skirt_01", "A:1,0,0", "CS_D", True),
          ("left_skirt_a_01", "A:-0.45,0,0.89", "CS_LA", False), ("right_skirt_a_01", "A:-0.45,0,-0.89", "CS_RA", False),
          ("left_skirt_b_01", "A:0.45,0,0.89", "CS_LB", False), ("right_skirt_b_01", "A:0.45,0,-0.89", "CS_RB", False)]
FEELERS = [("upper_feeler_02", [("LOCZ", 1)]), ("lower_feeler_02", [("LOCZ", -1)]),
           ("left_feeler_a_02", [("LOCX", 0.857), ("LOCZ", 0.514)]), ("right_feeler_a_02", [("LOCX", -0.857), ("LOCZ", 0.514)]),
           ("left_feeler_b_02", [("LOCX", 0.857), ("LOCZ", -0.514)]), ("right_feeler_b_02", [("LOCX", -0.857), ("LOCZ", -0.514)])]
RING = ["upper_feeler_02", "left_feeler_a_02", "left_feeler_b_02", "lower_feeler_02", "right_feeler_b_02", "right_feeler_a_02"]
# each petal's on-screen direction out from the ring centre (right, up), measured on frame 0 of each
# view (rig posed in Blender, meshes projected): the 3-D spread alone is foreshortened unevenly round
# the tilted ring (front: left petals +13.7 px, right +3.3), so the hood also pushes on screen
SPREAD = {"front": {"upper_feeler_02": (-0.101, 0.995), "left_feeler_a_02": (0.774, 0.633), "left_feeler_b_02": (0.818, -0.576),
                    "lower_feeler_02": (0.039, -0.999), "right_feeler_b_02": (-0.796, -0.605), "right_feeler_a_02": (-0.845, 0.535)},
          "back": {"upper_feeler_02": (0.044, 0.999), "left_feeler_a_02": (-0.795, 0.606), "left_feeler_b_02": (-0.818, -0.575),
                   "lower_feeler_02": (-0.109, -0.994), "right_feeler_b_02": (0.77, -0.638), "right_feeler_a_02": (0.785, 0.62)}}
HAIRS = ["upper_hair", "left_hair_a", "left_hair_b", "lower_hair", "right_hair_b", "right_hair_a"]


def live(amp, cyc, phase):
    """a sine on the slow clock, minus its frame-0 value: frame 0 stays the fitted rest pose"""
    return f"{amp}*(sin(2*pi*({cyc}*tq(t) - {phase:.4f})) + sin(2*pi*{phase:.4f}))"


def pose(view):
    p = []
    for bone, *_ in SKIRTS:
        p.append([bone, "SCALE", "1 + BREATH_SCALE*breath(t)"])
    for bone, axis, cs, breathes in SKIRTS:
        p.append([bone, axis, f"CROWN_SWEEP + {cs} + crown(t)" + (" - BREATH_OPEN*breath(t)" if breathes else "")])
    for bone in HAIRS:                                  # the crown's inner spikes bristle while hissing
        p.append([bone, "SCALE", "1 + HI_SPIKE*max(0, hood(t))"])
    for bone, locs in FEELERS:
        p.append([bone, "SCALE", "PETAL_SCALE"])
        for ax, k in locs:
            p.append([bone, ax, f"{k}*pout(t)"])
    # each petal bends about its tangent (Y x radial: + = tip opens outward), then sways about its radial axis
    for k, bone in enumerate(RING):
        loc = dict(dict(FEELERS)[bone])
        rx, rz = loc.get("LOCX", 0.0), loc.get("LOCZ", 0.0)
        tangent, radial = f"A:{rz},0,{-rx}", f"A:{rx},0,{rz}"
        ph = k / 6
        sign = 1 if k % 2 == 0 else -1                  # neighbours buzz opposite ways
        b3, b4 = bone.replace("_02", "_03"), bone.replace("_02", "_04")
        p.append([b3, tangent, live("CURL_A", "CURL_C", ph)
                  + f" + HOOD_FAN*hood(t) - COIL_CURL*coil(t) + {sign}*BUZZ_DEG*buzz(t)"])
        p.append([b4, tangent, live("CURL_A2", "CURL_C", ph + PARAMS["LIVE_LAG"]) + " + HOOD_FAN2*hood(t)"])
        p.append([bone, radial, live("SWAY_A", "SWAY_C", -ph)])
    p += [["root_feeler", "Y", "- PETAL_SWAY*(0.5 - 0.5*cos(4*pi*tq(t))) + spin(t) - HI_TWIST*coil(t)"],
          ["waist", "Z", "YAW"], ["waist", "X", "PITCH"], ["waist", "Y", "ROLL"],
          ["waist", "ROLLCAM", "tilt(t)"],
          ["origin", "LOCZ", "BOB*c"],
          # whole pixels are style.pixel_bob's shift of the finished sprite; only the fraction is rendered
          ["origin", "LOCCAM", "PX_U*(FY(t) - round(FY(t)))"],
          ["origin", "LOCCAMX", "PX_U*(FX(t) - round(FX(t)))"]]
    for k, bone in enumerate(RING):
        dx, dy = SPREAD[view][bone]
        p.append([bone, "LOCCAM", f"PX_U*(FY(t - (LAG_F + {k}*RIP_F)/NF) - FY(t) + {live('PBOB_A', 'PBOB_C', k / 6 + 0.25)}"
                  f" + {dy}*(HOOD_PX*hood(t) - COIL_PX*coil(t)))"])
        p.append([bone, "LOCCAMX", f"PX_U*{dx}*(HOOD_PX*hood(t) - COIL_PX*coil(t))"])
    return p


NOTE = ("round 10 (ours; Showdown has no Mega Glimmora animation). 330 frames = 9.9 s. Float measured on Showdown's "
        "floaters (base Glimmora, Bronzong, Claydol, Cosmoem, Nihilego): 3 floats of 90 frames (2.7 s), 7 px travel, "
        "crest broad / trough quick (wave skew), a sideways drift a quarter cycle behind (egg-shaped orbit) and a "
        "pendulum rock of TILT_DEG; petals trail the body by LAG_F frames. Whole pixels of FY / FX are "
        "style.pixel_bob's shift, the fraction is rendered (origin LOCCAM / LOCCAMX). Crown breathes on the float. "
        "Living petals (slow clock tq, 180 frames): each bends base -> tip (feeler_03 / _04), sways about its radial "
        "axis and bobs, phases stepping round the ring. Hiss, frames 90-149 (fast frames; float held at the crest): "
        "inhale 14 frames (rears 2 px, leans back 3 deg, crown clenches, petals tuck, curl in, ring winds back 6 deg), "
        "burst 5 frames (crown flares 20 deg, petals open into a wide hood: out 0.14, fanned 11 + 8 deg, pushed 5 px "
        "out on screen, inner spikes bristle, body strikes down 1 px), hiss held to frame 38 (petals buzz +-2.5 deg in 2-frame swings, "
        "neighbours opposite, crown quivers), relax 12 frames with a small overshoot. Spin, frames 210-299 (fast "
        "frames, one float cycle long): charge 20 frames, snap release, two turns coasting down, overshoot, settle. "
        "Frame 0 is the fitted rest pose on a whole pixel.")


def apply(path):
    cfg = json.loads(path.read_text())
    prev = {"pose_params": {k: cfg["pose_params"][k] for k in OBSOLETE + list(PARAMS) if k in cfg["pose_params"]},
            "pose": cfg["pose"], "motion": cfg["motion"],
            "pixel_bob": cfg["style"].get("pixel_bob"), "fast_frames": cfg["style"].get("fast_frames")}
    cfg.setdefault("motion_previous", prev)
    for k in OBSOLETE:
        cfg["pose_params"].pop(k, None)
    cfg["pose_params"].update(PARAMS)
    cfg["pose"] = pose("back" if "back" in path.name else "front")
    cfg["motion"] = {"frames": N, "functions": FUNCTIONS, "note": NOTE}
    cfg["style"]["pixel_bob"] = {"y": "FY(t)", "x": "FX(t) + jolt(t)"}
    cfg["style"]["fast_frames"] = [[HISS_F0, HISS_F0 + HISS_F - 1], [SPIN_F0, SPIN_F0 + SPIN_W - 1]]
    path.write_text(json.dumps(cfg, indent=2) + "\n")
    print("wrote", path)


if __name__ == "__main__":
    for a in sys.argv[1:]:
        apply(Path(a))
