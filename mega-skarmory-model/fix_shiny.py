"""Hand fix for the shiny palette: make_shiny scales each linear channel by its texture ratio, and the
normal yellow has a zero blue channel, so the silver shiny came out olive-yellow. Recompute the
ramps with make_shiny's own keep_steps() from the shiny texture colours measured per part."""
import json, sys
from pathlib import Path
import numpy as np
root = Path("/Users/manta/SpriteDrawer")
src = (root / "pipeline/make_shiny.py").read_text().split("KEEP_STEPS =")[0]
sys.argv = ["x", str(root / "mega-skarmory-model/mega_skarmory_front.json"), "/dev/null"]
g = {"__name__": "x"}; exec(src, g)
cfg = json.loads((root / "mega-skarmory-model/mega_skarmory_front.json").read_text())
target = {"yellow": "#bdbbae", "navy": "#645e47", "blade": "#3aa83a"}
for name in ("front", "back"):
    p = root / f"mega-skarmory-model/mega_skarmory_{name}_shiny.json"
    s = json.loads(p.read_text())
    for k, t in target.items():
        ramp = g["keep_steps"](cfg["palette"]["parts"][k], g["hexrgb"](cfg["parts"]["albedo"][k]), g["hexrgb"](t))
        print(name, k, s["palette"]["parts"][k], "->", ramp)
        s["palette"]["parts"][k] = ramp
        s["parts"]["albedo"][k] = t
    s["shiny_note"] = (s.get("shiny_note", "") + " Hand fix (mega-skarmory-model/fix_shiny.py, run after package.py): yellow -> silver "
                       "#bdbbae and navy -> olive #645e47 from the _rare_ textures via keep_steps(); blades -> green, muted "
                       "from the texture's #04c400 to #3aa83a.")
    p.write_text(json.dumps(s, indent=2) + "\n")
