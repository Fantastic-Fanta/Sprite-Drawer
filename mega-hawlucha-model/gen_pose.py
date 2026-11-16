"""Write pose / pose_params / motion into mega_hawlucha_front.json (v2: sumo brawler).

Run: /usr/local/bin/python3 mega-hawlucha-model/gen_pose.py [--reset] [NAME=value ...]
Params already in the config keep their values (only new names get the defaults below);
--reset drops params this generator no longer uses and resets all to DEFAULTS.
NAME=value on the command line changes one. Prints before -> after for every change.
Entries are sorted deepest bone first, so each bend uses the bone's rest axes (RIG.md, world
space at rest) before its parents move it. Right-side bends use the left bone's axis mirrored
(x, -y, -z): the same angle gives a mirror image, a negated angle gives the same-direction move
for anything sideways (sway).

Driver S(t) = sin(2*pi*t): the weight shifts toward the model's left (+X) and back to the right.
"""
import json
import math as _m
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = HERE / "mega_hawlucha_front.json"

DEFAULTS = {
    "AZIMUTH": 55, "ELEVATION": 10, "FOV": 30,
    # rest pose: sumo crouch (deg; world units for CROUCH)
    "CROUCH": 0.08, "LEAN": 22, "NECK": 18, "HEADUP": -22, "HDTURN": 12,
    "SPREAD": 38, "KNEE": 58, "KFWD": 8, "TOEOUT": 25,
    "ARM_FWD": 35, "ARM_UP": -15, "ELB": 15, "ELB_IN": 15, "WRIST": 10, "CLAW": 25,
    "WSPREAD": 0, "CREST": 10, "FAN": 10, "TAIL": 0,
    # motion (world units for SHIFT / DIP, deg for the rest)
    "SHIFT": 0.022, "DIP": 0.008, "ROLL": 2.0, "HEADC": 1.6,
    "ARM": 4.0, "ELBF": 4.0, "CLAWF": 8.0, "WING": 4.0, "WINGF": 1.0,
    "HAIR": 6.0, "HAIRF": 1.5, "TAILS": 5.0, "TAILF": 1.0, "FUR": 3.0, "CLOTH": 3.0,
}

depth, axes = {}, {}
for line in (HERE / "RIG.md").read_text().splitlines():
    m = re.match(r"^( *)(\w+)  head=.*axes x=\(([^)]*)\) y=\(([^)]*)\) z=\(([^)]*)\)", line)
    if m:
        depth[m.group(2)] = len(m.group(1)) // 2
        axes[m.group(2)] = {k: tuple(float(c) for c in m.group(i).split(","))
                            for k, i in (("x", 3), ("y", 4), ("z", 5))}

cfg = json.loads(CFG.read_text())
old = cfg.get("pose_params", {})
args = sys.argv[1:]
reset = "--reset" in args
cli = dict(a.split("=", 1) for a in args if "=" in a)
new = {}
for k, v in DEFAULTS.items():
    new[k] = float(cli[k]) if k in cli else (v if reset else old.get(k, v))
if not reset:
    for k, v in old.items():
        new.setdefault(k, float(cli[k]) if k in cli else v)
for k in sorted(set(old) | set(new)):
    if old.get(k) != new.get(k):
        print(f"  {k}: {old.get(k)} -> {new.get(k)}")

pose = []


def A(bone, axis, expr):
    pose.append([bone, "A:" + ",".join(f"{c:g}" for c in axis), expr])


def side(name, ax, expr, sway=None):
    """bend left_NAME about its own axis `ax` (or a world axis tuple) and right_NAME as its
    mirror image. `sway` (optional) is added to the left and subtracted on the right in mirror
    terms, so both sides move the same way on screen (a sideways weight shift)."""
    v = axes["left_" + name][ax] if isinstance(ax, str) else ax
    l = expr if not sway else f"{expr} + {sway}"
    r = expr if not sway else f"{expr} - ({sway})"
    A("left_" + name, v, l)
    A("right_" + name, (v[0], -v[1], -v[2]), r)


def _n(v):
    m = sum(c * c for c in v) ** 0.5
    return tuple(c / m for c in v)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _rot(v, axis, deg):
    """v turned about unit `axis` by `deg` (Rodrigues)"""
    import math
    c, s_ = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    k = axis
    kxv = _cross(k, v)
    kv = sum(a * b for a, b in zip(k, v))
    return tuple(v[i] * c + kxv[i] * s_ + k[i] * kv * (1 - c) for i in range(3))


