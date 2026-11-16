"""Writes pose / pose_params / motion into mega_baxcalibur_front.json (v3: menacing growl, planted feet, open eyes).
Keeps existing pose_params; new params get DEFAULTS; KEY=value args override. Prints every change.
Unused params (from v2) are dropped and printed.
Run: /usr/local/bin/python3 mega-baxcalibur-model/gen.py [--cfg PATH] [KEY=value ...]"""
import json, os, sys

CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mega_baxcalibur_front.json")

DEFAULTS = {
    "AZIMUTH": 64, "ELEVATION": 8, "FOV": 30,
    # rest pose (deg)
    "BODY": 38,     # whole-body lean forward (+) about world X at the waist
    "NECK": 18,     # neck pitch, + = head forward/down
    "NECK2": 0,     # upper neck pitch, + = forward/down
    "HEADP": -52,   # head pitch, + = nod down
    "HEADY": -30,   # head yaw, + = to its left (viewer's right)
    "SHRUG": 0,     # shoulders hunched forward (about world X)
    "ARMD": 30, "ARMF": 50, "ELB": 40,
    "ELBUP": 28,    # forearms lifted (about world X)
    "WRIST": 15,    # hands curled down (about world X)
    "CLAWR": 10,    # claw flex at rest (+ = closed)
    "SPREAD": 0,    # claws fanned apart (index / ring about world Z)
    "LID": -30,     # eyelids open (upper lids up, lower lid down); the bind pose has them shut
    "JAW0": 0,      # jaw at rest (eased mostly shut on the inhale)
    "LEGIN": 15, "HIP": 15, "KNEE": 20, "FOOT": 40,
    "TAIL1": 30, "TAIL2": 0, "TAIL3": 8,
    "BLADE": 33,    # dorsal blade tilted back (+)
    "TAILS": -40,   # tail sideways sweep
}

MOTION_DEFAULTS = {
    # driver: one heavy breath a loop, slow inhale (~63%), forceful exhale (~37%) (K warps the phase)
    "K": 0.5,
    "RISE": 0.02,   # body lifts on the inhale, sinks on the exhale (translation: feet keep their angle, knees bend)
    "BR": 1.0, "BR2": 0.6,   # chest / ribcage heave up and back on the inhale (deg)
    "SHU": 2.5,     # shoulders rise with the inhale
    "NFY": 0.05,    # neck pushes forward along its line on the exhale (model units)
    "NFZ": 0.012,   # ...and a little low
    "HZ": 0.04,     # neck holds the head's height against the chest heave (head travels forward, not up/down)
    "HPC": 1.0,     # head pitch countering the chest heave, so the head stays aimed (deg)
    "JAW": 18.0,    # jaw opens on the exhale growl (on top of JAW0)
    "RUM": 1.0,     # fast growl rumble while the jaw is open
    "BL": 1.2, "FL": 1.5,   # blade / back plates and chest crest ride the breath
    "SH": 1.5,      # shoulders hunch forward on the exhale
    "EB": 3.0, "WB": 4.0,   # elbows / wrists cock on the exhale
    "CL": 10.0,     # claws fan wider on the exhale
    "AS": 1.0,      # upper arms lift a little with the inhale
    "HR": 2.0,      # wrist spikes
    "TS": 1.5,      # slow tail sweep (wave base -> tip), once a loop, counter to the head
    "TL": 1.5,      # tail base lifts as the head pushes forward
}

LIDS = (("left_upper_eyelid_a", 1), ("right_upper_eyelid_a", 1), ("left_upper_eyelid_b", 1),
        ("right_upper_eyelid_b", 1), ("left_upper_eyelid_c", 1), ("right_upper_eyelid_c", 1),
        ("left_lower_eyelid", -1), ("right_lower_eyelid", -1))


