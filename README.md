# Sprite-Drawer

Turns 3D Pokémon models into animated pixel sprites in the Pokémon Showdown (Gen 6) style.

![Mega Glimmora, Golisopod and Dragalge: front, shiny, back, back shiny](final_sprites/overview.png)

Finished sprites are in [`final_sprites/`](final_sprites).

## Requirements

- Blender (scripts expect `/Applications/Blender.app`)
- Python 3 with `numpy` and `Pillow`
- Rust (`cargo`), optional: the fast core. Without it the same code runs in Python, just slower
- Your own models and Showdown reference frames: they aren't included in this repo

## Usage

The scripts are in [`pipeline/`](pipeline). Each Pokémon folder holds its config JSON (palette, pose, camera, style).

```bash
cargo build --release --manifest-path pipeline/rust/Cargo.toml   # once
python3 pipeline/build_all.py out/ golisopod-model/golisopod_front.json glimmora-model/glimmora_front.json --scale 4
```

`build_all.py` renders, builds and quality-checks each sprite, and makes its shiny if a `_shiny.json` sits next to it.
For one sprite step by step, and the full process, see [`SPRITE_PIPELINE.md`](pipeline/SPRITE_PIPELINE.md).

Fan project, not affiliated with Nintendo, Game Freak or The Pokémon Company.
