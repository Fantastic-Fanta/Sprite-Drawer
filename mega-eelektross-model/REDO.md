# Redo: Mega Eelektross

## The user's feedback (verbatim, 2026-11-15)

OK, but definitely not the camera angle: use a Drampa-type angle. It's an eel: give the body a swimming animation, as if riding and swimming in the waves, curving like an eel. All 3 eels, including the 2 white ones at the side, should swim. Look at the Showdown sprite of the original Eelektross for inspiration (play.pokemonshowdown.com/sprites/ani/eelektross.gif).

## Plan notes

- Target style.height: 200.
- Camera like Mega Drampa's (see mega-drampa-model's config AZIMUTH/ELEVATION). A travelling swim wave along the main body and both white eels, phase-offset.

## Game animation pack (the user downloaded it, 2026-11-15): use it

- `pack/source/Mega Eelektross.fbx` (60 fps, rig matches this model).
- Idle: `pm0604_51_00_10001_battlewait01_loop or _20001_ (preview both, take this Mega form's)` (121 f). Copy the action onto the existing textured .blend (import, keep the action, delete the rest, save a copy); play it with `motion.clip`; keep palette and shiny. Check it lands with no offset or scale. Frames and frame_ms at game speed with a seamless loop.
- The user's notes still stand: Drampa-like camera angle, and all three eels (the body and the two white side eels) must swim like eels. If the clip doesn't give the side eels a travelling wave, add one on top and say so.
