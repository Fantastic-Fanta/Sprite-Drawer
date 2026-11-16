"""Quick look at a pose / motion without a sprite build: Workbench renders (flat texture colours,
seconds not minutes) of a few loop frames, from the sprite camera and other angles, on one sheet.

Run:  python3 pipeline/preview.py CONFIG.json OUT.png [--frames 8] [--views sprite,side,top,back] [--size 200]
Rows = views, columns = frames evenly over the loop (frame numbers printed under them). Runs its
Blender under a machine slot (blender_slot.py) with a timeout. Judge pose and motion here; build
with build_all.py only once both pass.
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
    import blender_slot
    a = sys.argv[1:]
    if len(a) < 2 or a[0] in ("-h", "--help"):
        print(__doc__); sys.exit(0 if a and a[0] in ("-h", "--help") else 1)
    cfg, out = Path(a[0]).resolve(), Path(a[1])
    n = int(a[a.index("--frames") + 1]) if "--frames" in a else 8
    views = a[a.index("--views") + 1] if "--views" in a else "sprite,side"
    size = int(a[a.index("--size") + 1]) if "--size" in a else 200
    model = cfg.parent / json.loads(cfg.read_text())["model"]
    with tempfile.TemporaryDirectory() as tmp:
        code = blender_slot.run(["-b", "--python-exit-code", "1", str(model), "--python", __file__, "--", str(cfg), tmp, str(n), views, str(size)], 600)
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


if __name__ == "__main__":
    if IN_BLENDER:
        blender_main()
    else:
        main()
