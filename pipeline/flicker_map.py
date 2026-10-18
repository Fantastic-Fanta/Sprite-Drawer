"""Flicker as the eye sees it: changes between frames that motion doesn't explain.

Run:  python3 flicker_map.py SPRITE.gif [--block 6] [--heatmap out.png] [--json out.json]

For every frame and every block x block tile, find the shift (dx, dy in -1..1) that best maps
the tile onto the next frame. Pixels that still differ after that best shift are "unexplained":
the picture changed, not just moved (a highlight band vanishing, a line flipping between single
and double, a corner changing shape). Moving content is explained by the shift and not counted.
Each change is weighted by its brightness jump: that's what the eye notices (a near-black line
swapping with a near-white highlight is far more visible than one lavender shade stepping to the next).

Prints the unexplained-change rate (per solid pixel per frame), the worst tiles, and with
--heatmap marks where it happens on frame 0 (redder = more). Used as a gate in make_gif.py:
the config's qa.max_unexplained / qa.max_tile_unexplained are the limits.
"""
import json
import sys

import numpy as np
from PIL import Image, ImageSequence, ImageDraw


def keys(path):
    from check_loop import gif_frames
    fr = gif_frames(path)          # one per display tick (merged duplicate frames expanded)
    K = np.stack([np.where(a[..., 3] > 0, (a[..., 0].astype(np.int64) << 16) | (a[..., 1].astype(np.int64) << 8) | a[..., 2], -1)
                  for a in fr])
    return fr, K


def luma(K):
    """0..1 brightness per pixel; transparent counts as the mid-grey background"""
    r, g, b = (K >> 16) & 255, (K >> 8) & 255, K & 255
    return np.where(K == -1, 0.5, (0.3 * r + 0.59 * g + 0.11 * b) / 255)


