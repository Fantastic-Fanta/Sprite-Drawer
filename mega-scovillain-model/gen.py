"""Mega Scovillain pose + idle generator (v2, after the user's feedback). Writes pose / motion /
camera into mega_scovillain_front.json. v1 is gen.v1.py / mega_scovillain_front.v1.json.
Run: /usr/local/bin/python3 gen.py [KEY=value ...]   (overrides P; prints every change)

Reference: reference/za_render.png (the Legends Z-A menu render): a hydra stance, both heads up on
either side of the body (red on screen left, green on screen right), the red "necktie" spike
hanging in the middle between them, body facing left, both tongues out.

The bind pose has both heads floating in front of the body, away from their stubby necks. Each neck
chain is laid out by LOC (pure translations, so positions add up down the chain) along an S curve
from its root to a collar point, and each head is moved onto its collar. head_a (green) is on
left_neck (+X), head_b (red) on right_neck (-X). The motion is written the same way: every neck
joint's total offset is an expression in t (S + travelling wave + strike), and each joint gets
its own total minus its parent's."""
import json, sys, os, math

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "mega_scovillain_front.json")

P = dict(
    AZ=55, EL=10, TZ=0.72, ORTHO=2.925,
    # collars (neck_05 joint) and head bone offset from it
    RCX=-0.40, RCY=-0.16, RCZ=1.16, RHX=-0.02, RHY=-0.03, RHZ=0.10, RTURN=26, RNOD=6,
    GCX=0.38, GCY=-0.04, GCZ=1.20, GHX=0.02, GHY=-0.03, GHZ=0.10, GTURN=8, GNOD=8,
    S=0.09,          # S-curve amplitude along each neck (model units, in the screen plane)
    RJAW=18, GJAW=20, RTONGUE=0.85, GTONGUE=1.0, RZIG=22, GZIG=16,
    RARM=-15, LARM=-15, TAILUP=5,
    # motion
    CYC=2,           # weave cycles per loop (each neck)
    WAVE=0.04,      # travelling wave across the neck (screen plane, at the collar)
    DEPTH=0.025,     # the same wave toward/away from the camera, a quarter cycle off (a weave)
    TRAVEL=0.85,     # wave phase lag base -> collar (cycles): the wave climbs the neck
    STRIKE=0.08, GSK=0.6,     # head lunge at the snap (model units)
    RSNAP=0.22, GSNAP=0.72,   # snap times in the loop, half a loop apart
    YAW=4, NOD=4,    # head sway (deg), a beat after the collar
    GAPE=18, BITE=12,  # jaw opens before the snap, shuts on it (deg)
    LT=31, KF=-8, KB=10, FR=-3, FP=3,   # stance: thigh swing in, thigh pitch, knee bend, foot roll, foot pitch (deg)
    BREATH=0.010, SPINE=1.5, SHIFT=0.010,
    TIE=4,           # red necktie spike swing (deg)
    TONGUE=3, TAIL=2.5, ARM=4, CLOTH=5,
)
for a in sys.argv[1:]:
    k, v = a.split("=")
    P[k] = float(v)

REST = {
    "left_neck": [(0.01, 0.02, 0.69), (0.03, 0.01, 0.80), (0.07, -0.02, 0.88), (0.11, -0.06, 0.94), (0.17, -0.11, 0.97)],
    "right_neck": [(-0.01, 0.02, 0.69), (-0.03, 0.01, 0.80), (-0.07, -0.02, 0.88), (-0.11, -0.06, 0.94), (-0.17, -0.11, 0.97)],
    "head_a": (0.00, -0.56, 0.86), "head_b": (0.00, -0.56, 0.23),
}


def norm(v):
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


az = math.radians(P["AZ"])
VIEW = norm([-math.cos(az), math.sin(az), 0.0])      # camera looks along this (az 90 = +Y)


def lat(deg):
    g = math.radians(deg)
    return f"A:{math.cos(g):.3f},{math.sin(g):.3f},0"


def fmt(v):
    return f"{v:.4f}"


pose = []
CY = int(P["CYC"])


def strike(t0):
    return f"strike(t-{t0:.3f})"


