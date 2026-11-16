"""Mega Staraptor pose + flight wingbeat generator (v2: real flapping, after the user's feedback).
Usage: python3 gen_pose.py [KEY=value ...]
Keeps existing pose_params (only KEY=value overrides or new keys change), prints every change,
rewrites `pose` and `motion` from the template below.

Driver: one wingbeat. pw(t) is the beat phase, time-warped so the down-stroke (pw 0 -> 0.5) takes
~60% of each beat and the up-stroke ~40%. wd = cos(2 pi pw): +1 wings at the top, -1 at the bottom.
fd = fold, peaks in mid up-stroke (wrist and hand fold back, wing tucks), 0 through the down-stroke.
Everything else follows wd/fd a few LAGs later.
"""
import json, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "mega_staraptor_front.json")

DEFAULTS = dict(
    AZIMUTH=55, ELEVATION=12, FOV=30,
    # rest pose
    LEAN=-28.0,      # whole body pitch (world X, + = forward)
    TURN=0.0,        # whole body yaw (world Z)
    BANK=0.0,        # whole body roll (world Y)
    WMID=15.0,       # arm_01 mid-stroke raise (0 = horizontal)
    WSWEEP=-10.0,    # arm_01 sweep about Z (+ = tips back)
    ELB=5.0,         # arm_02 further raise
    HANDB=0.0,       # hand further raise
    LEGF=35.0, KNEE=10.0, TOE=25.0,
    HDY=-12.0, HDP=-12.0, NKP=-5.0,
    TAILP=0.0, CLOTHP=0.0,
    # wingbeat
    CYC=2,           # beats per loop
    WARP=0.30,       # down-stroke share: 0 = 50%, 0.3 = ~60%
    LAG=0.025,       # follow-through step (loop fraction)
    BEAT=42.0,       # arm_01 stroke half-amplitude (deg)
    BEAT2=10.0,      # arm_02 lagging stroke
    BEAT3=10.0,      # hand lagging stroke
    FOLD1=12.0,      # arm_01 sweeps back in the up-stroke
    FOLD2=25.0,      # arm_02 folds back in the up-stroke
    FOLD3=25.0,      # hand folds back in the up-stroke
    FOLDD=15.0,      # hand droops (bends down) in the up-stroke
    FEATH=8.0,       # feathers trailing flex
    BOB=0.10,        # body rise on the down-stroke (world units)
    BPITCH=3.0,      # body pitch with the beat
    HEADST=2.0,      # head counter-nod (keeps the face steady)
    TAILA=6.0, CLOTHA=5.0, LEGA=4.0, CRESTA=6.0, FEELA=5.0,
)

FUNCS = {
    # pw0: down-stroke takes the larger share (WARP); pw: a glide hold (GLIDE) where the spread wing
    # slows mid/low in the down-stroke, slowest at pw0 = GPH + 0.5, soft ease in and out
    "pw0": "CYC*t - WARP*(1 - cos(2*pi*CYC*t))/(2*pi)",
    "pw": "pw0(t) + GLIDE*sin(2*pi*(pw0(t) - GPH))/(2*pi)",
    # body: plain sine, rises through the down-stroke and drifts down over a longer stretch than the up-stroke
    "bob": "cos(2*pi*CYC*(t - BLAG))",
    "wd": "cos(2*pi*pw(t))",
    "fd": "(0.5 + 0.5*cos(2*pi*(pw(t) - 0.72)))**2",
    "vd": "sin(2*pi*pw(t))",
}
NEW = dict(TWIST=0.0, PRON=0.0, ELBF=0.0, HAIR=0.0, HTW=0.0, FLIP=0.0, AIR=0.0, SPRD=0.0,
           TAILY=0.0, TFAN=0.0, LLAG=0.08, FOOTP=0.0, TOEA=0.0, LEGS=0.0, GLIDE=0.0, GPH=-0.12, BLAG=0.0,
           SWP=0.0, SWL=0.0, PCH2=1.5, PCH3=2.0, SLAT=0.0, AIRB=0.0, SECD=0.0, TDIP=0.0, HCOMP=0.0, TILT=0.0)


def mir(ax):
    x, y, z = ax
    return (x, -y, -z)


def A(ax):
    return "A:%.2f,%.2f,%.2f" % ax


