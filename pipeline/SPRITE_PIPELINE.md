# Sprite pipeline

Renders a 3D Pokémon model in Blender and turns it into an animated pixel sprite in the
Pokémon Showdown Gen 6 style: hard shade bands, a fixed palette, 1-px lines and a loop with no
flicker. Each sprite is described by one config JSON; the scripts are shared by every Pokémon.

## Setup

- Blender at `/Applications/Blender.app`
- Python 3 with `numpy` and `Pillow`
- Rust, optional. It gives the fast core; without it the same rules run in Python:

```bash
cargo build --release --manifest-path pipeline/rust/Cargo.toml
```

Each Pokémon has its own folder: `golisopod-model/` holds the model (`MegaGolisopod/*.blend` plus
textures), `reference/` (Showdown frames), and one config per view: `golisopod_front.json`,
`golisopod_back.json`, `golisopod_front_shiny.json`, `golisopod_back_shiny.json`.

Commands below run from the repo root, with `B=/Applications/Blender.app/Contents/MacOS/Blender`.

## Build existing sprites

```bash
python3 pipeline/build_all.py out/ golisopod-model/golisopod_front.json glimmora-model/glimmora_front.json --scale 4
```

For each config this renders the frames, builds the GIF, runs the quality gate, and makes the
shiny when a `NAME_shiny.json` sits next to the config. Output: `out/NAME.gif`, `out/NAME_4x.gif`,
`out/NAME.qa.json`. A FAIL from the gate is printed and the build exits 1.

## Make a new sprite

### 1. Import the model

- `.fbx`: open it in Blender (or `$B -b --python pipeline/import_fbx.py -- MODEL.fbx OUT.blend`)
  and save a `.blend`.
- `.dae`: Blender 5 can't import it. Convert with `assimp export model.dae model.glb` and import the `.glb`.
- Make texture paths relative.
- Check the bind pose. Game rips are usually T-posed, so set a rest pose in `pose` before you
  add motion.

### 2. Get the reference

Save frame 0 of the Showdown GIF as `reference/showdown_frame0.png`, exact pixels with no scaling.
First check that it's a real sprite (many frames, about 15–30 colours). Mega placeholders are
often one anti-aliased still. Use those for the camera and silhouette only.
If Showdown has no sprite at all, use the base form's sprite for the camera and for `qa.tone_ref`.

### 3. Write the config

Start by copying an existing config. The main sections are:

| Section | What goes in it |
|---|---|
| `model` | path to the `.blend` |
| `palette` | `outline` colour plus `parts.<part>` shades, darkest → lightest |
| `parts` | `materials` (texture-name fragment → part), `albedo` (texture colour per part) |
| `landmarks` | e.g. `eye.ref_xy`, so the fit can't turn the face away |
| `pose` / `pose_params` | `[bone, axis, expression]` rotations; each param has a `fit` range |
| `camera`, `render` | camera angles, render size, `depth_range`, extra passes |
| `style` | sprite height, matcap, shade thresholds, line rules, `fast_frames`, `pixel_bob` |
| `qa` | limits for the quality gate (see Tests) |

Pose axes are `X/Y/Z` (world rotation), `A:x,y,z` (any axis), `SCALE`, `SCALEW` (widen a bone
chain), `LOCX/LOCY/LOCZ`, `LOCCAM`/`LOCCAMX` (camera up/right) and `ROLLCAM`. Expressions can use
`t`, `s`, `c`, `sin`, `cos`, `smooth`, `smoother`, `bump`, `damp`, `jitter`, `wave` and
`motion.functions` (see `motion.py`).

### 4. Fit the pose and camera

```bash
$B -b MODEL.blend --python pipeline/fit_pose.py -- CONFIG.json out/fit --restarts 20
```

Updates `pose_params` in place. Use `--local K` to start the restarts near the current pose, and
`--only` to fit a subset of params.

### 5. Render frame 0 and fit the look

```bash
$B -b MODEL.blend --python pipeline/render_sprite.py -- CONFIG.json out/f0 --test 0
python3 pipeline/learn_matcap.py CONFIG.json out/f0           # lighting -> style.matcap
python3 pipeline/tune_style.py CONFIG.json out/f0             # shade thresholds, lines, grain -> style
```

With no Showdown reference, set shade shares instead of tuning:
`match_shares.py CONFIG.json out/f0` (front) or `match_tones.py CONFIG.json out/f0` (back, matched to `qa.tone_ref`).

Optional extras:

