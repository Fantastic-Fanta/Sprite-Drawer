"""Check a whole sprite loop for blinks and line width (importable: loop_metrics()).

Run:  python3 check_loop.py CONFIG.json SPRITE.gif [--heatmap out.png]

Per pixel position over the loop, "dark" = outline colour or a part's darkest shade.
  dark flicker   dark runs (or gaps inside dark) lasting only 1-2 frames
  any blinks     any colour (or transparency) lasting <= 2 frames at a pixel
  thick lines    2x2 blocks of outline-colour pixels (a line wider than 1 px), per frame
  2-px diagonals staircase corners not needed to close the outline, and inner line pixels
                 touching the outline at 2+ points (diagonals count): both read as 2-px lines
  open outline   body pixels touching the outside, or an outlined part (style.part_outline)
                 touching another part with no line between ("colour leakage")
"Line" = the outline colour plus style.dark_line_colours (e.g. the dark blue): one dark band of
mixed line colours is still a 2-px line. The eye stamp (positions saved by make_gif.py as
<gif>.eyes.json) is skipped exactly; without that file, compact dark blobs are skipped.
Small filled dark blobs inside the body (pupils) are not lines and are skipped.
Slower, coherent flicker (a band switching every few frames) is flicker_map.py's job.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageSequence, ImageDraw


def hexrgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def pupil_blobs(a, l):
    """compact dark groups inside the body (<= 5x5, not touching the outside): pupils"""
    solid = a[..., 3] > 0
    P = np.pad(~solid, 1, constant_values=True)
    touches_out = P[1:-1, :-2] | P[1:-1, 2:] | P[:-2, 1:-1] | P[2:, 1:-1]
    seen = np.zeros_like(l); blob = np.zeros_like(l)
    for y0, x0 in zip(*np.nonzero(l)):
        if seen[y0, x0]:
            continue
        st, comp = [(y0, x0)], []
        seen[y0, x0] = True
        while st:
            y, x = st.pop(); comp.append((y, x))
            for yy in (y - 1, y, y + 1):
                for xx in (x - 1, x, x + 1):
                    if 0 <= yy < l.shape[0] and 0 <= xx < l.shape[1] and l[yy, xx] and not seen[yy, xx]:
                        seen[yy, xx] = True; st.append((yy, xx))
        ys, xs = zip(*comp)
        if max(ys) - min(ys) < 5 and max(xs) - min(xs) < 5 and not any(touches_out[y, x] for y, x in comp):
            blob[ys, xs] = True
    return blob


def line_blocks(a, l, blobs=None):
    m = l & ~(pupil_blobs(a, l) if blobs is None else blobs)
    return int((m[:-1, :-1] & m[1:, :-1] & m[:-1, 1:] & m[1:, 1:]).sum())


def stairs(a, l, keep=None, blobs=None):
    """staircase corners + inner lines hugging the outline. keep = line pixels that must stay
    (separators between an outlined part and another part): a corner there is a T-junction,
    exempt exactly like silhouette-closing corners."""
    solid = a[..., 3] > 0
    body = solid & ~l
    P = lambda m: np.pad(m, 1)
    L, B, O = P(l), P(body), np.pad(~solid, 1, constant_values=True)
    up, dn, lf, rt = L[:-2, 1:-1], L[2:, 1:-1], L[1:-1, :-2], L[1:-1, 2:]
    ul, ur, dl, dr = L[:-2, :-2], L[:-2, 2:], L[2:, :-2], L[2:, 2:]
    tb = B[:-2, 1:-1] | B[2:, 1:-1] | B[1:-1, :-2] | B[1:-1, 2:]
    to = O[:-2, 1:-1] | O[2:, 1:-1] | O[1:-1, :-2] | O[1:-1, 2:]
    corner = l & (((up & lf) & ~dn & ~rt & ~ul) | ((up & rt) & ~dn & ~lf & ~ur)
                  | ((dn & lf) & ~up & ~rt & ~dl) | ((dn & rt) & ~up & ~lf & ~dr)) & ~(tb & to)
    if keep is not None:
        corner &= ~keep
    R = P(l & to)
    rn = sum(R[1 + dy:R.shape[0] - 1 + dy, 1 + dx:R.shape[1] - 1 + dx].astype(int)
             for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx)
    along = l & ~to & (rn >= 2)
    if keep is not None:
        along &= ~keep            # a part line meeting the outline (junction), not a band
    return int(((corner | along) & ~(pupil_blobs(a, l) if blobs is None else blobs)).sum())


def short_runs(series_stack, max_len=2):
    """per pixel: number of runs (cyclic) of length <= max_len"""
    n = series_stack.shape[0]
    out = np.zeros(series_stack.shape[1:], int)
    for y, x in np.argwhere((series_stack != series_stack[0]).any(0)):
        s = series_stack[:, y, x]
        k = int(np.argmax(s != s[-1])); t = np.roll(s, -k)
        L = 1
        for i in range(1, n + 1):
            if i < n and t[i] == t[i - 1]:
                L += 1
            else:
                out[y, x] += L <= max_len
                L = 1
    return out


def colour_ref(cfg, r):
    if r == "outline":
        return hexrgb(cfg["palette"]["outline"])
    if r.startswith("#"):
        return hexrgb(r)
    if r.startswith("line:"):
        return hexrgb(cfg["palette"]["lines"][r[5:]])
    p, i = r.split(":")
    return hexrgb(cfg["palette"]["parts"][p][int(i)])


def gif_frames(path):
    """All frames of a GIF as RGBA arrays, one per display tick: GIF writers merge identical
    consecutive frames into one longer frame, so a frame shown for 2 ticks is repeated twice
    (otherwise a pixel held for 2 frames would look like a 1-frame blink)."""
    arrs, durs = [], []
    for im in ImageSequence.Iterator(Image.open(path)):     # (the iterator re-uses one image object)
        arrs.append(np.array(im.convert("RGBA"))); durs.append(im.info.get("duration", 0) or 0)
    base = min([d for d in durs if d > 0], default=0)
    out = []
    for a, d in zip(arrs, durs):
        out += [a] * (max(1, round(d / base)) if base else 1)
    return out


def slow_t(f, n, fast):
    """frame f of n -> 0..1 loop position with style.fast_frames removed (held during them), so
    slow motions (the float) pause during a fast event. Same as render_sprite.slow_t."""
    total = sum(b - a for a, b in fast)
    lost = 0
    for a, b in sorted(fast):
        if f >= b:
            lost += b - a
        elif f > a:
            return (a - lost) / (n - total)
    return (f - lost) / (n - total)


def unbob(cfg, frames):
    """undo style.pixel_bob (a known whole-sprite shift per frame), so time-based checks see the
    sprite's own changes, not the float / drift / shake. Same offsets as sprite_style.pixel_bob."""
    if not cfg["style"].get("pixel_bob"):
        return frames
    import motion
    offs = motion.offsets(cfg, len(frames))
    # the sprite was moved up by dy and right by dx: move it back
    return [np.roll(np.roll(a, dy, axis=0), -dx, axis=1) for a, (dy, dx) in zip(frames, offs)]


