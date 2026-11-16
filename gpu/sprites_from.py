"""python3 gpu/sprites_from.py CONFIG.json FRAMES_DIR OUT.gif: the unchanged sprite step on a frames folder (timed)"""
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from build import load
import sprite_style as ss

if __name__ == "__main__":
    cfg = load(Path(sys.argv[1]).resolve())
    t = time.time()
    sprites, clipped = ss.sprites(cfg, sys.argv[2])
    t_sprite = time.time() - t
    ss.save_gif(cfg, sprites, sys.argv[3])
    print(json.dumps({"sprite": t_sprite, "gif": time.time() - t - t_sprite, "clipped": clipped}))
