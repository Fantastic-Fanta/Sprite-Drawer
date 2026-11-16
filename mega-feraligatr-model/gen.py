"""Write Mega Feraligatr's palette / parts / clip / camera into mega_feraligatr_front.json.

Run: /usr/local/bin/python3 mega-feraligatr-model/gen.py [KEY=value ...]
Keys: AZIMUTH, ELEVATION, FRAMES, FRAME_MS, CLIP. Prints every change; keeps the rest.
Ramps: the prep draft's own sky / red / cream ramps stay; the new parts (scales, mouth, white, eye)
get ramps built the way prep_model.py builds them (OKLab lightness steps around the texture colour,
taken from the draft sky ramp's steps).
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "pipeline"))
from prep_model import srgb_to_lin, lin_to_lab, hexc  # noqa: E402

CFG = HERE / "mega_feraligatr_front.json"
cfg = json.loads(CFG.read_text())
old = json.loads(json.dumps(cfg))
kv = dict(a.split("=", 1) for a in sys.argv[1:])
lab = lambda h: lin_to_lab(srgb_to_lin(np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)]) / 255))


def ramp(albedo, steps):
    a = lab(albedo)
    out = []
    for d in steps:
        L = min(max(a[0] + d, 0.08), 0.985)
        k = 0.85 if L < 0.25 else 1
        out.append(hexc([L, a[1] * k, a[2] * k]))
    return out


# the draft sky ramp's lightness steps around its albedo
SKY_DRAFT = ["#0f7599", "#308aaf", "#68bfe6", "#74caf1", "#7fd5fd"]
steps = [lab(h)[0] - lab("#61b7de")[0] for h in SKY_DRAFT]
parts = cfg["palette"]["parts"]
draft = {"sky": SKY_DRAFT, "red": parts.get("red") or parts.get("crest"),
         "cream": parts.get("cream") or parts.get("belly")}
new_parts = {
    "body": draft["sky"],                        # blue hide (shiny: teal)
    "crest": draft["red"],                       # the red jaw-crest, back fins and arm fins (shiny: blue-violet)
    "scales": ramp("#56839a", steps),            # slate spikes / plates on body_b (same in the shiny)
    "belly": draft["cream"],                     # cream belly V and jaw (same in the shiny)
    "mouth": ramp("#b8767b", [steps[0], steps[1], 0.0]) + ramp("#ecb4b0", [0.0, steps[4]]),  # tongue + gums
    "white": ramp("#e4e4e4", [steps[0], steps[1], 0.0, steps[3], steps[4]]),               # teeth, claws
    "eye": ["#3a2208"] + ramp("#fcbd3f", [steps[1], 0.0, steps[3], steps[4]]),             # gold eye, dark pupil
}
cfg["palette"]["parts"] = new_parts
cfg["parts"] = {
    "materials": {"_eye": "eye|white", "body_a": "body|belly|mouth|white|scales", "body_b": "crest|scales"},
    "default_material": "default",
    "albedo": {"body": "#61bee7", "crest": "#c84d5f", "scales": "#56839a", "belly": "#e1cb97",
               "mouth": "#ecb4b0", "white": "#e4e4e4", "eye": "#fcbd3f"},
}
cfg["model"] = "MegaFeraligatr/MegaFeraligatr_idle.blend"
clip = kv.get("CLIP", cfg.get("motion", {}).get("clip", "pm0160_51_00_10001_battlewait01_loop"))
cfg["motion"] = {"frames": int(kv.get("FRAMES", cfg["motion"].get("frames", 54) if "clip" in cfg["motion"] else 54)),
                 "clip": clip, "note": cfg["motion"].get("note", "")}
cfg["style"]["frame_ms"] = int(kv.get("FRAME_MS", cfg["style"]["frame_ms"] if "clip" in old["motion"] else 40))
cfg["style"]["height"] = 200
cfg["render"].setdefault("hull", {})["cap_each_frame"] = True
for k in ("AZIMUTH", "ELEVATION"):
    if k in kv:
        cfg["pose_params"][k] = float(kv[k])
for k in ("NOTE",):
    if k in kv:
        cfg["motion"]["note"] = kv[k]


def diff(a, b, p=""):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            diff(a.get(k), b.get(k), f"{p}.{k}")
    elif a != b:
        print(f"{p}: {json.dumps(a)} -> {json.dumps(b)}")


diff(old, cfg)
CFG.write_text(json.dumps(cfg, indent=2) + "\n")
