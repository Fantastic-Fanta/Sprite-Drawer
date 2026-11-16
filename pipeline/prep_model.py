"""python3 prep_model.py MODEL.zip|DIR [--slug NAME] [--height 200] [--force]
Makes models/SLUG/: the unzipped model, RIG.md (bones, axes, feet, materials), prep/rest_*.png and a
draft SLUG_front.json (palette from the textures, camera framed, bind pose). Exit 2: model unusable.
"""
import json
import math
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np

try:
    import bpy  # noqa: F401
    IN_BLENDER = True
except ImportError:
    IN_BLENDER = False

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import blender  # noqa: E402

NAMES = {   # sRGB anchors for naming a part by its colour
    "red": (200, 40, 40), "orange": (230, 130, 40), "yellow": (230, 210, 60), "green": (70, 160, 60),
    "teal": (40, 160, 160), "blue": (50, 90, 200), "navy": (30, 40, 90), "purple": (130, 70, 170),
    "pink": (230, 140, 190), "brown": (120, 80, 50), "tan": (200, 170, 120), "white": (240, 240, 240),
    "gray": (128, 128, 128), "black": (25, 25, 25), "cream": (240, 230, 190), "sky": (150, 200, 235),
    "lime": (170, 220, 70), "maroon": (110, 30, 40), "gold": (210, 170, 50), "silver": (190, 195, 205),
}


def slug_of(name):
    m = re.search(r"#\d+\s+(.*)$", name)
    s = (m.group(1) if m else name).lower()
    s = re.sub(r"\(.*?\)", lambda x: x.group(0)[1:-1], s)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


# --- colour maths: OKLab -------------------------------------------------------------
def srgb_to_lin(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    c = np.clip(np.asarray(c, float), 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929], [0.2119034982, 0.6806995451, 0.1073969566],
               [0.0883024619, 0.2817188376, 0.6299787005]])
M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468], [1.9779984951, -2.4285922050, 0.4505937099],
               [0.0259040371, 0.7827717662, -0.8086757660]])


def lin_to_lab(c):
    return np.cbrt(np.asarray(c, float) @ M1.T) @ M2.T


def lab_to_lin(l):
    return (np.asarray(l, float) @ np.linalg.inv(M2).T) ** 3 @ np.linalg.inv(M1).T


def hexc(lab):
    return "#" + "".join(f"{int(round(v * 255)):02x}" for v in lin_to_srgb(lab_to_lin(lab)))


def kmeans(x, w, k, iters=40, seed=1):
    rng = np.random.default_rng(seed)
    c = [x[rng.choice(len(x), p=w / w.sum())]]
    for _ in range(1, k):                                   # k-means++ starts
        d = np.min([((x - ci) ** 2).sum(1) for ci in c], axis=0) * w
        c.append(x[rng.choice(len(x), p=d / d.sum())])
    c = np.array(c)
    for _ in range(iters):
        lab = np.argmin(((x[:, None] - c[None]) ** 2).sum(2), 1)
        new = np.array([np.average(x[lab == i], 0, w[lab == i]) if (lab == i).any() else c[i] for i in range(k)])
        if np.allclose(new, c):
            break
        c = new
    return c, lab


