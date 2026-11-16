"""Check a pose / motion against the idle rules, in numbers, without a sprite build.

Run:  python3 pipeline/check_motion.py CONFIG.json [--samples 32] [--no-clip] [--json OUT.json]
Every number is in sprite pixels (style.height scale at frame 0). Prints a short report, flags first:
  FROZEN    a part (bone chain driving mesh) that moves < 0.4 px over the whole loop
  BIG       a part that moves over 12% of the sprite's height (an idle, not an action; fine if
            meant). Ends of long chains (claw tips, hair) add up their joints' motion and move most
  JITTER    frame-to-frame motion that changes direction or speed sharply (> 0.25 px of
            acceleration in one frame): reads as shaking
  SEAM      the jump from the last frame back to the first is > 2x the loop's normal step
  FEET      a planted foot (motion.plant) that slides or lifts > 0.5 px; with nothing planted the
            lowest bones' movement is listed, not flagged
  CLIP      mesh faces of different parts passing through each other where the camera sees it,
            sampled over the loop with the motion on (no rest-pose baseline is subtracted;
            contacts at the joint where one part grows out of another are counted apart as seams)
Exit code 0 always; read the flags. Runs Blender under a machine slot with a timeout.
"""
import json
import re
import sys
from pathlib import Path

try:
    import bpy  # noqa: F401
    IN_BLENDER = True
except ImportError:
    IN_BLENDER = False

HERE = Path(__file__).resolve().parent


def chain(name):
    """the part a bone belongs to: its name without trailing numbers (arm_01, arm_02 -> arm)"""
    return re.sub(r"(_\d+)+$", "", name)


def side_free(name):
    """a part's name for the report: mirrored parts (left_x / right_x, l_x / r_x, x_l / x_r) together"""
    return re.sub(r"(^|_)(left|right|l|r)(_|$)", lambda m: m.group(1) if m.group(3) else "", name).strip("_") or name


