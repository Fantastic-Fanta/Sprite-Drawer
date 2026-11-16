"""python3 gpu/compare_gifs.py A.gif B.gif: per-frame differing pixels (RGBA) between two sprite GIFs"""
import sys
import numpy as np
from PIL import Image, ImageSequence


def frames(p):
    return [np.array(f.convert("RGBA")) for f in ImageSequence.Iterator(Image.open(p))]


def diff(a, b):
    A, B = frames(a), frames(b)
    if A[0].shape != B[0].shape:
        return {"size": (A[0].shape, B[0].shape)}
    d = [int(((x[..., 3] > 0) != (y[..., 3] > 0)).sum() + ((x[..., 3] > 0) & (y[..., 3] > 0) & (x[..., :3] != y[..., :3]).any(-1)).sum())
         for x, y in zip(A, B)]
    opaque = np.mean([(x[..., 3] > 0).sum() for x in A])
    return {"size": A[0].shape[:2], "frames": len(A), "identical_frames": sum(v == 0 for v in d), "mean_diff_px": float(np.mean(d)),
            "max_diff_px": max(d), "mean_opaque_px": float(opaque), "per_frame": d}


if __name__ == "__main__":
    r = diff(sys.argv[1], sys.argv[2])
    print({k: v for k, v in r.items() if k != "per_frame"})