def pose_list(p):
    P = []
    P.append(["spine_01", "A:1,0,0", "BODY"])
    P.append(["left_leg_01", "A:0,1,0", "LEGIN"])
    P.append(["right_leg_01", "A:0,1,0", "-LEGIN"])
    P.append(["left_leg_01", "A:0.77,0.59,0.25", "-HIP"])
    P.append(["right_leg_01", "A:0.77,-0.59,-0.25", "-HIP"])
    P.append(["left_leg_02", "A:0.77,0.59,0.25", "KNEE"])
    P.append(["right_leg_02", "A:0.77,-0.59,-0.25", "KNEE"])
    P.append(["left_foot", "A:0.77,0.59,0.25", "FOOT"])
    P.append(["right_foot", "A:0.77,-0.59,-0.25", "FOOT"])
    P.append(["tail_01", "A:1,0,0", "TAIL1"])
    P.append(["tail_03", "A:1,0,0", "TAIL2"])
    P.append(["tail_05", "A:1,0,0", "TAIL3"])
    P.append(["tail_02", "A:0,0,1", "TAILS*0.4"])
    P.append(["tail_04", "A:0,0,1", "TAILS*0.6"])
    P.append(["feeler_b", "A:1,0,0", "-BLADE"])
    P.append(["neck_01", "A:1,0,0", "NECK"])
    P.append(["neck_02", "A:1,0,0", "NECK2"])
    P.append(["head", "A:1,0,0", "HEADP"])
    P.append(["neck_02", "A:0,0,1", "HEADY*0.4"])
    P.append(["head", "A:0,0,1", "HEADY*0.6"])
    P.append(["lower_jaw", "A:1,0,0", "JAW0"])
    for b, s in LIDS:
        P.append([b, "A:1,0,0", f"LID*{s}"])
    P.append(["left_shoulder", "A:1,0,0", "SHRUG"])
    P.append(["right_shoulder", "A:1,0,0", "SHRUG"])
    P.append(["left_arm_01", "A:0,1,0", "ARMD"])
    P.append(["right_arm_01", "A:0,1,0", "-ARMD"])
    P.append(["left_arm_01", "A:0,0,1", "-ARMF"])
    P.append(["right_arm_01", "A:0,0,1", "ARMF"])
    P.append(["left_arm_02", "A:0,0,1", "-ELB"])
    P.append(["right_arm_02", "A:0,0,1", "ELB"])
    P.append(["left_arm_02", "A:1,0,0", "-ELBUP"])
    P.append(["right_arm_02", "A:1,0,0", "-ELBUP"])
    P.append(["left_hand_sub", "A:1,0,0", "WRIST"])
    P.append(["right_hand_sub", "A:1,0,0", "WRIST"])
    for f in ("index", "middle", "ring"):
        P.append([f"left_{f}", "A:0,1,0", "CLAWR"])
        P.append([f"right_{f}", "A:0,1,0", "-CLAWR"])
    P.append(["left_index", "A:0,0,1", "SPREAD"])
    P.append(["left_ring", "A:0,0,1", "-SPREAD"])
    P.append(["right_index", "A:0,0,1", "-SPREAD"])
    P.append(["right_ring", "A:0,0,1", "SPREAD"])
    return P


