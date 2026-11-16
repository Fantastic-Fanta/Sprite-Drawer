"""python3 new.py MODEL.zip|DIR [ANIM.zip|.fbx|.glb] [--slug NAME] [--height 200] [--force]
Model (+ the game's animation pack, same rig) -> models/SLUG/SLUG_front.json and out/SLUG/ GIFs, no hand work:
palette from the textures, the game idle that stays most in place, camera on the left front. Review the GIFs,
tweak the config if needed (build.py SLUG rebuilds), then build.py --publish SLUG."""
import json
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
NAMES = {"red": (200, 40, 40), "orange": (230, 130, 40), "yellow": (230, 210, 60), "green": (70, 160, 60),
         "teal": (40, 160, 160), "blue": (50, 90, 200), "navy": (30, 40, 90), "purple": (130, 70, 170),
         "pink": (230, 140, 190), "brown": (120, 80, 50), "tan": (200, 170, 120), "white": (240, 240, 240),
         "gray": (128, 128, 128), "black": (25, 25, 25), "cream": (240, 230, 190), "sky": (150, 200, 235),
         "lime": (170, 220, 70), "maroon": (110, 30, 40), "gold": (210, 170, 50), "silver": (190, 195, 205)}
M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929], [0.2119034982, 0.6806995451, 0.1073969566],
               [0.0883024619, 0.2817188376, 0.6299787005]])
M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468], [1.9779984951, -2.4285922050, 0.4505937099],
               [0.0259040371, 0.7827717662, -0.8086757660]])
to_lin = lambda c: np.where(np.asarray(c, float) <= 0.04045, np.asarray(c, float) / 12.92, ((np.asarray(c, float) + 0.055) / 1.055) ** 2.4)
to_lab = lambda c: np.cbrt(np.asarray(c, float) @ M1.T) @ M2.T          # linear sRGB -> OKLab


def hexc(lab):
    c = np.clip((np.asarray(lab, float) @ np.linalg.inv(M2).T) ** 3 @ np.linalg.inv(M1).T, 0, 1)
    return "#" + "".join(f"{int(round(v * 255)):02x}" for v in np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055))


def kmeans(x, w, k, iters=40):
    rng = np.random.default_rng(1)
    c = [x[rng.choice(len(x), p=w / w.sum())]]
    for _ in range(1, k):                        # k-means++ starts
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
    """parts = OKLab clusters of the texture colours on the model (lightness weighs less), merged while too
    close or too small; 5 shades each over its own lightness range; materials -> the parts they use"""
    mats = [s[0] for s in samples]
    w = np.array([s[4] for s in samples]) + 1e-9
    lab = to_lab(to_lin(np.array([s[1:4] for s in samples])))
    feat, k = lab * np.array([0.45, 1.0, 1.0]), 8
    while True:
        c, lab_i = kmeans(feat, w, k)
        share = np.array([w[lab_i == i].sum() for i in range(k)]) / w.sum()
        d = np.sqrt(((c[:, None] - c[None]) ** 2).sum(2)) + np.eye(k) * 9
        if k > 2 and (d.min() < 0.06 or share.min() < 0.006):
            k -= 1
            continue
        break
    parts, used = {}, {}
    for i in np.argsort(-share):
        m = lab_i == i
        L, ww = lab[m, 0], w[m]
        srt = np.argsort(L); cw = np.cumsum(ww[srt]) / ww.sum()
        pct = lambda p: L[srt][np.searchsorted(cw, p).clip(0, len(L) - 1)]
        ab = np.average(lab[m, 1:], 0, ww)
        Ls = sorted(min(max(v, 0.08), 0.98) for v in [pct(0.1) - 0.07, pct(0.1), pct(0.5), pct(0.9), pct(0.9) + 0.06])
        for a in range(1, 5):
            Ls[a] = max(Ls[a], Ls[a - 1] + 0.035)
        mean = np.average(lab[m], 0, ww)
        name = min(NAMES, key=lambda n: (((to_lab(to_lin(np.array(NAMES[n]) / 255)) - mean) * [0.6, 1, 1]) ** 2).sum())
        used[name] = used.get(name, 0) + 1
        parts[name + (str(used[name]) if used[name] > 1 else "")] = {
            "shades": [hexc([min(v, 0.99), ab[0] * (0.85 if v < 0.25 else 1), ab[1] * (0.85 if v < 0.25 else 1)]) for v in Ls],
            "albedo": hexc(mean), "lab": mean, "idx": int(i)}
    by_idx = {p["idx"]: n for n, p in parts.items()}
    by_mat = {}
    for mname in set(mats):
        m = np.array([x == mname for x in mats])
        use = [by_idx[i] for i in range(k) if w[m & (lab_i == i)].sum() / w[m].sum() >= 0.04]
        by_mat[mname] = use or [by_idx[int(np.bincount(lab_i[m], w[m], k).argmax())]]
    dark = min(parts.values(), key=lambda p: p["lab"][0])["lab"]
    return parts, by_mat, hexc([0.17, dark[1] * 0.3, dark[2] * 0.3])


