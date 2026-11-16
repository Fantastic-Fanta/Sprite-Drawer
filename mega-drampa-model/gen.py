"""Mega Drampa pose + idle generator. Writes pose / motion into mega_drampa_front.json.
Run: python3 gen.py [KEY=value ...]   (overrides P below; prints every change to pose/motion)"""
import json, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "mega_drampa_front.json")

P = dict(
    # rest pose (deg; +X = lean toward the face side, -Y)
    SPINE=-6, NECK1=24, NECK2=14, NECK3=-22, NECK4=-28, NECK5=26, HEAD=30, JAW=6,
    SS1=-18, SS2=20,     # rest side-to-side S (deg about world Y, on neck_02 / neck_04)
    TURN=14,           # head/neck turn about world Z toward the camera (deg, spread over neck_03..head)
    # motion
    BOB=0.03,          # hover, model units (~1.4 sprite px)
    NECKA=1.2,         # neck S-wave per joint (deg, forward/back), grows up the chain
    SIDE=1.0,          # neck S-wave per joint (deg, side to side), grows up the chain
    LAG=0.07,          # phase lag per joint (loop fraction): the wave travels up the neck
    ROAR=28,           # jaw opening on the roar (deg)
    LUNGE=2,           # lower neck pushes forward on the roar (deg per joint)
    WIND=1.5,            # lower neck draws back before the roar (deg per joint)
    HEADUP=5,          # head lifts a little as it roars (deg); the face stays forward
    CLOUD=0.8,         # cloud lobe up/down bend per joint (deg)
    ARM=1.2,           # arm drift (deg)
    WHISK=3.0,         # whisker / brow flutter (deg)
    JAWA=1.5,          # jaw breath (deg)
)
for a in sys.argv[1:]:
    k, v = a.split("=")
    P[k] = float(v)



def ph(lag):
    """the driver (hover) delayed by lag loop fractions: sin(2 pi (t - lag))"""
    return f"sin(2*pi*(t-{lag:.3f}))"


pose = []
# ---- rest pose
for b, k in [("spine_02", "SPINE"), ("neck_01", "NECK1"), ("neck_02", "NECK2"), ("neck_03", "NECK3"),
             ("neck_04", "NECK4"), ("neck_05", "NECK5"), ("head", "HEAD")]:
    if P[k]:
        pose.append([b, "X", f"{P[k]}"])
if P["SS1"]:
    pose.append(["neck_02", "A:0,1,0", f"{P['SS1']}"])
if P["SS2"]:
    pose.append(["neck_04", "A:0,1,0", f"{P['SS2']}"])
if P["TURN"]:
    for b in ["neck_03", "neck_05", "head"]:
        pose.append([b, "Z", f"{P['TURN'] / 3:.2f}"])
pose.append(["jaw", "A:1,0,0", f"{P['JAW']} + {P['JAWA']}*{ph(0.15)} + {P['ROAR']}*R(t-0.02)"])

# ---- motion: one driver (hover bob), everything else follows later
pose.append(["origin", "LOCZ", f"{P['BOB']}*wave(t, 0.15)"])
# neck: as the body rises the neck settles back, head nods a beat later (lag grows up the chain)
# S-wave travelling up the neck (forward/back and side to side), plus the roar: the lower neck
# draws back (W), then lunges forward as the jaw opens (R); the upper neck and head follow later
NECK = ["spine_02", "neck_01", "neck_02", "neck_03", "neck_04", "neck_05", "head"]
for i, b in enumerate(NECK):
    amp = P["NECKA"] * (0.35 + 0.22 * i)
    d = 0.02 * i
    roar = ""
    if 1 <= i <= 3:
        roar = f" + {P['LUNGE']:.2f}*R(t-{d:.3f}) - {P['WIND']:.2f}*W(t-{d:.3f})"
    elif i in (4, 5):
        roar = f" - {P['LUNGE'] * 0.5:.2f}*R(t-{d:.3f}) + {P['WIND'] * 0.5:.2f}*W(t-{d:.3f})"
    elif i == 6:
        roar = f" - {P['HEADUP']:.2f}*R(t-{d:.3f}) + {P['WIND'] * 0.6:.2f}*W(t-{d:.3f})"
    pose.append([b, "X", f"{amp:.2f}*{ph(0.06 + P['LAG'] * i)}{roar}"])
    if i:
        sa = P["SIDE"] * (0.4 + 0.2 * i)
        pose.append([b, "A:0,1,0", f"{sa:.2f}*{ph(0.30 + P['LAG'] * i)}"])