def blender_main():
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    from bpy_extras.object_utils import world_to_camera_view
    a = sys.argv[sys.argv.index("--") + 1:]
    cfg_path, out_json, samples, do_clip = a[0], a[1], int(a[2]), a[3] == "1"
    sys.argv = [sys.argv[0], "--", cfg_path, "/tmp/unused", "--setup-only"]
    g = {"__name__": "render_sprite", "__file__": str(HERE / "render_sprite.py")}
    exec(compile((HERE / "render_sprite.py").read_text(), str(HERE / "render_sprite.py"), "exec"), g)
    sc, arm, meshes, cfg = g["scene"], g["arm"], g["meshes"], g["cfg"]
    F = g["FRAMES"]
    g["place_camera"]()
    cam = sc.camera
    W, H = sc.render.resolution_x, sc.render.resolution_y

    # sprite px per normalised camera unit, from frame 0's height on screen
    g["pose_at"](0)
    dg = bpy.context.evaluated_depsgraph_get()
    ys = []
    for o in meshes:
        e = o.evaluated_get(dg); me = e.to_mesh()
        ys += [world_to_camera_view(sc, cam, o.matrix_world @ v.co).y for v in list(me.vertices)[::7]]
        e.to_mesh_clear()
    px = cfg["style"]["height"] / max(max(ys) - min(ys), 1e-6)

    def scr(p):
        v = world_to_camera_view(sc, cam, p)
        return Vector((v.x * W / H * px, v.y * px))

    # bones that move mesh, grouped into parts
    wt = {}
    for o in meshes:
        names = {vg.index: vg.name for vg in o.vertex_groups}
        for v in o.data.vertices:
            for ge in v.groups:
                n = names.get(ge.group)
                if n:
                    wt[n] = wt.get(n, 0) + ge.weight
    total_w = sum(wt.values()) or 1
    bones = [pb for pb in arm.pose.bones if wt.get(pb.name, 0) > total_w * 0.0005]
    mw = arm.matrix_world
    # each bone's own mesh points at rest (bind pose, armature space): the centroid of the vertices it
    # drives most and the one furthest from its head (a tip). FBX bone tails float off the mesh, so
    # they are not used. Posed: point @ (pose matrix @ rest matrix^-1).
    import mathutils
    reps = {}
    for o in meshes:
        names = {vg.index: vg.name for vg in o.vertex_groups}
        to_arm = mw.inverted() @ o.matrix_world
        for v in o.data.vertices:
            best = max(v.groups, key=lambda ge: ge.weight, default=None)
            if best is None or best.weight < 0.5:
                continue
            reps.setdefault(names.get(best.group), []).append(to_arm @ v.co)
    rest_pts = {}
    for pb in bones:
        vs = reps.get(pb.name)
        head = arm.data.bones[pb.name].head_local
        if not vs:
            rest_pts[pb.name] = [head.copy()]
            continue
        c = sum(vs, mathutils.Vector()) / len(vs)
        tip = max(vs, key=lambda v: (v - head).length)
        rest_pts[pb.name] = [c, tip]

    # every frame's bone positions (meshes hidden meanwhile: the armature alone evaluates fast)
    hidden = [o for o in meshes if not o.hide_viewport]
    for o in hidden:
        o.hide_viewport = True
    track = {pb.name: [] for pb in bones}
    lowz = {}
    plant = cfg.get("motion", {}).get("plant") or []
    for f in range(F):
        g["pose_at"](f / F)
        for pb in bones:
            m = pb.matrix @ arm.data.bones[pb.name].matrix_local.inverted()
            track[pb.name].append(tuple(scr(mw @ (m @ p)) for p in rest_pts[pb.name]))
        for pb in arm.pose.bones:
            lowz.setdefault(pb.name, []).append(mw @ pb.head)
    for o in hidden:
        o.hide_viewport = False
    # style.pixel_bob: the pose renders only the fraction of a float; the whole pixels are shifted
    # onto the finished sprite. Add them back, or every rounding flip reads as a 1 px jitter.
    for f, (dy, dx) in enumerate(g["motion"].offsets(cfg, F)):
        if dy or dx:
            d = Vector((dx, dy))
            for n in track:
                track[n][f] = tuple(p + d for p in track[n][f])

    still = set()
    for n in plant:
        if n in arm.pose.bones:
            still |= {n} | {c.name for c in arm.pose.bones[n].children_recursive}
    parts = {}
    for pb in bones:
        if pb.name in still:
            continue
        parts.setdefault(side_free(chain(pb.name)), []).append(pb.name)
    rep = {"px_per_unit_note": "all values in sprite px", "parts": {}, "flags": []}
    for part, names in sorted(parts.items()):
        travel = jitter = 0.0
        step = []; seam = 0.0
        for n in names:
            for k in range(len(track[n][0])):
                ps = [t[k] for t in track[n]]
                mean = sum(ps, Vector((0, 0))) / len(ps)
                travel = max(travel, max((p - mean).length for p in ps) * 2)
                for i in range(len(ps)):
                    acc = (ps[(i + 1) % F] - 2 * ps[i] + ps[i - 1]).length
                    jitter = max(jitter, acc)
                st = [(ps[i] - ps[i - 1]).length for i in range(1, F)]
                step.append(max(st) if st else 0)
                seam = max(seam, (ps[0] - ps[-1]).length)
        typical = max(step) if step else 0
        rep["parts"][part] = {"bones": len(names), "travel": round(travel, 2), "jitter": round(jitter, 3),
                              "seam_step": round(seam, 3), "max_step": round(typical, 3)}
        if travel < 0.4:
            rep["flags"].append(f"FROZEN {part}: moves {travel:.2f} px over the loop")
        elif travel > 0.12 * cfg["style"]["height"]:
            rep["flags"].append(f"BIG {part}: moves {travel:.1f} px (over 12% of the sprite's height: meant?)")
        if jitter > 0.25:
            rep["flags"].append(f"JITTER {part}: {jitter:.2f} px sudden change in one frame")
        if seam > max(2 * typical, 0.3):
            rep["flags"].append(f"SEAM {part}: last->first frame jump {seam:.2f} px (normal step {typical:.2f})")

    # feet
    guessed = not plant
    if not plant:
        z0 = min(p.z for ps in lowz.values() for p in ps)
        zr = max(p.z for ps in lowz.values() for p in ps) - z0
        plant = [n for n, ps in lowz.items() if ps[0].z - z0 < 0.06 * zr and wt.get(n, 0) > 0][:6]
    rep["feet"] = {}
    for n in plant:
        ps = [scr(p) for p in lowz[n]]
        mean = sum(ps, Vector((0, 0))) / len(ps)
        slide = max((p - mean).length for p in ps) * 2
        rep["feet"][n] = {"screen_move": round(slide, 2)}
        if slide > 0.5 and not guessed:          # with nothing planted (floating) the lowest bones are only shown
            rep["flags"].append(f"FEET {n}: moves {slide:.2f} px on screen (planted feet stay put)")

    # clipping: visible contacts between parts, sampled with the motion on
    if do_clip:
        vchain = {}
        for o in meshes:
            names = {vg.index: vg.name for vg in o.vertex_groups}
            vc = []
            for v in o.data.vertices:
                best = max(v.groups, key=lambda ge: ge.weight, default=None)
                vc.append(chain(names.get(best.group, "?")) if best else "?")
            vchain[o.name] = vc
        roots = []
        camp = cam.matrix_world.translation.copy()
        seam_r = 4 / px                                     # ~4 sprite px, in camera units
        tot, worst, per = {}, 0, {}
        for s in range(samples):
            g["pose_at"](s / samples)
            dg = bpy.context.evaluated_depsgraph_get()
            allv, allf, owner = [], [], []
            for o in meshes:
                e = o.evaluated_get(dg); me = e.to_mesh(); me.calc_loop_triangles()
                base = len(allv)
                allv += [o.matrix_world @ v.co for v in me.vertices]
                vc = vchain[o.name]
                for t in me.loop_triangles:
                    allf.append(tuple(base + i for i in t.vertices))
                    ch = [vc[i] for i in t.vertices]
                    owner.append(max(set(ch), key=ch.count))
                e.to_mesh_clear()
            tree = BVHTree.FromPolygons(allv, allf, all_triangles=True)
            roots = [mw @ pb.head for pb in arm.pose.bones if pb.parent and chain(pb.parent.name) != chain(pb.name)]
            cen = lambda f: (allv[f[0]] + allv[f[1]] + allv[f[2]]) / 3
            n_here = 0
            for i, j in tree.overlap(tree):
                if i >= j or set(allf[i]) & set(allf[j]) or owner[i] == owner[j]:
                    continue
                if any(x in owner[i] + owner[j] for x in ("eyelid",)):
                    continue
                pm = (cen(allf[i]) + cen(allf[j])) / 2
                dv = pm - camp; dist = dv.length
                hit = tree.ray_cast(camp, dv.normalized(), dist + 1e-3)
                if not (hit[0] is None or hit[2] in (i, j) or hit[3] > dist - 0.01):
                    continue
                sp = scr(pm)
                is_seam = any((scr(r) - sp).length < 4 for r in roots)
                k = tuple(sorted((owner[i], owner[j]))) + (("seam",) if is_seam else ())
                tot[k] = tot.get(k, 0) + 1
                per.setdefault(k, [0] * samples)[s] += 1
                if not is_seam:
                    n_here += 1
            worst = max(worst, n_here)
        rep["clip"] = {"samples": samples, "worst_sample": worst,
                       "pairs": [{"a": k[0], "b": k[1], "seam": len(k) == 3, "tris": v,
                                  "with_motion": max(per[k]) - min(per[k]) > max(per[k]) * 0.3}
                                 for k, v in sorted(tot.items(), key=lambda x: -x[1])][:15]}
        bad = [p for p in rep["clip"]["pairs"] if not p["seam"] and p["tris"] >= samples // 4]
        for p in bad[:6]:
            how = "comes and goes with the motion" if p["with_motion"] else "fixed in the pose (a modelled contact? check the preview)"
            rep["flags"].append(f"CLIP {p['a']} ~ {p['b']}: {p['tris']} visible intersecting tris over {samples} samples, {how}")
    Path(out_json).write_text(json.dumps(rep, indent=1))


def main():
    import tempfile
    sys.path.insert(0, str(HERE))
    import blender
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__); sys.exit(0 if a else 1)
    cfg = Path(a[0]).resolve()
    samples = int(a[a.index("--samples") + 1]) if "--samples" in a else 32
    model = cfg.parent / json.loads(cfg.read_text())["model"]
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(a[a.index("--json") + 1]) if "--json" in a else Path(tmp) / "check.json"
        code = blender.run(["-b", "--python-exit-code", "1", str(model), "--python", __file__, "--", str(cfg), str(out), str(samples),
                                 "0" if "--no-clip" in a else "1"], 900)
        if code or not out.exists():
            print(f"check failed (Blender exit {code})"); sys.exit(1)
        rep = json.loads(out.read_text())
    print(f"{len(rep['flags'])} flags" + (":" if rep["flags"] else " - all rules pass"))
    for f in rep["flags"]:
        print("  " + f)
    print("parts (travel px over the loop / max jitter px):")
    for p, v in sorted(rep["parts"].items(), key=lambda x: -x[1]["travel"]):
        print(f"  {p:28s} {v['travel']:5.2f}  {v['jitter']:.3f}")
    if rep.get("feet"):
        print("feet (screen move px):", ", ".join(f"{k} {v['screen_move']}" for k, v in rep["feet"].items()))
    if "clip" in rep:
        c = rep["clip"]
        print(f"clipping: worst sample {c['worst_sample']} visible tris; top pairs:")
        for p in c["pairs"][:8]:
            print(f"  {p['a']} ~ {p['b']}{' (joint seam)' if p['seam'] else ''}: {p['tris']}")


if __name__ == "__main__":
    if IN_BLENDER:
        blender_main()
    else:
        main()