def unpack(src, dest):
    """a zip (flattened) or folder into dest; returns the model file in it (.fbx / .glb / .gltf, or .dae via assimp)"""
    dest.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() == ".zip":
        with zipfile.ZipFile(src) as z:
            for m in z.infolist():
                if not m.is_dir() and not m.filename.startswith("__MACOSX"):
                    with z.open(m) as a, open(dest / Path(m.filename).name, "wb") as b:
                        shutil.copyfileobj(a, b)
    elif src.is_dir():
        for f in src.rglob("*"):
            if f.is_file():
                shutil.copy2(f, dest / f.name)
    else:
        return src
    pick = lambda ext: sorted(f for f in dest.iterdir() if f.suffix.lower() == ext and "_rare" not in f.stem)
    found = pick(".fbx") or pick(".glb") or pick(".gltf")
    if not found and pick(".dae"):
        glb = pick(".dae")[0].with_suffix(".glb")
        subprocess.run(["assimp", "export", str(pick(".dae")[0]), str(glb)], check=True, capture_output=True)
        found = [glb]
    if not found:
        sys.exit(f"UNUSABLE: no .fbx/.glb/.dae in {src.name}")
    return found[0]


def main():
    a = sys.argv[1:]
    if not a or a[0].startswith("-"):
        sys.exit(__doc__)
    opt = lambda k, d: a[a.index(k) + 1] if k in a else d
    src = Path(a[0]).expanduser()
    anim = Path(a[1]).expanduser() if len(a) > 1 and not a[1].startswith("-") else None
    m = re.search(r"#\d+\s+(.*)$", src.stem)
    slug = opt("--slug", re.sub(r"[^a-z0-9]+", "-", re.sub(r"[()]", "", (m.group(1) if m else src.stem).lower())).strip("-"))
    base, stem = ROOT / "models" / slug, slug.replace("-", "_")
    cfg_path = base / f"{stem}_front.json"
    if cfg_path.exists() and "--force" not in a:
        sys.exit(f"{cfg_path} exists (--force overwrites it)")
    folder = base / "".join(w.capitalize() for w in slug.split("-"))
    model = unpack(src, folder)
    pack = unpack(anim, base / "pack") if anim else None
    blend, info_path = folder / f"{folder.name}.blend", base / "scene.json"
    sys.path.insert(0, str(HERE))
    import blender
    code = blender.run(["-b", "--python-exit-code", "1", "--python", __file__, "--", str(model), str(blend), str(info_path)]
                       + ([str(pack)] if pack else []), 900)
    if code or not info_path.exists():
        sys.exit(f"UNUSABLE: Blender couldn't import {model.name} (exit {code})")
    info = json.loads(info_path.read_text())
    info_path.unlink()
    for w in info["warnings"]:
        print("WARNING:", w)
    if not info["samples"]:
        sys.exit("UNUSABLE: no texture colours found (textures missing?)")
    parts, by_mat, outline = palette(info["samples"])
    lo, hi = np.array(info["bbox"][0]), np.array(info["bbox"][1])
    size = float(max(hi - lo))
    default = max(info["materials"], key=info["materials"].get)
    clip = info.get("clip")
    cfg = {"name": slug.replace("-", " ").title(), "model": str(blend.relative_to(base)),
           "palette": {"outline": outline, "parts": {n: p["shades"] for n, p in parts.items()}},
           "parts": {"materials": {m: "|".join(ps) for m, ps in by_mat.items() if m != default} if len(by_mat) > 1 else {},
                     "default_material": default, "albedo": {n: p["albedo"] for n, p in parts.items()}},
           "camera": {"azimuth": "AZIMUTH", "elevation": "ELEVATION", "target": [round(float(v), 3) for v in (lo + hi) / 2],
                      "distance": round(size * 6, 2), "ortho_scale": round(size * 1.35, 3), "perspective_fov": "FOV"},
           "render": {"width": 1600, "height": 1600, "hull": {"thickness_px": 0.95, "cap_each_frame": True}},
           "pose_params": {"AZIMUTH": 70, "ELEVATION": 12, "FOV": 30},
           # the game plays its idles at 30 fps; frame_ms 30 keeps that speed
           "motion": {"frames": max(1, round(clip[1] * 1000 / 30 / 30)), "clip": clip[0]} if clip else {"frames": 1},
           "style": {"height": int(opt("--height", 200)), "frame_ms": 30, "frame_anchor": "first", "despeckle": 2}}
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")
    print(f"{cfg_path.relative_to(ROOT)}: {len(parts)} parts, idle {clip[0] if clip else 'none (static)'}")
    import build
    sys.exit(1 if build.build([slug]) else 0)


