# Redo: Mega Raichu Y

## The user's feedback (verbatim, 2026-11-15)

Both Raichus should be MUCH MORE energetic. Y is probably levitating but still bouncing around. Give it MUCH MORE energy.

## Plan notes

- Target style.height: 200.
- Levitating but bouncy: quick bobs, body tilts, tail whipping, ears and arms reacting.

## Game animation pack (the user downloaded it, 2026-11-15): use it

- `pack/source/inner/source/Mega Raichu Y.fbx` (FBX, 60 fps, rig `pm0026_52_00`: same as this model). Textures in `pack/source/inner/textures/`.
- Idle candidates: `pm0026_52_00_00001_battlewait01_loop` (62 f), `_10001_` (81 f). Preview them and use the one for this Mega form; if several fit, the liveliest (the user wants MUCH more energy).
- Copy the action onto the existing textured .blend (import, keep the action, delete the rest, save a copy); play it with `motion.clip`; keep palette and shiny. Check that it lands with no offset or scale. Frames and frame_ms at game speed with a seamless loop. Add energy on top only if the clip is too calm, and say so.
