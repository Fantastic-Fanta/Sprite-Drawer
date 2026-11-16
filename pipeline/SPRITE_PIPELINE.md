# Sprite pipeline

Renders a 3D Pokémon model in Blender and turns it into an animated pixel sprite: flat palette
colours, three cel bands and lines from an inverted hull. Each sprite is described by one config
JSON; the scripts are shared by every Pokémon.

The lines come from the model itself. Every mesh gets a copy pushed out a little along its normals,
with its normals flipped and back faces culled (an inverted hull). The hull shows around the
silhouette, and inside wherever a nearer part sits in front of something further back. Where the
lines go is never traced, painted or tuned per Pokémon.

## Setup

- Blender at `/Applications/Blender.app`
- Python 3 with `numpy` and `Pillow`

Each Pokémon has its own folder: `models/mega-golisopod/` holds the model (`MegaGolisopod/*.blend`
plus textures, local only) and one config per view: `mega_golisopod_front.json`,
`mega_golisopod_back.json`, and a `_shiny.json` next to each. Approved GIFs go to
`sprites/mega-golisopod/`.

Commands below run from the repo root, with `B=/Applications/Blender.app/Contents/MacOS/Blender`.

## Build existing sprites

```bash
python3 pipeline/build.py                          # every Pokémon in models/
python3 pipeline/build.py mega-golisopod           # one (or several, or single CONFIG.json paths)
python3 pipeline/build.py --publish mega-golisopod # approved: copy out/mega-golisopod/ into sprites/
```

For each front / back config this renders the frames, builds the GIF and its 4x copy, and makes
the shiny when a `NAME_shiny.json` sits next to the config. Output: `out/<pokemon>/NAME.gif` and
`NAME_4x.gif` (`--out DIR` writes them straight into DIR). Publish copies the built files as they
are, so the GIFs you reviewed are the ones that land in `sprites/`.

## Make a new sprite

Fast path: `prep_model.py MODEL.zip` writes steps 1–3's draft. Pose and animate it with `preview.py`
and `check_motion.py`, then `package.py` does the back, the shinies and the build. The steps below
are what those scripts do, for doing one by hand.

### 1. Import the model

- `.fbx`: open it in Blender and save a `.blend` (`prep_model.py` does this for you).
- `.dae`: Blender 5 can't import it. Convert with `assimp export model.dae model.glb` and import the `.glb`.
- Make texture paths relative.
- Check the bind pose. Game rips are usually T-posed, so set a rest pose in `pose` before you
  add motion.
