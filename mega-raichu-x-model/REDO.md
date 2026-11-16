# Redo: Mega Raichu X

## The user's feedback (verbatim, 2026-11-15)

Both Raichus should be MUCH MORE energetic. It's the evolution of Pikachu: think about what it's doing with its tail, it's probably bouncing around. Give it MUCH MORE energy.

## Plan notes

- Target style.height: 200.
- A lively bouncing idle (hops or springy knee bounces), tail whipping with follow-through, ears flicking. Still a clean loop.

## Game animation pack (the user downloaded it, 2026-11-15): use it

- `pack/source/inner/source/Mega Raichu X.fbx` (FBX, 60 fps, rig `pm0026_51_00`: same as this model). Textures in `pack/source/inner/textures/`.
- Idle candidates: `pm0026_51_00_00001_battlewait01_loop` (61 f), `_10001_` (81 f), `_20001_` (101 f). Preview them and use the one for this Mega form; if several fit, the liveliest (the user wants MUCH more energy).
- Copy the action onto the existing textured .blend (import, keep the action, delete the rest, save a copy); play it with `motion.clip`; keep palette and shiny. Check that it lands with no offset or scale. Frames and frame_ms at game speed with a seamless loop. Add energy on top only if the clip is too calm, and say so.