# cloud lobes: up/down undulation about each bone's own horizontal axis, lag + amplitude growing to the tip
def chain(bones, axis, amp, lag0, grow=0.25, lag=None):
    lag = P["LAG"] if lag is None else lag
    for i, b in enumerate(bones):
        pose.append([b, axis, f"{amp * (1 + grow * i):.2f}*{ph(lag0 + lag * i)}"])

def ax(v, sx):
    """left-side axis -> this side's (mirror across x: an axial vector (a,b,c) -> (a,-b,-c))"""
    a, b, c = v if sx > 0 else (v[0], -v[1], -v[2])
    return f"A:{a:.2f},{b:.2f},{c:.2f}"


for side, sx in (("left", 1), ("right", -1)):
    # cloud lobes lie flat; each bone's y axis is horizontal across the lobe: up/down bend
    chain([f"{side}_feeler_d_0{i}" for i in range(2, 8)], ax((0.70, -0.71, 0), sx), P["CLOUD"] * 0.7, 0.17)
    chain([f"{side}_feeler_e_0{i}" for i in range(1, 8)], ax((0.91, -0.42, 0), sx), P["CLOUD"] * 0.6, 0.16)
    chain([f"{side}_feeler_c_0{i}" for i in range(1, 5)], ax((0.51, -0.86, 0), sx), P["CLOUD"] * 0.5, 0.10)
    chain([f"{side}_feeler_a_0{i}" for i in range(1, 3)], ax((0.58, -0.81, 0), sx), P["CLOUD"], 0.20)
    chain([f"{side}_feeler_b_0{i}" for i in range(1, 3)], ax((0.60, -0.80, 0), sx), P["CLOUD"], 0.20)
    # arm + claw drift with the hover; the wing tufts trail
    pose.append([f"{side}_arm_01", ax((0, -0.5, 0.87), sx), f"{P['ARM']:.2f}*{ph(0.10)}"])
    chain([f"{side}_wing_a_0{i}" for i in range(1, 5)], ax((0.86, -0.20, 0.46), sx), P["CLOUD"] * 0.6, 0.14)
    chain([f"{side}_wing_b_0{i}" for i in range(1, 5)], ax((0.91, -0.26, 0.33), sx), P["CLOUD"] * 0.6, 0.16)
    chain([f"{side}_wing_c_0{i}" for i in range(1, 3)], ax((0.95, -0.09, 0.30), sx), P["CLOUD"] * 0.6, 0.12)
    # whiskers and brows: light strands, lag the head, plus a faster small flutter
    for b, v in [(f"{side}_hair_01", (0.30, -0.29, 0.91)), (f"{side}_hair_02", (0.35, -0.44, 0.82))]:
        pose.append([b, ax(v, sx), f"{P['WHISK']:.2f}*{ph(0.45)} + {P['WHISK']*0.3:.2f}*sin(4*pi*(t-0.2)) - {P['WHISK']*1.5:.2f}*R(t-0.08)"])
    for i in range(1, 5):
        pose.append([f"{side}_eyebrow_0{i}", ax((0.21, 0.21, 0.95), sx), f"{P['WHISK']*0.4:.2f}*{ph(0.40 + 0.05*i)}"])
# tail cloud: long chain, the slowest and furthest-lagging
chain([f"feeler_a_0{i}" for i in range(1, 8)], "A:1,0,0", P["CLOUD"] * 0.5, 0.18)
pose.append(["hair_a", "A:1,0,0", f"{P['WHISK']*0.5:.2f}*{ph(0.40)}"])
pose.append(["hair_b", "A:1,0,0", f"{P['WHISK']*0.5:.2f}*{ph(0.42)}"])

c = json.load(open(CFG))
old = {(p[0], p[1]): p[2] for p in c.get("pose", [])}
new = {(p[0], p[1]): p[2] for p in pose}
for k in sorted(set(old) | set(new)):
    if old.get(k) != new.get(k):
        print(f"  {k}: {old.get(k)} -> {new.get(k)}")
c["pose"] = pose
fn = {"R": "smoother((t % 1 - 0.30)/0.18) * (1 - smoother((t % 1 - 0.60)/0.28))",
      "W": "bump((t % 1 - 0.04)/0.36)"}
if c["motion"].get("functions") != fn:
    print("  motion.functions:", c["motion"].get("functions"), "->", fn)
c["motion"]["functions"] = fn
json.dump(c, open(CFG, "w"), indent=2)
print("params:", P)