def n4(m):
    Q = np.pad(m, 1)
    return Q[:-2, 1:-1] | Q[2:, 1:-1] | Q[1:-1, :-2] | Q[1:-1, 2:]


def part_masks(cfg, a, line, eye):
    """[(own, other)] per outlined part (style.part_outline): its body pixels, and every other
    part's body pixels. A part's highlight colour (borrowed from another part) counts as the
    part where it sits next to it. Shared by the check (open_outline) and the drawing step
    (sprite_style.seal_parts / clean_lines), so the two can never disagree."""
    solid = a[..., 3] > 0
    body = solid & ~line & ~eye
    key = a[..., 0].astype(int) * 65536 + a[..., 1].astype(int) * 256 + a[..., 2]
    part_of = {}
    for name, shades in cfg["palette"]["parts"].items():
        for h in shades:
            r, g, b = hexrgb(h); part_of.setdefault(r * 65536 + g * 256 + b, name)
    out = []
    for name in cfg["style"].get("part_outline", []):
        own = np.zeros_like(solid); other = np.zeros_like(solid)
        for k, pn in part_of.items():
            m = body & (key == k)
            if pn == name:
                own |= m
            else:
                other |= m
        hl = cfg["style"].get("highlight", {}).get(name)
        if hl:
            r, g, b = colour_ref(cfg, hl["colour"]); hk = r * 65536 + g * 256 + b
            near = body & (key == hk) & n4(own)
            own |= near; other &= ~near
        out.append((own, other))
    return out


def open_outline(cfg, a, line, eye):
    """Pixels where the outline doesn't close: a body pixel touching the transparent outside,
    or a pixel of an outlined part (style.part_outline, e.g. the shell) touching another part
    directly, with no line between them (the 'colour leakage' between shell and body)."""
    solid = a[..., 3] > 0
    body = solid & ~line & ~eye
    P = np.pad(~solid, 1, constant_values=True)
    to_out = body & (P[:-2, 1:-1] | P[2:, 1:-1] | P[1:-1, :-2] | P[1:-1, 2:])
    n = int(to_out.sum())
    for own, other in part_masks(cfg, a, line, eye):
        n += int((own & n4(other)).sum())
    return n


