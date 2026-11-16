"""scratch copy for check_motion: whole float in the pose, no pixel_bob (check_motion ignores it)"""
import json; from pathlib import Path
d = Path(__file__).parent; c = json.loads((d/"mega_chandelure_front.json").read_text())
for p in c["pose"]:
    if p[0] == "origin" and p[1] == "LOCCAM": p[2] = "PX_U*FY(t)"
    if p[0] == "origin" and p[1] == "LOCCAMX": p[2] = "PX_U*FX(t)"
c["style"].pop("pixel_bob", None)
(d/"_check.json").write_text(json.dumps(c, indent=1))
