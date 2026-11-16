"""Writes pose / motion into mega_floette_front.json. Keeps existing pose_params values
(only adds missing ones) unless named as KEY=value on the command line; prints every change."""
import json, sys
from pathlib import Path

CFG = Path(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].endswith(".json") else \
    Path(__file__).parent / "mega_floette_front.json"
args = [a for a in sys.argv[1:] if "=" in a]
cfg = json.loads(CFG.read_text())

DEFAULTS = {
    "AZIMUTH": 70, "ELEVATION": 12, "FOV": 30,
    # pose: stem turned up from the hips so the flower floats above the fairy (art)
    "STEM_F": 45.0,      # per joint, feeler_01..04, about own y (world X): forward/back
    "STEM_S": 0.0,       # per joint, feeler_01..04, about own z: sideways
    "STEM_LEAN": 0.0,    # feeler_05..08, sideways lean of the long stem
    "FLOWER_TILT": 0.0, "FLOWER_ROLL": 0.0,  # feeler_12 about own y: tips the flower face to the camera
    "BODY_TILT": 0.0,    # spine about own y (lean)
    "HEAD_TILT": 0.0,
    "L_DOWN": 0.0, "L_FWD": 0.0, "L_ELB": 0.0,
    "R_DOWN": 0.0, "R_FWD": 0.0, "R_ELB": 0.0,
    "TAIL_CURL": 0.0,
    # motion (amplitudes; 0 = off)
    "NF": 120, "PX_U": 0.006,
    "HOVER_PX": 0.0, "SKEW": 0.15, "DRIFT_PX": 0.0,
    "SWAY_DEG": 0.0, "SWAY_LAG": 0.06, "COMP": 0.0, "ROCK_KEEP": 0.2, "ROCK_SIGN": -1, "BOBSW_DEG": 0.0,
    "FLOWER_DEG": 0.0, "FLOWER_LAG": 0.14,
    "PETAL_DEG": 0.0, "PETAL_LAG": 0.2, "PETAL_C": 2,
    "BODY_DEG": 0.0, "BODY_LAG": 0.08,
    "ARMS_DEG": 0.0, "ARMS_LAG": 0.12,
    "TAILM_DEG": 0.0, "TAILM_LAG": 0.16,
    "FEEL_DEG": 0.0, "FEEL_C": 2,
    "CURVE_S": 0.0, "CURVE_F": 0.0, "STEMW_DEG": 0.0, "STEMW_LAG": 0.04,
}
OVERRIDE = {k.split("=")[0]: float(k.split("=")[1]) for k in args}
pp = cfg.setdefault("pose_params", {})
for k, v in DEFAULTS.items():
    if k in OVERRIDE:
        v = OVERRIDE[k]
        if pp.get(k) != v:
            print(f"  {k}: {pp.get(k)} -> {v}")
        pp[k] = v
    elif k not in pp:
        print(f"  {k}: (new) {v}")
        pp[k] = v
for k in OVERRIDE:
    if k not in DEFAULTS:
        print(f"  unknown param {k}")

cfg["motion"]["frames"] = int(pp["NF"])
cfg["motion"]["functions"] = {
    "FY": "HOVER_PX*wave(t + 0.25, SKEW)",                    # flower bob, sprite px, +up
    "hn": "wave(t + 0.25, SKEW)",                              # normalised bob
    "dr": "sin(2*pi*t)",                                       # normalised drift
    "pa": "SWAY_DEG*sin(2*pi*(t - SWAY_LAG))",                 # pendulum angle of the fairy, deg
    # whole-sprite shift that keeps the flower in place while the stem swings below it
    "FX": "DRIFT_PX*dr(t) + COMP*pa(t)",
}
pose = []
pose += [["origin", "LOCCAM", "PX_U*(FY(t) - round(FY(t)))"],
         ["origin", "LOCCAMX", "PX_U*(FX(t) - round(FX(t)))"]]

FY_, FZ_ = "A:1,0,0", "A:0,-1,0"   # stem chain own y / z at rest
# stem: turned up near the hips; the long stem leans; the swing is a screen-plane bend spread
# over the lower stem, each joint a little later toward the fairy (the free end lags)
for i in range(1, 5):
    pose.append([f"feeler_{i:02d}", FY_, "STEM_F"])
    pose.append([f"feeler_{i:02d}", FZ_, "STEM_S"])
