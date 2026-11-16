"""Mega Skarmory pose + flight wingbeat generator.
Usage: /usr/local/bin/python3 gen.py [KEY=value ...]
Keeps existing pose_params (only KEY=value overrides or new keys change), prints every change,
rewrites `pose`, `motion`, palette parts from the template below.

Driver: one wingbeat. pw(t) is the beat phase, time-warped so the down-stroke (pw 0 -> 0.5) takes
~57% of each beat. wd = cos(2 pi pw): +1 wings at the top, -1 at the bottom.
fd = fold, peaks mid up-stroke (wing sweeps back, blades close and droop), ~0 on the down-stroke.
Everything else follows wd/fd a few LAGs later.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "mega_skarmory_front.json")

DEFAULTS = dict(
    AZIMUTH=55, ELEVATION=12, FOV=30,
    # rest pose (HOME / Z-A art: airborne, body pitched forward, wings up and back, legs trailing)
    LEAN=20.0,       # whole body pitch about world X (+ = head down / forward)
    TURN=0.0,        # whole body yaw (world Z)
    NECK=-4.0,       # each neck bone about X (- = head back up), counters LEAN
    HDP=-4.0,        # head pitch about X
    HDY=0.0,         # head yaw toward the camera
    WMID=10.0,       # root_wing mid-stroke raise
    WSWEEP=12.0,     # root_wing sweep back about Z
    WFAN=0.0,        # feather fan spread (in-plane)
    LEGB=-40.0,      # legs swing (about X): - = back, trailing
    KNEE=-15.0,      # shin
    TOED=60.0,       # front toe blades droop
    THUMBD=-15.0,    # back toe blade droop
    TAILP=0.0,
    # wingbeat
    CYC=2, WARP=0.22, LAG=0.025,
    BEAT=40.0,       # root_wing stroke half-amplitude (deg)
    FLEX=10.0,       # feather out-of-plane flex, grows down the chain, lagging
    SWB=12.0,        # wing sweeps forward on the way down (back at the top, forward at the bottom)
    PRON=20.0,       # leading-edge twist at the bottom of the stroke
    FOLD1=14.0,      # wing sweeps back in the up-stroke
    FOLDC=10.0,      # blades close the fan in the up-stroke
    FOLDD=14.0,      # blade tips droop in the up-stroke
    BOB=0.06,        # body rise on the down-stroke (world units)
    BPITCH=3.0, HEADST=2.5,
    TAILA=7.0, LEGA=5.0, CRESTA=7.0, TOEA=5.0,
)

FUNCS = {
    "pw": "CYC*t - WARP*(1 - cos(2*pi*CYC*t))/(2*pi)",
    "wd": "cos(2*pi*pw(t))",
    "fd": "(0.5 + 0.5*cos(2*pi*(pw(t) - 0.78)))**2",
}

PALETTE = {
    "yellow": ["#ceab00", "#e4c200", "#f0cd23", "#fcd938", "#ffe548"],
    "navy": ["#253a5a", "#374d6f", "#415779", "#4a6083", "#546a8e"],
    # wing / crest / toe blades: same look as navy, one step off in blue so the shiny swap can
    # tell them apart (the shiny turns these green, the neck plates grey-olive)
    "blade": ["#253a5b", "#374d70", "#41577a", "#4a6084", "#546a8f"],
    "mouth": ["#9f686a", "#b57d7e", "#c08788", "#f2b5b6", "#ffc8c9"],
    # the eye is black in the texture (coloured in the game's shader): blood red in the art
    "eye": ["#9c0e1c", "#c01424", "#dc2430", "#f04848", "#ff7474"],
}
PARTS = {
    "materials": {"body_a": "yellow|navy", "body_b": "yellow|blade",
                  "body_a_01": "mouth", "l_eye": "eye", "r_eye": "eye"},
    "default_material": "body_b",
    "albedo": {"yellow": "#e5c300", "navy": "#374c6e", "blade": "#374c6f", "mouth": "#cf9596",
               "eye": "#000000"},
}

X = "A:1.00,0.00,0.00"


def A(ax):
    return "A:%.2f,%.2f,%.2f" % tuple(ax)


def mir(ax):
    x, y, z = ax
    return (-x, y, z)   # mirror across the body plane (x -> -x): a rotation axis flips to (x, -y, -z)


def axmir(ax):
    x, y, z = ax
    return (x, -y, -z)


# wing bones' own axes (left side, from RIG.md): y = out-of-plane flex, z = in-plane (fan)
WING = {
    "a": [((-0.41, -0.66, 0.62), (0.54, -0.73, -0.42)), ((-0.21, -0.59, 0.78), (0.54, -0.73, -0.42)),
          ((0.03, -0.48, 0.88), (0.54, -0.73, -0.42))],
    "b": [((-0.23, -0.62, 0.75), (0.55, -0.72, -0.42)), ((-0.07, -0.55, 0.83), (0.55, -0.72, -0.42)),
          ((0.13, -0.43, 0.89), (0.55, -0.72, -0.42)), ((0.26, -0.34, 0.91), (0.55, -0.72, -0.42))],
    "c": [((-0.04, -0.60, 0.80), (0.56, -0.67, -0.48)), ((0.17, -0.47, 0.87), (0.56, -0.67, -0.48)),
          ((0.38, -0.30, 0.88), (0.56, -0.67, -0.48))],
    "d": [((0.10, -0.52, 0.85), (0.58, -0.66, -0.48)), ((0.34, -0.34, 0.88), (0.58, -0.66, -0.48)),
          ((0.54, -0.13, 0.83), (0.58, -0.66, -0.48))],
}
FAN = {"a": -1.0, "b": -0.35, "c": 0.35, "d": 1.0}   # leading blade a, trailing blade d


def build():
    P = []
    add = lambda b, ax, e: P.append([b, ax, e])
    # whole body: pitch, rises while the wings push down
    add("waist", "X", "LEAN - BPITCH*wd(t-2*LAG)")
    add("waist", "Z", "TURN")
    add("waist", "LOCZ", "-BOB*wd(t-3*LAG)")
    # neck / head counter the lean and steady the face
    for i in range(1, 6):
        add(f"neck_0{i}", X, f"NECK + 0.3*HEADST*wd(t-{2 + i * 0.4:.1f}*LAG)")
    add("head", "A:0.00,-0.40,0.92", "HDY")   # head yaw about its own long axis: + = face toward the camera
    add("head", X, "HDP + HEADST*wd(t-4*LAG)")
    # hair_a (the short crest) cuts into the head at any bend: it rides on the head
    add("hair_b_02", X, "-0.8*CRESTA*wd(t-6*LAG)")
    for side, s in (("left", 1), ("right", -1)):
        m = (lambda ax: ax) if s == 1 else axmir
        up = m((0.0, -1.0, 0.0))     # raise the wing
        sw = m((0.0, 0.0, 1.0))      # sweep the wing back
        add(f"{side}_root_wing", A(up), "WMID + BEAT*wd(t)")
        add(f"{side}_root_wing", A(sw), "WSWEEP + SWB*wd(t) + FOLD1*fd(t)")
        # pronation: the leading edge tips down through the down-stroke (wing faces show)
        add(f"{side}_root_wing", A(m((1.0, 0.0, 0.0))), "PRON*(0.5 - 0.5*wd(t-0.5*LAG))")
        for f, chain in WING.items():
            for j, (yax, zax) in enumerate(chain):
                if s == -1:   # right side: the left axis mirrored (a rotation axis maps x,y,z -> x,-y,-z)
                    yax, zax = axmir(yax), axmir(zax)
                k = j + 1
                g = 0.6 + 0.4 * j
                # out-of-plane flex: the blades bend up as the wing pushes down (trailing), droop in the fold
                add(f"{side}_wing_{f}_0{j + 1}", A(yax),
                    f"({g:.2f}*FLEX*wd(t-{k:.1f}*LAG) - {0.5 * j:.1f}*FOLDD*fd(t-{k:.1f}*LAG))")
                # in-plane fan: spread at rest, closes in the up-stroke
                if j == 0:
                    add(f"{side}_wing_{f}_01", A(zax),
                        f"{FAN[f]:.2f}*(WFAN - FOLDC*fd(t-{k:.1f}*LAG))")
        # legs trail behind, swinging a beat later
        add(f"{side}_leg_01", X, "-LEGB + LEGA*wd(t-4*LAG)")
        add(f"{side}_leg_02", X, "KNEE + 0.6*LEGA*wd(t-5*LAG)")
        for toe in ("index", "middle"):
            add(f"{side}_foot_{toe}_01", X, "TOED + 0.5*TOEA*wd(t-5*LAG)")
            add(f"{side}_foot_{toe}_04", X, "TOEA*wd(t-6*LAG)")
        add(f"{side}_foot_thumb_01", X, "THUMBD - 0.5*TOEA*wd(t-5*LAG)")
        add(f"{side}_foot_thumb_04", X, "-TOEA*wd(t-6*LAG)")
        # the blade fringes ride on their toes: same bend at the same joint, so they never cut through
        add(f"{side}_feeler_a_02", X, "-TOEA*wd(t-6*LAG)")
        for fl in ("b", "c"):
            add(f"{side}_feeler_{fl}_02", X, "TOEA*wd(t-6*LAG)")
    add("tail", X, "TAILP - 0.6*TAILA*wd(t-5*LAG)")
    return P


def main():
    cfg = json.load(open(CFG))
    pp = cfg.get("pose_params", {})
    for k, v in DEFAULTS.items():
        if k not in pp:
            print(f"new  {k} = {v}")
            pp[k] = v
    for arg in sys.argv[1:]:
        k, v = arg.split("=", 1)
        v = float(v) if any(c in v for c in ".e") else int(v)
        print(f"set  {k}: {pp.get(k)} -> {v}")
        pp[k] = v
    cfg["pose_params"] = pp
    if cfg["palette"]["parts"] != PALETTE:
        print("palette parts:", list(cfg["palette"]["parts"]), "->", list(PALETTE))
        cfg["palette"]["parts"] = PALETTE
    if cfg["parts"] != PARTS:
        print("parts.materials:", cfg["parts"].get("materials"), "->", PARTS["materials"])
        cfg["parts"] = PARTS
    cfg["pose"] = build()
    mo = cfg.setdefault("motion", {})
    mo["frames"] = 96
    mo["functions"] = FUNCS
    mo.pop("plant", None)   # airborne
    json.dump(cfg, open(CFG, "w"), indent=2)
    print("wrote", CFG, len(cfg["pose"]), "pose entries")


if __name__ == "__main__":
    main()
