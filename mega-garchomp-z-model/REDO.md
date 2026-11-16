# Redo: Mega Garchomp Z

## The user's feedback (verbatim, 2026-11-15)

Yes it's a levitating land shark. A bit more to the side on camera angle. The 2 fins should read more physically correct as 'flying' or balancing itself in the air like a wizard.

## Plan notes

- Target style.height: 200.
- Camera a bit more side-on (still facing left). Arm fins spread and making small balancing adjustments, like levitating.

## Game animation pack (the user downloaded it, 2026-11-15): use it

- `pack/source/Mega Garchomp Z.fbx` (FBX, 60 fps, rig `pm0445_52_00`: same as this model).
- Idle: `pm0445_52_00_20001_battlewait01_loop` (frames 1-251, about 4.2 s). Copy it onto the existing textured .blend (import, keep the action, delete the rest, save a copy); play it with `motion.clip`; keep palette and shiny. Check that it lands with no offset or scale.
- 251 frames is long: sample it at game speed, about 30-40 ms per frame, keeping a seamless loop.
- The user's camera note still stands: turn a bit more to the side. Fins should read as balancing in the air.