def teeth(cfg, a):
    """1-px jags in the silhouette: spurs (an outline pixel with the outside on 3+ sides) and
    dents (an outside pixel with the sprite on 3+ sides). They read as nubs on a straight edge."""
    solid = a[..., 3] > 0
    o = solid & np.all(a[..., :3] == hexrgb(cfg["palette"]["outline"]), -1)
    T = np.pad(~solid, 1, constant_values=True)
    nout = T[:-2, 1:-1].astype(int) + T[2:, 1:-1] + T[1:-1, :-2] + T[1:-1, 2:]
    return int((o & (nout >= 3)).sum() + (~solid & (nout <= 1)).sum())


def separators(cfg, a, line, eye):
    """line pixels with an outlined part on one side and another part on the other (4-nbrs)"""
    sep = np.zeros(a.shape[:2], bool)
    for own, other in part_masks(cfg, a, line, eye):
        sep |= n4(own) & n4(other)
    return sep & line


def loop_metrics(cfg, path):
    OUT = hexrgb(cfg["palette"]["outline"])
    DARK = [OUT] + [hexrgb(v[0]) for v in cfg["palette"]["parts"].values()]
    # every colour that counts as a line for the 1-px rule (same set as the drawing step)
    LINE = [OUT] + [colour_ref(cfg, r) for r in cfg["style"].get("dark_line_colours", [])]
    frames = gif_frames(path)
    eyes_file = Path(path).with_suffix(".eyes.json")
    eyes = []
    for k, a in enumerate(frames):
        m = np.zeros(a.shape[:2], bool)
        if eyes_file.exists():
            pts = json.loads(eyes_file.read_text())[k]
            if pts:
                ys, xs = zip(*pts); m[list(ys), list(xs)] = True
        eyes.append(m)
    still = unbob(cfg, frames)                       # time-based checks: float removed
    dark = np.array([(a[..., 3] > 0) & np.any([np.all(a[..., :3] == c, -1) for c in DARK], 0) for a in still])
    line = np.array([(a[..., 3] > 0) & np.any([np.all(a[..., :3] == c, -1) for c in LINE], 0) & ~e
                     for a, e in zip(frames, eyes)])
    key = np.stack([np.where(a[..., 3] > 0, a[..., 0].astype(int) * 65536 + a[..., 1].astype(int) * 256 + a[..., 2], -1)
                    for a in still])
    # intentional fast motion (style.fast_frames, e.g. a spin) changes every pixel every frame by
    # design: blink / flicker are measured on the other frames only (still every frame for the
    # per-frame rules: 1-px lines, closed outline, teeth)
    fast = {i for a, b in cfg["style"].get("fast_frames", []) for i in range(a, b + 1)}
    slow = [i for i in range(len(frames)) if i not in fast]
    dark, key = dark[slow], key[slow]
    flick = short_runs(dark.astype(int))
    # normalised versions (per frame and per sprite pixel) so sprites of any size and loop length
    # can share one calibration (e.g. Showdown's Carbink for floating Pokemon). dark = outline only
    outline_only = np.array([(a[..., 3] > 0) & np.all(a[..., :3] == OUT, -1) for a in still])[slow]
    n_slow = len(slow)
    solid_px = float(np.mean([(a[..., 3] > 0).sum() for a in frames]))
    rates = {"blink_rate": round(float(short_runs(key).sum()) / (n_slow * solid_px), 5),
             "dark_flicker_rate": round(float(short_runs(outline_only.astype(int)).sum()) / (n_slow * solid_px), 5),
             "solid_px": round(solid_px)}
    thick = [line_blocks(a, l) for a, l in zip(frames, line)]
    stair = [stairs(a, l, separators(cfg, a, l, e)) for a, l, e in zip(frames, line, eyes)]
    opened = [open_outline(cfg, a, l, e) for a, l, e in zip(frames, line, eyes)]
    return {"frames": len(frames), "dark_flicker": int(flick.sum()), "any_blinks": int(short_runs(key).sum()),
            "thick_lines": int(sum(thick)), "thick_lines_max": int(max(thick)),
            "diag_2px": int(sum(stair)), "diag_2px_max": int(max(stair)),
            "open_outline": int(sum(opened)), "open_outline_max": int(max(opened)),
            "silhouette_teeth": round(float(np.mean([teeth(cfg, a) for a in frames])), 2), **rates,
            "_flicker_map": flick, "_frames": frames}