def build(pp):
    import math
    tb = math.radians(pp.get("TILT", 0.0))  # flap axis tipped so the stroke plane leans forward
    P = []
    add = lambda b, ax, e: P.append([b, ax, e])
    # whole body: rises while the wings push down (highest just after the bottom of the stroke)
    add("waist", "X", "LEAN - BPITCH*wd(t-2*LAG)")
    add("waist", "Z", "TURN")
    add("waist", "Y", "BANK")
    add("waist", "LOCZ", "-BOB*bob(t)")
    for side, s in (("left", 1), ("right", -1)):
        up = (0.0, -1.0, 0.0) if s == 1 else mir((0.0, -1.0, 0.0))
        sw = (0.0, 0.0, 1.0) if s == 1 else mir((0.0, 0.0, 1.0))
        fx = (1.0, 0.0, 0.0)
        # main stroke + fold (shoulder leads)
        flap = (0.0, -math.cos(tb), math.sin(tb)) if s == 1 else mir((0.0, -math.cos(tb), math.sin(tb)))
        add(f"{side}_arm_01", A(flap), "WMID + BEAT*wd(t)")
        add(f"{side}_arm_01", A(sw), "WSWEEP + FOLD1*fd(t) + SWP*wd(t) - SWL*vd(t)")  # + = tips back: tilted stroke plane
        # wing pitch: constant twist (shows the far wing's surface) + pronate on the down-stroke
        add(f"{side}_arm_01", A(fx), "TWIST + PRON*vd(t)")
        add(f"{side}_arm_02", A(fx), "PCH2*PRON*vd(t-LAG)")
        # elbow: lags the shoulder, folds in tight on the up-stroke
        add(f"{side}_arm_02", A(up), "ELB + BEAT2*wd(t-LAG) - ELBF*fd(t)")
        add(f"{side}_arm_02", A(sw), "FOLD2*fd(t-LAG)")
        # wrist: lags the elbow, hand trails up on the down-stroke, flips/droops and folds on the up-stroke
        add(f"{side}_hand", A(up), "HANDB + BEAT3*wd(t-2*LAG) + HAIR*vd(t-LAG) - FOLDD*fd(t-LAG)")
        add(f"{side}_hand", A(sw), "FOLD3*fd(t-2*LAG)")
        add(f"{side}_hand", A(fx), "HTW + PCH3*PRON*vd(t-2*LAG) + FLIP*fd(t-LAG)")
        # primaries trail the hand, tips bend up under air pressure on the down-stroke, fan open / close
        # (v5: one LAG later than v4 so the air seems to carry the feathers)
        for b, k, m in (("horn_d_01", 4, 0.8), ("horn_d_02", 5, 0.6), ("horn_e_01", 4, 0.8), ("horn_e_02", 5, 0.6),
                        ("claw_c", 4, 0.8)):
            add(f"{side}_{b}", A(up), f"{m}*(FEATH*wd(t-{k}*LAG) + AIR*vd(t-{k - 1}*LAG))")
            add(f"{side}_{b}", A(sw), f"{m}*AIRB*vd(t-{k - 1}*LAG)**2")  # air pushes the tips back in both strokes
        for b, m in (("horn_e_01", 1.0), ("claw_c", 0.4), ("horn_d_01", -0.4)):
            add(f"{side}_{b}", A(fx), f"{m}*SLAT*fd(t-2*LAG)")  # slats: primaries twist apart, gaps open
        add(f"{side}_horn_d_01", A(sw), "SPRD*(0.4 - fd(t-3*LAG))")
        add(f"{side}_horn_e_01", A(sw), "-SPRD*(0.4 - fd(t-3*LAG))")
        # secondaries flex about X behind the arm
        for b, k, m in (("horn_a_01", 2, 0.5), ("horn_a_02", 3, 0.4), ("horn_b_01", 2, 0.5), ("horn_b_02", 3, 0.4),
                        ("horn_c_01", 3, 0.5), ("horn_c_02", 4, 0.4), ("claw_a", 2, 0.5), ("claw_b", 3, 0.5)):
            add(f"{side}_{b}", A(fx), f"{m}*FEATH*wd(t-{k}*LAG)")
            add(f"{side}_{b}", A(up), f"-{m}*SECD*fd(t-{k - 1}*LAG)")
        # legs dangle as passive weight (eagle talons): thigh down and a little back, shank hanging,
        # swinging back while the body lifts (down-stroke) a few frames late, then forward and settling;
        # + on X = back. Pendulum: thigh lags the body, shank lags the thigh, toes flex last.
        add(f"{side}_leg_01", "X", "-LEGF + LEGA*vd(t-LLAG)")
        add(f"{side}_leg_01", "Y", "%d*LEGS" % -s)  # splay the legs apart so the talons hang clear
        add(f"{side}_leg_02", "X", "KNEE + 0.7*LEGA*vd(t-LLAG-2*LAG)")
        add(f"{side}_foot", "X", "FOOTP + 0.5*LEGA*vd(t-LLAG-3*LAG)")
        toes = {"index": (0.93, -0.38 * s, 0.0), "middle": (1.0, 0.0, 0.0), "ring": (0.93, 0.38 * s, 0.0),
                "thumb": (-1.0, 0.0, 0.0)}
        for toe, ax in toes.items():
            n = 2 if toe == "thumb" else 3
            for j in range(1, n + 1):
                add(f"{side}_foot_{toe}_0{j}", A(ax), "(TOE + TOEA*vd(t-LLAG-4*LAG))*%.2f" % (0.6 + 0.2 * j))
        # back plumes trail
        cl = (1.0, 0.0, 0.0)
        add(f"{side}_cloth_a_01", A(cl), "CLOTHP + 0.5*CLOTHA*wd(t-4*LAG)")
        add(f"{side}_cloth_a_02", A(cl), "CLOTHA*wd(t-5*LAG)")
        for c in "bcde":
            add(f"{side}_cloth_{c}", A(cl), "1.3*CLOTHA*wd(t-6*LAG)")
        # head side feathers
        for b, k in (("feeler_a", 5), ("feeler_b_01", 5), ("feeler_b_02", 6), ("feeler_c_01", 5), ("feeler_c_02", 6),
                     ("feeler_d", 6), ("feeler_e", 6)):
            add(f"{side}_{b}", A(fx), f"FEELA*wd(t-{k}*LAG)")
        add(f"{side}_feeler_f", A(fx), "FEELA*wd(t-5*LAG)")
    # neck / head: steadies against the body (counter-nod)
    # (+ pitch = head/beak down). Tiny, late, eased correction only.
    add("neck", "A:1.00,0.00,0.00", "NKP + 0.4*HEADST*wd(t-5*LAG)")
    add("head", "A:0.00,-0.26,0.97", "HDY")
    add("head", "A:1.00,0.00,0.00", "HDP + HEADST*wd(t-6*LAG) + HCOMP*BPITCH*wd(t-3*LAG)")
    # crest trails
    add("hair_a_01", "A:1.00,0.00,0.00", "0.5*CRESTA*wd(t-5*LAG)")
    add("hair_a_02", "A:1.00,0.00,0.00", "0.8*CRESTA*wd(t-6*LAG)")
    add("hair_a_03", "A:1.00,0.00,0.00", "CRESTA*wd(t-7*LAG)")
    add("hair_e", "A:1.00,0.00,0.00", "CRESTA*wd(t-7*LAG)")
    for h in ("hair_b", "hair_c", "hair_d"):
        add(h, "A:1.00,0.00,0.00", "CRESTA*wd(t-6*LAG)")
    add("feeler_a", "A:1.00,0.00,0.00", "FEELA*wd(t-5*LAG)")
    add("feeler_b_01", "A:1.00,0.00,0.00", "0.6*FEELA*wd(t-5*LAG)")
    add("feeler_b_02", "A:1.00,0.00,0.00", "FEELA*wd(t-6*LAG)")
    # tail trails (pitch, + = down)
    add("tail_01", "A:1.00,0.00,0.00", "TAILP + 0.6*TAILA*wd(t-5*LAG) + TDIP*vd(t-2*LAG)")
    add("tail_02", "A:1.00,0.00,0.00", "TAILA*wd(t-6*LAG)")
    # tail steers: a slow yaw/roll once per loop, plus fans (widens) on the down-stroke
    add("tail_01", "A:0.00,0.00,1.00", "TAILY*sin(2*pi*t)")
    add("tail_02", "A:0.00,0.00,1.00", "1.3*TAILY*sin(2*pi*(t-0.06))")
    add("tail_01", "SCALEW", "1 + TFAN*(0.5 + 0.5*vd(t-2*LAG))")
    return P


def main():
    cfg = json.load(open(CFG))
    pp = cfg.get("pose_params", {})
    for k, v in {**DEFAULTS, **NEW}.items():
        if k not in pp:
            print(f"new  {k} = {v}")
            pp[k] = v
    for arg in sys.argv[1:]:
        k, v = arg.split("=", 1)
        v = float(v) if "." in v or "e" in v else int(v)
        print(f"set  {k}: {pp.get(k)} -> {v}")
        pp[k] = v
    cfg["pose_params"] = pp
    cfg["model"] = "MegaStaraptor/MegaStaraptor_open.blend"
    cfg["pose"] = build(pp)
    m = cfg.setdefault("motion", {})
    m["frames"] = 150  # 2 beats x 75 frames x 20 ms = 1.5 s per beat
    m["functions"] = FUNCS
    m.pop("plant", None)  # flying: no foot touches the ground
    json.dump(cfg, open(CFG, "w"), indent=2)
    print("wrote", CFG, len(cfg["pose"]), "pose entries")


if __name__ == "__main__":
    main()
