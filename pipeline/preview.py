"""Quick look at a pose / motion without a sprite build: Workbench renders (flat texture colours,
seconds not minutes) of a few loop frames, from the sprite camera and other angles, on one sheet.

Run:  python3 pipeline/preview.py CONFIG.json OUT.png [--frames 8] [--views sprite,side,top,back] [--size 200]
Rows = views, columns = frames evenly over the loop (frame numbers printed under them). Runs its
Blender under a machine slot (blender.py) with a timeout. Judge pose and motion here; build
with build.py only once both pass.

Live:  python3 pipeline/preview.py CONFIG.json --live
Opens Blender's window on the config's model, through the sprite camera, playing the loop in real
time. Edit pose / pose_params / motion (plant too) / style.fast_frames / camera in the config and
save: it picks the change up within a fraction of a second and keeps playing. Space pauses, arrow
keys step frames. It shows the model, not the sprite look (palette, bands, hull lines). It quits by
itself after SPRITE_LIVE_IDLE_MIN minutes (default 30) without a config save; 0 = never.
--live --selftest: set up and bake once in the background, print the timings, quit.
"""
import json
import math
import sys
from pathlib import Path

try:
    import bpy  # noqa: F401
    IN_BLENDER = True
except ImportError:
    IN_BLENDER = False

HERE = Path(__file__).resolve().parent
VIEWS = {"sprite": None, "front": (90, 5), "side": (0, 5), "top": (90, 80), "back": (270, 12), "left": (180, 5)}


def blender_main():
    import bpy
    a = sys.argv[sys.argv.index("--") + 1:]
    cfg_path, out_dir, n, views, size = a[0], Path(a[1]), int(a[2]), a[3].split(","), int(a[4])
    sys.argv = [sys.argv[0], "--", cfg_path, str(out_dir), "--setup-only"]
    g = {"__name__": "render_sprite", "__file__": str(HERE / "render_sprite.py")}
    exec(compile((HERE / "render_sprite.py").read_text(), str(HERE / "render_sprite.py"), "exec"), g)
    sc, CAM = g["scene"], g["CAM"]
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "TEXTURE"
    sc.render.film_transparent = False
    sc.world = sc.world or bpy.data.worlds.new("W")
    sc.world.color = (0.62, 0.62, 0.62)
    sc.view_settings.view_transform = "Standard"
    sc.render.resolution_x = sc.render.resolution_y = size
    frames = g["FRAMES"]
    fs = [round(i * frames / n) for i in range(n)]
    for f in fs:
        g["pose_at"](f / frames)
        for v in views:
            saved = dict(CAM)
            if VIEWS[v] is not None:
                CAM["azimuth"], CAM["elevation"] = VIEWS[v]
                if v == "back":                            # the back camera: azimuth + 180, from above
                    CAM["azimuth"] = f"({saved['azimuth']}) + 180" if isinstance(saved["azimuth"], str) else saved["azimuth"] + 180
            g["place_camera"]()
            CAM.clear(); CAM.update(saved)
            sc.render.filepath = str(out_dir / f"{v}_{f:04d}.png")
            bpy.ops.render.render(write_still=True)
    (out_dir / "frames.json").write_text(json.dumps(fs))


def main():
    from PIL import Image, ImageDraw
    import tempfile
    sys.path.insert(0, str(HERE))
    import blender
    a = sys.argv[1:]
    if len(a) < 2 or a[0] in ("-h", "--help"):
        print(__doc__); sys.exit(0 if a and a[0] in ("-h", "--help") else 1)
    cfg, out = Path(a[0]).resolve(), Path(a[1])
    n = int(a[a.index("--frames") + 1]) if "--frames" in a else 8
    views = a[a.index("--views") + 1] if "--views" in a else "sprite,side"
    size = int(a[a.index("--size") + 1]) if "--size" in a else 200
    model = cfg.parent / json.loads(cfg.read_text())["model"]
    with tempfile.TemporaryDirectory() as tmp:
        code = blender.run(["-b", "--python-exit-code", "1", str(model), "--python", __file__, "--", str(cfg), tmp, str(n), views, str(size)], 600)
        if code or not (Path(tmp) / "frames.json").exists():
            print(f"preview failed (Blender exit {code})"); sys.exit(1)
        fs = json.loads((Path(tmp) / "frames.json").read_text())
        vs = views.split(",")
        sheet = Image.new("RGB", (size * len(fs), (size + 16) * len(vs)), (150, 150, 150))
        d = ImageDraw.Draw(sheet)
        for r, v in enumerate(vs):
            for c, f in enumerate(fs):
                sheet.paste(Image.open(Path(tmp) / f"{v}_{f:04d}.png").convert("RGB"), (c * size, r * (size + 16)))
                d.text((c * size + 4, r * (size + 16) + size + 2), f"{v} f{f}", fill=(0, 0, 0))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print(f"wrote {out} ({len(vs)} views x {len(fs)} frames)")


def live_main(cfg_path, SELFTEST):
    """--live, inside Blender's window: the model through the sprite camera, playing the loop in real
    time, reloaded whenever the config is saved (--selftest: set up and bake once, print the timings)"""
    import bpy, time, os
    t0 = time.time()
    # the render script's scene setup (camera, pose code), without rendering
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


def live(cfg, selftest):
    """start Blender's window on the config's model with live_main (holds a Blender slot; it quits by
    itself after SPRITE_LIVE_IDLE_MIN minutes without a config save)"""
    sys.path.insert(0, str(HERE))
    import blender
    model = cfg.parent / json.loads(cfg.read_text())["model"]
    sys.exit(blender.run((["-b"] if selftest else []) + [str(model), "--python", __file__, "--", str(cfg), "--live"]
                         + (["--selftest"] if selftest else []), None))


if __name__ == "__main__":
    if IN_BLENDER and "--live" in sys.argv:
        a = sys.argv[sys.argv.index("--") + 1:]
        live_main(Path(a[0]).resolve(), "--selftest" in a)
    elif IN_BLENDER:
        blender_main()
    elif "--live" in sys.argv:
        live(Path(sys.argv[1]).resolve(), "--selftest" in sys.argv)
    else:
        main()