def palette(samples):
    """parts from the texture colours on the model: clusters in OKLab (lightness counts less, so
    light and shade of one colour stay one part), merged while too close; each part gets 5 shades
    spread over its own lightness range plus a step beyond each end for the shade bands"""
    mats = [s[0] for s in samples]
    lin = srgb_to_lin(np.array([s[1:4] for s in samples])); w = np.array([s[4] for s in samples]) + 1e-9
    lab = lin_to_lab(lin)
    feat = lab * np.array([0.45, 1.0, 1.0])
    k = 8
    while True:
        c, lab_i = kmeans(feat, w, k)
        share = np.array([w[lab_i == i].sum() for i in range(k)]) / w.sum()
        d = np.sqrt(((c[:, None] - c[None]) ** 2).sum(2)) + np.eye(k) * 9
        i, j = np.unravel_index(np.argmin(d), d.shape)
        tiny = share.argmin()
        if k > 2 and (d[i, j] < 0.06 or share[tiny] < 0.006):
            k -= 1
            continue
        break
    parts, used = {}, {}
    order = np.argsort([-share[i] for i in range(k)])
    for i in order:
        m = lab_i == i
        L = lab[m, 0]; ww = w[m]
        srt = np.argsort(L); cw = np.cumsum(ww[srt]) / ww.sum()
        pct = lambda p: L[srt][np.searchsorted(cw, p).clip(0, len(L) - 1)]
        ab = np.average(lab[m, 1:], 0, ww)
        Ls = [pct(0.1) - 0.07, pct(0.1), pct(0.5), pct(0.9), pct(0.9) + 0.06]
        Ls = sorted(min(max(v, 0.08), 0.98) for v in Ls)
        for a in range(1, 5):                              # at least 0.035 between neighbours
            Ls[a] = max(Ls[a], Ls[a - 1] + 0.035)
        shades = [hexc([min(v, 0.99), ab[0] * (0.85 if v < 0.25 else 1), ab[1] * (0.85 if v < 0.25 else 1)]) for v in Ls]
        mean = np.average(lab[m], 0, ww) * np.array([0.6, 1, 1])
        name = min(NAMES, key=lambda n: ((lin_to_lab(srgb_to_lin(np.array(NAMES[n]) / 255)) * np.array([0.6, 1, 1]) - mean) ** 2).sum())
        used[name] = used.get(name, 0) + 1
        if used[name] > 1:
            name = f"{name}{used[name]}"
        parts[name] = {"shades": shades, "albedo": hexc(np.average(lab[m], 0, ww)), "share": float(share[i]),
                       "lab": np.average(lab[m], 0, ww), "idx": int(i)}
    # materials -> the parts they actually use (>= 4% of the material's area)
    by_mat = {}
    names_by_idx = {p["idx"]: n for n, p in parts.items()}
    for mname in set(mats):
        m = np.array([x == mname for x in mats])
        tot = w[m].sum()
        use = [names_by_idx[i] for i in range(k) if w[m & (lab_i == i)].sum() / tot >= 0.04]
        by_mat[mname] = use or [names_by_idx[int(np.bincount(lab_i[m], w[m], k).argmax())]]
    darkest = min(parts.values(), key=lambda p: p["lab"][0])["lab"]
    outline = hexc([0.17, darkest[1] * 0.3, darkest[2] * 0.3])
    return parts, by_mat, outline


def bone_tree(bones, foot_names):
    by = {b["name"]: b for b in bones}
    kids = {}
    for b in bones:
        kids.setdefault(b["parent"], []).append(b["name"])
    lines = []

    def walk(n, d):
        b = by[n]
        if n.endswith("_end") and not b["children"]:
            return
        ax = " ".join(f"{k}=({v[0]:+.2f},{v[1]:+.2f},{v[2]:+.2f})" for k, v in b["axes"].items())
        flag = "  <- foot candidate" if n in foot_names else ""
        lines.append(f"{'  ' * d}{n}  head=({b['head'][0]:.2f},{b['head'][1]:.2f},{b['head'][2]:.2f})"
                     f"  w={b['weight']:.0f}  axes {ax}{flag}")
        for c in kids.get(n, []):
            walk(c, d + 1)
    for r in kids.get(None, []):
        walk(r, 0)
    return lines