def neck(side, head, collar, hoff, turn, sign, t0, phase, sk=1.0):
    """lay the chain along an S from its root to the collar and give it its motion"""
    rest = REST[side]
    base = rest[0]
    d = norm([collar[k] - base[k] for k in range(3)])
    p1 = norm(cross(d, VIEW))                         # across the neck, in the screen plane
    if p1[0] * sign < 0:
        p1 = [-x for x in p1]                         # + = outward
    p2 = norm(cross(p1, d))                           # across the neck, toward / away from the camera
    face = [math.sin(math.radians(turn)), -math.cos(math.radians(turn)), -0.35]
    face = norm(face)
    tot_prev = ["0", "0", "0"]
    for i in range(1, 5):
        fr = i / 4
        want = [base[k] + (collar[k] - base[k]) * fr for k in range(3)]
        # S: bows inward low on the neck, outward high up, back on the line at the collar
        s = -P["S"] * math.sin(2 * math.pi * fr) * (1 if i < 4 else 0)
        stat = [want[k] + s * p1[k] - rest[i][k] for k in range(3)]
        amp = 0.25 + 0.75 * fr                        # the free end moves most
        lag = P["TRAVEL"] * fr
        wv = f"sin(2*pi*({CY}*t-{lag + phase:.3f}))"
        dp = f"cos(2*pi*({CY}*t-{lag + phase:.3f}))"
        lw = fr ** 1.5                                # the strike is carried mostly by the top of the neck
        tot = []
        for k in range(3):
            e = f"{fmt(stat[k])}+{fmt(P['WAVE'] * amp * p1[k])}*{wv}+{fmt(P['DEPTH'] * amp * p2[k])}*{dp}" \
                f"+{fmt(P['STRIKE'] * sk * lw * face[k])}*{strike(t0)}"
            tot.append(e)
        for k, ax in enumerate("XYZ"):
            pose.append([f"{side}_0{i + 1}", f"LOC{ax}", f"({tot[k]})-({tot_prev[k]})"])
        tot_prev = tot
    # head onto the collar (the static part of the joint total at fr=1)
    hw = [collar[k] + hoff[k] for k in range(3)]
    cum = [collar[k] - rest[4][k] for k in range(3)]
    for k, ax in enumerate("XYZ"):
        dv = hw[k] - (REST[head][k] + cum[k])
        if abs(dv) > 1e-4:
            pose.append([head, f"LOC{ax}", fmt(dv)])
    return f"sin(2*pi*({CY}*t-{P['TRAVEL'] + phase + 0.10:.3f}))"   # the head's sway, a beat after the collar


# red head (right_neck, -X, far side), green head (left_neck, +X, near side); half a cycle apart
rsw = neck("right_neck", "head_b", (P["RCX"], P["RCY"], P["RCZ"]), (P["RHX"], P["RHY"], P["RHZ"]), P["RTURN"], -1, P["RSNAP"], 0.0)
gsw = neck("left_neck", "head_a", (P["GCX"], P["GCY"], P["GCZ"]), (P["GHX"], P["GHY"], P["GHZ"]), P["GTURN"], 1, P["GSNAP"], 0.5, P["GSK"])