def aim_axis(rest_dir, target_dir):
    """axis (unit) and angle (deg) turning rest_dir onto target_dir"""
    import math
    a, b = _n(rest_dir), _n(target_dir)
    ax = _n(_cross(a, b))
    ang = math.degrees(math.acos(max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b))))))
    return ax, ang


def S(lag):
    """the weight-shift driver, `lag` of a loop later"""
    return f"S(t-{lag:g})"


def P(lag):
    """the settle: 0 mid-shift, 1 at each side (twice a loop), eased"""
    return f"P(t-{lag:g})"


def F(lag, k=2):
    """a faster flutter (k cycles per loop) for light strands"""
    return f"sin({2 * k}*pi*(t-{lag:g}))"


# --- body: lean in, roll a little over the loaded leg, head locked on the target ------
# world +X tilt leans forward; world +Y tilt rolls the top toward +X (model's left)
A("spine_01", (1, 0, 0), f"0.5*LEAN + 0.2*LEAN*0")
A("spine_01", (0, 1, 0), f"ROLL*{S(0.04)}")
A("spine_02", (1, 0, 0), f"0.5*LEAN - 0.6*ROLL*{P(0.06)}")  # chest coils in at each side
A("spine_02", (0, 1, 0), f"0.6*ROLL*{S(0.08)}")
A("neck", (1, 0, 0), "NECK")
A("neck", (0, 1, 0), f"-0.8*ROLL*{S(0.12)}")
A("head", (1, 0, 0), f"HEADUP + 0.5*HEADC*{P(0.14)}")
A("head", (0, 1, 0), f"-HEADC*{S(0.16)}")                    # head counters: stays level
A("head", (0, 0, 1), f"HDTURN - 0.5*HEADC*{S(0.16)}")

# --- arms out and forward like a wrestler's, claws open to grab --------------------------
# arms: aim upper arm and forearm at target directions (left side, torso rest frame), then
# bend about fixed axes. ARM_FWD / ARM_UP / ELB / ELB_IN are the targets' angles:
#   upper arm: out to the side, turned ARM_FWD deg forward and ARM_UP deg up (negative = down)
#   forearm: forward, ELB deg up from horizontal and ELB_IN deg in toward the middle
U_REST, F_REST = (0.99, 0.10, 0.0), (0.74, -0.32, 0.60)
_cu, _su = _m.cos(_m.radians(new["ARM_UP"])), _m.sin(_m.radians(new["ARM_UP"]))
u_t = (_cu * _m.cos(_m.radians(new["ARM_FWD"])), -_cu * _m.sin(_m.radians(new["ARM_FWD"])), _su)
_ce = _m.cos(_m.radians(new["ELB"]))
f_t = (-_ce * _m.sin(_m.radians(new["ELB_IN"])), -_ce * _m.cos(_m.radians(new["ELB_IN"])), _m.sin(_m.radians(new["ELB"])))
ua, uang = aim_axis(U_REST, u_t)
f_in_parent = _rot(f_t, ua, -uang)          # forearm target before the upper arm's turn
fa, fang = aim_axis(F_REST, f_in_parent)
up_ax = _n(_cross(u_t, (0, 0, 1)))           # turns the upper arm (as aimed) up / down
side("arm_01", ua, f"{uang:.2f}")
side("arm_01", axes["left_arm_01"]["z"], "0", f"ARM*{S(0.12)}")     # shoulders turn with the shift
side("arm_01", _rot(up_ax, ua, -uang), f"-0.6*ARM*{P(0.14)}")
side("arm_02", fa, f"{fang:.2f}")
side("arm_02", axes["left_arm_02"]["y"], f"-ELBF*{P(0.18)}")
side("hand", "z", f"WRIST + 0.5*ELBF*{P(0.22)}")
for f in ("index", "middle", "ring"):
    for j, w in (("02", 1.0), ("03", 0.8)):
        side(f"{f}_{j}", "y", f"CLAW*{w:g} + {w:g}*CLAWF*{P(0.24)}")

# --- wings hanging off the arms: they flex a beat after the arms, tips flutter ------------
for name, lag in (("wing_b", 0.18), ("wing_c", 0.20), ("wing_d", 0.22), ("wing_e", 0.24)):
    side(f"{name}_01", "z", f"WSPREAD + WING*{P(lag)}", f"0.4*WING*{S(lag)}")
    side(f"{name}_02", "z", f"1.2*WING*{P(lag + 0.05)} + WINGF*{F(lag + 0.05)}")