| Need | Script |
|---|---|
| a crisp eye taken from the reference | `make_eye_stamp.py CONFIG.json X0 Y0 X1 Y1` |
| cast shadows (`style.cast_shadow`) | `fit_shadow.py CONFIG.json out/f0 out/tmp` |
| inner lines along armour plates (`style.seam_lines`) | `make_seams.py MODEL_DIR TEXTURE --islands K`, then list the maps under `render.texture_passes` |
| a separate material for some faces | `kelp_mat.py` / `layer_mat.py` |

Check frame 0 against the reference. Always look at the image as well as the score:

```bash
python3 pipeline/make_gif.py CONFIG.json out/f0 x --first-only out/f0.png
python3 pipeline/compare.py CONFIG.json out/f0.png --out out/compare.png
```

Repeat steps 4–5 while the score improves.

### 6. Preview the motion

```bash
python3 pipeline/render_parallel.py CONFIG.json out/prev --frames 0,20,40,60,80
python3 pipeline/preview_check.py CONFIG.json out/prev PART_A PART_B --png out/prev.png
```

This checks the per-frame rules and the smallest gap between two parts in seconds. A 1-px gap that
opens and closes is the most common cause of pops. If a frame touches the render edge, widen
`render.width`/`height`, `camera.ortho_scale` and the FOV together.

### 7. Build the full loop

```bash
python3 pipeline/render_parallel.py CONFIG.json out/frames
python3 pipeline/make_gif.py CONFIG.json out/frames out/NAME.gif --scale 4 --auto
```

`make_gif` runs the quality gate and writes `out/NAME.qa.json`. On a FAIL, `--auto` tries the
remedies in `qa.remedies` and refits failing parts' shade thresholds, then keeps the best build.

### 8. Make the shiny

```bash
python3 -I pipeline/make_shiny.py CONFIG.json CONFIG_shiny.json --keep-steps
python3 pipeline/palette_swap.py CONFIG.json CONFIG_shiny.json out/NAME.gif out/NAME_shiny.gif --scale 4
```

The shiny is the finished normal sprite with its colours swapped, like Showdown's. Two parts must
not share a colour if only one of them changes in the shiny.

### 9. Back view

The back camera is the front camera turned 180°: azimuth + 180, elevation negated, with the same
body turn. Write it as a separate `_back.json` and build it the same way.

## Tests

### Quality gate (`qa.py`)

Runs automatically after every `make_gif` / `palette_swap` build; run it by hand with
`python3 pipeline/qa.py CONFIG.json SPRITE.gif`. Each check is compared with a limit in the
config's `qa` section. Checks without a limit set are skipped, and so are the ones that need a
reference when the config has none.

**Per-frame rules** (must be 0 unless noted)

