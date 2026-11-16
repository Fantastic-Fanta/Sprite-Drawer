"""Mega Falinks v2: a knight built from six troopers joined at their hip knobs (the round side
discs). Writes pose / pose_params / motion of the front config. Keeps existing pose_params unless
overridden (KEY=value) or --reset (take the defaults below); prints every change.
  python3 gen_pose.py [CONFIG] [--reset] KEY=value ...
Static layout: every trooper gets an absolute orientation (yaw/pitch/roll, degrees) and is moved so
its knob sits on its neighbour's knob (computed here, so a changed angle keeps the joints shut).
Rest model: troopers in single file along +Y, facing -Y; +X = the model's left (near the camera)."""
import json, sys, math
import numpy as np

cfgp = "mega-falinks-model/mega_falinks_front.json"
args = sys.argv[1:]
if args and args[0].endswith(".json"):
    cfgp = args.pop(0)
reset = "--reset" in args
args = [a for a in args if a != "--reset"]
cfg = json.load(open(cfgp))

D = dict(
    AZIMUTH=65, ELEVATION=10, FOV=30,
    # legs e (right, -X, back foot) and f (left, +X, front foot): position, toe-out yaw, roll
    LX=0.36, LYB=0.20, LYF=-0.24, LYAW=18, LROLL=22,
    # pelvis d: hangs between the legs on their inner knobs; lean
    DP=0.0,
    # torso a (leader) on d: yaw toward camera, lean forward, roll; sink into d
    AYAW=12, APITCH=6, AROLL=0, ASINK=0.10,
    # shield arm b on a's left knob: pitch about the knob axle (+ = face down), yaw out
    BPITCH=10, BYAW=-8, BROLL=30, KO=0.05,
    # shield: in front of b, facing OX,OY,OZ; distance forward, down, out from b's centre
    OX=0.42, OY=-0.90, OZ=0.12, SHF=0.42, SHD=0.05, SHO=0.15, SHSPIN=0, SHS=0.85,
    # blade arm c on a's right knob; blade (c's horn) direction
    CPITCH=-35, CYAW=10, CROLL=-25, BLS=1.35, BLX=-0.20, BLY=-0.80, BLZ=0.62,
    BHORN=30,   # b's own horn: bent back (deg) so it crests over the shield
    DARM=55,    # d's little arms reach down to the leg knobs
    # motion
    WX=0.028, WZ=0.012, AL=0.06, AR=2.5, AYW=1.5, ABR=0.010,
    ARML=0.12, BSW=3.0, CSW=3.5, SHL=0.20, SHW=2.5, BLL=0.22, BLW=4.0, BLV=3.0,
    LGD=0.014, LRK=2.0, SMALL=5.0,
)

old = dict(cfg.get("pose_params", {}))
P = dict(D) if reset else {k: old.get(k, v) for k, v in D.items()}
for a in args:
    k, v = a.split("="); P[k] = float(v)
for k in sorted(set(P) | set(old)):
    if old.get(k) != P.get(k):
        print(f"{k}: {old.get(k)} -> {P.get(k)}")


def R(axis, deg):
    axis = np.asarray(axis, float); axis = axis / np.linalg.norm(axis)
    th = math.radians(deg); K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * K @ K


def ypr(yaw, pitch, roll):
    """yaw about Z (+ turns the face toward +X), pitch about X (+ face down), roll about Y"""
    return R((0, 0, 1), yaw) @ R((1, 0, 0), pitch) @ R((0, 1, 0), roll)


def axis_angle(M):
    ang = math.degrees(math.acos(max(-1, min(1, (np.trace(M) - 1) / 2))))
    if ang < 1e-6:
        return (0, 0, 1), 0.0
    ax = np.array([M[2, 1] - M[1, 2], M[0, 2] - M[2, 0], M[1, 0] - M[0, 1]])
    return ax / np.linalg.norm(ax), ang


def rot_to(a, b):
    a = np.asarray(a, float) / np.linalg.norm(a); b = np.asarray(b, float) / np.linalg.norm(b)
    ax = np.cross(a, b); s = np.linalg.norm(ax)
    if s < 1e-9:
        return np.eye(3)
    return R(ax, math.degrees(math.atan2(s, a @ b)))


f = lambda x: f"{x:.4f}"
pose = []


def rot_entry(bone, M):
    ax, ang = axis_angle(M)
    if ang > 1e-4:
        pose.append([bone, "A:" + ",".join(f"{c:.4f}" for c in ax), f(ang)])


def place(bone, rest_head, M, target_head):
    rot_entry(bone, M)
    for i, n in enumerate("XYZ"):
        d = target_head[i] - rest_head[i]
        if abs(d) > 1e-5:
            pose.append([bone, "LOC" + n, f(d)])