def main():
    a = sys.argv[1:]
    if not a or a[0].startswith("-") or a[0] in ("-h", "--help"):
        print(__doc__); sys.exit(0 if a and a[0] in ("-h", "--help") else 1)
    src = Path(a[0]).expanduser()
    slug = a[a.index("--slug") + 1] if "--slug" in a else slug_of(src.stem)
    height = int(a[a.index("--height") + 1]) if "--height" in a else 200
    base = ROOT / "models" / slug
    stem = slug.replace("-", "_")
    cfg_path = base / f"{stem}_front.json"
    if cfg_path.exists() and "--force" not in a:
        print(f"{cfg_path} exists already (--force to redo the prep; it overwrites the config)"); sys.exit(1)
    folder = base / "".join(w.capitalize() for w in slug.split("-"))
    folder.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() == ".zip":
        with zipfile.ZipFile(src) as z:
            for m in z.infolist():                    # flatten: the rips nest one folder deep at most
                if m.is_dir() or m.filename.startswith("__MACOSX"):
                    continue
                target = folder / Path(m.filename).name
                with z.open(m) as fsrc, open(target, "wb") as fdst:
                    shutil.copyfileobj(fsrc, fdst)
    elif src.is_dir():
        for f in src.rglob("*"):
            if f.is_file():
                shutil.copy2(f, folder / f.name)
    files = sorted(folder.iterdir())
    pick = lambda ext: [f for f in files if f.suffix.lower() == ext and "_rare" not in f.stem]
    model = (pick(".fbx") or pick(".glb") or pick(".gltf") or [None])[0]
    if model is None and pick(".dae"):
        dae = pick(".dae")[0]
        model = dae.with_suffix(".glb")
        r = subprocess.run(["assimp", "export", str(dae), str(model)], capture_output=True, text=True)
        if r.returncode:
            print(f"UNUSABLE: assimp couldn't convert {dae.name}: {r.stderr[-400:]}"); sys.exit(2)
    if model is None:
        print(f"UNUSABLE: no .fbx/.glb/.dae in {src.name}"); sys.exit(2)
    blend = folder / f"{folder.name}.blend"
    prep = base / "prep"
    code = blender.run(["-b", "--python-exit-code", "1", "--python", str(HERE / "prep_model.py"), "--", str(model), str(blend), str(prep)], 600)
    if code or not (prep / "scene.json").exists():
        print(f"UNUSABLE: Blender couldn't import {model.name} (exit {code})"); sys.exit(2)
    info = json.loads((prep / "scene.json").read_text())
    if not info["bones"]:
        print("UNUSABLE: no armature: nothing to pose"); sys.exit(2)
    if not info["samples_linear_rgb"]:
        print("UNUSABLE: no texture colours found (textures missing?)"); sys.exit(2)

    parts, by_mat, outline = palette(info["samples_linear_rgb"])
    lo, hi = np.array(info["bbox"]["min"]), np.array(info["bbox"]["max"])
    centre = (lo + hi) / 2
    size = float(max(hi - lo))
    # 3/4 front from the model's left (a front sprite looks screen-left); models face -Y
    cfg = {
        "name": slug.replace("-", " ").title(),
        "model": str(blend.relative_to(base)),
        "palette": {"outline": outline, "parts": {n: p["shades"] for n, p in parts.items()}},
        "parts": {"materials": {m: "|".join(ps) for m, ps in by_mat.items()} if len(by_mat) > 1 else {},
                  "default_material": max(info["materials"], key=lambda m: info["materials"][m]["area"]),
                  "albedo": {n: p["albedo"] for n, p in parts.items()}},
        "camera": {"azimuth": "AZIMUTH", "elevation": "ELEVATION", "target": [round(float(v), 3) for v in centre],
                   "distance": round(size * 6, 2), "ortho_scale": round(size * 1.35, 3), "perspective_fov": "FOV"},
        "render": {"width": 1600, "height": 1600, "hull": {"thickness_px": 0.95, "cap_each_frame": True}},
        "pose_params": {"AZIMUTH": 70, "ELEVATION": 12, "FOV": 30},
        "pose": [],
        "motion": {"frames": 120, "note": "TODO: the idle (new-sprite skill)"},
        "style": {"height": height, "frame_ms": 30, "frame_anchor": "first", "despeckle": 2},
    }
    if len(by_mat) > 1:
        cfg["parts"]["materials"].pop(cfg["parts"]["default_material"], None)
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")

    # --- RIG.md: everything the posing step needs, compact ---------------------------
    bones = info["bones"]
    by = {b["name"]: b for b in bones}
    zmin, h = lo[2], hi[2] - lo[2]
    feet = [b["name"] for b in bones
            if b["head"][2] - zmin < 0.12 * h and b["parent"] and by[b["parent"]]["parent"]
            and not b["name"].endswith("_end") and b["weight"] > 0
            and not (b["parent"] and by[b["parent"]]["head"][2] - zmin < 0.12 * h and by[b["parent"]]["weight"] > 0)]
    lines = [f"# {cfg['name']}: rig and prep", "",
             f"Source: {info['source']} -> `{blend.relative_to(ROOT)}`. Config draft: `{cfg_path.relative_to(ROOT)}`.",
             f"Size (bind pose): {hi[0]-lo[0]:.2f} x {hi[1]-lo[1]:.2f} x {h:.2f} (x, y, z); ground z = {zmin:.3f}.",
             "Facing: assumed -Y (camera AZIMUTH 90 = straight front). Check `prep/rest_front.png` shows the face.",
             f"Actions in the file: {', '.join(info['actions']) or 'none'}.", ""]
    if info["warnings"]:
        lines += ["## Warnings", ""] + [f"- {w}" for w in info["warnings"]] + [""]
    lines += ["## Palette (draft, from the texture colours on the model)", "",
              "| part | share | shades (dark -> light) | materials |", "|---|---|---|---|"]
    for n, p in parts.items():
        ms = ", ".join(m for m, ps in by_mat.items() if n in ps)
        lines.append(f"| {n} | {p['share']*100:.0f}% | {' '.join(p['shades'])} | {ms} |")
    lines += ["", "Merge or rename parts if two are really one colour; a part the shiny changes and one it",
              "doesn't must not share shades.", "",
              "## Foot candidates for motion.plant", "",
              ", ".join(f"`{f}`" for f in feet) or "none found (floating / no legs?)", "",
              "## Bones", "",
              "Each line: head position, mesh weight it drives (0 = a helper), and its own axes in world",
              "space at rest. Bend a limb about one of its own axes: `[\"bone\", \"A:x,y,z\", \"deg\"]`.",
              "World X/Y/Z only for the whole body.", "", "```"]
    lines += bone_tree(bones, set(feet)) + ["```", ""]
    (base / "RIG.md").write_text("\n".join(lines))
    print(f"prepared {base.relative_to(ROOT)}: {len(bones)} bones, {len(parts)} parts, foot candidates {feet}")
    print(f"  config  {cfg_path.relative_to(ROOT)}\n  rig     {(base / 'RIG.md').relative_to(ROOT)}\n  views   {prep.relative_to(ROOT)}/rest_*.png")


