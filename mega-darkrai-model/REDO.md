# New: Mega Darkrai

The user downloaded this model on 2026-11-15. It is prepped (`prep_model.py`): config, `RIG.md`, `prep/rest_*.png`.

## Game animation pack (the user downloaded it, 2026-11-15): use it

- `pack/source/MegaDarkrai.fbx` (60 fps, rig matches this model).
- Idle: `pm0491_51_00_20001_battlewait01_loop` (241 f, ~4 s: sample at ~30-40 ms per frame). Copy the action onto the existing textured .blend (import, keep the action, delete the rest, save a copy); play it with `motion.clip`; keep palette and shiny. Check it lands with no offset or scale. Frames and frame_ms at game speed with a seamless loop.
- New sprite: do the prep check (palette parts, shiny) as the skill says; then the clip, height 200 (tall: check by width), cap, facing left with the face readable.