V = np.array
SHG = 0.32
HEAD = dict(a=V([0, 0, 0.32]), b=V([0, 1.5, 0.28]), c=V([0, 3.0, 0.28]), d=V([0, 4.0, 0.18]),
            e=V([0, 5.0, 0.18]), f=V([0, 6.0, 0.18]))
KNOB = dict(a=(0.50, 0.14), b=(0.31, 0.16), c=(0.31, 0.16), d=(0.20, 0.10), e=(0.26, 0.11), f=(0.26, 0.11))
knob = lambda k, side: V([side * KNOB[k][0], 0, KNOB[k][1]])     # side +1 = trooper's left (+X)

# --- legs: planted, toes out, rolled so the inner knob tilts up toward the pelvis ---
Me = ypr(-P["LYAW"], 0, -P["LROLL"]); Mf = ypr(P["LYAW"], 0, P["LROLL"])
He = V([-P["LX"], P["LYB"], 0.18]); Hf = V([P["LX"], P["LYF"], 0.18])
lift = lambda M: -min((M @ V([s * 0.10, 0, -0.18]))[2] for s in (-1, 1))   # head height: lowest foot on the ground
He[2] = lift(Me); Hf[2] = lift(Mf)
place("waist_e", HEAD["e"], Me, He); place("waist_f", HEAD["f"], Mf, Hf)
Hcl = dict(e=He[2], f=Hf[2])
ke = He + Me @ knob("e", +1); kf = Hf + Mf @ knob("f", -1)   # inner knobs
# --- pelvis d between them: its knobs on theirs (best fit: midpoint, d rolled to the knob line) ---
mid = (ke + kf) / 2; span = kf - ke
Md = rot_to((1, 0, 0), span) @ ypr(0, P["DP"], 0)
Hd = mid - Md @ V([0, 0, KNOB["d"][1]])
place("waist_d", HEAD["d"], Md, Hd)
# --- torso a sits on d ---
Ma = ypr(P["AYAW"], P["APITCH"], P["AROLL"])
d_top = Hd + Md @ V([0, 0, 0.34])
Ha = d_top - Ma @ V([0, 0, -0.26]) - V([0, 0, P["ASINK"]])
place("waist_a", HEAD["a"], Ma, Ha)
ka_l = Ha + Ma @ knob("a", +1); ka_r = Ha + Ma @ knob("a", -1)
# --- arms: their inner knob on a's knob (pressed in by KO) ---
Mb = Ma @ ypr(P["BYAW"], P["BPITCH"], P["BROLL"])
Hb = ka_l - Mb @ (knob("b", -1) + V([-P["KO"], 0, 0]))
place("waist_b", HEAD["b"], Mb, Hb)
Mc = Ma @ ypr(P["CYAW"], P["CPITCH"], P["CROLL"])
Hc = ka_r - Mc @ (knob("c", +1) + V([P["KO"], 0, 0]))
place("waist_c", HEAD["c"], Mc, Hc)
# --- shield (feeler_a_01, child of waist_b): face OX,OY,OZ, in front of b ---
o = V([P["OX"], P["OY"], P["OZ"]]); o = o / np.linalg.norm(o)
Ms = rot_to((0, 0, 1), o) @ R((0, 0, 1), P["SHSPIN"])
fwd_b = Mb @ V([0, -1, 0]); out_b = Mb @ V([1, 0, 0])
cb = Hb + Mb @ V([0, 0, 0.16])                               # b's body centre
Hs_want = cb + P["SHF"] * fwd_b - V([0, 0, P["SHD"]]) + P["SHO"] * out_b - Ms @ V([0, 0, 0.10])
Hs_now = Hb + Mb @ (V([0, 1.5, 1.78]) - HEAD["b"])
rot_entry("feeler_a_01", Ms @ Mb.T)
for i, n in enumerate("XYZ"):
    pose.append(["feeler_a_01", "LOC" + n, f(Hs_want[i] - Hs_now[i])])
pose.append(["feeler_a_01", "SCALE", "SHS"])
for i, n in enumerate("XYZ"):   # top disc back onto the big disc's cone (rest gap 0.5 along the normal)
    pose.append(["feeler_a_02", "LOC" + n, f(-SHG * P["SHS"] * o[i])])
# --- blade: c's horn chain turned to BL ---
h0 = Mc @ V([0, -0.89, 0.46])
rot_entry("horn_c_01", rot_to(h0, V([P["BLX"], P["BLY"], P["BLZ"]])))
pose.append(["horn_c_01", "SCALE", "BLS"])
pose += [["horn_a_01", "X", f"-BHORN"]]
pose += [["left_shoulder_b", "Y", "DARM"], ["right_shoulder_b", "Y", "-DARM"]]
static_n = len(pose)

