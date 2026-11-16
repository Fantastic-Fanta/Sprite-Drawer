"""Writes pose / pose_params / motion of mega_falinks_front.json. Keeps existing param values
unless overridden: python3 gen_pose.py [CONFIG] KEY=value ... ; prints every change."""
import json, sys
cfgp = "mega-falinks-model/mega_falinks_front.json"
args = sys.argv[1:]
if args and args[0].endswith(".json"):
    cfgp = args.pop(0)
cfg = json.load(open(cfgp))
D = dict(  # defaults (formation from the official art; units = model units, degrees)
    AZIMUTH=78, ELEVATION=10, FOV=30,
    # formation layout
    AX=-14, AZ=0.78,                       # leader a: lifted onto d, pitched back so its horn stands up
    BX=0.95, BZ=0.9, BP=10, BYAW=90,       # b = left arm (+X), holds the shield
    CX=-0.95, CZ=0.9, CP=-20, CYAW=-90,    # c = right arm (-X), the spear
    CH=-40,                                # spear (c's horn) pitched further down
    BH=80,                                 # b's horn turned back, behind its body
    SHY=75, SHZ=-35, SHX=1.38, SHYY=-0.15, SHZZ=1.32,  # shield: tilt, turn to camera, centre
    DY=0.12, DZ=0.36,                      # d = waist, sits on e and f
    EX=-0.33, EY=-0.12, EYAW=-15,          # e, f = the feet
    FX=0.33, FY=-0.12, FYAW=15,
    DARM=25, SHG=0.32, KN=15,                               # d's arms spread down-out
    # motion
    LAG=0.045,                             # phase step per trooper down the line a->f
    AB=0.03, SB=0.035, DB=0.02, FB=0.012,  # bob amplitudes: leader, side arms, waist, feet (dip)
    SW=1.5,                                # roll sway per trooper (deg)
    HB=3.0, SPB=2.5, SHB=2.5, SHB2=2.0, ARB=4.0, HRB=3.0, LGA=1.5, LGB=4.0, LGC=4.0, LGD=3.0,
)
P = dict(cfg.get("pose_params", {}))
for k, v in D.items():
    P.setdefault(k, v)
for a in args:
    k, v = a.split("="); v = float(v)
    print(f"{k}: {P.get(k)} -> {v}"); P[k] = v
old = cfg.get("pose_params", {})
for k in P:
    if k in old and old[k] != P[k] and k not in [a.split('=')[0] for a in args]:
        print(f"{k}: {old[k]} -> {P[k]}")

pose = []
# --- static formation (rest model: six troopers in single file along +Y) ---
pose += [["waist_a", "X", "AX"], ["waist_a", "LOCZ", "AZ"]]
pose += [["waist_b", "Z", "BYAW"], ["waist_b", "Y", "BP"],
         ["waist_b", "LOCX", "BX"], ["waist_b", "LOCY", "-1.5"], ["waist_b", "LOCZ", "BZ"]]
pose += [["waist_c", "Z", "CYAW"], ["waist_c", "Y", "CP"],
         ["waist_c", "LOCX", "CX"], ["waist_c", "LOCY", "-3.0"], ["waist_c", "LOCZ", "CZ"]]
pose += [["horn_c_01", "Y", "CH + SPB*BC(t-0.06)"], ["horn_a_01", "Z", "BH"]]
pose += [["feeler_a_01", "Y", "SHY"], ["feeler_a_01", "Z", "SHZ + SHB*BB(t-0.06)"],
         ["feeler_a_01", "LOCX", "SHX - BX"], ["feeler_a_01", "LOCY", "SHYY"],
         ["feeler_a_01", "LOCZ", "SHZZ - 1.78 - BZ"],
         ["feeler_a_02", "LOCX", "-SHG*0.79"], ["feeler_a_02", "LOCY", "SHG*0.55"], ["feeler_a_02", "LOCZ", "-SHG*0.26"],
         ["feeler_a_02", "Z", "SHB2*BB(t-0.12)"]]
pose += [["waist_d", "LOCY", "DY - 4.0"], ["waist_d", "LOCZ", "DZ"],
         ["left_shoulder_b", "Y", "DARM + ARB*BD(t-0.06)"], ["right_shoulder_b", "Y", "-DARM - ARB*BD(t-0.06)"]]
for k in "ef":   # knees a little bent so the planted legs have slack to stretch as well as bend
    pose += [[f"left_crotch_{k}", "X", "KN"], [f"left_leg_{k}", "X", "-2*KN"],
             [f"right_crotch_{k}", "X", "KN"], [f"right_leg_{k}", "X", "-2*KN"]]
pose += [["waist_e", "Z", "EYAW"], ["waist_e", "LOCX", "EX"], ["waist_e", "LOCY", "EY - 5.0"],
         ["waist_f", "Z", "FYAW"], ["waist_f", "LOCX", "FX"], ["waist_f", "LOCY", "FY - 6.0"]]
# --- idle: one breath driver per trooper, phase-shifted down the line a->f ---
pose += [["waist_a", "LOCZ", "AB*BA(t)"], ["waist_a", "Y", "SW*SWA(t)"],
         ["waist_b", "LOCZ", "SB*BB(t)"], ["waist_b", "X", "SW*SWB(t)"],
         ["waist_c", "LOCZ", "SB*BC(t)"], ["waist_c", "X", "-SW*SWC(t)"],
         ["waist_d", "LOCZ", "DB*BD(t)"], ["waist_d", "Y", "SW*SWD(t)"],
         ["waist_e", "LOCZ", "FB*(BE(t)-1)"], ["waist_e", "Y", "0.7*SW*SWE(t)"],
         ["waist_f", "LOCZ", "FB*(BF(t)-1)"], ["waist_f", "Y", "0.7*SW*SWF(t)"]]
# followers: leader's hands, dangling legs, small horns
pose += [["left_hand_a", "Y", "-HB*BA(t-0.05)"], ["right_hand_a", "Y", "HB*BA(t-0.05)"]]
for k, f in (("a", "BA"), ("b", "BB"), ("c", "BC"), ("d", "BD")):
    pose += [[f"left_leg_{k}", "X", f"LG{k.upper()}*{f}(t-0.07)"], [f"right_leg_{k}", "X", f"-LG{k.upper()}*{f}(t-0.09)"]]
pose += [["horn_e", "Y", "HRB*BD(t-0.08)"], ["horn_f_01", "Y", "-HRB*BD(t-0.1)"]]
cfg["pose_params"] = P
cfg["pose"] = pose
m = cfg.setdefault("motion", {})
m["frames"] = 120
fn = {"BR": "wave(2*t, 0.12)", "SWY": "sin(2*pi*t)"}
for i, k in enumerate("ABCDEF"):
    fn[f"B{k}"] = f"BR(t - {i}*LAG)"
    fn[f"SW{k}"] = f"SWY(t - {i}*LAG)"
m["functions"] = fn
m["plant"] = ["left_foot_e", "right_foot_e", "left_foot_f", "right_foot_f"]
cfg["camera"]["target"] = cfg["camera"].get("target")
json.dump(cfg, open(cfgp, "w"), indent=2)
print("wrote", cfgp, len(pose), "pose entries")
