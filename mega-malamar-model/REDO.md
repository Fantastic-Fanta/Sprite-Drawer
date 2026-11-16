# Redo: Mega Malamar

The user PASSED Malamar (already in final_sprites). They asked that any passed sprite with a new game animation be re-rendered with it.

## Plan notes

- Keep everything that passed: camera, height 200, palette, shiny, cap. Only the motion changes to the game clip.

## Game animation pack (the user downloaded it, 2026-11-15): use it

- `pack/source/Mega Malamar (ZA).fbx` (60 fps, rig matches this model).
- Idle: `pm0727_51_00_20001_battlewait01_loop` (131 f). Copy the action onto the existing textured .blend (import, keep the action, delete the rest, save a copy); play it with `motion.clip`; keep palette and shiny. Check it lands with no offset or scale. Frames and frame_ms at game speed with a seamless loop.
- The pack is the shiny version: take only the action; the palette and shiny stay as they are.
