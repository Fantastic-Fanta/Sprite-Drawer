"""Write pose / pose_params / motion into mega_magearna_front.json (or --cfg PATH).
Keeps existing param values (config wins over DEFAULTS) unless --reset; KEY=value args override.
Prints every change."""
import json, sys
from pathlib import Path
args = sys.argv[1:]
CFG = Path(__file__).parent / "mega_magearna_front.json"
if "--cfg" in args:
    i = args.index("--cfg"); CFG = Path(args[i + 1]); del args[i:i + 2]
RESET = "--reset" in args
args = [a for a in args if a != "--reset"]
DEFAULTS = dict(AZIMUTH=72, ELEVATION=10, FOV=30,
    GTILT=90, GYAW=-20, GX=0.3, GZ=0.45, GY=0.08,
    LARMD=50, LARMF=12, LELB=28, LELBD=-10, RARMD=5, RARMF=25, RELB=8, HANDF=65,
    HEADZ=0, HEADT=8, ROD=0.02, GAP=0.07,
    PXU=0.00818, LAG=0.07, DIP=0.5, SWAY=1.6, SHIFT=1.6, BREATH=1.2, HEADB=2.5, EAR=4.0,
    ARM=4.0, ELB=6.0, RARM=1.5, STAR=1.5, SKIRT=1.0, PANEL=1.2,
    GB=2.0, GL=0.15, GPH=0.12, GTIL=2.0, KNEE=7)