- A surface the game colours in its shader rather than in the albedo texture (e.g. Mega
  Dragalge's wings) can get its own material: see `models/mega-dragalge/layer_mat.py` / `kelp_mat.py`.

### 2. Write the config

Start by copying an existing config (`models/mega-zygarde/mega_zygarde_front.json` is the smallest).

| Section | What goes in it |
|---|---|
| `model` | path to the `.blend` |
| `palette` | `outline` colour plus `parts.<part>` shades, darkest → lightest |
| `parts` | `materials` (texture- or material-name fragment → the parts it may become, `"purple\|red"`), `default_material`, `albedo` (texture colour per part, for `make_shiny.py`) |
| `camera`, `render` | camera angles, render size; `render.hull` optional (see below) |
| `pose` / `pose_params` | `[bone, axis, expression]` rotations; each param can have a `fit` range |
| `motion` | `frames`, `functions`, or `clip` (one of the model's own actions) |
| `style` | `height` (frame 0's height in sprite px), `frame_ms`; the rest is optional (see below) |

The palette decides the colours: every pixel of the texture goes to the part of its nearest
palette shade, and then to that part's shade nearest its colour. So each part needs shades spread
across the texture colours it covers, darkest to lightest. A material listed in `parts.materials`
only goes to the parts named there: use it where a texture's colours would snap to the wrong part
(Lapras's shell, Mega Dragalge's crimson wings). Where two parts' ramps overlap (a gunmetal armour nearer a
slate claw shade than its own), set `parts.match` to `"albedo"`: parts are then told apart by
their one `parts.albedo` texture colour instead of their shades.

Pose axes are `X/Y/Z` (world rotation), `A:x,y,z` (any axis), `SCALE`, `SCALEW` (widen a bone
chain), `LOCX/LOCY/LOCZ`, `LOCCAM`/`LOCCAMX` (camera up/right) and `ROLLCAM`. Expressions can use
`t`, `s`, `c`, `sin`, `cos`, `smooth`, `smoother`, `bump`, `damp`, `jitter`, `wave` and
`motion.functions` (see `motion.py`).

### 3. Set the camera

With a Showdown sprite of the Pokémon (`reference`: frame 0 as `reference/showdown_frame0.png`,
exact pixels), fit the pose and camera to it:

```bash
$B -b MODEL.blend --python pipeline/fit_pose.py -- CONFIG.json out/fit --restarts 20
```

This updates `pose_params` in place. Use `--local K` to start the restarts near the current pose,
and `--only` to fit a subset of params. Without a reference (most Megas), set `AZIMUTH`,
`ELEVATION` and `FOV` by eye.

### 4. Check frame 0

```bash
python3 pipeline/render_parallel.py CONFIG.json out/f0 --frames 0
python3 pipeline/make_gif.py CONFIG.json out/f0 x --first-only out/f0.png
```

If a frame touches the render edge, widen `render.width`/`height`, `camera.ortho_scale` and the
FOV together (`make_gif` fails on a cut-off frame).

### 5. Animate

Watch the motion live while you edit it:

```bash
$B MODEL.blend --python pipeline/live_preview.py -- CONFIG.json
```

Blender opens on the sprite camera and plays the loop; save the config and it reloads in a
fraction of a second. It shows the model, not the sprite look. Keep feet on the ground: list the
ankles in `motion.plant` and a body dip or sway bends the legs instead of sliding the feet.

### 6. Build the loop

```bash
python3 pipeline/build.py CONFIG.json
```

### 7. Make the shiny

```bash
python3 -I pipeline/make_shiny.py CONFIG.json CONFIG_shiny.json --keep-steps
python3 pipeline/palette_swap.py CONFIG.json CONFIG_shiny.json out/NAME.gif out/NAME_shiny.gif --scale 4
```

The shiny is the finished normal sprite with its colours swapped, like Showdown's. Two parts must
not share a colour if only one of them changes in the shiny. `build.py` does the swap by itself
once `CONFIG_shiny.json` exists.

### 8. Back view

Copy the front config to `_back.json` and change only the camera: azimuth + 180, and a positive
elevation (about the front's own) so the camera looks down on the back, never up from below.
Pose, motion, palette and style stay the same. Build it the same way.

## The look (`sprite_style.py`)

For every sprite pixel, from the full-size render passes:

- **Part and colour.** The part is the palette part most of its render samples snap to, leaving
  out samples under the hull (they belong to the line). A sample of a material in
  `parts.materials` (the ID pass) only snaps to that material's parts. Its colour is the mean of those samples,
  snapped to that part's shades. A pixel on a border takes one side's colour, never a blend.
- **Shade bands.** The shade moves one step darker or lighter by the light on the pixel's mean
  normal (N.L): below the 25th percentile of frame 0 one darker, above the 70th one lighter.
  The limits are fixed for the whole loop, so the bands don't jump.
- **Lines.** A pixel is outline colour where the hull covers 35% of it. A 1–2 px gap in a line is
  filled where the hull still covers 12%, with line on both sides, so no line gets wider. Lines
  are never thinned or moved. Where the hull has a crack at a hard edge, the pixel right outside
  the body closes the silhouette.
- **Slivers.** A texture colour reaching a pixel or two past the edge a line follows leaves bits
  of a part (up to 3 px) touching the line; they take the colour around them.

All of it is automatic. Optional settings:

| Setting | Default | Effect |
|---|---|---|
| `render.hull.thickness_px` | 1.15 | line width in sprite px, turned into world units from frame 0's size on screen and `style.height` |
| `render.hull.thickness` | — | the hull's thickness in world units instead |
| `render.hull.even` | `true` | keeps the hull the same width round sharp corners |
| `render.hull.spike` | 2.0 | even offset at a needle-sharp tip is capped to this many thicknesses (else it draws long strands) |
| `render.hull.cap_each_frame` | `false` | cap spikes in every frame's pose, not just frame 0's |
| `parts.match` | `"palette"` | `"albedo"`: tell parts apart by `parts.albedo`, not by palette shades |
| `style.light` | `[-0.15, 0.45, 0.88]` | light direction in camera space (x right, y up, z to the viewer) |
| `style.bands` | frame 0's 25th / 70th percentile | N.L limits for one shade darker / lighter |
| `style.flat_parts` | none | parts that keep their texture shade (marks, gems) |
| `style.cover`, `style.weak_cover` | 0.35, 0.12 | hull coverage for a line pixel / a filled gap |
| `style.ring` | `true` | close the silhouette where the hull cracks |
| `style.despeckle` | 0 | specks of up to this many px inside one part, ringed by one other colour of it, take that colour (lines untouched) |
| `style.fast_frames` | none | frame ranges of a fast event (a spin): slow motions pause during them |
| `style.frame_anchor` | — | `"first"`: frame 0's pixel grid, grown to fit the loop |
| `style.pixel_bob` | none | whole-pixel shift of each finished sprite (`motion.py`) |
| `motion.plant` | none | bones (ankles) held at their mean spot over the loop: a body dip or sway bends the two bones above each instead of moving the foot |

## Tests

### Regression (`regress.py`)

Rebuilds the regression sprites (Lapras, Glimmora, Golisopod and Dragalge front, Dragalge back and
its shiny, Zygarde front and back) and compares every frame with the saved goldens in `.regress/`.

```bash
python3 pipeline/regress.py                     # build again, compare frame by frame (~20 s)
python3 pipeline/regress.py render-check        # render again, compare every pass (~3 min)
python3 pipeline/regress.py full                # both
python3 pipeline/regress.py golden NAME [--rev GIT_REV]   # save a new golden
```

Goldens use the config snapshot taken when they were saved, so editing a config doesn't move the
target. Any speed change must leave both checks IDENTICAL. The pre-push hook (`.githooks/pre-push`,
on with `git config core.hooksPath .githooks`) runs the first check whenever a push changes `pipeline/`.

## Settings

| Variable | Default | Effect |
|---|---|---|
| `SPRITE_RENDER_JOBS` | 4 | Blender processes (4 suits 16 GB) |
| `SPRITE_RENDER_THREADS` | 1 | threads per Blender process |
| `SPRITE_RENDER_FORMAT` | `TGA` | `TGA` (faster, ~7× the disk) or `PNG` |
| `SPRITE_RENDER_CACHE` | `.render_cache/` | render cache folder; `0` = off |
| `SPRITE_RENDER_CACHE_GB` | 20 | cache size cap, oldest first |
| `SPRITE_JOBS` | all cores | build processes; 1 = single process |

A render is reused from the cache when nothing it reads has changed: the config's render, camera,
pose and motion, `parts.materials`, `style.height` and `fast_frames`, the model files, the render scripts and Blender
itself. Any other style change skips Blender entirely.

## Scripts

| Script | Purpose |
|---|---|
| `build.py` | render + build + shiny + 4x for every / named Pokémon; `--publish` to `sprites/` |
| `render_sprite.py` | Blender: pose the model, render the colour / ID / data / hull passes |
| `render_parallel.py` | render over several Blender processes, with the cache |
| `render_many.py` | Blender worker kept up between sprites (used by `build.py`) |
| `make_gif.py` | frames → sprite GIF |
| `sprite_style.py` | the look: part colours, shade bands, hull lines |
| `motion.py` | motion helpers shared by render and style |
| `fit_pose.py` | Blender: fit pose + camera to the reference |
| `make_shiny.py`, `palette_swap.py` | shiny config and shiny recolour |
| `regress.py` | regression tests |
| `prep_model.py` (+ `prep_scene.py`) | model zip → model folder, `.blend`, draft config (palette from the textures, camera, size), `RIG.md` |
| `preview.py` | Workbench sheet of a few loop frames from several views, in seconds: judge pose and motion without a build |
| `check_motion.py` | the idle rules in sprite px: frozen / big / jitter / loop seam / feet / visible clipping |
| `package.py` | front config → back + shiny configs, build, contact sheet, check, report skeleton |
| `blender_slot.py` | machine-wide cap on Blender processes, timeouts, stray-Blender reaper |
| `live_preview.py` | the loop playing live in Blender's window, reloaded on every config save |
