"""Quality gate: every check, against the limits in CONFIG.json "qa", PASS / FAIL.

Run:  python3 qa.py CONFIG.json SPRITE.gif [--json report.json]
make_gif.py runs this automatically after every build (and can retry with remedies: --auto).

Checks (what each catches, and where the limit comes from):
  style_score      overall match of frame 0 to the Showdown frame       (compare.py)
  extra_line_px    our inner lines with no Showdown line within 2 px     (compare.py: "line spam")
  missing_line_px  Showdown inner lines we don't have within 2 px        (compare.py)
  thick_lines      2x2 blocks of line colour (outline + dark line colours), all frames (user rule: 0)
  diag_2px         2-px diagonals / lines hugging the outline, same colours (check_loop.py, user rule: 0)
  open_outline     body touching the outside, or an outlined part touching another part directly
                   ("colour leakage"), all frames                        (check_loop.py: 0)
  silhouette_teeth 1-px spurs + dents in the silhouette, mean per frame (check_loop.py; Showdown: 4)
  shadow_f1        where each part's darkest fill shade sits vs Showdown (F1 within 1 px)  (compare.py)
  dark_rim_excess  share of those darks hugging the outline, minus Showdown's (a rim, not a shadow)
  blob_shade_err   how dark each separate piece (petal, flipper) is vs Showdown's same piece   (compare.py)
  <part>_edge_ratio how much of a part is drawn as edges (outline / inner lines), ours / Showdown's;
                   a flat blob scores low (qa.structure_parts, compare.py)
  <part>_shape_f1  does our part sit where Showdown's does, same footprint (F1 within 1 px)
  <part>_tones     shades of a part actually in use (each >= 1 % of it): a full ramp, not a few flat bands
  blink_rate, dark_flicker_rate, pop_max_norm, big_pops_share: the same, normalised per frame and
                   sprite pixel (pops by sqrt(px / 1000)), for limits calibrated on a Showdown sprite
                   with the same kind of motion (floating: Carbink; see SPRITE_PIPELINE.md)
  dark_flicker     dark pixels on/off for 1-2 frames                     (check_loop.py)
  any_blinks       any colour lasting 1-2 frames                         (check_loop.py)
  (style.fast_frames - intentional fast motion such as a spin - is left out of blinks, flicker and
   pops, which it breaks by design; every per-frame rule still applies to those frames)
  pop_max          biggest coherent visible change in one frame step     (flicker_map.py; Showdown's own GIF: 3.8)
  big_pops         frame steps with a pop >= 2                           (flicker_map.py; Showdown: 22 of 89)
  tone_mix_l1      brightness mix over the loop (5 luma bands) vs qa.tone_ref, the same Pokemon's
                   Showdown sprite (for a Mega with no sprite: the base form's, same view / shiny):
                   muddy mid-greys where Showdown has light fills and dark lines (check_loop.tone_bands)
  shade_slivers    interior fill pixels with <= 1 same-colour neighbour: shading broken into 1-px
                   streaks / flecks by render detail (our limit 0.15: builds judged dirty scored
                   0.26-0.29, clean ones 0.06-0.09; Showdown's hand-drawn detail scores higher but
                   follows the forms, which a render can't)
  blotch_share     share of pixels in small islands (<= 12 px, corner-touching pixels joined)
                   enclosed by one other colour (14 Showdown sprites: 0.001-0.0135, median 0.0052)
  <part>_mix_l1    colour mix inside a part's area vs Showdown's (lines, shades and highlights
                   included): catches wrong structure inside a part (compare.py, qa.region_parts)
"""
import json
import sys

import numpy as np
from pathlib import Path

import check_loop
import compare
import flicker_map

CHECKS = [  # name, direction ("max" = must be <=, "min" = must be >=)
    ("style_score", "min"), ("extra_line_px", "max"), ("missing_line_px", "max"),
    ("thick_lines", "max"), ("diag_2px", "max"), ("dark_flicker", "max"), ("any_blinks", "max"),
    ("pop_max", "max"), ("big_pops", "max"), ("shell_mix_l1", "max"), ("open_outline", "max"),
    ("blink_rate", "max"), ("dark_flicker_rate", "max"), ("pop_max_norm", "max"), ("big_pops_share", "max"),
    ("silhouette_teeth", "max"), ("shadow_f1", "min"), ("dark_rim_excess", "max"), ("blob_shade_err", "max"),
    ("tone_mix_l1", "max"), ("shade_slivers", "max"), ("blotch_share", "max"),
]


