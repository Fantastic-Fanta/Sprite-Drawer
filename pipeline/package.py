"""Finished front config -> everything delivered for review, no LLM needed:
back config, both shiny configs, the build, a contact sheet, the motion check, a report skeleton.

Run:  python3 pipeline/package.py FRONT.json [--out out/POKEMON] [--back-elevation 15] [--no-build]
  NAME_back.json         the front config with the camera turned round: azimuth + 180, elevation
                         --back-elevation (default: the front's, at least 10: looking down on the
                         back, never up from below); pose, motion, palette, style unchanged
  NAME_front_shiny.json  make_shiny.py --keep-steps (palette from the model's _rare_ textures)
  NAME_back_shiny.json   the back config with the front shiny's colours
  OUT/                   NAME_front/back(_shiny)(_4x).gif via build.py, sheet.png (8 frames of
                         each GIF), check.txt (check_motion.py on the front), report.md (filled
                         where it can be; the motion idea and the rule-by-rule review are left to write),
                         with a spike scan (frames whose outline pixels jump: a hull spike, or a dark
                         body tilting - look at the frame)
Re-running replaces the back and shiny configs: edit the front config, not them. A finished report.md
(no TODO left) is kept: the rebuild's numbers are added at its end.
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = sys.executable


def run(args, log):
    t = time.time()
    r = subprocess.run([PY] + [str(a) for a in args], capture_output=True, text=True)
    log.append((Path(str(args[0])).name, time.time() - t, r.returncode))
    if r.returncode:
        print(r.stdout[-2000:], r.stderr[-2000:])
        raise SystemExit(f"{Path(str(args[0])).name} failed")
    return r.stdout


def spike_frames(out, stem):
    """frames whose near-black pixel count jumps above the loop's median: a hull spike (a long black
    strand or wedge) in that frame. A dark body that tilts can also trip it: look at the frame."""
    import numpy as np
    from PIL import Image, ImageSequence
    lines = []
    for v in ("front", "back"):
        g = out / f"{stem}_{v}.gif"
        if not g.exists():
            continue
        c = []
        for f in ImageSequence.Iterator(Image.open(g)):
            a = np.asarray(f.convert("RGBA"))
            c.append(int(((a[..., 3] > 0) & (a[..., :3].max(-1) < 40)).sum()))
        c = np.array(c)
        med = float(np.median(c))
        bad = [(i, int(x - med)) for i, x in enumerate(c) if x - med > max(12, 0.04 * med)]
        if bad:
            lines.append(f"- SPIKE? {v}: {len(bad)} frames with extra outline pixels, worst "
                         + ", ".join(f"f{i} +{d}" for i, d in sorted(bad, key=lambda b: -b[1])[:4]))
    return lines


def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__); sys.exit(0 if a and a[0] in ("-h", "--help") else 1)
    front = Path(a[0]).resolve()
    stem = re.sub(r"_front$", "", front.stem)
    out = Path(a[a.index("--out") + 1]) if "--out" in a else ROOT / "out" / front.parent.name
    out = out.resolve(); out.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(front.read_text())
    log, t0 = [], time.time()

    # back: same everything, camera turned round and looking down
    back = json.loads(front.read_text())
    pp = back["pose_params"]
    el = float(a[a.index("--back-elevation") + 1]) if "--back-elevation" in a else max(float(pp.get("ELEVATION", 12)), 10)
    pp["AZIMUTH"] = round((float(pp["AZIMUTH"]) + 180) % 360, 3)
    pp["ELEVATION"] = el
    back["name"] = cfg["name"] + " (back)"
    back["reference_source"] = (f"package.py: the front config ({front.name}) with the camera turned round "
                                f"(azimuth + 180) and looking down from {el:g} deg")
    for k in [k for k in back if k.startswith("fit")]:
        back.pop(k)
    back_path = front.with_name(f"{stem}_back.json")
    back_path.write_text(json.dumps(back, indent=2) + "\n")

    # shinies
    fshiny = front.with_name(f"{stem}_front_shiny.json")
    run([HERE / "make_shiny.py", front, fshiny, "--keep-steps"], log)
    fs = json.loads(fshiny.read_text())
    bshiny = json.loads(back_path.read_text())
    bshiny["palette"], bshiny["parts"] = fs["palette"], fs["parts"]
    bshiny["render"]["texture_swap"] = fs["render"].get("texture_swap", {})
    bshiny["name"] = fs.get("name", cfg["name"]) + " (back)"
    if "shiny_note" in fs:
        bshiny["shiny_note"] = fs["shiny_note"]
    front.with_name(f"{stem}_back_shiny.json").write_text(json.dumps(bshiny, indent=2) + "\n")

    if "--no-build" in a:
        print(f"configs written; no build"); return
    run([HERE / "build.py", front, back_path, "--out", out], log)
    check = run([HERE / "check_motion.py", front], log)
    (out / "check.txt").write_text(check)

    # contact sheet: 8 frames of each 1x GIF, at sprite size (it is read by a model: keep it small)
    from PIL import Image, ImageSequence
    rows = []
    for v in ("front", "front_shiny", "back", "back_shiny"):
        g = out / f"{stem}_{v}.gif"
        if not g.exists():
            continue
        frames = [f.convert("RGBA") for f in ImageSequence.Iterator(Image.open(g))]
        pick = [frames[round(i * len(frames) / 8)] for i in range(8)]
        rows.append(pick)
    if rows:
        w, h = max(f.width for r in rows for f in r), max(f.height for r in rows for f in r)
        sheet = Image.new("RGBA", (w * 8, h * len(rows)), (200, 200, 200, 255))
        for y, r in enumerate(rows):
            for x, f in enumerate(r):
                sheet.alpha_composite(f, (x * w, y * h))
        sheet.save(out / "sheet.png")
    if (out / "frames").is_dir() and not any((out / "frames").iterdir()):
        (out / "frames").rmdir()

    flags = [l.strip() for l in check.splitlines()[1:] if l.startswith("  ") and l.strip().split()[0].isupper()]
    spikes = spike_frames(out, stem)
    took = f"{time.time() - t0:.0f}s (" + ", ".join(f"{n} {s:.0f}s" for n, s, _ in log) + ")"
    old = (out / "report.md").read_text() if (out / "report.md").exists() else ""
    if old and "TODO" not in old:
        # a finished report: keep it, add this build's numbers at the end
        add = ["", f"## Rebuild {time.strftime('%Y-%m-%d %H:%M')}", "",
               f"style.height {cfg['style']['height']}, package.py {took}.", "",
               "Check (check_motion.py, front):", ""] + ([f"- {f}" for f in flags] or ["- all rules pass"]) + \
              ["", "Spike scan:", ""] + (spikes or ["- no frame with a jump in outline pixels"]) + [""]
        (out / "report.md").write_text(old.rstrip("\n") + "\n" + "\n".join(add))
        print(f"packaged {stem} -> {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out} in {time.time() - t0:.0f}s"
              " (report.md kept, rebuild section added)")
        return
    rpt = [f"# {cfg['name']}", "",
           f"Configs: `{front.relative_to(ROOT)}` (+ `_back`, `_front_shiny`, `_back_shiny`). GIFs and `sheet.png` here.", "",
           "## Motion idea", "", cfg.get("motion", {}).get("note", "TODO"), "",
           "## Check (check_motion.py, front)", ""] + ([f"- {f}" for f in flags] or ["- all rules pass"]) + [
           "", "Full numbers: `check.txt`.", "",
           "## Spike scan (outline pixels per frame)", ""] + (spikes or ["- no frame with a jump in outline pixels"]) + [
           "",
           "## Naturalness review", "",
           "TODO, one line each: one driver with follow-through; weight; grounded/floating; nothing frozen; subtle; clean loop.", "",
           "## Doubts and decisions", "", "TODO", "",
           "## Time", "", f"- package.py: {took}",
           "- TODO: prep, pose, motion (minutes each)", ""]
    (out / "report.md").write_text("\n".join(rpt))
    print(f"packaged {stem} -> {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