POSE = [
    # gears: stand upright beside the skirt, turned a little to the camera
    ["left_horn_02", "LOCX", "GX"], ["right_horn_02", "LOCX", "-GX"],
    ["left_horn_02", "LOCZ", "GZ"], ["right_horn_02", "LOCZ", "GZ"],
    ["left_horn_02", "LOCY", "GY"], ["right_horn_02", "LOCY", "GY"],
    ["left_horn_02", "A:1,0,0", "GTILT"], ["right_horn_02", "A:1,0,0", "GTILT"],
    ["left_horn_02", "A:0,0,1", "-GYAW"], ["right_horn_02", "A:0,0,1", "GYAW"],
    # blaster: the thin red stamen rods (feeler_i..n) are thinner than a sprite pixel and broke the
    # hull into dots and dashes; tuck them into the cone so the flower reads as petals + cone
    ["feeler_i", "SCALE", "ROD"], ["feeler_j", "SCALE", "ROD"], ["feeler_k", "SCALE", "ROD"],
    ["feeler_l", "SCALE", "ROD"], ["feeler_m", "SCALE", "ROD"], ["feeler_n", "SCALE", "ROD"],
    # the flower floated a hand-width off the gun arm's tip (model rest pose); seat it on the hand
    ["feeler_a", "LOCX", "GAP*sin((RARMF + RELB + HANDF)*pi/180)"],
    ["feeler_a", "LOCY", "-GAP*cos((RARMF + RELB + HANDF)*pi/180)"],
    # arms: the free arm hangs soft with a bent elbow (a doll's port de bras), the gun arm held out
    ["left_arm_01", "A:0,1,0", "LARMD"], ["left_arm_01", "A:0,0,1", "-LARMF"],
    ["left_arm_02", "A:0,0,1", "-LELB"], ["left_arm_02", "A:0,1,0", "LELBD"],
    ["right_arm_01", "A:0,1,0", "-RARMD"], ["right_arm_01", "A:0,0,1", "RARMF"],
    ["right_arm_02", "A:0,0,1", "RELB"],
    ["right_hand", "A:0,0,1", "HANDF"],
    # legs: knee slack so the planted legs can give under the weight shift
    ["left_leg_01", "A:1,0,0", "-KNEE"], ["left_leg_02", "A:1,0,0", "2*KNEE"],
    ["right_leg_01", "A:1,0,0", "-KNEE"], ["right_leg_02", "A:1,0,0", "2*KNEE"],
    # head: a doll-like tilt
    ["head", "A:0,-1,0", "HEADT"], ["head", "A:0,0,1", "HEADZ"],
    # ---- idle: one soft weight shift drives it (w); everything trails a beat later ----
    ["waist", "LOCX", "-SHIFT*PXU*w(t)"],
    ["waist", "A:0,1,0", "SWAY*w(t)"],
    ["waist", "LOCZ", "-DIP*PXU*(0.5 + 0.5*cos(4*pi*t))"],         # sinks as the weight passes centre
    ["spine", "A:1,0,0", "BREATH*sin(4*pi*(t - LAG))"],
    ["spine", "A:0,1,0", "-0.7*SWAY*w(t - LAG)"],                   # upper body counter-balances
    ["head", "A:0,-1,0", "HEADB*w(t - 2*LAG)"],
    ["left_ear_01", "A:0,-1,0", "EAR*w(t - 3*LAG)"], ["left_ear_02", "A:0,-1,0", "1.4*EAR*w(t - 4*LAG)"],
    ["right_ear_01", "A:0,-1,0", "EAR*w(t - 3*LAG)"], ["right_ear_02", "A:0,-1,0", "1.4*EAR*w(t - 4*LAG)"],
    # free arm floats out and in, elbow then wrist trailing
    ["left_arm_01", "A:0,1,0", "ARM*w(t - 2*LAG)"],
    ["left_arm_02", "A:0,0,1", "-ELB*w(t - 3*LAG)"],
    ["left_hand", "A:0,0,1", "-1.2*ELB*w(t - 4*LAG)"],
    # gun arm: steadier (aiming), a slight float; the flower stays rigid on the hand
    ["right_arm_01", "A:0,1,0", "-RARM*w(t - 2*LAG)"],
    ["right_arm_02", "A:0,1,0", "-RARM*w(t - 3*LAG)"],
    ["right_hand", "A:0,1,0", "-STAR*w(t - 4*LAG)"],
    # skirt swings like a bell a beat behind the hips, the side panels a beat later
    ["skirt", "A:0,1,0", "-SKIRT*w(t - 1.5*LAG)"],
    ["left_root_skirt", "A:0,1,0", "-PANEL*w(t - 2.5*LAG)"], ["right_root_skirt", "A:0,1,0", "-PANEL*w(t - 2.5*LAG)"],
    # gears hover on their own bob
    ["left_horn_02", "LOCZ", "GB*PXU*sin(2*pi*(t - GL))"], ["right_horn_02", "LOCZ", "GB*PXU*sin(2*pi*(t - GL - GPH))"],
    ["left_horn_02", "A:0,1,0", "GTIL*sin(2*pi*(t - GL - 0.2))"], ["right_horn_02", "A:0,1,0", "-GTIL*sin(2*pi*(t - GL - GPH - 0.2))"],
]
MOTION = {"frames": 120, "plant": ["left_foot", "right_foot"],
  "functions": {"w": "sin(2*pi*t)"},
  "note": "Graceful clockwork doll: one slow weight shift from foot to foot drives it (120 x 30 ms = 3.6 s). The hips glide SHIFT px and roll SWAY deg, sinking DIP px each time the weight passes centre (planted feet, knees giving); the chest counter-balances and breathes twice per loop; the head tilts after it, the ribbon-ears trail further and swing most. The free arm floats out and in like a port de bras, elbow and wrist each a beat behind. The gun arm stays steady, aiming, with only a slight float; its flower is rigid. The skirt swings like a bell a beat behind the hips, its side panels a beat later. The gears hover on their own soft bob."}
def main():
    c = json.loads(CFG.read_text())
    old = c.get("pose_params", {})
    pp = dict(DEFAULTS)
    if not RESET: pp.update({k: v for k, v in old.items() if k in DEFAULTS})
    for a in args:
        k, v = a.split("="); pp[k] = float(v)
    for k in sorted(set(pp) | set(old)):
        if old.get(k) != pp.get(k): print(f"  {k}: {old.get(k)} -> {pp.get(k)}")
    c["pose_params"] = pp
    if c.get("pose") != POSE: print(f"  pose: {len(c.get('pose', []))} -> {len(POSE)} entries")
    c["pose"] = POSE; c["motion"] = MOTION
    c["style"]["height"] = 165
    c["render"].setdefault("hull", {})["cap_each_frame"] = True
    CFG.write_text(json.dumps(c, indent=2))
main()
