"""Writes palette / parts / pose / pose_params / motion into mega_chimecho_front.json.
Keeps existing pose_params; new params get DEFAULTS; KEY=value args override. Prints every change.
Run: /usr/local/bin/python3 mega-chimecho-model/gen.py [KEY=value ...]"""
import json, os, sys

CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mega_chimecho_front.json")

DEFAULTS = {
    "AZIMUTH": 70, "ELEVATION": 12, "FOV": 30,
    "PX_U": 0.0075,     # world units per sprite px (approx, frame 0 height / style.height)
    # rest pose (deg)
    "BOW": 35,          # bow lobes raised into the art's V (about -Y at hair_01)
    "BOW2": 0,          # extra raise further out (hair_03)
    # float (sprite px / deg), the driver: one bob and one sideways drift per loop
    "FLOAT_A": 1.5, "SKEW": 0.12, "DRIFT_A": 1.0, "TILT": 1.2,
    # followers (deg) and their lags (fraction of the loop)
    "BOWF": 2.5, "BOWF_LAG": 0.08, "FING": 3.0, "FING_LAG": 0.14,
    "CHIME": 2.0, "CHIME_LAG": 0.10, "STRM": 2.5, "STRM_LAG": 0.06,
    "FLUT": 2.0, "FLUT_C": 2,
    "BELL": 2.5, "BELL_LAG": 0.10, "TAIL": 2.5, "TAIL_LAG": 0.06,
    "HFEEL": 4.0,
}


def pose_list(p):
    P = []
    # --- rest pose: bow lobes up into a V (left = +X side, its axis -Y raises it; right mirrored)
    P.append(["left_hair_01", "A:0,-1,0", "BOW + bowf(t)"])
    P.append(["right_hair_01", "A:0,-1,0", "-(BOW + bowf(t))"])
    P.append(["left_hair_03", "A:0,-1,0", "BOW2 + 0.6*bowf(t - BOWF_LAG)"])
    P.append(["right_hair_03", "A:0,-1,0", "-(BOW2 + 0.6*bowf(t - BOWF_LAG))"])
    # bow fingers flex a beat later
    for side, sg in (("left", 1), ("right", -1)):
        for f in ("a", "b", "c"):
            P.append([f"{side}_horn_{f}_02", "A:0,-1,0", f"{sg}*fing(t)"])
    # --- float driver: whole sprite bob / drift (whole px) + fraction in the render, lean
    P.append(["origin", "LOCCAM", "PX_U*(FY(t) - round(FY(t)))"])
    P.append(["origin", "LOCCAMX", "PX_U*(FX(t) - round(FX(t)))"])
    P.append(["waist", "ROLLCAM", "tilt(t)"])
    # --- hanging chimes: pendulum trailing the drift, chain lags toward the free end, plus flutter
    for side in ("left", "right"):
        for k, f in enumerate(("a", "b", "c")):
            ph = 0.03 * k  # neighbours a touch apart, not in lockstep
            P.append([f"{side}_feeler_{f}_02", "A:0,-1,0", f"CHIME*swing(t - CHIME_LAG - {ph})"])
            for j, b in enumerate(("04", "05", "06")):
                lag = f"(CHIME_LAG + {ph} + {j+1}*STRM_LAG)"
                P.append([f"{side}_feeler_{f}_{b}", "A:0,-1,0", f"STRM*swing(t - {lag})"])
                P.append([f"{side}_feeler_{f}_{b}", "A:1,0,0", f"FLUT*{(0.5 if f=='b' else 1)*(j+1)/3:.3f}*sin(2*pi*(FLUT_C*t - {lag} - {0.17*k + (0.5 if side=='right' else 0):.3f}))"])
    # --- the little Chimecho hanging in the ring: pendulum, tail trails
    P.append(["head", "A:0,-1,0", "BELL*swing(t - BELL_LAG)"])
    for j, b in enumerate(("tail_02", "tail_04", "tail_06")):
        P.append([b, "A:0,-1,0", f"TAIL*swing(t - BELL_LAG - {j+1}*TAIL_LAG)"])
    for b in ("center_tail", "left_tail", "right_tail"):
        P.append([b, "A:1,0,0", f"0.8*TAIL*sin(2*pi*(2*t - BELL_LAG - 4*TAIL_LAG))"])
    P.append(["feeler_01", "A:1,0,0", "HFEEL*0.5*sin(2*pi*(2*t - 0.15))"])
    P.append(["feeler_02", "A:1,0,0", "HFEEL*sin(2*pi*(2*t - 0.25))"])
    return P


MOTION = {
    "frames": 120,
    "functions": {
        "hover": "FLOAT_A*wave(t + 0.25, SKEW)",
        "drift": "DRIFT_A*sin(2*pi*t)",
        "FY": "hover(t)",
        "FX": "drift(t)",
        # lean into the drift (leads it a quarter beat: the body leads, everything else trails)
        "tilt": "TILT*cos(2*pi*t)",
        # trailing swing: hangs back against the body's sideways speed
        "swing": "-cos(2*pi*t)",
        # bow lobes trail the bob a beat: dip while the body rises, lift while it sinks
        "bowf": "BOWF*sin(2*pi*(t - BOWF_LAG))",
        "fing": "FING*sin(2*pi*(t - FING_LAG))",
    },
}

PALETTE = {
    "outline": "#1f060a",
    "parts": {
        "yellow": ["#cebb67", "#e5d27d", "#f0dd88", "#fce994", "#fff49f"],
        "eye": ["#b48f22", "#cba632", "#d8b33c", "#e6c046", "#f2cd52"],
        "red": ["#b03f54", "#c85567", "#d46071", "#e16a7c", "#ed7586"],
        "white": ["#b6c2c6", "#cfdadd", "#dbe5e8", "#e9f1f3", "#f8fcfd"],
        "blue": ["#9db5c1", "#b3cbd8", "#bed6e3", "#cee6f3", "#e1faff"],
        "navy": ["#2c5f78", "#386f8c", "#3f7896", "#4783a3", "#5190b2"],
        "green": ["#557c2c", "#628e34", "#6a9a3a", "#74a641", "#7fb44a"],
    },
}
PARTS = {
    "materials": {
        "r_eye": "eye", "l_eye": "eye",
        "body_b_01": "yellow", "body_a_02": "yellow",
        "body_b_00": "red|white",
        "body_a_01": "blue|red|navy|green",
    },
    "default_material": "body_b_00",
    "albedo": {
        "yellow": "#e3cf7b", "eye": "#e6c646", "red": "#ce5a6c", "white": "#dce8ea",
        "blue": "#b7cfdc", "navy": "#3a7898", "green": "#6a9a3a",
    },
}


def main():
    c = json.load(open(CFG))
    pp = c.get("pose_params", {})
    over = dict(a.split("=", 1) for a in sys.argv[1:])
    for k, v in DEFAULTS.items():
        if k not in pp:
            pp[k] = v; print(f"new  {k} = {v}")
    for k, v in over.items():
        v = float(v)
        print(f"set  {k}: {pp.get(k)} -> {v}"); pp[k] = v
    c["pose_params"] = pp
    c["pose"] = pose_list(pp)
    note = c.get("motion", {}).get("note", "")
    c["motion"] = dict(MOTION, note=note)
    c["palette"] = PALETTE
    c["parts"] = PARTS
    c["style"]["pixel_bob"] = {"y": "FY(t)", "x": "FX(t)"}
    json.dump(c, open(CFG, "w"), indent=2)
    print("pose entries:", len(c["pose"]))


main()
