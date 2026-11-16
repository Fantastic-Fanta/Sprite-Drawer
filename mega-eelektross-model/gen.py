"""Writes pose / pose_params / motion into mega_eelektross_front.json.
Usage: python3 gen.py [KEY=value ...] [--out PATH]. Keeps existing pose_params unless overridden; prints changes."""
import json, sys, pathlib
HERE = pathlib.Path(__file__).parent
CFG = HERE / "mega_eelektross_front.json"
args = [a for a in sys.argv[1:] if "=" in a and not a.startswith("--")]
out = CFG
if "--out" in sys.argv:
    out = pathlib.Path(sys.argv[sys.argv.index("--out") + 1])
cfg = json.loads(CFG.read_text())

DEFAULTS = dict(AZIMUTH=40, ELEVATION=12, FOV=30,
                PITCH=0, NECK=0, HEAD=0, TCURL=0, ACURL=0, ASPLAY=0, ADROOP=0,
                FINC=0, ROLL=0, BOB=0.04, RS=0.6, PS=1.2, NS=1.5, JAW=2, HS=2.5, TS=2.5, ZR=0.6, LAG=0.05, FS=6, AS=1.5, AW=1.6, ALAG=0.035, MJ=3, AF=5, HLIFT=0)
pp = dict(DEFAULTS); pp.update(cfg.get("pose_params", {}))
for a in args:
    k, v = a.split("=", 1)
    pp[k] = float(v) if v.replace('.', '', 1).replace('-', '', 1).isdigit() else v
old = cfg.get("pose_params", {})
for k in sorted(set(pp) | set(old)):
    if old.get(k) != pp.get(k):
        print(f"  {k}: {old.get(k)} -> {pp.get(k)}")

pose = []
P = lambda b, ax, e: pose.append([b, ax, e])
S = lambda ph, k=1: f"sin(2*pi*({k}*t - {ph}))"          # loop-safe sine, phase in loops
# driver: hover bob (broad crest, quick trough) + a slight pitch rock a beat later
P("waist", "LOCZ", "BOB*wave(t, 0.1)")
P("waist", "Y", "ROLL + RS*" + S("0.20"))
P("waist", "X", "PITCH + PS*" + S("0.08"))
P("neck", "A:1,0,0", "NECK + NS*" + S("0.16"))
P("head", "A:1,0,0", "HEAD + NS*0.7*" + S("0.22"))
P("lower_jaw", "A:1,0,0", "JAW*(0.5 + 0.5*" + S("0.30") + ")")
# dorsal horn chain + head tendrils trail the head
for i in range(1, 6):
    P(f"horn_{i:02d}", "A:1,0,0", ("HLIFT + " if i == 1 else "") + f"HS*{0.5 + 0.15*i:.2f}*" + S(f"{0.25 + i*0.04:.2f}"))
P("hair_a", "A:1,0,0", "HS*1.2*" + S("0.35"))
P("hair_b", "A:1,0,0", "HS*1.4*" + S("0.42"))
# tail: rest curl up, a travelling wave (pitch) + a quarter-cycle-later yaw, tip lagging most
for i in range(1, 9):
    g = 0.5 + 0.12 * i
    P(f"tail_{i:02d}", "A:1,0,0", f"TCURL*{0.4 + 0.15 * i:.2f} + TS*{g:.2f}*" + S(f"0.12 + {i}*LAG"))
    P(f"tail_{i:02d}", "A:0,0,1", f"ZR*TS*{g:.2f}*" + S(f"0.37 + {i}*LAG"))
# body fins / feelers on the hips and legs flutter a beat behind
for b, ph in (("feeler_a", 0.20), ("feeler_b", 0.26), ("feeler_c", 0.32), ("feeler_d", 0.38)):
    P(b, "A:1,0,0", f"FS*" + S(f"{ph}"))
for s, sg in (("left", 1), ("right", -1)):
    P(f"{s}_leg_01", "A:0,1,0", f"{sg}*FS*0.8*" + S("0.28"))
    # arm tubes: hang off the body, lift a beat after the bob, trail as a chain
    P(f"{s}_arm_01", "A:0,0,1", f"{sg}*ASPLAY")
    P(f"{s}_arm_01", "A:0,1,0", f"{sg}*(ADROOP + AS*" + S("0.14" if s == "left" else "0.19") + ")")
    off = 0.0 if s == "left" else 0.06
    for i in range(2, 11):
        g = 0.3 + 0.12 * i
        P(f"{s}_feeler_b_{i:02d}", "A:1,0,0", f"ACURL*{g:.2f} + AW*{g:.2f}*" + S(f"{0.18 + off} + {i}*ALAG"))
        P(f"{s}_feeler_b_{i:02d}", "A:0,0,1", f"{sg}*ZR*AW*{g:.2f}*" + S(f"{0.43 + off} + {i}*ALAG"))
    # tube mouth jaws breathe; arm fins flutter
    for j, d in (("upper_jaw_d", 1), ("lower_jaw_d", 1)):
        P(f"{s}_{j}", "A:1,0,0", f"{d}*MJ*(0.5 + 0.5*" + S(f"{0.3 + off}") + ")")
    for h, ph in (("hair_a", 0.3), ("hair_b", 0.34)):
        for i in range(1, 5):
            P(f"{s}_{h}_{i:02d}", "A:0,1,0", f"AF*{0.5 + 0.2*i:.2f}*" + S(f"{ph + off} + {i}*0.04"))

cfg["pose_params"] = pp
cfg["pose"] = pose
cfg["motion"]["frames"] = 120
out.write_text(json.dumps(cfg, indent=2) + "\n")
print("wrote", out)
