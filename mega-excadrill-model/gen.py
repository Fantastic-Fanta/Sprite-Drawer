"""Writes palette / parts / pose / pose_params / motion into mega_excadrill_front.json.
Keeps existing pose_params; new params get DEFAULTS; KEY=value args override. Prints every change.
Run: /usr/local/bin/python3 mega-excadrill-model/gen.py [KEY=value ...]"""
import json, os, sys

CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mega_excadrill_front.json")

DEFAULTS = {
    "AZIMUTH": 55, "ELEVATION": 12, "FOV": 30,
    "BODY": 0,       # whole-body lean forward (+) about world X at the spine
    "HEADP": 0,      # head pitch, + = nod down
    "HEADY": 0,      # head yaw, + = to its left (toward the camera side)
    "DRILL": -95,    # head drill tipped back (-) about world X
    "DRILLS": 0,     # head drill swung sideways about world Z
    "DRY": 0, "DRZ": 0,  # head drill slid back (+Y) / up (+Z), model units
    "RUP": -10,      # right (far, low) arm: raise (+) about its own y
    "RFWD": 85,      # right arm swung forward about world Z
    "LUP": 35,       # left (near, raised) arm: raise (+)
    "LFWD": 80,      # left arm swung forward
    "LROLL": 160,    # left arm rolled about its own length: red fins on top, as in the art
    "RROLL": 180,    # right arm rolled: spikes on top, red fins underneath, as in the art
    "RELB": 0, "LELB": 0,
    "LELBD": 0,      # left blade lowered (+) at the elbow, about the screen-left horizontal  # elbows (blade) bend forward-in
    "LEGIN": 0, "KNEE": 0, "FOOT": 0,
}

MOTION_DEFAULTS = {
    "BR": 1.2,                # breath: spine pitch (deg), the driver, 2 breaths a loop
    "HB": 1.0,                # head follows
    "DRB": 0.8,               # heavy head drill follows late
    "LAB": 2.0, "LEB": 1.5,   # raised blade: shoulder / elbow follow
    "RAB": 1.5, "REB": 1.2,   # low blade
    "SH": 3.0,                # shoulder spikes
    "DIP": 0.006, "SW": 0.005,  # body dip per breath / weight shift once a loop (model units)
}


def pose_list(p):
    P = []
    P.append(["spine", "A:1,0,0", "BODY"])
    # head drill: tip it back over the shoulders
    P.append(["feeler", "A:1,0,0", "DRILL"])
    P.append(["feeler", "A:0,0,1", "DRILLS"])
    P.append(["feeler", "LOCY", "DRY"])
    P.append(["feeler", "LOCZ", "DRZ"])
    # head
    P.append(["head", "A:1,0,0", "HEADP"])
    P.append(["head", "A:0,0,1", "HEADY"])
    # arms (T-pose along X): raise about world Y, then swing forward about world Z
    P.append(["left_arm_01", "A:1,0,0", "LROLL"])
    P.append(["left_arm_01", "A:0,1,0", "-LUP"])
    P.append(["left_arm_01", "A:0,0,1", "-LFWD"])
    P.append(["right_arm_01", "A:1,0,0", "RROLL"])
    P.append(["right_arm_01", "A:0,1,0", "RUP"])
    P.append(["right_arm_01", "A:0,0,1", "RFWD"])
    P.append(["left_arm_02_roll", "A:0,0,1", "-LELB"])
    P.append(["right_arm_02_roll", "A:0,0,1", "RELB"])
    P.append(["left_arm_02_roll", "A:-0.5,0.87,0", "-LELBD"])
    # legs
    P.append(["left_leg_01", "A:0,1,0", "LEGIN"])
    P.append(["right_leg_01", "A:0,1,0", "-LEGIN"])
    P.append(["left_leg_02", "A:1,0,0", "KNEE"])
    P.append(["right_leg_02", "A:1,0,0", "KNEE"])
    P.append(["left_foot", "A:1,0,0", "FOOT"])
    P.append(["right_foot", "A:1,0,0", "FOOT"])
    return P


