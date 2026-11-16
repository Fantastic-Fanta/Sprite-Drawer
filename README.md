# Sprite-Drawer

## Requirements

- Blender (scripts expect `/Applications/Blender.app`)
- Python 3 with `numpy` and `Pillow`
- Your own models (and, for fitting the camera, Showdown reference frames): they aren't included in this repo

## Usage

The scripts are in [`pipeline/`](pipeline). Each Pokémon folder holds its config JSON (palette, pose, camera, style).

```bash
python3 pipeline/build_all.py out/ golisopod-model/golisopod_front.json mega-zygarde-za/zygarde_front.json --scale 4
```

`build_all.py` renders and builds each sprite, and makes its shiny if a `_shiny.json` sits next to it.
Sprites are flat palette colours with cel bands and lines from an inverted hull, so the 3D model decides where every line goes.
For one sprite step by step, and the full process, see [`SPRITE_PIPELINE.md`](pipeline/SPRITE_PIPELINE.md).

Fan project, not affiliated with Nintendo, Game Freak or The Pokémon Company.
