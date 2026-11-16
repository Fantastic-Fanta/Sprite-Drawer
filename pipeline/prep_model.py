"""Model zip (or folder) -> a ready-to-pose sprite folder: no LLM needed for any of it.

Run:  python3 pipeline/prep_model.py MODEL.zip|DIR [--slug mega-greninja] [--height 200] [--force]
Makes models/SLUG/ in the repo:
  models/SLUG/<Model>/       the unzipped rip and its .blend (gitignored)
  models/SLUG/prep/          rest_front/side/top.png (Workbench views of the bind pose), scene.json
  models/SLUG/RIG.md         what the posing step needs: size, facing, bone tree with each bone's own
                             axes (for "A:x,y,z" bends), foot candidates for motion.plant, materials -> parts
  models/SLUG/SLUG_front.json the draft config: palette and parts from the texture colours actually
                             on the model, camera framed to its size, style.height, hull 0.95,
                             despeckle 2, a 120-frame loop; pose empty (the bind pose), motion to write
Then: pose and animate it (the new-sprite skill), then package.py builds back, shinies and GIFs.
Slug: from the zip name ("... #0658 Mega Greninja.zip" -> mega-greninja). Exit code 2 = the model
can't be used as it is (no armature, no importable file, missing textures): see the message.
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import blender_slot  # noqa: E402

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
    code = blender_slot.run(["-b", "--python-exit-code", "1", "--python", str(HERE / "prep_scene.py"), "--", str(model), str(blend), str(prep)], 600)
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
        "reference": None,
        "reference_source": "prep_model.py draft: set the pose from HOME / official art (reference/)",
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


if __name__ == "__main__":
    main()