def scene_main():
    """Blender side (prep_model.py runs this file in Blender): import the model, save it as a .blend with
    relative texture paths, and describe it for the config (rig, materials, texture colours, size) plus
    rest-pose views. Args after --: MODEL.fbx|.glb OUT.blend OUT_DIR. Writes OUT_DIR/scene.json and
    OUT_DIR/rest_{front,side,top}.png."""
    import bpy, sys, json, math, os, random
    import numpy as np
    from pathlib import Path
    from mathutils import Vector

    src, out_blend, out_dir = sys.argv[sys.argv.index("--") + 1:][:3]
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    ext = Path(src).suffix.lower()
    if ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=src)
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=src)
    else:
        raise SystemExit(f"can't import {ext}")
    bpy.ops.wm.save_as_mainfile(filepath=out_blend)
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=out_blend)

    scene = bpy.context.scene
    arms = [o for o in scene.objects if o.type == "ARMATURE"]
    meshes = [o for o in scene.objects if o.type == "MESH" and not o.name.startswith("Icosphere")]
    arm = arms[0] if arms else None
    info = {"source": Path(src).name, "warnings": []}
    if len(arms) != 1:
        info["warnings"].append(f"{len(arms)} armatures (the pipeline expects exactly one)")

    # --- size (rest pose, deformed meshes) ----------------------------------------
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in meshes:
        e = o.evaluated_get(dg); me = e.to_mesh()
        pts += [o.matrix_world @ v.co for v in me.vertices]
        e.to_mesh_clear()
    lo = Vector([min(p[i] for p in pts) for i in range(3)]); hi = Vector([max(p[i] for p in pts) for i in range(3)])
    info["bbox"] = {"min": [round(v, 4) for v in lo], "max": [round(v, 4) for v in hi]}

    # --- rig ----------------------------------------------------------------------
    weight = {}
    for o in meshes:
        names = {vg.index: vg.name for vg in o.vertex_groups}
        for v in o.data.vertices:
            for ge in v.groups:
                n = names.get(ge.group)
                if n:
                    weight[n] = weight.get(n, 0) + ge.weight
    bones = []
    if arm:
        mw = arm.matrix_world
        for b in arm.data.bones:
            m = (mw @ b.matrix_local).to_3x3().normalized()
            bones.append({"name": b.name, "parent": b.parent.name if b.parent else None,
                          "head": [round(c, 3) for c in mw @ b.head_local],
                          "tail": [round(c, 3) for c in mw @ b.tail_local],
                          "children": [c.name for c in b.children],
                          "weight": round(weight.get(b.name, 0), 1),
                          # the bone's own axes in world space at rest: bend axes for "A:x,y,z" pose entries
                          "axes": {k: [round(c, 3) for c in m.col[i]] for i, k in enumerate("xyz")}})
    info["bones"] = bones
    info["actions"] = [a.name for a in bpy.data.actions]

    # --- materials, textures, colour samples ---------------------------------------
    def base_image(mat):
        """the albedo image of a material: the image feeding Base Color, else one named like an albedo"""
        if not mat or not mat.node_tree:
            return None
        nodes = mat.node_tree.nodes
        for n in nodes:
            if n.type == "BSDF_PRINCIPLED":
                stack = [l.from_node for l in n.inputs["Base Color"].links]
                seen = set()
                while stack:
                    x = stack.pop()
                    if x in seen:
                        continue
                    seen.add(x)
                    if x.type == "TEX_IMAGE" and x.image:
                        return x.image
                    stack += [l.from_node for i in x.inputs for l in i.links]
        imgs = [n.image for n in nodes if n.type == "TEX_IMAGE" and n.image]
        for key in ("alb", "col", "diff", "base"):
            for im in imgs:
                if key in im.name.lower():
                    return im
        return imgs[0] if imgs else None

    pix_cache = {}
    def pixels(img):
        if img.name not in pix_cache:
            if not img.has_data:
                try:
                    img.reload()
                except Exception:
                    pass
            w, h = img.size
            if w == 0:
                pix_cache[img.name] = None
            else:
                a = np.empty(w * h * 4, dtype=np.float32); img.pixels.foreach_get(a)
                pix_cache[img.name] = a.reshape(h, w, 4)
        return pix_cache[img.name]

    mats, samples = {}, []
    rng = random.Random(1)
    for o in meshes:
        e = o.evaluated_get(dg); me = e.to_mesh()
        me.calc_loop_triangles()
        uv = me.uv_layers.active.data if me.uv_layers.active else None
        for t in me.loop_triangles:
            mat = o.material_slots[t.material_index].material if o.material_slots else None
            mname = mat.name if mat else "(none)"
            img = base_image(mat)
            d = mats.setdefault(mname, {"image": img.filepath if img else None, "image_name": img.name if img else None,
                                        "area": 0.0, "missing": False})
            a = t.area
            d["area"] += a
            if img is None or uv is None:
                continue
            px = pixels(img)
            if px is None:
                d["missing"] = True
                continue
            h, w = px.shape[:2]
            # a few points per triangle, more on big ones
            n = 1 + int(a * 400)
            for _ in range(min(n, 6)):
                r1, r2 = rng.random(), rng.random()
                if r1 + r2 > 1:
                    r1, r2 = 1 - r1, 1 - r2
                u = uv[t.loops[0]].uv * (1 - r1 - r2) + uv[t.loops[1]].uv * r1 + uv[t.loops[2]].uv * r2
                x, y = int((u.x % 1) * w) % w, int((u.y % 1) * h) % h
                c = px[y, x]
                if c[3] > 0.5:
                    samples.append([mname, round(float(c[0]), 4), round(float(c[1]), 4), round(float(c[2]), 4), round(a / n, 6)])
        e.to_mesh_clear()
    for m, d in mats.items():
        if d["image"] and not d["missing"] and d["image_name"] and not bpy.data.images[d["image_name"]].has_data:
            d["missing"] = True
        if d["missing"]:
            info["warnings"].append(f"material {m}: texture {d['image']} missing or unreadable")
    info["materials"] = mats
    if len(samples) > 40000:
        samples = rng.sample(samples, 40000)
    info["samples_linear_rgb"] = samples             # [material, r, g, b, area weight]; 8-bit textures: sRGB-encoded

    # --- rest views (Workbench, a few seconds) -------------------------------------
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "TEXTURE"
    scene.render.film_transparent = False
    scene.world = scene.world or bpy.data.worlds.new("W"); scene.world.color = (0.55, 0.55, 0.55)
    scene.view_settings.view_transform = "Standard"
    scene.render.resolution_x = scene.render.resolution_y = 420
    for o in scene.objects:
        if o.name.startswith("Icosphere"):
            o.hide_render = True
    cd = bpy.data.cameras.new("C"); cd.type = "ORTHO"; cam = bpy.data.objects.new("C", cd)
    scene.collection.objects.link(cam); scene.camera = cam
    centre = (lo + hi) / 2; size = max(hi - lo) * 1.15
    cd.ortho_scale = size; cd.clip_end = size * 20
    for name, az, el in (("front", 90, 5), ("side", 0, 5), ("top", 90, 85)):
        a, e = math.radians(az), math.radians(el)
        d = Vector((math.cos(a) * math.cos(e), -math.sin(a) * math.cos(e), math.sin(e)))
        cam.location = centre + d * size * 5
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = str(out_dir / f"rest_{name}.png")
        bpy.ops.render.render(write_still=True)

    (out_dir / "scene.json").write_text(json.dumps(info))
    print("PREP_SCENE_OK")


if __name__ == "__main__":
    if IN_BLENDER:
        scene_main()
    else:
        main()
