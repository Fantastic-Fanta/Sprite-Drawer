"""Live motion preview: the model in Blender's viewport through the sprite camera, playing the loop
in real time, reloaded whenever the config is saved. For working on a motion; the sprite look
(palette, bands, hull lines) only comes from a real build.

Run (not -b: it opens Blender's window):
  $B MODEL.blend --python pipeline/live_preview.py -- CONFIG.json
  e.g. $B golisopod-model/MegaGolisopod/MegaGolisopod.blend --python pipeline/live_preview.py -- golisopod-model/golisopod_front.json
Edit pose / pose_params / motion (plant too) / style.fast_frames / camera in the config and save: the viewport
picks it up within a fraction of a second and keeps playing. Space pauses, arrow keys step frames.
--selftest: set up and bake once, print the timings, quit (works with -b).
Quits by itself after SPRITE_LIVE_IDLE_MIN minutes (default 30) without a config save, so a
forgotten preview doesn't keep playing (and using several cores) in the background; 0 = never.
"""
import bpy, sys, json, math, time, os
from pathlib import Path

args = sys.argv[sys.argv.index("--") + 1:]
cfg_path = Path(args[0]).resolve()
SELFTEST = "--selftest" in args
HERE = Path(__file__).resolve().parent if "__file__" in globals() else Path(sys.argv[sys.argv.index("--python") + 1]).resolve().parent

# the render script's scene setup (camera, pose code), without rendering
t0 = time.time()
sys.argv = [sys.argv[0], "--", str(cfg_path), str(HERE.parent / "out" / "live"), "--setup-only"]
src = HERE / "render_sprite.py"
g = {"__name__": "render_sprite", "__file__": str(src)}
exec(compile(src.read_text(), str(src), "exec"), g)
scene, arm, meshes = g["scene"], g["arm"], g["meshes"]
print(f"[live] scene set up in {time.time() - t0:.1f}s", flush=True)

state = {"mtime": cfg_path.stat().st_mtime_ns, "poses": [], "baking": False, "saved": time.time()}
IDLE_S = float(os.environ.get("SPRITE_LIVE_IDLE_MIN", 30)) * 60


def bake():
    """every frame's pose, as each bone's matrix_basis: playback then only copies matrices.
    The meshes are hidden meanwhile so each pose step evaluates the armature alone."""
    t = time.time()
    state["baking"] = True
    hidden = [o for o in meshes if not o.hide_viewport]
    for o in hidden:
        o.hide_viewport = True
    n = g["FRAMES"]
    poses = []
    try:
        for f in range(n):
            g["pose_at"](f / n)
            poses.append([(pb, pb.matrix_basis.copy()) for pb in arm.pose.bones])
    finally:
        for o in hidden:
            o.hide_viewport = False
        state["baking"] = False
    ad = arm.animation_data
    if ad and ad.action:             # motion.clip: baked already, don't let the action fight the bake
        ad.action = None
    state["poses"] = poses
    scene.frame_start, scene.frame_end = 0, n - 1
    ms = g["cfg"]["style"].get("frame_ms", 30)
    scene.render.fps, scene.render.fps_base = 1000, ms   # exactly 1000/frame_ms frames a second
    show(scene.frame_current)
    print(f"[live] baked {n} frames in {time.time() - t:.1f}s", flush=True)


def show(f):
    poses = state["poses"]
    if not poses:
        return
    for pb, m in poses[f % len(poses)]:
        pb.matrix_basis = m


def on_frame(sc, *_):
    if not state["baking"]:
        show(sc.frame_current)


def load():
    cfg = json.loads(cfg_path.read_text())
    g["cfg"] = cfg
    g["P"].clear()
    g["P"].update(cfg["pose_params"])
    g["FRAMES"] = cfg["motion"]["frames"]
    g["CAM"] = cfg["camera"]
    g["CLIP"] = cfg.get("motion", {}).get("clip")
    scene.render.resolution_x, scene.render.resolution_y = cfg["render"]["width"], cfg["render"]["height"]
    g["place_camera"]()
    g["plant"]()
    bake()


def watch():
    try:
        m = cfg_path.stat().st_mtime_ns
        if m != state["mtime"]:
            state["mtime"], state["saved"] = m, time.time()
            load()
        elif IDLE_S and time.time() - state["saved"] > IDLE_S:
            print(f"[live] no config save for {IDLE_S / 60:.0f} min: quitting", flush=True)
            bpy.ops.wm.quit_blender()
            return None
    except Exception as e:               # half-saved JSON, a typo in an expression: keep the last good bake
        print(f"[live] config not loaded: {e}", flush=True)
    return 0.25


def setup_view():
    for o in scene.objects:
        if o.name.startswith("Icosphere"):      # glTF bone-display helper, hidden in renders too
            o.hide_viewport = True
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type != "VIEW_3D":
                continue
            sp = area.spaces.active
            sp.shading.type = "SOLID"
            sp.shading.light = "FLAT"
            sp.shading.color_type = "TEXTURE"
            sp.shading.show_object_outline = False
            sp.shading.background_type = "VIEWPORT"
            sp.shading.background_color = (0.75, 0.75, 0.75)
            sp.overlay.show_overlays = False
            sp.region_3d.view_perspective = "CAMERA"
            with bpy.context.temp_override(window=win, area=area, region=next(r for r in area.regions if r.type == "WINDOW")):
                bpy.ops.view3d.view_center_camera()
            if not bpy.context.screen.is_animation_playing:
                with bpy.context.temp_override(window=win, area=area):
                    bpy.ops.screen.animation_play()
            return None
    return None


load()
bpy.app.handlers.frame_change_post.append(on_frame)
if SELFTEST:
    t = time.time()
    for f in range(g["FRAMES"]):
        scene.frame_set(f)
    print(f"[live] stepped through {g['FRAMES']} frames in {time.time() - t:.2f}s", flush=True)
else:
    bpy.app.timers.register(watch, first_interval=0.25, persistent=True)
    bpy.app.timers.register(setup_view, first_interval=0.5)
    print(f"[live] watching {cfg_path}", flush=True)
