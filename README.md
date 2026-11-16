# Sprite-Drawer

Animated pixel sprites from 3D Pokémon models: flat palette colours, cel bands, and lines from an
inverted hull, so the 3D model decides where every line goes.

```
sprites/<pokemon>/   finished GIFs: <name>_front, _back, _front_shiny, _back_shiny, each with a _4x copy
models/<pokemon>/    the configs (palette, pose, motion, camera); the ripped model sits here locally
pipeline/            the scripts (see pipeline/SPRITE_PIPELINE.md)
```

## Requirements

- Blender at `/Applications/Blender.app`
- Python 3 with `numpy` and `Pillow`
- The models themselves: they aren't in this repo

## Build

```bash
python3 pipeline/build.py                         # every Pokémon
python3 pipeline/build.py mega-absol-z            # one (its models/ folder name)
python3 pipeline/build.py --publish mega-absol-z  # copy the reviewed GIFs from out/ into sprites/
```

`build.py` renders and builds the front and back, their shinies and the 4x copies into
`out/<pokemon>/`. Renders are cached, so rebuilding after a style change skips Blender.

## Tests

```bash
python3 pipeline/regress.py        # rebuild the test sprites and compare every pixel (~20 s)
python3 pipeline/regress.py full   # also re-render them in Blender (~3 min)
```

A pre-push hook (`.githooks/`) runs the first whenever a push changes `pipeline/`. Turn it on in a
fresh clone with `git config core.hooksPath .githooks`.

Fan project, not affiliated with Nintendo, Game Freak or The Pokémon Company.
