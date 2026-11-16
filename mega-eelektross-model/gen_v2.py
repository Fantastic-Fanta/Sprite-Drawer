"""v2 (after the user's feedback): play the game idle (motion.clip) with a Drampa-like camera, and
add a travelling swim wave on top of the three eels (main body: spine + tail; the two white side
eels: left/right_feeler_b chains) about each chain's own bend axes.
Usage: /usr/local/bin/python3 gen_v2.py [KEY=value ...] [--out PATH]
Keeps existing pose_params unless overridden; prints every change."""
import json, sys, pathlib
HERE = pathlib.Path(__file__).parent
CFG = HERE / "mega_eelektross_front.json"
out = pathlib.Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else CFG
cfg = json.loads(CFG.read_text())
CLIP = "pm0604_51_00_20001_battlewait01_loop"
NOTE = "An eel swimming in place: a travelling wave runs head to tail along all three eels. The game's own idle (pm0604_51_00_20001_battlewait01_loop from the Z-A pack, 121 frames at 60 fps = 2.0 s; _10001_ is identical) drives everything: the body rolls and dips, the main tail carries a sideways wave root to tip, the two white side eels carry an up-down wave root to tip, the fins, horn and mouths follow. Added on top: a vertical travelling wave on the main body (hips -> tail_08, about each bone's own pitch axis, SWV=6 deg/joint growing to the tip, 0.09 loop later per joint, one cycle per loop) so the main eel also rides up and down the waves like the side eels. 100 frames x 20 ms = 2.0 s, game speed."

# camera like Mega Drampa's front config (AZIMUTH 50, ELEVATION 14)
DEFAULTS = dict(AZIMUTH=50, ELEVATION=14, FOV=30,
                SW=0.0,      # main-body swim wave amplitude (deg per joint, yaw = across the view)
                SWV=0.0,     # main-body vertical part of the wave (deg per joint)
                EW=0.0,      # side-eel swim wave amplitude (deg per joint, yaw)
                EWV=0.0,     # side-eel vertical part (deg per joint)
                WL=0.09,     # phase lag per joint (loops): the wave travels head -> tail
                HEADW=0.0)   # head counter-turn so the face stays steady and readable
old = cfg.get("pose_params", {}) if cfg.get("motion", {}).get("clip") == CLIP else {}
pp = dict(DEFAULTS); pp.update(old)
for a in sys.argv[1:]:
    if "=" in a and not a.startswith("--"):
        k, v = a.split("=", 1); pp[k] = float(v)
for k in sorted(set(pp) | set(cfg.get("pose_params", {}))):
    if cfg.get("pose_params", {}).get(k) != pp.get(k):
        print(f"  {k}: {cfg.get('pose_params', {}).get(k)} -> {pp.get(k)}")

pose = []
P = lambda b, ax, e: pose.append([b, ax, e])
S = lambda ph: f"sin(2*pi*(t - {ph}))"      # one cycle per loop: seamless
if pp["SW"] or pp["SWV"]:
    # main eel: hips -> tail tip (hips hangs off the waist, so the head, arms and side eels are
    # not moved); each joint a phase later and a bit bigger toward the tail tip
    chain = ["hips"] + [f"tail_{i:02d}" for i in range(1, 9)]
    for i, b in enumerate(chain):
        g = 0.5 + 0.1 * i
        if pp["SW"]:
            P(b, "A:0,0,1", f"SW*{g:.2f}*" + S(f"{i}*WL"))
        if pp["SWV"]:
            P(b, "A:1,0,0", f"SWV*{g:.2f}*" + S(f"0.25 + {i}*WL"))
    if pp["HEADW"]:
        P("head", "A:0,0,1", "-HEADW*" + S("0"))
for s, sg, off in (("left", 1, 0.0), ("right", -1, 0.5)):
    if pp["EW"] or pp["EWV"]:
        for i in range(1, 11):
            g = 0.5 + 0.08 * i
            b = f"{s}_feeler_b_{i:02d}"
            if pp["EW"]:
                P(b, "A:0,0,1", f"{sg}*EW*{g:.2f}*" + S(f"{0.15 + off} + {i}*WL"))
            if pp["EWV"]:
                P(b, "A:1,0,0", f"EWV*{g:.2f}*" + S(f"{0.40 + off} + {i}*WL"))

cfg["model"] = "MegaEelektross/MegaEelektross_anim.blend"
cfg["pose_params"] = pp
cfg["pose"] = pose
cfg["motion"] = {"frames": 100, "clip": CLIP, "note": NOTE}
cfg["style"]["height"] = 200
cfg["style"]["frame_ms"] = 20
cfg["render"].setdefault("hull", {})["cap_each_frame"] = True
out.write_text(json.dumps(cfg, indent=2) + "\n")
print("wrote", out, "pose rows:", len(pose))