# --- tail feathers off the back: swing opposite the hips, lag most -----------------------
A("center_wing_01", axes["center_wing_01"]["z"], f"-TAILS*{S(0.20)}")
A("center_wing_01", (1, 0, 0), f"TAIL + 0.3*TAILS*{P(0.22)}")
A("center_wing_02", axes["center_wing_02"]["z"], f"-1.3*TAILS*{S(0.27)} + TAILF*{F(0.27)}")
side("wing_a_01", "z", "0.3*TAILS*0", f"-0.8*TAILS*{S(0.21)}")
side("wing_a_02", "z", f"0.6*TAILF*{F(0.28)}", f"-1.1*TAILS*{S(0.28)}")

# --- crest: three plumes trail the head side to side, flutter at the tips ---------------
for i, (w, fl) in enumerate(((0.5, 0), (0.8, 0.3), (1.0, 0.6), (1.2, 1.0)), start=1):
    lag = 0.18 + 0.05 * i
    crest = ""
    if i == 1:  # sweep all three plumes back together about world X (no plume crosses another)
        for b in ("center_hair_01", "left_hair_01", "right_hair_01"):
            A(b, (-1, 0, 0), "CREST")
    sway = f"-{w:g}*HAIR*{S(lag)}"
    pitch = f"{crest}{0.4 * w:g}*HAIR*{P(lag)} + {fl:g}*HAIRF*{F(lag)}"
    A(f"center_hair_{i:02d}", axes[f"center_hair_{i:02d}"]["z"], sway)
    A(f"center_hair_{i:02d}", axes[f"center_hair_{i:02d}"]["y"], pitch)
    side(f"hair_{i:02d}", "y", pitch)
    for sd in ("left", "right"):  # all plumes sway about the centre plume's axis, as one
        A(f"{sd}_hair_{i:02d}", axes[f"center_hair_{i:02d}"]["z"], sway)
side("hair_01", "z", "-FAN")

# --- neck ruff, shoulder pads, waist fluff: small, a beat late ---------------------------
for name, lag in (("feeler_a", 0.12), ("feeler_b", 0.16), ("feeler_c", 0.18), ("horn", 0.12)):
    side(name, "y", f"FUR*{P(lag)}")
side("cloth_a", "y", f"FUR*{P(0.10)}")
A("back_feeler", axes["back_feeler"]["y"], f"FUR*{P(0.18)}")
for name, lag in (("cloth_b", 0.12), ("cloth_c", 0.14), ("cloth_d", 0.12), ("cloth_e", 0.14),
                  ("cloth_f", 0.16), ("cloth_g", 0.16)):
    side(name, "y", f"{'0.3' if name == 'cloth_c' else '0.8'}*CLOTH*{P(lag)}")
A("front_cloth_01", (0, 1, 0), f"-0.6*CLOTH*{S(0.12)}")
A("front_cloth_02", (0, 1, 0), f"-0.8*CLOTH*{S(0.17)}")
A("back_cloth_a", (0, 1, 0), f"-0.6*CLOTH*{S(0.14)}")
A("back_cloth_b", (0, 1, 0), f"-0.8*CLOTH*{S(0.18)}")

# --- legs: sumo squat, thighs out, shins near vertical, feet flat and toed out -----------
# leg z (forward axis): + swings the leg out to the side; leg y: knee forward / back
side("leg_01", "z", "SPREAD")
side("leg_01", "y", "-KFWD")
side("leg_02", "z", "-KNEE")
side("leg_02", "y", "KFWD")
side("foot", "z", "KNEE - SPREAD")
side("foot", (0, 0, 1), "TOEOUT")

pose.sort(key=lambda e: -depth.get(e[0], 0))
pose.append(["waist", "LOCX", f"SHIFT*{S(0)}"])
pose.append(["waist", "LOCZ", f"-CROUCH - DIP*{P(0.02)}"])

cfg["pose_params"] = new
if cfg.get("pose") != pose:
    print(f"  pose: {len(cfg.get('pose', []))} -> {len(pose)} entries")
cfg["pose"] = pose
mo = cfg.setdefault("motion", {})
mo["functions"] = {"S": "sin(2*pi*t)", "P": "0.5 - 0.5*cos(4*pi*t)"}
mo["plant"] = ["left_foot", "right_foot"]
CFG.write_text(json.dumps(cfg, indent=2) + "\n")
print("wrote", CFG)