| Check | Fails when |
|---|---|
| `thick_lines` | a 2×2 block of line colour appears (a line wider than 1 px) |
| `diag_2px` | a staircase corner or a line hugging the outline reads as a 2-px line |
| `open_outline` | the body touches the outside, or an outlined part touches another part with no line between |
| `silhouette_teeth` | too many 1-px spurs or dents in the silhouette, per frame (limit about 1.25 × Showdown's) |
| `render_clipped` | any frame touches the render edge (checked in `make_gif`) |

**Over the loop** (stability)

| Check | Fails when |
|---|---|
| `dark_flicker` / `dark_flicker_rate` | dark pixels switch on or off for 1–2 frames |
| `any_blinks` / `blink_rate` | any colour lasts only 1–2 frames at a pixel |
| `pop_max` / `pop_max_norm` | the biggest visible change in one frame step that motion doesn't explain is too large |
| `big_pops` / `big_pops_share` | too many frame steps have a pop ≥ 2 |

The `_rate`, `_norm` and `_share` versions are normalised by sprite size and loop length, so their
limits can come from a Showdown sprite with the same kind of motion (`calibration/*.json`:
floating Carbink, idle Golisopod, sway Dragalge). Frames listed in `style.fast_frames`, such as a
spin, are left out of these checks; the per-frame rules still apply to them.

**Against the Showdown reference** (frame 0)

| Check | Measures |
|---|---|
| `style_score` | overall match, 0–100: silhouette, parts, shading, palette mix, lines, size |
| `extra_line_px` / `missing_line_px` | our inner lines with no Showdown line within 2 px, and the reverse |
| `<part>_mix_l1` | colour mix inside one part vs Showdown's |
| `shadow_f1`, `dark_rim_excess`, `blob_shade_err` | where the darkest shades sit, whether they hug the outline, and how dark each piece is |
| `<part>_edge_ratio`, `<part>_shape_f1`, `<part>_tones` | edge share, footprint and number of shades in use for a part |

**Cleanliness** (mainly for sprites with no reference)

| Check | Measures |
|---|---|
| `tone_mix_l1` | brightness mix vs `qa.tone_ref` (Showdown's sprite of the same or base form) |
| `shade_slivers` | fill pixels broken into 1-px streaks by render detail |
| `blotch_share` | small enclosed islands of another colour |

### Finding where a check failed

```bash
python3 pipeline/flicker_map.py out/NAME.gif --heatmap out/pop.png          # where pops happen
python3 pipeline/check_loop.py CONFIG.json out/NAME.gif --heatmap out/loop.png   # blinks, thick lines, diagonals
python3 pipeline/compare.py CONFIG.json out/NAME.gif --out out/compare.png  # reference | ours | diff | extra/missing lines
```

### Regression (`regress.py`)

Rebuilds the regression sprites (Lapras, Glimmora, Golisopod and Dragalge front, plus Dragalge back
and its shiny) and compares every frame, eye position and QA value with the saved goldens in `.regress/`.

```bash
python3 pipeline/regress.py check               # build again, compare frame by frame
python3 pipeline/regress.py render-check        # render again, compare every pass
python3 pipeline/regress.py golden NAME [--rev GIT_REV]   # save a new golden
```

Goldens use the config snapshot taken when they were saved, so editing a config doesn't move the
target. Any speed change must leave both checks IDENTICAL.

### Rust kernels (`rust/check_kernels.py`)

```bash
python3 pipeline/rust/check_kernels.py CONFIG.json FRAMES_DIR [KERNEL ...]
```

Runs a real build with each Rust rule checked against its Python original on every call. Exit 1
on any mismatch; the failing inputs are saved to `.regress/kernel_fail_<name>.npz`.

## Settings

| Variable | Default | Effect |
|---|---|---|
| `SPRITE_RENDER_JOBS` | 4 | Blender processes (4 suits 16 GB) |
| `SPRITE_RENDER_THREADS` | 1 | threads per Blender process |
| `SPRITE_RENDER_FORMAT` | `TGA` | `TGA` (faster, ~7× the disk) or `PNG` |
| `SPRITE_RENDER_CACHE` | `.render_cache/` | render cache folder; `0` = off |
| `SPRITE_RENDER_CACHE_GB` | 20 | cache size cap, oldest first |
| `SPRITE_JOBS` | all cores | build processes; 1 = single process |
| `SPRITE_RUST` | on | `0` = Python only |

A render is reused from the cache when nothing it reads has changed: the config's render, camera,
pose and motion, the model files, the render scripts and Blender itself. A style or QA change
therefore skips Blender entirely. Lines come from `linetrace.py` by default;
`render.freestyle.engine: "freestyle"` switches back to Freestyle.

## Scripts

| Script | Purpose |
|---|---|
| `build_all.py` | batch: render + build + QA + shiny for many configs |
| `render_sprite.py` | Blender: pose the model, render colour / id / data / rest / line passes |
| `render_parallel.py` | render over several Blender processes, with the cache |
| `render_many.py` | Blender worker kept up between sprites (used by `build_all`) |
| `make_gif.py` | frames → sprite GIF, then QA |
| `sprite_style.py` | the look: shading, palette bands, lines, cleanup, stabilisation over time |
| `linetrace.py` | mesh edges as lines (replaces Freestyle) |
| `motion.py` | motion helpers shared by render, style and checks |
| `fit_pose.py` | Blender: fit pose + camera to the reference |
| `learn_matcap.py` | learn the lighting from the reference |
| `tune_style.py` | search style numbers against `compare.py`'s score |
| `match_shares.py`, `match_tones.py` | shade thresholds for sprites with no reference |
| `fit_shadow.py` | fit the cast-shadow sun |
| `make_eye_stamp.py` | cut the eye from the reference into the config |
| `make_seams.py` | seam / island maps for armour lines |
| `make_shiny.py`, `palette_swap.py` | shiny config and shiny recolour |
| `qa.py`, `check_loop.py`, `flicker_map.py`, `compare.py` | quality gate and its checks |
| `preview_check.py` | quick per-frame check on a few frames |
| `regress.py`, `rust/check_kernels.py` | regression tests |
| `res_study.py` | render resolution vs quality |
| `ref_decode.py` | rebuild a Showdown frame from browser-exported text |
| `import_fbx.py`, `kelp_mat.py`, `layer_mat.py` | Blender model prep |
| `rustcore.py`, `rust/` | Rust versions of the per-pixel rules (same pixels as Python) |