# heads: facing, then the sway (yaw + nod, a beat after the neck), then the nod into the bite
for head, turn, nod, sw, t0, jaw, J, tongue, zig, tsc, ysign in (
        ("head_b", P["RTURN"], P["RNOD"], rsw, P["RSNAP"], "jaw_b_01", P["RJAW"], "tongue_b", P["RZIG"], P["RTONGUE"], 1),
        ("head_a", P["GTURN"], P["GNOD"], gsw, P["GSNAP"], "jaw_a_01", P["GJAW"], "tongue_a", P["GZIG"], P["GTONGUE"], -1)):
    L = lat(turn)
    pose.append([head, "Z", f"{turn}+{P['YAW'] * ysign:.2f}*{sw}"])
    pose.append([head, L, f"{nod}+{P['NOD']:.2f}*{sw.replace('sin', 'cos')}+12*{strike(t0)}"])
    # jaw: open at rest, gapes wide before the snap, shuts on it, a small chatter with the sway
    pose.append([jaw, L, f"{J}+{P['GAPE']}*gape(t-{t0:.3f})-{P['BITE']}*bite(t-{t0:.3f})+2*{sw}"])
    if tsc != 1:
        pose.append([f"{tongue}_01", "SCALE", f"{tsc}"])
    for i in range(1, 7):
        sg = 1 if i % 2 else -1
        amt = zig * (1.5 if i == 1 else 1.0) * (sg if i > 1 else 1)
        lagt = 0.08 + 0.05 * i
        pose.append([f"{tongue}_0{i}", L, f"{amt:.1f}+{P['TONGUE'] * (0.4 + 0.15 * i):.2f}*sin(2*pi*({CY}*t-{P['TRAVEL'] + lagt:.3f}))"
                     f"+{P['TONGUE'] * 0.3:.2f}*sin(2*pi*(4*t-{0.07 * i:.2f}))+{P['TONGUE'] * 0.8:.2f}*strike(t-{t0 + 0.04 + 0.015 * i:.3f})"])
        # and a sideways lash after the snap
        pose.append([f"{tongue}_0{i}", "Z", f"{P['TONGUE'] * 0.6 * (0.5 + 0.2 * i):.2f}*sin(2*pi*({CY}*t-{P['TRAVEL'] + lagt + 0.15:.3f}))"])

# ---- stance (rest): legs under the hips, knees a little bent, soles flat on the ground plane.
# The bind legs splay sideways with the soles tipped onto their inner edges. World Y swings a leg
# in (mirrored per side), world X pitches it; then motion.plant holds each ankle.
for side, sy in (("left", 1), ("right", -1)):
    if P["LT"]: pose.append([f"{side}_leg_01", f"A:0,{sy},0", f"{P['LT']}"])
    if P["KF"]: pose.append([f"{side}_leg_01", "A:1,0,0", f"{P['KF']}"])
    if P["KB"]: pose.append([f"{side}_leg_02", "A:1,0,0", f"{P['KB']}"])
    if P["FR"]: pose.append([f"{side}_foot", f"A:0,{sy},0", f"{P['FR']}"])
    if P["FP"]: pose.append([f"{side}_foot", "A:1,0,0", f"{P['FP']}"])

# ---- body: braced, it shifts its weight against the heads' weave and pants with them
pose.append(["waist", "LOCZ", f"-{P['BREATH']}*(0.5+0.5*cos(2*pi*({CY}*t-0.05)))-0.012*(strike(t-{P['RSNAP']:.3f})+strike(t-{P['GSNAP']:.3f}))"])
pose.append(["waist", "LOCX", f"{P['SHIFT']}*sin(2*pi*({CY}*t-0.55))"])
pose.append(["spine_02", "A:-1,0,0", f"{P['SPINE']}*sin(2*pi*({CY}*t-0.10))"])
# red necktie spike: hangs in the middle, swings a beat after the body and kicks after each snap
for b, k, lag in (("cloth_a_01", 0.5, 0.15), ("cloth_a_02", 0.9, 0.22), ("feeler_a_01", 0.7, 0.20), ("feeler_a_02", 1.1, 0.28)):
    pose.append([b, "A:0,1,0", f"{P['TIE'] * k:.2f}*sin(2*pi*({CY}*t-{lag + 0.55:.2f}))"])
    pose.append([b, "A:1,0,0", f"{P['TIE'] * k * 0.5:.2f}*sin(2*pi*({CY}*t-{lag + 0.30:.2f}))+{P['TIE'] * k * 0.6:.2f}*(strike(t-{P['RSNAP'] + lag * 0.3:.3f})+strike(t-{P['GSNAP'] + lag * 0.3:.3f}))"])
# tail: rest lift, then a sway climbing to the tip (counter to the body shift)
for i in range(3, 7):
    pose.append([f"tail_0{i}", "A:1,0,0", f"{P['TAILUP'] * (i - 2) / 2.5:.2f}"])
for i in range(1, 7):
    pose.append([f"tail_0{i}", "A:0,0,1", f"{P['TAIL'] * (0.3 + 0.2 * i):.2f}*sin(2*pi*(t-{0.10 + 0.06 * i:.2f}))"])