def scene_main():
    """inside Blender: import the model (and pack), keep the chosen idle, save the .blend, describe it"""
    import random
    from mathutils import Matrix, Vector
    src, out_blend, info_path, *pack = sys.argv[sys.argv.index("--") + 1:]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    imp = lambda f: bpy.ops.import_scene.fbx(filepath=f) if f.lower().endswith(".fbx") else bpy.ops.import_scene.gltf(filepath=f)
    imp(src)
    scene, info = bpy.context.scene, {"warnings": []}
    arms = [o for o in scene.objects if o.type == "ARMATURE"]
    if len(arms) != 1:
        sys.exit(f"{len(arms)} armatures: the pipeline needs exactly one")
    arm = arms[0]
    meshes = [o for o in scene.objects if o.type == "MESH" and not o.name.startswith("Icosphere")]
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in meshes:
        e = o.evaluated_get(dg); me = e.to_mesh()
        pts += [o.matrix_world @ v.co for v in me.vertices]
        e.to_mesh_clear()
    lo, hi = [min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]
    info["bbox"] = [lo, hi]

    # the idle: the pack's (or the model's own) battlewait / wait actions; the one whose body moves least
    before = {k: set(getattr(bpy.data, k)) for k in ("objects", "actions", "meshes", "materials", "images", "armatures", "collections")}
    if pack:
        imp(pack[0])
    new = {k: [d for d in getattr(bpy.data, k) if d not in before[k]] for k in before}
    acts = [x for x in bpy.data.actions if "battlewait" in x.name] or [x for x in bpy.data.actions if "wait" in x.name]
    src_arm = next((o for o in new["objects"] if o.type == "ARMATURE"), None)

    def play(obj, act, f):
        ad = obj.animation_data or obj.animation_data_create()
        ad.action = act
        if getattr(act, "slots", None):
            ad.action_slot = act.slots[0]
        scene.frame_set(int(f), subframe=f - int(f))
        bpy.context.view_layer.update()

    def travel(act):
        s, e = act.frame_range
        cs = []
        for i in range(8):
            play(arm, act, s + (e - s) * i / 8)
            cs.append(sum((arm.matrix_world @ pb.head for pb in arm.pose.bones), Vector()) / len(arm.pose.bones))
        return max((c - cs[0]).length for c in cs)

    keep = min(acts, key=travel) if acts else None
    if keep and src_arm:                         # the pack's rig must drive ours the same way
        shared = [b.name for b in src_arm.pose.bones if b.name in arm.pose.bones]
        s, e = keep.frame_range
        gap = 0.0
        for f in (s, (s + e) / 2):
            play(src_arm, keep, f); play(arm, keep, f)
            gap = max([gap] + [((src_arm.matrix_world @ src_arm.pose.bones[b].matrix).translation
                                - (arm.matrix_world @ arm.pose.bones[b].matrix).translation).length for b in shared])
        if gap > 0.01 * max(h - l for l, h in zip(lo, hi)):
            info["warnings"].append(f"the pack's rig doesn't match the model's (bone gap {gap:.3f}): check the motion")
    for k, ds in new.items():
        for d in ds:
            if d is not keep:
                getattr(bpy.data, k).remove(d)
    for x in [x for x in bpy.data.actions if x is not keep]:
        bpy.data.actions.remove(x)
    if keep:
        keep.name = keep.name.split("|")[-1]
        keep.use_fake_user = True
        info["clip"] = [keep.name, keep.frame_range[1] - keep.frame_range[0]]
    (arm.animation_data or arm.animation_data_create()).action = None
    for pb in arm.pose.bones:                    # back to the rest pose the idle search left behind
        pb.matrix_basis = Matrix.Identity(4)
    scene.frame_set(0)
    dg = bpy.context.evaluated_depsgraph_get()
    bpy.ops.wm.save_as_mainfile(filepath=out_blend)
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=out_blend)

    # texture colour samples: a few points per triangle from each material's albedo image
    def albedo(mat):
        if not mat or not mat.node_tree:
            return None
        nodes = mat.node_tree.nodes
        for n in nodes:
            if n.type == "BSDF_PRINCIPLED":
                stack, seen = [l.from_node for l in n.inputs["Base Color"].links], set()
                while stack:
                    x = stack.pop()
                    if x in seen:
                        continue
                    seen.add(x)
                    if x.type == "TEX_IMAGE" and x.image:
                        return x.image
                    stack += [l.from_node for i in x.inputs for l in i.links]
        imgs = [n.image for n in nodes if n.type == "TEX_IMAGE" and n.image]
        return next((im for key in ("alb", "col", "diff", "base") for im in imgs if key in im.name.lower()), imgs[0] if imgs else None)

    pix, area, samples, rng = {}, {}, [], random.Random(1)
    for o in meshes:
        e = o.evaluated_get(dg); me = e.to_mesh()
        me.calc_loop_triangles()
        uv = me.uv_layers.active.data if me.uv_layers.active else None
        for t in me.loop_triangles:
            mat = o.material_slots[t.material_index].material if o.material_slots else None
            mname, img = mat.name if mat else "(none)", albedo(mat)
            area[mname] = area.get(mname, 0.0) + t.area
            if img is None or uv is None:
                continue
            if img.name not in pix:
                if not img.has_data:
                    try:
                        img.reload()
                    except Exception:
                        pass
                w, h = img.size
                a = np.empty(w * h * 4, np.float32)
                if w:
                    img.pixels.foreach_get(a)
                pix[img.name] = a.reshape(h, w, 4) if w else None
                if not w:
                    info["warnings"].append(f"texture {img.filepath} missing")
            px = pix[img.name]
            if px is None:
                continue
            h, w = px.shape[:2]
            n = 1 + int(t.area * 400)
            for _ in range(min(n, 6)):
                r1, r2 = rng.random(), rng.random()
                if r1 + r2 > 1:
                    r1, r2 = 1 - r1, 1 - r2
                u = uv[t.loops[0]].uv * (1 - r1 - r2) + uv[t.loops[1]].uv * r1 + uv[t.loops[2]].uv * r2
                c = px[int((u.y % 1) * h) % h, int((u.x % 1) * w) % w]
                if c[3] > 0.5:
                    samples.append([mname, float(c[0]), float(c[1]), float(c[2]), t.area / n])
        e.to_mesh_clear()
    info["materials"], info["samples"] = area, rng.sample(samples, 40000) if len(samples) > 40000 else samples
    Path(info_path).write_text(json.dumps(info))


if __name__ == "__main__":
    scene_main() if IN_BLENDER else main()