def run(cfg_path, gif):
    cfg_path = Path(cfg_path)
    cfg = json.loads(cfg_path.read_text())
    # no style reference (e.g. a back view: Showdown has no Mega back sprite): the checks that
    # compare with a reference are skipped; every per-frame and motion rule still applies
    if cfg.get("reference"):
        ref = compare.load(cfg_path.parent / cfg["reference"])
        c = compare.score(cfg, ref, compare.load(gif, 0))
    else:
        c = {}
    lm = check_loop.loop_metrics(cfg, gif)
    fr_, K = flicker_map.keys(gif)
    if cfg["style"].get("pixel_bob"):                # the float is a known whole-sprite shift: undo it
        st = check_loop.unbob(cfg, fr_)
        K = np.stack([np.where(a[..., 3] > 0, (a[..., 0].astype(np.int64) << 16) | (a[..., 1].astype(np.int64) << 8) | a[..., 2], -1) for a in st])
    pw, _ = flicker_map.pops(K)
    # steps into, during or out of intentional fast motion (style.fast_frames) are not pops
    fast = {i for a, b in cfg["style"].get("fast_frames", []) for i in range(a, b + 1)}
    if fast:
        n = len(pw)
        pw = np.array([v for i, v in enumerate(pw) if i not in fast and (i + 1) % n not in fast])
    values = {**({"style_score": c["style_score"], "extra_line_px": c["extra_line_px"], "missing_line_px": c["missing_line_px"],
                  "shadow_f1": c["shadow_f1"], "dark_rim_excess": c["dark_rim_excess"], "blob_shade_err": c["blob_shade_err"]} if c else {}),
              "thick_lines": lm["thick_lines"], "diag_2px": lm["diag_2px"], "dark_flicker": lm["dark_flicker"],
              "open_outline": lm["open_outline"], "silhouette_teeth": lm["silhouette_teeth"],
              "any_blinks": lm["any_blinks"], "pop_max": round(float(pw.max()), 2), "big_pops": int((pw >= 2.0).sum()),
              # normalised to sprite size / loop length (calibrated on a Showdown sprite with the same
              # kind of motion, e.g. Carbink for floaters): a pop's weight grows with the sprite's
              # linear size, so pop_max is divided by sqrt(solid px / 1000)
              "blink_rate": lm["blink_rate"], "dark_flicker_rate": lm["dark_flicker_rate"],
              "pop_max_norm": round(float(pw.max()) / (lm["solid_px"] / 1000) ** 0.5, 2),
              "big_pops_share": round(float((pw >= 2.0).mean()), 3)}
    limits0 = cfg.get("qa", {})
    if any(k in limits0 for k in ("tone_mix_l1", "shade_slivers", "blotch_share")):
        sample = fr_[::4]                                    # every 4th frame is plenty for these
        if "tone_ref" in limits0:
            ref_b = np.array(limits0["tone_ref"]["bands"], float)
            values["tone_mix_l1"] = round(float(np.abs(check_loop.tone_bands(sample) - ref_b).sum()), 3)
        import sprite_style
        lc = sprite_style.dark_line_colours(cfg)
        values["shade_slivers"] = round(float(np.mean([check_loop.shade_slivers(a, lc) for a in sample])), 3)
        bl = [check_loop.blotches(a) for a in sample]
        values["blotch_share"] = round(sum(b[0] for b in bl) / max(sum(int((a[..., 3] > 0).sum()) for a in sample), 1), 4)
    for part, m in c.get("region_mix", {}).items():          # per-part colour mix (e.g. shell_mix_l1)
        values[f"{part}_mix_l1"] = m["l1"]
    limits = cfg.get("qa", {})
    results = []
    for part, v in c.get("edge_ratio", {}).items():          # per-part structure (e.g. core_edge_ratio)
        values[f"{part}_edge_ratio"] = v
    for part, v in c.get("shape_f1", {}).items():            # per-part footprint (e.g. core_shape_f1)
        values[f"{part}_shape_f1"] = v
    for part, v in c.get("tone_count", {}).items():          # per-part shades in use (e.g. core_tones)
        values[f"{part}_tones"] = v["ours"]
    checks = CHECKS + [(k, "max") for k in limits if k.endswith("_mix_l1") and (k, "max") not in CHECKS] \
        + [(k, "min") for k in limits if k.endswith("_edge_ratio") or k.endswith("_shape_f1") or k.endswith("_tones")]
    for name, way in checks:
        if name not in limits or name not in values:
            continue
        v, lim = values[name], limits[name]
        ok = v <= lim if way == "max" else v >= lim
        results.append((name, v, lim, way, ok))
    return values, results


def report(results):
    for name, v, lim, way, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:16s} {v:>8}   ({'<=' if way == 'max' else '>='} {lim})")
    fails = [r for r in results if not r[4]]
    print(f"QA: {'PASS' if not fails else 'FAIL (' + ', '.join(r[0] for r in fails) + ')'}")
    return not fails


if __name__ == "__main__":
    values, results = run(sys.argv[1], sys.argv[2])
    ok = report(results)
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps({"values": values, "pass": ok}, indent=2))
    sys.exit(0 if ok else 1)