SW = {5: 0.30, 6: 0.25, 7: 0.20, 8: 0.15, 9: 0.10}
for i in range(5, 12):
    lean = "STEM_LEAN" if i <= 8 else "0"
    # a soft S down the long stem (lower half one way, upper half the other) and a slight forward
    # bow, plus a sway that travels from the flower down to the fairy (lower joints later)
    curve = "0.75*CURVE_S" if i <= 8 else "-CURVE_S"      # 4 joints one way, 3 the other: no net tilt
    wave = f"STEMW_DEG*sin(2*pi*(t - STEMW_LAG*{11 - i}))"
    # FZ_ bends the stem across the sprite camera's view, FY_ toward the camera (and tips the
    # flower's face at it, hiding the stem): the S and the main sway go on FZ_
    pose.append([f"feeler_{i:02d}", FZ_, f"{lean} + {curve} + {wave}"])
    pose.append([f"feeler_{i:02d}", FY_, f"CURVE_F + 0.5*STEMW_DEG*cos(2*pi*(t - STEMW_LAG*{11 - i} + 0.1))"])
    if i in SW:
        pose.append([f"feeler_{i:02d}", "ROLLCAM", f"{SW[i]:.2f}*SWAY_DEG*sin(2*pi*(t - SWAY_LAG - {(9 - i)*0.015:.3f}))"])
        pose.append([f"feeler_{i:02d}", FY_, f"{SW[i]:.2f}*BOBSW_DEG*hn(t - SWAY_LAG - {(9 - i)*0.015:.3f})"])
# flower head: cancels most of the stem's tilt, keeps a little slow rock of its own
pose.append(["feeler_12", "ROLLCAM", "ROCK_SIGN*(1 - ROCK_KEEP)*pa(t - 0.0) + FLOWER_DEG*dr(t - FLOWER_LAG)"])
# flower head: tilt to camera, then rocks after the stem (heavy, wide: slow and late)
pose.append(["feeler_12", FY_, "FLOWER_TILT - BOBSW_DEG*hn(t - SWAY_LAG)"])
pose.append(["feeler_12", FZ_, "FLOWER_ROLL"])
# petals: light tips flex last
for side, ax in [("front_feeler_a", "A:1,0,0"), ("left_feeler_b", "A:-0.5,0.87,0"),
                 ("right_feeler_b", "A:-0.5,-0.87,0")]:
    for j, wj in [("01", 0.5), ("02", 1.0)]:
        pose.append([f"{side}_{j}", ax, f"PETAL_DEG*{wj}*hn(t - PETAL_LAG - {0.04 if j == '02' else 0})"])
for b, ax in [("front_feeler_b", "A:1,0,0"), ("left_feeler_d", "A:-0.5,0.87,0"), ("right_feeler_d", "A:-0.5,-0.87,0")]:
    pose.append([b, ax, f"1.5*PETAL_DEG*sin(2*pi*(PETAL_C*t - 0.3))"])

# fairy: hangs from the stem; body swings a beat after, arms and tail later
pose.append(["spine", "A:1,0,0", "BODY_TILT + BODY_DEG*hn(t - BODY_LAG)"])
pose.append(["spine", "ROLLCAM", "BODY_DEG*sin(2*pi*(t - SWAY_LAG - BODY_LAG))"])
pose.append(["head", "A:1,0,0", "HEAD_TILT + 0.6*BODY_DEG*hn(t - BODY_LAG - 0.05)"])
# arms: DOWN about world +/-Y, FWD about world Z (toward the face side, -Y), elbow the same
ARMAX = {"left": ("A:0,1,0", "A:0,0,-1"), "right": ("A:0,-1,0", "A:0,0,1")}
for s in ("left", "right"):
    dn, fw = ARMAX[s]
    P = s[0].upper()
    ph = 0.0 if s == "left" else 0.03
    pose.append([f"{s}_arm_01", dn, f"{P}_DOWN + ARMS_DEG*hn(t - ARMS_LAG - {ph})"])
    pose.append([f"{s}_arm_01", fw, f"{P}_FWD"])
    pose.append([f"{s}_arm_02", fw, f"{P}_ELB + 0.6*ARMS_DEG*hn(t - ARMS_LAG - 0.04 - {ph})"])
    for j in ("01", "02", "03"):
        pose.append([f"{s}_feeler_a_{j}", "A:0,-1,0" if s == "left" else "A:0,1,0",
                     f"FEEL_DEG*{0.5 + 0.25*int(j)}*sin(2*pi*(FEEL_C*t - {0.06*int(j)}))"])
# tail coil: only tail_03 swings (tail_02 carries the stem, so tail_01/02 stay put)
pose.append(["tail_01", "A:1,0,0", "TAIL_CURL"])
pose.append(["tail_03", "A:1,0,0", "TAILM_DEG*hn(t - TAILM_LAG)"])
pose.append(["tail_03", "ROLLCAM", "0.7*TAILM_DEG*sin(2*pi*(t - SWAY_LAG - TAILM_LAG))"])
old = len(cfg.get("pose", []))
cfg["pose"] = pose
cfg["style"]["pixel_bob"] = {"y": "FY(t)", "x": "FX(t)"}
cfg["motion"]["note"] = (Path(__file__).parent / "motion.note").read_text().strip() \
    if (Path(__file__).parent / "motion.note").exists() else cfg["motion"].get("note")
print(f"pose: {old} -> {len(pose)} entries")
CFG.write_text(json.dumps(cfg, indent=2) + "\n")
