"""Write the tail whip (on top of motion.clip) into mega_raichu_y_front.json. Keeps existing
pose_params unless overridden: python3 gen.py KEY=value ... (prints every change).
ROLLCAM = in-picture tilt about each bone head; root first, so each joint adds to its parents."""
import json, sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "mega_raichu_y_front.json")
cfg = json.load(open(CFG))
pp = cfg.setdefault("pose_params", {})
for k, v in {"AZIMUTH": 60.0, "ELEVATION": 10, "WC": 3.0, "WB": 6.0, "WF": 2.5}.items():
    pp.setdefault(k, v)
for a in sys.argv[1:]:
    k, v = a.split("="); old = pp.get(k); pp[k] = float(v); print(f"{k}: {old} -> {pp[k]}")
W = "2*pi*t"
# the clip's body bob: low at t=0, high at t=0.5 (waist z ~ -cos W); the tail drags behind it,
# each joint a beat later, the bolt with a 2x flutter on top
pose = [
    ["tail_05", "ROLLCAM", f"-WC*sin({W} - 0.6)"],
    ["tail_06", "ROLLCAM", f"-WC*sin({W} - 0.9)"],
    ["tail_07", "ROLLCAM", f"-WC*sin({W} - 1.2)"],
    ["tail_08", "ROLLCAM", f"-1.3*WC*sin({W} - 1.5)"],
    ["tail_09", "ROLLCAM", f"-0.8*WB*sin({W} - 1.8) - 0.6*WF*sin(2*{W} - 2.2)"],
    ["tail_10", "ROLLCAM", f"-WB*sin({W} - 2.1) - WF*sin(2*{W} - 2.6)"],
]
cfg["pose"] = pose
json.dump(cfg, open(CFG, "w"), indent=2)
print("wrote", CFG)