def motion_list(p):
    def ph(d):   # warped breath phase (0..2pi a loop), lag d in loop fractions
        x = f"2*pi*(t - {d})" if d else "2*pi*t"
        return f"({x} - K*(1 - cos({x})))"
    I = lambda d=0: f"(0.5 - 0.5*cos{ph(d)})"             # inhale 0..1 (1 = chest full)
    E = lambda d=0: f"max(0, -sin{ph(d)})**2"             # exhale growl envelope 0..1, 0 through the inhale
    R = "sin(20*pi*t)"                                    # rumble, 10 a loop
    W = lambda d: f"sin(2*pi*t - {d})"
    M = [
        ["waist", "LOCZ", f"RISE*({I()} - 0.5)"],
        ["spine_01", "A:1,0,0", f"-BR*{I(0.02)}"],
        ["spine_02", "A:1,0,0", f"-BR2*{I(0.04)}"],
        ["left_shoulder", "A:0,1,0", f"-SHU*{I(0.06)}"],
        ["right_shoulder", "A:0,1,0", f"SHU*{I(0.06)}"],
        ["left_shoulder", "A:1,0,0", f"SH*{E(0.02)}"],
        ["right_shoulder", "A:1,0,0", f"SH*{E(0.03)}"],
        ["neck_02", "LOCY", f"-NFY*{E(0.0)}"],
        ["neck_02", "LOCZ", f"-NFZ*{E(0.0)} - HZ*({I(0.03)} - 0.5)"],
        ["head", "A:1,0,0", f"HPC*{I(0.05)} + RUM*0.2*{E(0.03)}*{R}"],
        ["lower_jaw", "A:1,0,0", f"JAW*{E(0.03)} + RUM*{E(0.03)}*{R}"],
        ["feeler_b", "A:1,0,0", f"-BL*{I(0.08)}"],
        ["feeler_a", "A:1,0,0", f"FL*{I(0.06)}"],
        ["feeler_c", "A:1,0,0", f"-FL*0.3*{I(0.09)}"],
        ["left_arm_01", "A:1,0,0", f"-AS*{I(0.08)}"],
        ["right_arm_01", "A:1,0,0", f"-AS*{I(0.1)}"],
        ["left_arm_02", "A:1,0,0", f"-EB*{E(0.06)}"],
        ["right_arm_02", "A:1,0,0", f"-EB*{E(0.07)}"],
        ["left_hand_sub", "A:1,0,0", f"-WB*{E(0.09)}"],
        ["right_hand_sub", "A:1,0,0", f"-WB*{E(0.1)}"],
        ["left_index", "A:0,0,1", f"CL*{E(0.11)}"],
        ["left_ring", "A:0,0,1", f"-CL*{E(0.11)}"],
        ["right_index", "A:0,0,1", f"-CL*{E(0.12)}"],
        ["right_ring", "A:0,0,1", f"CL*{E(0.12)}"],
        ["left_middle", "A:0,1,0", f"-CL*0.5*{E(0.11)}"],
        ["right_middle", "A:0,1,0", f"CL*0.5*{E(0.12)}"],
        ["left_root_hair", "A:0,1,0", f"-HR*{E(0.13)}"],
        ["right_root_hair", "A:0,1,0", f"HR*{E(0.14)}"],
        ["tail_01", "A:1,0,0", f"TL*{E(0.06)}"],
        ["tail_04", "A:1,0,0", f"-TL*0.8*{E(0.1)}"],
    ]
    for i, b in enumerate(["tail_03", "tail_04", "tail_05", "tail_06", "tail_07", "tail_08"]):
        M.append([b, "A:0,0,1", f"TS*{1 + 0.3 * i:.2f}*{W(round(1.0 + 0.4 * i, 2))}"])
    return M


NOTE = ("growling breath of a heavy predator (HOME stance: low forward-leaning body on bent legs, balanced by the "
        "tail; eyes wide open; shoulders hunched, claws spread). Based on the Showdown animated idle of base "
        "Baxcalibur (reference/showdown_ani_baxcalibur.gif: one slow breath a loop, the torso heaves up and sinks, "
        "the knees take it, the tail sweeps slowly). Driver: one breath per loop, slow inhale (~63%), forceful exhale "
        "(~37%) (phase warp K). Inhale: the body rises (RISE), the chest and ribcage heave up and back (BR, BR2), "
        "the shoulders rise (SHU), the blade and back plates ride it (BL, FL), the jaw eases mostly shut. Exhale: the "
        "neck pushes forward and a little low along its line (NFY, NFZ, a translation, not a pitch), the neck holds the "
        "head's height against the heave (HZ) and the head pitch only counters the chest (HPC), so the head travels "
        "forward and back, not up and down. The jaw opens into the growl (JAW) with a fast rumble (RUM), the "
        "shoulders hunch, the elbows, wrists and claws cock and fan, each a beat later. The tail base lifts against "
        "the head push and a slow sideways wave runs to the tip. Feet planted flat; the body only translates "
        "vertically, so the knees bend and the feet keep their angle.")

KEEP = set(DEFAULTS) | set(MOTION_DEFAULTS)


def main():
    args = sys.argv[1:]
    cfg_path = CFG
    if args and args[0] == "--cfg":
        cfg_path, args = args[1], args[2:]
    cfg = json.load(open(cfg_path))
    params = cfg.setdefault("pose_params", {})
    over = dict(a.split("=", 1) for a in args)
    for k in [k for k in params if k not in KEEP]:
        print(f"drop {k} = {params.pop(k)}")
    for k, v in {**DEFAULTS, **MOTION_DEFAULTS}.items():
        if k not in params:
            params[k] = v
            print(f"new  {k} = {v}")
    for k, v in over.items():
        v = float(v)
        print(f"set  {k}: {params.get(k)} -> {v}")
        params[k] = v
    cfg["pose"] = pose_list(params) + motion_list(params)
    cfg["motion"]["plant"] = ["left_foot", "right_foot"]
    cfg["motion"]["note"] = NOTE
    json.dump(cfg, open(cfg_path, "w"), indent=2)
    print(f"pose: {len(cfg['pose'])} entries -> {cfg_path}")


if __name__ == "__main__":
    main()