# --- idle: weight shift ---
# Driver W: the pelvis shifts its weight from leg to leg (+ = onto the front/left leg f) and sinks
# into the loaded leg (DIP). Torso follows a beat later (AL) and leans over the loaded leg; the arm
# troopers follow it a beat later again (ARML); shield and blade a beat after their arms, with
# their own small ready-motion (blade tip circling, shield tilting).
fn = {"W": "sin(2*pi*t)", "DIP": "0.5 - 0.5*cos(4*pi*t)", "BRE": "wave(t, 0.1)"}
pose += [["waist_d", "LOCX", "WX*W(t)"], ["waist_d", "LOCZ", "-WZ*DIP(t)"], ["waist_d", "Y", "1.5*W(t-0.03)"]]
# legs: the loaded one squats a little on its planted feet
# legs: rock a little about their feet as the weight comes on (a pitch about the foot line: the
# head-pivot rotation plus the matching LOCY, so the soles stay put)
for k, sg, lag in (("e", 1, 0.05), ("f", -1, 0.07)):
    th = f"({sg}*LRK*W(t-{lag}))"
    pose += [[f"waist_{k}", "X", th], [f"waist_{k}", "LOCY", f"-{th}*pi/180*{f(Hcl[k])}"]]
pose += [["waist_a", "LOCX", "1.1*WX*W(t-AL)"], ["waist_a", "LOCZ", "-WZ*DIP(t-AL) + ABR*BRE(t-AL)"],
         ["waist_a", "Y", "AR*W(t-AL)"], ["waist_a", "Z", "AYW*W(t-AL-0.1)"]]
for k, sw in (("b", "BSW"), ("c", "CSW")):
    pose += [[f"waist_{k}", "LOCX", f"1.2*WX*W(t-AL-ARML)"],
             [f"waist_{k}", "LOCZ", f"-WZ*DIP(t-AL-ARML) + 1.3*ABR*BRE(t-AL-ARML)"],
             [f"waist_{k}", "Y", f"AR*W(t-AL-ARML)"],
             [f"waist_{k}", "X", f"{sw}*W(t-AL-ARML-0.05)"]]
pose += [["feeler_a_01", "X", "SHW*W(t-AL-SHL)"], ["feeler_a_01", "Z", "0.6*SHW*sin(2*pi*(t-AL-SHL-0.15))"],
         ["feeler_a_02", "Z", "SMALL*sin(2*pi*(t-AL-SHL-0.1))"],
         ["horn_c_01", "X", "BLW*W(t-AL-BLL)"], ["horn_c_01", "Z", "BLV*cos(2*pi*(t-AL-BLL))"],
         ["horn_c_02", "X", "0.5*BLW*W(t-AL-BLL-0.05)"],
         ["horn_a_01", "X", "0.35*SMALL*W(t-AL-ARML-0.12)"],
         ["horn_e", "Y", "SMALL*W(t-0.15)"], ["horn_f_01", "Y", "-SMALL*W(t-0.2)"],
         ["left_shoulder_b", "Y", "SMALL*W(t-0.1)"], ["right_shoulder_b", "Y", "SMALL*W(t-0.1)"],
         ["left_hand_a", "X", "0.5*SMALL*W(t-AL-0.1)"], ["right_hand_a", "X", "-0.5*SMALL*W(t-AL-0.1)"]]
for k, lag in (("a", 0.12), ("b", 0.24), ("c", 0.24), ("d", 0.1)):
    pose += [[f"left_leg_{k}", "X", f"SMALL*W(t-{lag})"], [f"right_leg_{k}", "X", f"-SMALL*W(t-{lag}-0.03)"]]

cfg["pose_params"] = P
cfg["pose"] = pose
m = cfg.setdefault("motion", {})
m["frames"] = 120
m["functions"] = fn
m["plant"] = ["left_foot_e", "right_foot_e", "left_foot_f", "right_foot_f"]
m["note"] = ("A knight on guard, built from six troopers joined at their hip knobs: leader a is head and "
             "torso, b the shield arm, c the machete arm (its horn is the blade), d the pelvis hanging on "
             "the leg troopers' inner knobs, e/f the legs (left foot forward). Driver: a slow weight shift "
             "from leg to leg, the pelvis sinking into the loaded leg; the torso follows a beat later and "
             "leans over it, the arm troopers a beat after that, and the shield and blade last, with their "
             "own small ready-motion (blade tip circling, shield tilting). Legs squat a little under the load.")
cfg["camera"]["azimuth"] = "AZIMUTH"
json.dump(cfg, open(cfgp, "w"), indent=2)
print("wrote", cfgp, static_n, "static +", len(pose) - static_n, "motion entries")
print("heads: a", Ha.round(2), "b", Hb.round(2), "c", Hc.round(2), "d", Hd.round(2), "e", He.round(2), "f", Hf.round(2))
