"""python3 regress.py [POKEMON ...]: rebuild (renders cached unless the render code changed) and compare every
GIF with sprites/<pokemon>/, pixel for pixel. Exit 1 if any differs. The pre-push hook runs it."""
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageSequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build                                     # noqa: E402

TESTS = ["mega-glimmora", "mega-golisopod", "mega-dragalge", "mega-zygarde", "mega-raichu-x"]
frames = lambda p: [np.array(f.convert("RGBA")) for f in ImageSequence.Iterator(Image.open(p))]

if __name__ == "__main__":
    bad = 0
    for name in sys.argv[1:] or TESTS:
        out = build.OUT / "regress" / name
        shutil.rmtree(out, ignore_errors=True)
        build.build([name], out)
        for g in sorted((build.SPRITES / name).glob("*.gif")):
            n = out / g.name
            a, b = frames(g), frames(n) if n.exists() else []
            same = len(a) == len(b) and all(x.shape == y.shape and (x == y).all() for x, y in zip(a, b))
            bad += not same
            print(f"{g.name}: {'IDENTICAL' if same else 'DIFFERS'}")
    shutil.rmtree(build.OUT / "regress", ignore_errors=True)
    sys.exit(1 if bad else 0)