if __name__ == "__main__":
    args = sys.argv[1:]
    cfg = json.load(open(args[0]))
    m = loop_metrics(cfg, args[1])
    print(f"{m['frames']} frames")
    print(f"flicker events (dark on/off lasting <= 2 frames): {m['dark_flicker']} total, at {int((m['_flicker_map'] > 0).sum())} pixel positions")
    print(f"thick lines (2x2 outline blocks) per frame: max {m['thick_lines_max']}, total {m['thick_lines']}")
    print(f"any-colour blinks (a colour lasting <= 2 frames at a pixel): {m['any_blinks']}")
    print(f"2-px diagonals (unneeded staircase corners + lines hugging the outline) per frame: max {m['diag_2px_max']}, total {m['diag_2px']}")
    print(f"open outline (body touching the outside, or an outlined part touching another part directly): max {m['open_outline_max']}/frame, total {m['open_outline']}")
    if "--heatmap" in args:
        a = m["_frames"][0]; S = 6; fl = m["_flicker_map"]
        big = Image.fromarray(a).resize((a.shape[1] * S, a.shape[0] * S), Image.Resampling.NEAREST)
        bg = Image.new("RGBA", big.size, (122, 170, 153, 255)); bg.alpha_composite(big)
        d = ImageDraw.Draw(bg)
        mx = fl.max() or 1
        for y, x in zip(*np.nonzero(fl)):
            t = fl[y, x] / mx
            d.rectangle([x * S, y * S, x * S + S - 1, y * S + S - 1], outline=(255, int(200 * (1 - t)), 0, 255), width=2)
        bg.save(args[args.index("--heatmap") + 1])


def blotches(a, max_size=12):
    """Small same-colour islands (<= max_size px, 8-connected) enclosed by a single other colour:
    a fleck of one shade sitting inside another flat area reads as dirt. Accent pixels and
    highlights in Showdown sprites sit against lines (2+ bordering colours), so they don't count.
    Returns (pixels in such islands, number of islands)."""
    K = np.where(a[..., 3] > 0, (a[..., 0].astype(np.int64) << 16) | (a[..., 1].astype(np.int64) << 8) | a[..., 2], -1)
    H, W = K.shape
    seen = np.zeros((H, W), bool)
    px = cnt = 0
    for y0, x0 in zip(*np.nonzero(K >= 0)):
        if seen[y0, x0]:
            continue
        c0 = K[y0, x0]
        comp, st, border = 0, [(y0, x0)], set()
        seen[y0, x0] = True
        while st:
            y, x = st.pop(); comp += 1
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if not dy and not dx:
                        continue
                    yy, xx = y + dy, x + dx
                    inb = 0 <= yy < H and 0 <= xx < W
                    if inb and K[yy, xx] == c0:            # corner-touching pixels join (a diagonal line is one piece)
                        if not seen[yy, xx]:
                            seen[yy, xx] = True; st.append((yy, xx))
                    elif not (dy and dx):                  # what encloses it: the 4-neighbours
                        border.add(int(K[yy, xx]) if inb else -1)
        if comp <= max_size and len(border) == 1 and -1 not in border:
            px += comp; cnt += 1
    return px, cnt


TONE_BANDS = [0, 0.25, 0.4, 0.55, 0.7, 1.01]


def tone_bands(frames):
    """share of the sprite's pixels in each brightness band (Rec.601 luma: <.25, .25-.4, .4-.55,
    .55-.7, >.7), over all frames. Compared with the same Pokemon's Showdown sprite (qa.tone_ref):
    muddy mid-greys where Showdown has light fills and dark lines read as dirty."""
    h = np.zeros(len(TONE_BANDS) - 1)
    for a in frames:
        s = a[..., 3] > 0
        Y = (0.3 * a[..., 0] + 0.59 * a[..., 1] + 0.11 * a[..., 2])[s] / 255
        h += np.histogram(Y, TONE_BANDS)[0]
    return h / max(h.sum(), 1)


def shade_slivers(a, line_cols=None):
    """share of interior fill pixels (not touching the outside, not a line) with at most one
    same-colour 4-neighbour: shading broken into 1-px streaks and flecks by render detail.
    Lines (1 px by design) are the given line colours (outline + style.dark_line_colours); without
    them, anything darker than luma .25 (for Showdown sprites, whose line colours we don't know)"""
    K = np.where(a[..., 3] > 0, (a[..., 0].astype(np.int64) << 16) | (a[..., 1].astype(np.int64) << 8) | a[..., 2], -1)
    Y = (0.3 * a[..., 0] + 0.59 * a[..., 1] + 0.11 * a[..., 2]) / 255
    P = np.pad(K, 1, constant_values=-1)
    nb = [P[:-2, 1:-1], P[2:, 1:-1], P[1:-1, :-2], P[1:-1, 2:]]
    if line_cols is not None:
        is_line = np.zeros(K.shape, bool)
        for c in line_cols:
            is_line |= K == ((int(c[0]) << 16) | (int(c[1]) << 8) | int(c[2]))
        interior = (K >= 0) & np.all([n >= 0 for n in nb], 0) & ~is_line
    else:
        interior = (K >= 0) & np.all([n >= 0 for n in nb], 0) & (Y >= 0.25)
    same = sum((n == K).astype(int) for n in nb)
    return float((interior & (same <= 1)).sum() / max(interior.sum(), 1))
