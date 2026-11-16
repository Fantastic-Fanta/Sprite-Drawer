"""Write pose / pose_params / motion for Mega Delphox (v2: surfing its broom).
Keeps existing pose_params unless overridden: python3 gen.py [KEY=value ...] [--out PATH] [--fresh]
(--fresh starts from DEFAULTS). Prints every change. v1 (hovering witch) is gen_v1.py.

Frame: Delphox faces -Y; the main broom is turned to run along X under its feet, stick
(leading end) toward -X = screen left, flame trailing toward +X. Its feet are already apart
along X, so it stands across the broom like a surfer, chest to the camera side."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = HERE / "mega_delphox_front.v2.json"
out = CFG
args = sys.argv[1:]
if "--out" in args:
    i = args.index("--out"); out = Path(args[i + 1]); del args[i:i + 2]
fresh = "--fresh" in args
args = [a for a in args if a != "--fresh"]

DEFAULTS = {
    "AZIMUTH": 55, "ELEVATION": 14, "FOV": 30,
    # --- rest: the board (main broom) ---
    "BRR": -90, "BRX": -0.15, "BRY": 0.0, "BRZ": 0.17, "BRP": 0,
    # --- rest: side brooms sailing alongside, same heading, a little nose-up ---
    "SBR": -90, "SBP": 10,
    "BX": -0.75, "BY": 0.55, "BZ": 2.25,       # feeler_b: behind, high (offset from rest head z=-0.8)
    "CX": -1.15, "CY": -0.55, "CZ": 2.05,      # feeler_c: in front, a little lower (rest z=-1.2)
    # --- rest: surfer stance ---
    "CR": 0.05, "KNB": 12,                     # crouch: hip drop (units), shin bend (deg)
    "LEAN": 8, "TWIST": 6, "SIDE": 0,          # torso forward lean, twist toward travel, side tilt
    "HDT": 12, "HDU": 10,                      # head turn toward travel (-X), head up
    "RAD": 15, "RAF": 25, "RELB": 15,          # lead (right) arm: down, forward, elbow
    "LAD": 40, "LAB": 20, "LELB": 20,          # trailing (left) arm: down, back, elbow
    "SLV": 60, "SLV2": 20,                     # sleeves hang
    "HAIRD": 25, "HAIRB": 15,                  # long ear strands droop / sweep back
    "TAILS": 35, "TAILD": 5,                   # robe tail trails toward +X, droops
    "BDF": 6,                                  # beard forward off the robe
    # --- idle: riding a wave ---
    "RISE": 2.5,                               # board + rider rise/fall, sprite px (amplitude)
    "PX_U": 0.02,                              # world units per sprite px (measured)
    "PITCH": 3.0, "BANK": 2.0,                 # board nose-up while rising; roll toward camera
    "KN": 0.035, "KNA": 6,                     # knee absorb: hip dip (units), shin bend (deg)
    "SPB": 2.0, "SWY": 2.0, "HSTAB": 0.6,      # chest follow, side sway, head steadies (x pitch)
    "RAB": 6.0, "LAB2": 5.0, "EB": 3.0,        # arms balance
    "SB": 6.0, "SB2": 5.0,                     # sleeves
    "HRB": 4.0, "HRB2": 3.0,                   # ear strands
    "TB": 5.0, "TB2": 5.0, "TB3": 4.0,         # robe tail
    "FB": 2.0, "EB2": 2.0,                     # beard, back robe flap
    "SLAG": 0.9, "SLAG2": 1.5,                 # side brooms trail the board by (rad)
    "SBOB": 1.0, "SPIT": 4.0,                  # side broom extra bob (px) and pitch (deg)
    "FLK": 5.0,                                # flame lick
}
cfg = json.loads(CFG.read_text())
old = dict(cfg.get("pose_params", {}))
params = dict(DEFAULTS)
if not fresh:
    params.update({k: v for k, v in old.items() if k in DEFAULTS})
for a in args:
    k, v = a.split("=", 1)
    params[k] = float(v)
for k in sorted(set(params) | set(old)):
    if old.get(k) != params.get(k):
        print(f"  {k}: {old.get(k)} -> {params.get(k)}")

W = "2*pi*t"
DIP = f"KN*(1 - sin({W} - 0.5))/2"          # knees compress just after the trough
pose = [
    # ===== rest =====
    # the board: turn the broom across, under the soles
    ["feeler_a", "Z", "BRR"],
    ["feeler_a", "LOCX", "BRX"], ["feeler_a", "LOCY", "BRY"], ["feeler_a", "LOCZ", "BRZ"],
    ["feeler_a", "Y", "BRP"],
    # side brooms: same heading, nose a little up, alongside and above
    ["feeler_b", "Z", "SBR"], ["feeler_b", "Y", "SBP"],
    ["feeler_c", "Z", "SBR"], ["feeler_c", "Y", "SBP"],
    ["feeler_b", "LOCX", "BX"], ["feeler_b", "LOCY", "BY"], ["feeler_b", "LOCZ", "BZ"],
    ["feeler_c", "LOCX", "CX"], ["feeler_c", "LOCY", "CY"], ["feeler_c", "LOCZ", "CZ"],
    # stance: soft knees (shins forward), torso leans in and turns toward travel
    ["left_leg_02", "A:1,0,0", "-KNB"], ["right_leg_02", "A:1,0,0", "-KNB"],
    ["spine_01", "A:1,0,0", "LEAN"],
    ["spine_02", "A:0,0,1", "-TWIST"],
    ["spine_01", "A:0,1,0", "SIDE"],
    ["head", "A:0,0,1", "-HDT"],
    ["head", "A:-1,0,0", "HDU+LEAN"],
    # lead arm (right, -X) out ahead for balance; trailing arm low and back
    ["right_arm_01", "A:0,1,0", "-RAD"], ["right_arm_01", "A:0,0,1", "RAF"],
    ["right_arm_02", "A:0,0,1", "RELB"],
    ["left_arm_01", "A:0,1,0", "LAD"], ["left_arm_01", "A:0,0,1", "LAB"],
    ["left_arm_02", "A:0,0,1", "-LELB"],
    ["left_feeler_c_01", "A:1,0,0", "-SLV"], ["right_feeler_c_01", "A:1,0,0", "-SLV"],
    ["left_feeler_c_02", "A:1,0,0", "-SLV2"], ["right_feeler_c_02", "A:1,0,0", "-SLV2"],
    ["left_hair_e_01", "A:0.26,-0.97,0", "-HAIRD"], ["right_hair_e_01", "A:-0.26,-0.97,0", "HAIRD"],
    ["left_hair_e_01", "A:0,0,1", "HAIRB"], ["right_hair_e_01", "A:0,0,-1", "HAIRB"],
    ["tail_01", "A:0,0,1", "-TAILS"], ["tail_01", "A:1,0,0", "-TAILD"],
    ["feeler_d_01", "A:-1,0,0", "BDF"],

    # ===== idle: riding a wave (driver = board height FY, one swell per loop) =====
    # knees absorb: hips dip, shins fold, soles brought back onto the board
    ["waist", "LOCZ", "-CR - " + DIP],
    ["left_leg_02", "A:1,0,0", f"-KNA*(1 - sin({W} - 0.5))/2"],
    ["right_leg_02", "A:1,0,0", f"-KNA*(1 - sin({W} - 0.5))/2"],
    ["left_foot", "LOCZ", "CR + " + DIP], ["right_foot", "LOCZ", "CR + " + DIP],
    # upper body follows, head steadies against the board pitch
    ["spine_02", "A:1,0,0", f"SPB*sin({W} - 1.0)"],
    ["spine_02", "A:0,1,0", f"SWY*sin({W} - 1.2)"],
    ["head", "A:0,1,0", f"-HSTAB*PITCH*cos({W} - 0.4)"],
    ["head", "A:-1,0,0", f"-HSTAB*SPB*sin({W} - 1.4)"],
    # arms balance (lead arm lifts as the board drops), elbows later
    ["right_arm_01", "A:0,1,0", f"-RAB*sin({W} - 1.0)"],
    ["left_arm_01", "A:0,1,0", f"-LAB2*sin({W} - 1.2)"],
    ["right_arm_02", "A:0,1,0", f"-EB*sin({W} - 1.5)"],
    ["left_arm_02", "A:0,1,0", f"-EB*sin({W} - 1.7)"],
    # light trailing parts lag most
    ["left_feeler_c_01", "A:1,0,0", f"SB*sin({W} - 1.6)"],
    ["right_feeler_c_01", "A:1,0,0", f"SB*sin({W} - 1.5)"],
    ["left_feeler_c_02", "A:1,0,0", f"SB2*sin({W} - 2.1)"],
    ["right_feeler_c_02", "A:1,0,0", f"SB2*sin({W} - 2.0)"],
    ["left_hair_e_01", "A:0.26,-0.97,0", f"HRB*sin({W} - 1.5)"],
    ["right_hair_e_01", "A:-0.26,-0.97,0", f"-HRB*sin({W} - 1.5)"],
    ["left_hair_e_03", "A:0.26,-0.97,0", f"HRB2*sin({W} - 2.1)"],
    ["right_hair_e_03", "A:-0.26,-0.97,0", f"-HRB2*sin({W} - 2.1)"],
    ["tail_01", "A:1,0,0", f"TB*sin({W} - 1.2)"],
    ["tail_02", "A:1,0,0", f"TB2*sin({W} - 1.7)"],
    ["tail_03", "A:1,0,0", f"TB3*sin({W} - 2.2)"],
    ["tail_02", "A:0,0,1", f"0.5*TB2*sin({W} - 1.9)"],
    ["feeler_d_01", "A:-1,0,0", f"FB*sin({W} - 1.3)"],
    ["feeler_e", "A:1,0,0", f"EB2*sin({W} - 1.4)"],
    # the other brooms sail alongside, a beat behind the board
    ["feeler_b", "LOCCAM", f"PX_U*(RISE*(sin({W} - SLAG) - sin({W})) + SBOB*sin({W} - SLAG))"],
    ["feeler_c", "LOCCAM", f"PX_U*(RISE*(sin({W} - SLAG2) - sin({W})) + SBOB*sin({W} - SLAG2))"],
    ["feeler_b", "Y", f"PITCH*(cos({W} - SLAG) - cos({W})) + SPIT*cos({W} - SLAG)"],
    ["feeler_c", "Y", f"PITCH*(cos({W} - SLAG2) - cos({W})) + SPIT*cos({W} - SLAG2)"],
    # flames lick: a wave up each flame, growing toward the tip (3 per loop)
    ["horn_a_01", "A:0,0,1", f"0.5*FLK*sin(3*{W})"],
    ["horn_a_02", "A:0,0,1", f"0.8*FLK*sin(3*{W} - 0.9)"],
    ["horn_a_03", "A:0,1,0", f"1.0*FLK*sin(3*{W} - 1.8)"],
    ["horn_a_04", "A:0,0,1", f"1.2*FLK*sin(3*{W} - 2.7)"],
    ["horn_c", "A:0,1,0", f"FLK*sin(3*{W} - 1.2)"],
    ["horn_b", "A:0,1,0", f"FLK*sin(3*{W} - 0.4)"],
    ["horn_d_01", "A:0,0,1", f"FLK*sin(3*{W} - 2.0)"],
    ["horn_d_02", "A:0,1,0", f"FLK*sin(3*{W} - 2.9)"],
    ["horn_e_01", "A:0,0,1", f"FLK*sin(3*{W} - 0.5)"],
    ["horn_e_02", "A:0,1,0", f"FLK*sin(3*{W} - 1.4)"],
    # last: the board and rider ride the swell together. Whole pixels go to style.pixel_bob, the
    # remainder here; the board pitches nose-up while rising and banks a little (pivot at the soles)
    ["origin", "LOCCAM", "PX_U*(FY(t) - round(FY(t)))"],
    ["origin", "Y", f"PITCH*cos({W})"],
    ["origin", "X", f"BANK*sin({W} - 0.6)"],
]
cfg["pose_params"] = params
cfg["pose"] = pose
cfg["motion"] = {
    "frames": 120,
    "functions": {"FY": f"RISE*sin({W})"},
    "note": ("Mega Delphox surfs its flaming broom (Z-A art: it rides the big branch, the two small "
             "brooms fly the same way beside it). It stands across the broom like a surfboard, feet "
             "on the stick, knees soft, lead arm out ahead for balance, head turned toward travel. "
             "One driver: the board and rider crest a slow swell, one per 3.6 s loop, nose up while "
             "rising, banking a little. The knees absorb it (hips dip just after the trough), chest, "
             "head and arms follow a beat later; robe tail, sleeves, ear strands and beard trail "
             "most; the two small brooms ride the same swell a beat and a half behind; flames lick."),
}
cfg["style"]["pixel_bob"] = {"y": "FY(t)"}
cfg["render"].setdefault("hull", {})["cap_each_frame"] = True
out.write_text(json.dumps(cfg, indent=2) + "\n")
print("wrote", out)
