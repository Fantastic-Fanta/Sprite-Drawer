"""python3 gpu/compare_passes.py BLENDER_FRAMES GPU_FRAMES [N]: per-pass differences on N frames"""
import sys
from pathlib import Path
import numpy as np
from PIL import Image

a_dir, b_dir = Path(sys.argv[1]), Path(sys.argv[2])
frames = range(1, 161, 160 // int(sys.argv[3]) if len(sys.argv) > 3 else 40)
ld = lambda d, k, f: np.array(Image.open(d / f"{k}_{f:04d}.tga").convert("RGBA")).astype(int)
for f in frames:
    A, B = {k: ld(a_dir, k, f) for k in ("color", "id", "data", "hull")}, {k: ld(b_dir, k, f) for k in ("color", "id", "data", "hull")}
    ca, cb = A["color"][..., 3] > 127, B["color"][..., 3] > 127
    both = ca & cb
    box = lambda m: Image.fromarray((m * 255).astype(np.uint8)).getbbox()
    rgb = np.abs(A["color"][..., :3] - B["color"][..., :3]).max(-1)[both]
    ida, idb = A["id"][..., 3] > 127, B["id"][..., 3] > 127
    idsame = (A["id"][..., :3] == B["id"][..., :3]).all(-1)
    dn = np.abs(A["data"][..., :2] - B["data"][..., :2]).max(-1)[ida & idb]
    ha, hb = A["hull"][..., 3] > 127, B["hull"][..., 3] > 127
    print(f"frame {f}: color opaque px {ca.sum()} vs {cb.sum()} (xor {(ca ^ cb).sum()}), bbox>8 {box(A['color'][..., 3] > 8)} vs {box(B['color'][..., 3] > 8)}\n"
          f"  color |d| on both: median {np.median(rgb):.0f} p99 {np.percentile(rgb, 99):.0f}; id cover xor {(ida ^ idb).sum()}, id colour differs {(~idsame & ida & idb).sum()}\n"
          f"  normal |d| (0-255): median {np.median(dn):.0f} p99 {np.percentile(dn, 99):.0f}; hull px {ha.sum()} vs {hb.sum()} xor {(ha ^ hb).sum()}")
    if f == 1:
        print("  id colours blender", np.unique(A["id"][ida][:, :3], axis=0)[:8].tolist(), "gpu", np.unique(B["id"][idb][:, :3], axis=0)[:8].tolist())
