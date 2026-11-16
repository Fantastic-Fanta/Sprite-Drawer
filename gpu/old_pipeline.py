"""python3 gpu/old_pipeline.py CONFIG.json OUT: the current route (RenderPool, no cache) timed, then the sprite step"""
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from build import load
from blender import RenderPool
import sprite_style as ss

if __name__ == "__main__":
    cfg, out = load(Path(sys.argv[1]).resolve()), Path(sys.argv[2]).resolve()
    t = time.time()
    with RenderPool() as pool:
        pool.render(cfg, out / "frames", cache=False)
    t_render = time.time() - t
    t = time.time()
    sprites, _ = ss.sprites(cfg, out / "frames")
    t_sprite = time.time() - t
    ss.save_gif(cfg, sprites, out / "old_front.gif")
    print(json.dumps({"render": t_render, "sprite": t_sprite, "gif": time.time() - t - t_sprite}))
