# Sprite-Drawer

Turns 3D Pokémon models into animated pixel sprites in the Pokémon Showdown (Gen 6) style.

![Mega Glimmora, Golisopod and Dragalge: front, shiny, back, back shiny](final_sprites/overview.png)

Finished sprites are in [`final_sprites/`](final_sprites).

## Requirements

- Blender (scripts expect `/Applications/Blender.app`)
- Python 3 with `numpy` and `Pillow`
- Your own models and Showdown reference frames: they aren't included in this repo

## Usage

The scripts are in [`pipeline/`](pipeline). Each Pokémon folder holds its config JSON (palette, pose, camera, style).

```bash
python3 pipeline/render_parallel.py golisopod-model/golisopod_front.json frames/
python3 pipeline/make_gif.py golisopod-model/golisopod_front.json frames/ out.gif --scale 4
```

`make_gif.py` also runs the quality checks. See [`SPRITE_PIPELINE.md`](pipeline/SPRITE_PIPELINE.md) for the full process.

Fan project, not affiliated with Nintendo, Game Freak or The Pokémon Company.