def unexplained(K, block=6, contrast=True):
    """per pixel: unexplained change summed over the loop; with contrast=True each change
    is weighted by its brightness jump (dark line <-> white highlight = ~0.7, shade step = ~0.05)"""
    n, H, W = K.shape
    P = np.pad(K, ((0, 0), (1, 1), (1, 1)), constant_values=-1)
    Y = luma(K); PY = np.pad(Y, ((0, 0), (1, 1), (1, 1)), constant_values=0.5)
    total = np.zeros((H, W))
    for i in range(n):
        a, b = K[i], P[(i + 1) % n]
        best = None
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                diff = (a != b[1 + dy:1 + dy + H, 1 + dx:1 + dx + W]).astype(float)
                if contrast:
                    diff *= np.abs(Y[i] - PY[(i + 1) % n][1 + dy:1 + dy + H, 1 + dx:1 + dx + W])
                # per-tile differing count for this shift
                t = diff[:H // block * block, :W // block * block].reshape(H // block, block, W // block, block).sum((1, 3))
                best = t if best is None else np.minimum(best, t)
        # spread the tile's residual evenly over its pixels for the heat map
        total[:H // block * block, :W // block * block] += np.kron(best, np.ones((block, block))) / (block * block)
    return total


def pops(K, block=6):
    """Per frame step: the biggest connected patch of unexplained change, weighted by brightness
    jump. A whole highlight band or line appearing at once (a "pop") is far more noticeable than
    the same amount of change scattered as single pixels. Returns per-step max pop weights and
    the pixel mask of the biggest pop for each step."""
    n, H, W = K.shape
    P = np.pad(K, ((0, 0), (1, 1), (1, 1)), constant_values=-1)
    Y = luma(K); PY = np.pad(Y, ((0, 0), (1, 1), (1, 1)), constant_values=0.5)
    out, masks = [], []
    for i in range(n):
        j = (i + 1) % n
        best_w = np.full((H // block, W // block), np.inf)
        resid = np.zeros((H, W))
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                w = (K[i] != P[j][1 + dy:1 + dy + H, 1 + dx:1 + dx + W]) * np.abs(Y[i] - PY[j][1 + dy:1 + dy + H, 1 + dx:1 + dx + W])
                t = w[:H // block * block, :W // block * block].reshape(H // block, block, W // block, block).sum((1, 3))
                better = t < best_w
                best_w = np.where(better, t, best_w)
                up = np.kron(better, np.ones((block, block), bool))
                region = resid[:H // block * block, :W // block * block]
                region[up] = w[:H // block * block, :W // block * block][up]
        m = resid > 0.15                              # visible change (bigger than a shade step)
        seen = np.zeros_like(m); best, best_mask = 0.0, None
        for y0, x0 in zip(*np.nonzero(m)):
            if seen[y0, x0]:
                continue
            st, comp = [(y0, x0)], []
            seen[y0, x0] = True
            while st:
                y, x = st.pop(); comp.append((y, x))
                for yy in (y - 1, y, y + 1):
                    for xx in (x - 1, x, x + 1):
                        if 0 <= yy < H and 0 <= xx < W and m[yy, xx] and not seen[yy, xx]:
                            seen[yy, xx] = True; st.append((yy, xx))
            wsum = sum(resid[y, x] for y, x in comp)
            if wsum > best:
                best, best_mask = wsum, comp
        out.append(best); masks.append(best_mask or [])
    return np.array(out), masks


def report(path, block=6, contrast=True):
    fr, K = keys(path)
    n = len(fr)
    U = unexplained(K, block, contrast)
    solid = (K != -1).sum()
    rate = U.sum() / solid
    tiles = U[:U.shape[0] // block * block, :U.shape[1] // block * block].reshape(
        U.shape[0] // block, block, U.shape[1] // block, block).sum((1, 3)) / n
    return fr, U, rate, float(tiles.max()), tiles


if __name__ == "__main__":
    args = sys.argv[1:]
    block = int(args[args.index("--block") + 1]) if "--block" in args else 6
    plain = report(args[0], block, contrast=False)
    print(f"unexplained change (count): {plain[2]:.4f} per solid px per frame; worst tile {plain[3]:.2f} px/frame")
    fr, U, rate, worst, tiles = report(args[0], block)
    order = np.dstack(np.unravel_index(np.argsort(-tiles, axis=None), tiles.shape))[0][:5]
    print(f"VISIBLE flicker (contrast-weighted): {rate:.4f} per solid px per frame; worst {block}x{block} tile {worst:.3f}")
    print("  worst tiles (y, x of top-left, px/frame):", [(int(y * block), int(x * block), round(float(tiles[y, x]), 2)) for y, x in order])
    _, K = keys(args[0])
    pw, pm = pops(K, block)
    big_pops = int((pw >= 2.0).sum())
    print(f"POPS (biggest coherent visible change per frame step): max {pw.max():.2f}, mean {pw.mean():.2f}, "
          f"steps with a pop >= 2.0: {big_pops} of {len(pw)}; worst step {int(np.argmax(pw))} -> {int(np.argmax(pw)) + 1}")
    if "--json" in args:
        json.dump({"rate": rate, "worst_tile": worst, "pop_max": float(pw.max()), "pop_mean": float(pw.mean()),
                   "big_pops": big_pops}, open(args[args.index("--json") + 1], "w"))
    if "--pops" in args:                           # picture of the worst pop: before | after | where
        i = int(np.argmax(pw)); j = (i + 1) % len(pw); S = 6
        fr_all = fr
        tiles = []
        for a in (fr_all[i], fr_all[j]):
            big = Image.fromarray(a).resize((a.shape[1] * S, a.shape[0] * S), Image.Resampling.NEAREST)
            bg = Image.new("RGBA", big.size, (122, 170, 153, 255)); bg.alpha_composite(big); tiles.append(bg)
        d = ImageDraw.Draw(tiles[1])
        for y, x in pm[i]:
            d.rectangle([x * S, y * S, x * S + S - 1, y * S + S - 1], outline=(255, 0, 200, 255), width=2)
        sheet = Image.new("RGBA", (tiles[0].width * 2 + 20, tiles[0].height), (60, 60, 60, 255))
        sheet.paste(tiles[0], (0, 0)); sheet.paste(tiles[1], (tiles[0].width + 20, 0))
        sheet.save(args[args.index("--pops") + 1])
    if "--heatmap" in args:
        a = fr[0]; S = 6
        big = Image.fromarray(a).resize((a.shape[1] * S, a.shape[0] * S), Image.Resampling.NEAREST)
        bg = Image.new("RGBA", big.size, (122, 170, 153, 255)); bg.alpha_composite(big)
        d = ImageDraw.Draw(bg)
        m = U.max() or 1
        for y, x in np.argwhere(U > 0.5):
            t = min(1.0, U[y, x] / m)
            d.rectangle([x * S, y * S, x * S + S - 1, y * S + S - 1], outline=(255, int(220 * (1 - t)), 0, 255), width=2)
        bg.save(args[args.index("--heatmap") + 1])
