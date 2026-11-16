# Redo: Mega Greninja

## The user's feedback (verbatim, 2026-11-15)

I downloaded a Mega Greninja Z-A pack that includes animation: use that.

## Plan notes

- Target style.height: 200.
- The pack is unpacked at mega-greninja-model/pack/source/MegaGreninja1.glb (also prepped as mega-greninja-za-model/). Actions include pm0725_51_00_20001_battlewait01_loop (the game idle, ~48 frames at 24 fps). Use the game idle via motion.clip: either move the action onto the existing mega-greninja .blend (same rig names) or use the pack model if it is complete and textured; keep the existing palette/shiny if you can. Frame count/timing should follow the clip.