for b, lag in (("feeler_b", 0.35), ("feeler_c", 0.40), ("feeler_d", 0.45)):
    pose.append([b, "A:1,0,0", f"{P['CLOTH'] * 0.3:.2f}*sin(2*pi*(t-{lag}))"])
# arms: spread a little (rest), twitch with the weave; black cloth and leg feelers flutter
for side, sx, R in (("left", 1, P["LARM"]), ("right", -1, P["RARM"])):
    ax = f"A:{-0.01 * sx:.2f},-1.00,0.01"
    pose.append([f"{side}_arm_01", ax, f"{R * sx:.1f}+{P['ARM'] * sx:.2f}*sin(2*pi*({CY}*t-{0.15 + (0.5 if sx > 0 else 0):.2f}))"])
    pose.append([f"{side}_hand_sub", ax, f"{P['ARM'] * 1.5 * sx:.2f}*sin(2*pi*({CY}*t-{0.25 + (0.5 if sx > 0 else 0):.2f}))"])
    for b, lag in ((f"{side}_cloth_a", 0.25), (f"{side}_cloth_b", 0.28), (f"{side}_cloth_c_01", 0.20),
                   (f"{side}_cloth_c_02", 0.26), (f"{side}_cloth_c_03", 0.32), (f"{side}_feeler_a", 0.3), (f"{side}_feeler_b", 0.34)):
        pose.append([b, "A:1,0,0", f"{P['CLOTH']:.2f}*sin(2*pi*({CY}*t-{lag:.2f}))+{P['CLOTH'] * 0.25:.2f}*sin(2*pi*(4*t-{lag:.2f}))"])

c = json.load(open(CFG))
c["motion"]["plant"] = ["left_foot", "right_foot"]
c["motion"]["note"] = (
    "menacing two-headed hydra (Z-A render: heads up on either side, red necktie spike hanging in the middle): "
    "the driver is the heads' weave: a wave travels up each S-curved neck (two cycles a loop, in the screen plane "
    "plus a quarter-cycle-off depth sway, so the heads circle), the two necks half a cycle apart; each head yaws and "
    "nods a beat after its collar, and once a loop each head draws back, snaps forward with its jaw gaping then "
    "shutting (red at 0.22, green at 0.72); the braced body pants and shifts against the weave, feet planted; "
    "the necktie spike, tongues, tail and cloth flaps trail and kick after each snap")
c["motion"]["functions"] = {
    # a snap at t=0 (periodic): a slow draw-back, a fast lunge, an eased return
    "strike": "exp(7*(cos(2*pi*t)-1))*(1+0.4*sin(2*pi*t))-0.3*exp(6*(cos(2*pi*(t+0.13))-1))",
    "gape": "exp(10*(cos(2*pi*(t+0.05))-1))",
    "bite": "exp(12*(cos(2*pi*(t-0.02))-1))",
}
c["pose_params"].update(AZIMUTH=P["AZ"], ELEVATION=P["EL"])
c["camera"]["target"] = [0.0, -0.042, P["TZ"]]
c["camera"]["ortho_scale"] = P["ORTHO"]
c["render"].setdefault("hull", {})["cap_each_frame"] = True
c["style"]["height"] = 200
c["reference"] = "reference/za_render.png"
c["reference_source"] = ("Legends Z-A menu render (serebii.net legendsz-a/pokemon/952-m.png), shiny in reference/za_render_shiny.png; "
                         "v1's official artwork kept as reference/official.png")
old = {(p[0], p[1]): p[2] for p in c.get("pose", [])}
new = {(p[0], p[1]): p[2] for p in pose}
ch = [k for k in sorted(set(old) | set(new)) if old.get(k) != new.get(k)]
print(f"pose: {len(old)} -> {len(new)} entries, {len(ch)} changed")
for k in ch:
    if "neck" not in k[0]:
        print(f"  {k}: {str(old.get(k))[:70]} -> {str(new.get(k))[:90]}")
c["pose"] = pose
json.dump(c, open(CFG, "w"), indent=2)
print("params:", P)