def motion_list(p):
    B = "sin(4*pi*t%s)"
    return [
        ["spine", "A:1,0,0", "-BR*" + B % ""],
        ["neck", "A:1,0,0", "-HB*0.5*" + B % " - 0.5"],
        ["head", "A:1,0,0", "-HB*" + B % " - 0.8"],
        ["feeler", "A:1,0,0", "DRB*" + B % " - 1.0"],
        ["left_arm_01", "A:-1,0,0", "LAB*" + B % " - 0.8"],
        ["left_arm_02_roll", "A:-1,0,0", "LEB*" + B % " - 1.2"],
        ["right_arm_01", "A:-1,0,0", "RAB*" + B % " - 0.9"],
        ["right_arm_02_roll", "A:-1,0,0", "REB*" + B % " - 1.3"],
        ["left_horn_02", "A:0,1,0", "-SH*" + B % " - 1.1"],
        ["right_horn_02", "A:0,1,0", "SH*" + B % " - 1.1"],
        ["origin", "LOCZ", "-DIP*" + B % " - 0.3"],
        ["origin", "LOCX", "SW*sin(2*pi*t)"],
    ]


NOTE = ("heavy drill-armoured mole braced to charge (HOME / official art stance: body turned to its right, both arm "
        "blades held forward together as one drill, the head drill raised forward-up over the face, the big back drill laid "
        "back over its shoulders): slow guarded breathing, 2 breaths in 120 frames. The chest lifts (spine BR) and the body "
        "dips with each breath (DIP); the head drill nods a beat later, the arm drill rises a little later still with its tip "
        "lagging most; the heavy back drill settles last and least. The weight shifts side to side once a loop (SW); the "
        "feet stay planted (motion.plant) and the short legs bend under the dip; the shoulder spikes follow.")


PALETTE = {
    "outline": "#0f0f0f",
    "parts": {
        "body":  ["#3a302d", "#4a3f3b", "#584d48", "#675b56", "#766a64"],
        "marks": ["#6e3634", "#824341", "#95504e", "#a65d5a", "#b56966"],
        "red":   ["#c84a33", "#e0553c", "#fc6244", "#fd7a5f", "#fe927a"],
        "steel": ["#6e6f70", "#9b9c9d", "#b0b1b3", "#c4c5c7", "#d0d1d4"],
        "white": ["#c9c6c4", "#d6d3d1", "#e2e0de", "#f0efee", "#fdfdfd"],
        "black": ["#000000", "#0b0b0b", "#1a1a1a", "#2a2a2a", "#3a3a3a"],
    },
}
PARTS = {
    "materials": {
        "r_eye": "black|white",
        "l_eye": "black|white",
        "body_a_00": "body|marks|red|steel|white|black",
        "body_a_01": "body|marks|red|steel|white|black",
        "body_a_02": "body|marks|red|steel|white|black",
        "body_a_03": "body|marks|red|steel|white|black",
    },
    "default_material": "body_b",
    "albedo": {
        "body": "#584d48", "marks": "#95504e", "red": "#fc6244",
        "steel": "#c4c5c7", "white": "#e2e0de", "black": "#0b0b0b",
    },
}


def main():
    cfg = json.load(open(CFG))
    params = cfg.setdefault("pose_params", {})
    over = dict(a.split("=", 1) for a in sys.argv[1:])
    for k, v in {**DEFAULTS, **MOTION_DEFAULTS}.items():
        if k not in params:
            params[k] = v
            print(f"new  {k} = {v}")
    for k, v in over.items():
        v = float(v)
        print(f"set  {k}: {params.get(k)} -> {v}")
        params[k] = v
    cfg["palette"] = PALETTE
    cfg["parts"] = PARTS
    cfg["pose"] = pose_list(params) + motion_list(params)
    cfg["motion"]["plant"] = ["left_foot", "right_foot"]
    cfg["motion"]["note"] = NOTE
    json.dump(cfg, open(CFG, "w"), indent=2)
    print(f"pose: {len(cfg['pose'])} entries")


if __name__ == "__main__":
    main()
