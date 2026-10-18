# Showdown-style sprites from 3D models: pipeline and record

Goal: render a game model in Blender so that it matches the Pokémon Showdown animated
sprites (the Gen 6 / X-Y style, `play.pokemonshowdown.com/sprites/ani/*.gif`) in
everything except motion. Motion is our own idle loop.

Worked example: Lapras (Pokémon X/Y model from The Models Resource), compared against
`sprites/ani/lapras.gif` frame 0. Everything Lapras-specific lives in `lapras.json`;
the scripts are generic.

---

## 1. The Showdown style, as measured

Measured on the reference frame with `compare.py`, not guessed.

| Property | Showdown (Lapras frame 0) | Rule in our pipeline |
|---|---|---|
| Canvas | 94×84, the Pokémon fills it | frame 0 scaled to 82 px tall + 1 px outline each side = 84 (`style.height`) |
| Timing | 89 frames × 30 ms, loops forever | `style.frame_ms = 30`; frame count is ours (motion) |
| Transparency | on/off only, no semi-transparent pixels | alpha threshold 50% after box-downscale |
| Colours | **15 total** | fixed palette in config; nothing else can appear |
| Palette structure | 1 outline colour + 3–5 shades per part | `palette.outline`, `palette.parts.<part>` darkest → lightest |
| Outline colour | `#373f43` (dark blue-grey, not black) | same |
| Outline share | 16.4% of pixels | measured, matched |
| Silhouette outline | 1 px, continuous; 28% of its pixels are stair corners | 1 px closed outline built from the body (every body pixel's outside 4-neighbour). Earlier rounds copied Showdown's stair corners with a supersampled outline (`outline_width`/`outline_cover`); dropped in #15 because the corners read as 2-px diagonals |
| Inner outlines | 201 px: shell rim all round, neck/body overlap, under flippers, mouth, ear | depth jumps + sharp folds + `part_outline` parts |
| Line continuity | 5 lone line pixels, 9 fragments ≤ 3 px | measured, matched |
| Double line | shadow-side edges carry the part's darkest shade just inside the outline | `style.rim_light`, `style.rim_shade` |
| Inner lines on skin | drawn in dark blue `#4e748a`, not the outline grey | `style.inner_line` |
| Eyes | pupil in outline colour; **eye white in the shell's lavender shades**, not cream | `parts.eye` (`light: "shell:4"`) |
| Light | several lights: key from front-left, dark under the chin, **rim light along the back edge** | **learned matcap** (`learn_matcap.py`): a 9×9 table normal → brightness, learned from the reference. One directional light can't reproduce it. |
| Shading | hard bands, no gradients, no dithering | thresholds on the light value → shade index |
| Shade mix within each part | blue 10/58/18/14 %, cream 11/11/5/55/17 %, shell 5/6/14/23/53 % | thresholds set by histogram matching (`tune_style.py`), so the mix matches by construction |
| Grain | 9.8% of pixels differ from all 4 neighbours (blue 7%, cream 7%, **shell 32%**) | texture detail nudges the light value (`style.grain` per part); colours point-sampled at pixel centres like the 3DS rendering at native resolution |
| Eyes | a crisp hand-drawn shape: slanted pupil block in outline grey, eye white in shell lavender, cream highlight, dark-blue lid lines | **eye stamp** (`make_eye_stamp.py`): the reference's eye pixels, placed each frame on the 3D eye centre (sub-pixel, smoothed over 5 frames, only moved when it's really moved > 0.7 px). Drawing the eye from the texture at sprite size made it a different blur every frame |
| Line width | (our rule, stricter than Showdown: its outlines have 28% staircase corners and 12 doubled spots) | **every line pixel-perfect, 1 px counting diagonals**: inner lines thinned to a skeleton; staircase corners removed (a line pixel with one horizontal + one vertical line neighbour) unless needed to close the outline; inner lines touching the outline at 2+ points (diagonals count) removed; no 2×2 blocks; the outline is built from the body only (no added corner pixels); inner lines keep 1 px clear of the eye. Checked every frame by `check_loop.py` (target 0) |
| Shell | outline all round; along the lower edge, per row: **outline, lip (2 px), `=` dark-blue, `#` crease, top surface**; few lines deeper inside; cream-white highlights on spikes and top, not on the lip; shadow-side rim 1–2 shades darker than the surface | `parallel_lines` with `offset [1, 0]`: a shifted copy of the shell/body border, `=` at +2 and `#` at +3 from the first lip pixel (an isoline at a fixed *distance* jumped around and popped; a shifted copy moves exactly with the border); detected shell lines off (`crease_cos_part`, `depth_jump_part`); highlights keep ≥ 6 px from the shell/body border (`min_border_dist`); rim relative: 2 shades darker (`rim_shade.shell = {drop: 2}`); shell shade thresholds fitted to Showdown's *shell area* mix by `make_gif.py --auto`. Gate: `shell_mix_l1` 0.112 (≤ 0.12) |
| Mouth | a dark-blue `=` line where the blue upper jaw meets the cream chin, from the snout up toward the cheek, continuing round the chin; not drawn further down the neck | `border_lines`: blue/cream border drawn in `blue:0` on the blue side, only inside a box relative to the eye (`box_dx` −18..4, `box_dy` 3..12). Also `line_side: ["blue"]`: a fold line on a blue/cream crease goes on the blue side. (The model's mouth crease alone was too broken to survive as a line) |
| Overlap lines on cream | darkest cream `#c3baa7`, not outline grey (e.g. under the chin, belly/flipper crease) | `style.inner_line.cream = "cream:0"` (the black line across the neck was this) |
| Stray pixels | none | a body pixel whose part differs from all its neighbours (pale pixel against the outline, cream dot in blue) takes their colour (`clean_parts`) |
| Canvas | the sprite never touches the image edge | 1 px empty margin (`canvas_margin`); beyond the canvas counts as outside in every check |
| Lines over time | lines belong to the model's surface: they move with it and never re-configure | **lines carried from one key frame** (`transport_lines`): frame 0 is drawn normally; its final line pixels are moved to every other frame through the rest pass (`rest_NNNN.png`: where on the unposed model each pixel is). Per-frame detection made the shell lip switch between single / double / dashed lines every few frames (pops up to 7.6) |
| Stability over time | (our rule: Showdown's own GIF scores 759 on the flicker metric) | **nothing blinks**: (1) shape: a pixel joining/leaving the body for ≤ `min_frames` (2) frames is undone, using the neighbouring frame's data; (2) lines, rim and shade per pixel = majority/median over 3 frames; (3) eye position held ≥ 3 frames; (4) finished frames: any colour lasting ≤ 2 frames takes its neighbour in time, then repair re-closes the outline and re-applies the line rules, always picking the fix that agrees with the previous/next frame; repeated until stable; (5) a last pass settles 1–2 frame shading steps, redraws the eye stamp and clears ghost eye pixels, and re-applies the 1-px rules |
| Cleanliness | grain is always light (one shade away); only 2 dark specks inside the body | **anti-speck rules**: grain compares a pixel only with its own part, and moves it at most `grain_max_bands` (1) shade; pixels 2+ shades darker than all neighbours are lifted; inner-line pieces under `min_line_px` (4) that don't touch the silhouette are dropped; any lone dark pixel inside the body takes its neighbours' colour; across the loop, a dark pixel that's dark in one frame only takes the previous frame's colour (`steady_loop`) |

## 2. Files

Scripts and `calibration/` are in `pipeline/`; each Pokémon's config, reference and outputs sit in
its own folder (e.g. `lapras-model/Lapras/`).

| File | What it does |
|---|---|
| `lapras.json` | everything for one Pokémon: palette, part rules, landmarks, pose bones + params, camera, style numbers, fit ranges, run log |
| `render_sprite.py` | Blender: poses the model, renders colour / ID / normal+depth passes per frame |
| `sprite_style.py` | the look: matcap shading, palette bands, rim shade, inner lines, supersampled outline (Python + numpy + Pillow) |
| `make_gif.py` | runs `sprite_style` over all frames → GIF (+ `--scale 4` copy, `--first-only` PNG) |
| `compare.py` | scores a frame against the reference, prints every metric, writes reference \| ours \| difference |
| `fit_pose.py` | Blender: searches pose + camera so parts and landmarks land where the reference's do |
| `learn_matcap.py` | learns the game's lighting from the reference as a matcap (also saved standalone as `matcap_xy.json`) |
| `tune_style.py` | searches the style numbers against `compare.py`'s score |
| `make_eye_stamp.py` | cuts the eye out of the reference into the config (`parts.eye.stamp`) |
| `check_loop.py` | whole-loop checks: dark flicker, any-colour blinks, 2×2 line blocks, 2-px diagonals (staircase corners / lines hugging the outline); `--heatmap` marks where |
| `flicker_map.py` | flicker as the eye sees it: change between frames that a 1-px shift doesn't explain, weighted by brightness jump; **pops** = biggest coherent patch of such change per frame step; `--pops` pictures the worst |
| `qa.py` | the quality gate: every check against the limits in the config's `qa` section, PASS / FAIL; run automatically by `make_gif.py` (`--auto` also fits failing parts' shade thresholds and tries remedies) |
| `reference/showdown_frame0.png` | the reference frame, exact pixels from the Showdown GIF |
| `render_parallel.py` | the full render split over 4 Blender processes (`--frames 0:60` or `0,5,9` for a subset); ~20 s for 160 frames |
| `preview_check.py` | per-frame rules + closest gap between two parts on a few rendered frames, seconds instead of a full build |
| `fit_shadow.py` | fits the cast-shadow sun direction / strength (`--mode cast\|unlit`) |
| `match_shares.py` | shade thresholds from target shade shares on frame 0, for sprites with no reference to match |
| `make_shiny.py` | shiny config from the model's shiny textures: per-part colour change; `--keep-steps` keeps the normal ramp's brightness steps |
| `palette_swap.py` | the shiny sprite = the finished normal sprite recoloured (Showdown's way), then QA |
| `ref_decode.py` | rebuilds a Showdown frame / silhouette from the compact text the browser exports, checks its hash |
| `calibration/*.json` | motion limits measured on Showdown's own sprites (floating Carbink, idle Golisopod and its shiny, sway Dragalge) |
| `match_tones.py` | shade shares fitted so frame 0's brightness mix matches `qa.tone_ref` (no-reference sprites) |
| `kelp_mat.py` | Blender: gives the faces skinned to chosen bones their own material (Dragalge's horns) |
| `motion.py` | expression helpers, `motion.functions`, whole-pixel offsets (`style.pixel_bob`), shared by render / style / checks |
| `make_seams.py` | seam maps: each texture's UV-island borders + normal-map grooves, painted white in texture space (per Pokemon, `render.seams`) |
| `build_all.py` | many sprites in one go: renders the next sprite while the previous one builds, one Blender pool for the batch, shinies by `palette_swap` |
| `render_many.py` | Blender worker for `render_parallel.RenderPool`: stays up between sprites, takes render jobs on stdin |
| `rustcore.py`, `rust/` | Rust versions of the per-pixel rules (line cleanup, debounce, fault count, pupils, shape / shading over time); same pixels as the Python, which runs when the library isn't built |
| `linetrace.py` | the lines pass without Freestyle: the mesh's own borders, silhouettes and creases, kept where visible, drawn `thickness` px wide (Rust, numpy fallback); `render.freestyle.engine` picks it (`"trace"`, default) or Freestyle (`"freestyle"`) |
| `res_study.py` | render resolution vs quality: builds at lower render sizes, reports render time, QA, Showdown score, pixels changed |
| `regress.py` | regression check: builds (and renders) the regression sprites again and compares every frame, eye and QA value with saved goldens (`.regress/`) |
| `rust/check_kernels.py` | runs a real build with each Rust rule checked against its Python original on every call |

## 3. Steps

```bash
B=/Applications/Blender.app/Contents/MacOS/Blender
P=../../pipeline        # run from the Pokémon's folder (here lapras-model/Lapras/)
# 1. pose + camera fitted to the reference (updates pose_params; 20–30 random starts, ~5 min)
$B -b Lapras.blend --python $P/fit_pose.py -- lapras.json /tmp/fit --restarts 20
# 2. render frame 0
$B -b Lapras.blend --python $P/render_sprite.py -- lapras.json /tmp/f0 --test 0
# 3. lighting, learned from the reference (updates style.matcap)
python3 $P/learn_matcap.py lapras.json /tmp/f0 --out matcap_xy.json
# 4. style numbers fitted to the reference (updates style)
python3 $P/tune_style.py lapras.json /tmp/f0
# 5. check: score + side-by-side picture
python3 $P/make_gif.py lapras.json /tmp/f0 x --first-only /tmp/f0.png
python3 $P/compare.py lapras.json /tmp/f0.png --out /tmp/compare.png
# repeat 1–5 while the score improves; then the full loop:
$B -b Lapras.blend --python $P/render_sprite.py -- lapras.json /tmp/frames
python3 $P/make_gif.py lapras.json /tmp/frames lapras_sprite.gif --scale 4
# make_gif runs the quality gate (qa.py) after building; --auto tries the config's qa.remedies
# on a FAIL and keeps the best; the report is saved as lapras_sprite.qa.json; exit code 1 = FAIL
# 6. when something fails, look at where:
python3 $P/flicker_map.py lapras_sprite.gif --pops /tmp/pop.png      # worst pop, before | after
python3 $P/check_loop.py lapras.json lapras_sprite.gif --heatmap /tmp/flicker.png
python3 $P/compare.py lapras.json lapras_sprite.gif --out /tmp/compare.png   # 4th panel: extra / missing lines
```
One-off per Pokémon, before step 4: `python3 $P/make_eye_stamp.py lapras.json 24 13 31 19`
(a box around the eye in the reference frame).

Always look at the `--out` picture as well as the numbers: twice, my eye was wrong (the
shell *is* that grainy) and twice the numbers missed something (stray pale edge pixels;
the head pitch). Add a metric when the picture shows something the numbers don't.

## 3b. The quality gate (why problems now get caught automatically)

Until #18 the checks had blind spots, so problems were found by eye, one screenshot at a time:

| Blind spot | Consequence | Check that closes it |
|---|---|---|
| frame-0 comparison let Showdown's outline pixels match *anything*, and compared line *counts* only | extra lines in the wrong place scored fine | `compare.py` line placement: our inner lines with no Showdown line within 2 px (extra), and the reverse (missing) |
| loop checks only counted colours lasting 1–2 frames | a line that switches every 3–10 frames, or a band that re-draws itself, passed | `flicker_map.py`: change not explained by a 1-px shift, weighted by brightness jump; **pops** (biggest coherent change per step) |
| whole-sprite averages | a few loud spots hid behind a calm average (ours averaged *calmer* than Showdown while the shell lip popped) | pops are per patch, with a picture of the worst |
| nothing gated the build | the GIF was written whatever the numbers said | `qa.py` runs inside `make_gif.py`; limits in `qa`; `--auto` remedies; FAIL = exit code 1 |
| a dark line next to the outline in another colour (dark blue beside the grey outline) counted as two 1-px lines | the shell lip read as a 3-px band and passed | "line" = outline **plus** `style.dark_line_colours`, in drawing and in every check |
| nothing checked that part outlines stay closed | the shell's light grey touched the blue directly ("colour leakage") | `open_outline`: body touching the outside, or an outlined part (`style.part_outline`) touching another part with no line between (`check_loop.part_masks`, shared with the drawing step) |
| per-frame fixes made after the time debounce weren't debounced themselves | they blinked | `rule_safe_debounce`: one more debounce that keeps a change only if `hard_faults` (the checks' own counts) don't go up |
| silhouette smoothness wasn't measured | a 1-px nub on the flipper's straight bottom edge | `silhouette_teeth`: 1-px spurs + dents per frame (Showdown: 4) |

Limits (`lapras.json` → `qa`): user rules 0 (thick lines, 2-px diagonals); pop limits are Showdown's
own GIF on the same metric (largest pop 3.8, 22 of 89 steps with a pop ≥ 2). For calibration: the
same animation with flat texture colours only (no lines, no shading) scores largest pop 1.8, 0 steps
≥ 2, so anything above that is made by the styling, not by the motion.

## 4. Applying this to another Pokémon

1. **Model**: get the X/Y (or Sun/Moon) rip; import into Blender, save a `.blend`.
   Blender 5 can't import `.dae`: `assimp export model.dae model.glb`, import the `.glb`.
   Make texture paths relative if they're absolute (`/Textures/…`).
2. **Reference**: save frame 0 of the Showdown GIF as `reference/showdown_frame0.png`
   (exact pixels, no scaling).
3. **Palette**: list the reference's colours. The darkest grey that traces the silhouette
   is the outline. Group the rest into parts (skin, belly, shell, …), each darkest →
   lightest. A dark shade used only beside lines (Lapras's `#4e748a`) goes first in its
   part; `style.first_shade` keeps it out of normal shading. Note which part's colours the
   eye whites use (Lapras: shell).
4. **Parts**: `parts.materials` maps texture-name fragments to parts (`"BodyB": "shell"`,
   `"Eye": "eye"`); the default material splits by nearest texture colour in `parts.albedo`.
5. **Landmarks**: mark the pupil centre in the reference (`landmarks.eye.ref_xy`). Without
   it the fit happily turns the face away, because a silhouette can't tell a face from the
   back of a head.
6. **Pose**: list bone rotations in `pose` as `[bone, axis, expression]` (axis X/Y/Z in
   world space, or SCALE). Expressions use `pose_params` and `s`, `c` (our idle). Give
   every parameter a `fit` range. Start with body pitch/roll, neck bend, head turn/pitch/
   scale, each limb's swing and tilt, tail.
7. **Lighting**: start from `matcap_xy.json` (X/Y battle lighting should be the same for
   every Pokémon), then re-learn it on the new reference.
8. Run section 3, read the report and the picture, iterate.

### Lessons from Lapras

* **Which limb is which depends on the camera.** At the fitted camera (63° toward the
  front) the flipper at Showdown's bottom-left is Lapras's *right* flipper. Name pose
  params by bone side (L/R), not "near/far".
* A limb that can only swing sideways can't reach the ground: give each limb a tilt too.
* Random restarts matter: one descent from a hand pose got stuck at 0.63 part match;
  30 random starts found 0.78, and better pose parameters took it to 0.86.
* Don't un-premultiply Blender's PNG colours: they're already straight alpha, and dividing
  again turns edge pixels white.
* Score shading within 1 px: a 1-px pose offset isn't a style difference, but an exact-pixel
  score treats it as one.

## 5. Iteration log (Lapras)

Score = `compare.py` style score (0–100): silhouette 20, parts 25, shading (within 1 px) 20,
palette mix 15, lines (+ grain, fragments) 15, size 5. Scores before #7 used the strict
shading metric and fewer line checks, so they read ~4 points lower than they would now.

| # | Change | Score | Main gaps after |
|---|---|---|---|
| 0 | First palette version (single outline, hand-posed) | 65.8 | pose, shade mix, grain, frame 0 too small (80 px) |
| 1 | Config-driven pipeline; frame 0 scaled to exact height | 67.2 | pose leans (Showdown sits upright); too much light cream (35% vs 17%); grain 6% vs 10%; stair corners 41% vs 28% |
| 2 | Pose fit with 30 random starts + perspective/head-scale params | 73.8 | shade mix, lines |
| 3 | `tune_style.py`: histogram-matched thresholds, light/lines/grain search; supersampled outline | 79.2 | front flipper missing; where light falls (50%) |
| 4 | Tilt params for both front flippers; right flipper identified as the visible one | 80.4 | shading placement |
| 5 | Learned matcap lighting | 80.7 | face in profile, Showdown's looks at the viewer |
| 6 | Eye whites in shell colours; eye landmark in the fit; head turn/pitch freed | 80.7 | head too small (fit shrank it) |
| 7 | Shading scored within 1 px; lone-line metric | 84.9 | stray pale edge pixels |
| 8 | Colour point-sampled at pixel centres (fixes white edge pixels) | 84.1 | head size |
| 9 | Head scale ≥ 1.0; refit | 85.9 | parts 0.83, shading 0.75, shell grain 19% vs 32% |
| 10 | Per-part grain + line-fragment metrics (stricter); retune | 85.2 | pose: parts 0.83 |
| 11 | Body roll, neck side-bend, tail swing, rear-flipper tilt added to the fit (20 starts) | 85.0 | fit gained only 0.001: pose is at this rig's ceiling |
| 12 | Final full loop (89 × 30 ms), scored on frame 0 of the GIF | 85.1 | user: "unclean random black grains" |
| 13 | Speck cleanup (see "Cleanliness" above); `dark_specks` metric added, speck/fragment metrics made one-sided (fewer than Showdown is fine) | 85.6 | user: black flickers near fins and mouth; eyes blurry; shell lines too thick |
| 14 | Eye stamp; 1-px lines everywhere; shape + layer + pixel stabilisation over time with time-aware repair; `check_loop.py` | 86.0 | whole loop: dark flicker 689 → 1, any-colour blinks 2822 → 8, 2×2 line blocks 1522 → 0 |
| 15 | User: double lines under the chin, faint glitches, 2-px diagonal outlines, flicker at shell/fins. Pixel-perfect lines (diagonals count), cream overlap lines in darkest cream, stray-pixel cleanup, canvas margin, eye held ≥ 3 frames, time-aware choice in every repair, ghost-eye cleanup | **83.6** | whole loop: 0 thick lines, 0 2-px diagonals (were ~90/frame), dark flicker 3, any-colour blinks 11. Score drops only in "lines": Showdown itself has staircase corners we now forbid |
| 16 | User: shell looks too sharp - is Showdown like this? Measured: rim lines matched but 46 interior shell lines vs Showdown's 8, and no highlights vs 8.6%. Per-part fold/depth thresholds for the shell, shell highlight, stray-pixel cleanup taught that a part's highlight colour belongs to it | **82.9** | shell: rim 32 (35), inside 7 (8), highlight 9.9% (8.6%); loop: dark flicker 2, blinks 7, 0 thick lines, 0 2-px diagonals |
| 17 | User: Showdown does have a set of lines on the shell, and a mouth line. Mapped both pixel by pixel: shell lip = outline, lip, `=`, `#`; mouth = `=` on the blue side of the jaw. #16 had removed the lip crease (a depth line) with the spike lines. Restored via per-part minimum line length, crease shade on the lip side, spike-only highlights; mouth via eye-relative border lines | **82.2** | shell rim 34 (35), highlight 8.4% (8.6%); loop: dark flicker 2, blinks 7, 0 thick lines, 0 2-px diagonals |
| 18 | User: giant flicker + outline spam on the shell, and why isn't that caught automatically? Added line placement, visible-flicker and pop checks, the `qa.py` gate in `make_gif.py`. Measured the cause (pops 7.6 vs Showdown 3.8, 36 vs 22 steps; flat-colour floor 1.8) and ablated it: per-frame detected lines made ¾ of the pops. Tried longer votes, hysteresis, fixed-distance lip lines, surface-voted lines, Freestyle 3D lines: none fixed it. Carrying frame 0's line drawing through the surface pass did; tail sway halved (motion) for the thin flipper tip | see final QA | pops 7.6 → 4.8 before the tail change, steps with pops 36 → 18 (Showdown 22) |
| 19 | Remaining pop was a genuine motion artefact: the breathing rock shifted the rear flippers' base, and the long thin flipper tip crossed a pixel row in one step. Motion change (ours to choose): rear flippers stay planted (thighs cancel the breathing) and the breathing rock is halved (1.5° → 0.75°) | **83.9** | **QA PASS**: largest pop 3.18 (Showdown 3.8), steps with pops 11 (Showdown 22), extra lines 15, thick lines 0, 2-px diagonals 0, dark flicker 4, blinks 11 |
| 20 | User: shell still not like Showdown's. Pixel diff: our lip had a cream highlight band where Showdown has `= #`, the crease was missing, highlights in the wrong place. Added a per-part colour-mix check (`shell_mix_l1`, was 0.336) to the gate; lip structure as a shifted copy of the border; highlights off the lip; relative rim; `--auto` now fits a failing part's shade thresholds itself and saves the winning remedy | **84.7** | **QA PASS**: shell mix 0.112, largest pop 3.18, pops 20, extra lines 15, thick 0, 2-px diagonals 0 |
| 21 | User: lip lines 'so thick, what happened to my rule', and colour leakage at the shell outline; make sure checks catch both. Cause 1: the dark-blue lip line next to the grey outline wasn't counted as line, so the 1-px rule never saw the 3-px band; it is now (`dark_line_colours`), the lip `=` shade is gone. Cause 2: no check for part outlines; `clean_lines` / debounce removed separator pixels. Added `open_outline` (was 1167, then 370), separators are never pruned, `seal_parts` closes gaps choosing the fix that makes no 2-px line, 1-px shell slivers are absorbed, T-junction corners exempt (like silhouette closures), a rule-safe final debounce, and silhouette dents filled (`silhouette_teeth` check) | **84.3** | **QA PASS**: open outline 0, thick 0, 2-px diagonals 0, dark flicker 3, blinks 5, largest pop 2.99, pops 21, shell mix 0.104, teeth 1.9/frame (Showdown 4) |

### Lessons from the leakage / thick-lip fix (#21)

* **Define "line" once and use it everywhere.** The drawing step thought the dark blue was
  shading; the checks thought only the grey was a line. A dark band of two line colours is
  a 2-px line. `dark_line_colours` is the one list both use.
* **A check and its fix must share code.** `check_loop.part_masks` decides what counts as
  shell vs other (the shell's highlight colour counts as shell where it touches shell);
  `seal_parts`, `clean_lines`' separators and the check all call it, so they can't disagree.
* **Some pixels are required by two rules at once.** A part line meeting the outline makes
  an L-corner / hugging pixel that the 1-px rule would prune but the closed-outline rule
  needs. Treat it like the silhouette's closing corners: exempt in the check, kept in the
  cleanup. Exemptions are only for pixels whose removal would *break* another rule.
* **Fix last-step blinks with the checks as referee.** Per-frame fixes after the time
  debounce blink. Debounce again, but keep a change only if that frame's hard-fault count
  doesn't rise; if a single pixel can't change alone, try its 5×5 neighbourhood, then hold
  the neighbourhood as the previous / next frame draws it. Blinks 15 → 5.
* A 1-px sliver of an outlined part can't have its own outline without a 2-px line:
  absorb it into the neighbouring part.

### Lessons from the flicker / line-width fix

* Measure the whole loop (`check_loop.py`), not frame 0: the specks fix looked done on frame 0
  but the loop still had 689 short dark blinks.
* Stabilise in order: shape first, then layers (lines/rim/shade), then final pixels. Debouncing
  only final pixels fights the outline repair (a pixel goes outline → body → outline forever).
* Repairs must look at the neighbouring frames: when a 2×2 block has to be broken, change the
  pixel to the colour it has before/after, or the fix itself becomes a blink.
* Point-sampled features (eyes) can't be stable at sprite size: draw them from a stamp.
* The remaining 8 single-pixel blinks are where the outline must move to stay closed (shell
  join, rear-flipper tip); requiring 3-frame runs instead of 2 only took it to 5.

### Lessons from the shell

* Matching a *total* (all inner lines) can hide a wrong *distribution*: the tuner matched
  Showdown's line count by putting lines inside the shell that Showdown keeps on the rim.
  Measure per part and per place (rim vs interior) before trusting a match.
* Protruding details (spikes) make depth-jump lines across the surface; give such parts
  their own, stricter thresholds.
* Look for highlight colours borrowed from another part (Showdown's shell uses the belly's
  cream-white for its highlights), and tell cleanup passes they belong.

### Lessons from the shell, round 4 (#20)

* "Looks different" needs a per-part check: whole-sprite colour mixes and line counts were fine
  while the shell's inside was wrong. A part-area colour mix (lines, shades, highlights
  included) flagged it at once (0.336) and tracked every fix down to 0.112.
* For bands that follow an edge, copy the edge (shift it), don't threshold a distance field:
  distance isolines rearrange in jumps as a diagonal edge moves; a shifted copy can't.
* A stray-pixel cleanup must know every colour a part may legitimately contain (highlights,
  shades borrowed from other parts) or it silently erases them.
* Anything I tuned by hand twice became automatic: `--auto` fits a failing part's shade
  thresholds and writes the winning remedy back to the config.

### Lessons from the quality gate (#18)

* A check passing means nothing if it can't see the failure: write the check from the user's
  complaint first (here: "something changes that isn't motion, and it's loud"), confirm it flags
  the bad build, then fix.
* Calibrate every limit against the reference (Showdown's own GIF) and a floor (the same motion
  with no styling): that separates "our styling flickers" from "the animation moves".
* Ablate before fixing: switching features off one at a time showed per-frame line detection
  caused most pops, saving more guessing.
* Check which bone actually moves a part before changing motion: the rear flippers hang off
  the thighs, not the tail, and moved because the body's breathing rock shifted their base.
* Anything decided independently per frame at 1 px will flip. Decide once and carry it
  (lines via the rest pass); threshold tricks (votes, hysteresis, fixed distances, 3D line
  tracing) all failed because each frame still decided on its own.

### Lessons from the shell lines and mouth (#17)

* Read the reference pixel by pixel (print it as characters, ours beside it) before tuning:
  the shell's lower edge is a fixed 5-step structure, and the mouth is a border line, not a
  crease. Counting lines (as in #16) missed both.
* Separate lines by kind, not just by threshold: the lip crease and the spike lines were both
  depth lines; length told them apart (long crease vs short spike pieces).
* Where a feature exists in the model but breaks up at sprite size (the mouth crease), draw
  it from a rule anchored to a landmark (border line in a box relative to the eye).

### Lessons from the pixel-perfect pass

* "1 px" has to count diagonals: a staircase with filled corners is 1 px in a 2×2 test but
  reads as 2 px. Check both (`check_loop.py` does).
* Time smoothing and line rules fight unless every repair looks at the neighbouring frames
  and picks the fix that agrees with them; when there's no such fix, 1 px wins.
* Debounce must not smear the eye stamp (ghost pupils): smooth everything, then redraw the
  eye and clear eye colours left where the eye was in another frame.
* Treat beyond-the-canvas as outside, and keep a 1 px empty margin: the sprite touching the
  canvas edge broke the outline checks at the head top and flipper tip.
* On a black background the outline (`#373f43`) almost disappears and the darker shade just
  inside reads as the edge, so check renders on black as well as on a light background.

### Lessons from the speck fix

* The grains had three separate causes: (1) grain compared each pixel with a local average
  that crossed part borders, so every cream pixel next to blue looked "dark" and dropped to
  the darkest shade; (2) fold/overlap lines breaking into 1–3 px dashes; (3) grain jumping
  two shades. Find causes by switching features off one at a time and counting.
* After changing anything that alters the light values (grain, matcap), re-run
  `learn_matcap.py` and `tune_style.py`: stale thresholds put 3× too many pixels in the
  darkest shade.
* Check the whole loop, not just frame 0: specks that move each frame read as flicker.

### Where it still differs (final, frame 0)

| Metric | Ours | Showdown | Notes |
|---|---|---|---|
| Size | 96×84 | 94×84 | |
| Silhouette overlap | 0.895 | 1 | remaining shape gap is the pose: Showdown's frame comes from the game's own idle animation, which we can't reproduce exactly |
| Parts in the same place | 0.837 | 1 | same cause |
| Shade band within 1 px | 0.755 | 1 | mostly follows the pose gap |
| Palette mix (L1) | 0.080 | 0 | all 15 colours, same proportions within ~2% |
| Outline / inner / stair corners | 335 / 192 / 27.7% | 325 / 201 / 28.3% | matched |
| Lone pixels / fragments / dark specks | 0 / 3 / 2 | 5 / 9 / 2 | cleaner than Showdown on purpose (after #13) |
| Whole loop (after #15) | 3 dark flicker, 11 colour blinks, 0 thick lines, 0 2-px diagonals | 759 on the flicker metric; 28% staircase corners | stabler and stricter than Showdown on purpose |
| Grain blue / cream / shell | 6 / 5 / 16% | 7 / 7 / 32% | shell texture detail is too smooth at sprite size; more grain there hurt other metrics |

Possible next steps: fit against several Showdown frames at once (more pose evidence),
and derive shell grain from a sharper texture-detail filter.

## 6. Second Pokémon: Mega Glimmora (Legends Z-A rip)

Files: `../../glimmora-model/` — `glimmora.json` (config), `MegaGlimmora/` (the extracted zip +
`MegaGlimmora.blend`, imported from the `.fbx`), `reference/`, `make_reference.py`,
`mega_glimmora_sprite.gif` / `_4x.gif` / `.qa.json`, `compare_frame0.png`. The pipeline scripts are
shared: run them from `lapras-model/Lapras/` with the Glimmora config path.

**Reference.** Showdown has no real Mega Glimmora sprite: `sprites/ani/glimmora-mega.gif` is a
single 90×90 still, an anti-aliased render (239 colours, soft dark rim), not an animated pixel
sprite. So: the still gives camera, pose, silhouette and colours; `make_reference.py` snaps it to a
12-colour palette (edge + very dark pixels → outline) as `reference/showdown_frame0.png`.
Showdown's real **base** Glimmora animated sprite (`reference/showdown_base_frame0.png`) gives the
conventions: 1-px dark outline, ~30 colours, flat bands, and it calibrates the teeth limit (6/frame).

**Steps taken** (same as section 3): FBX import (Blender reads FBX + armature directly, no assimp) →
config (parts by material group, see below) → `fit_pose` (camera + body turn; part match 0.70) →
petal scale / spread sweep scored by `compare.py` → idle motion → `learn_matcap` → `tune_style` →
`make_gif --auto` → visual check → grain off.

**Pipeline changes this needed (all generic, Lapras re-checked: still PASS, same numbers):**

| Change | Why |
|---|---|
| `render.depth_range` (was hard-coded ±250 units) | Switch rips are ~3 units tall: depth pass would be 1–2 grey levels |
| `fit_pose.py` uses its own folder's `render_sprite.py` | one copy of the pipeline for every Pokémon |
| pose axes `LOCX/LOCY/LOCZ` (world translation) | petal spread, bob |
| `parts.materials` value `"petal\|teal"` = material limited to those parts (nearest albedo among them) | petals' dark bases were nearest to the *spike* colour → grey specks inside petals |
| `style.transport_shading` (frame 0's shade ranks carried through the rest pass) | option for small idle motions; on for Glimmora |
| `check_loop.gif_frames`: frames expanded by GIF duration | Pillow merges identical consecutive frames; the checks then saw a 2-frame hold as a 1-frame blink (52 fake flickers) |
| `qa.py` checks any `<part>_mix_l1` in the limits | Glimmora gates `core_mix_l1`, `petal_mix_l1` |
| `compare.py --json` skips internal arrays | crashed on `_lines` |

**Motion (ours).** Petal ring sways 3° around the spike axis (applied before the body turn, so it's
the flower's own axis). A 3-D bob and a 4° sway were rejected by the gate: they made 1-px gaps
between petals / crown open and close (pops 4–6). Petals pushed 0.18 units out so no gap is borderline.

**Final QA: PASS** — style 80.1, extra / missing lines 0 / 1, thick 0, 2-px diagonals 0, open outline 0,
dark flicker 0, blinks 0, largest pop 3.74, steps with pops 11, teeth 4.0 (limit 7.5 = 1.25 × Showdown's
Glimmora), core mix 0.16, petal mix 0.05. The style-score margin is thin (80.1 vs 80).

**Where it still differs:** the crown reads as one lilac mass (the still shows separate spiky
lilac petals with a bright teal star); the petals' teal stalks show where the still hides them;
our sprite is 76×88 vs the still's 82×87 (narrower). Outlining the crown made 176 extra line px
(the still separates crown and petals by colour, not lines), so it's off.

### Lessons from Glimmora

* **Check the reference is a real sprite** (frame count, colour count) before matching it.
* **Restrict parts per material** when textures share colours across parts.
* **Thin gaps between moving parts are the main pop source** for multi-piece Pokémon: choose the
  motion so nothing passes within ~1 px of another piece.
* **The gate catches the tuner too:** `tune_style` re-enabled grain for score; the user's rule wins.

### Glimmora round 2: "Showdown's shadows are more obvious, higher contrast"

Measured first: the shade *amounts* already matched (petal mix L1 0.02); the *placement* didn't.
Showdown's still has whole dark petals (bottom 65 % darkest navy, lower-right 40 %) and light
ones (upper 7–12 %); ours put the darkest navy in a thin band along every petal's outline
(petal dark-rim excess +0.106) and spread it evenly over all petals (16–35 % each), so every petal
averaged out to mid-blue.

| Change | Why |
|---|---|
| `render.shadow` pass: white diffuse lit by one hard sun, no ambient (`render_sprite.py`) | per-pixel *cast* shadows: faces the sun but blocked (N·L from the data pass vs what arrived) |
| `style.cast_shadow` {strength, unlit_strength, mode, cover} | pushes cast-shadowed pixels (and, gentler, faces turned from the sun) into the dark shades as solid masses |
| `fit_shadow.py` (grid of sun directions incl. from behind, `--dirs` for finer search) | fits the sun to the reference; for Glimmora: from above, slightly behind (0, 0.985, −0.174) |
| `learn_matcap.py` skips cast-shadow pixels | otherwise shadowed petals teach the matcap that those facing directions are dark |
| `style.edge_lift` {petal: 0.2}; `rim_light` −9 pinned (`style.tune_fixed`) | the rim came from the petals' curled-away edges, not the matcap ring (an edge clamp didn't move it) |
| `tune_style.py`: the gate's shadow limits are constraints (100 pt per unit of violation); `tune_fixed` for pinned knobs | the tuner had traded the shadows (and turned grain back on) for score |
| `compare.py`: `shadow_f1`, `dark_rim_excess` (worst part), `blob_shade_err` (how dark each separate piece is vs Showdown's same piece) → `qa.py` | the old checks couldn't see placement: counts matched while the picture didn't |

Limits (Glimmora): shadow_f1 ≥ 0.68, dark_rim_excess ≤ 0.03, blob_shade_err ≤ 0.06 (before: 0.679,
+0.106, 0.082). Things that didn't work: any single sun from the viewer's side (no cast shadow lands
where Showdown's darks are), sun lighting instead of the matcap (style −5), stronger cast shadows
(piece error up: too dark everywhere), the matcap edge clamp.

**Final QA: PASS** — style 81.2, shadow_f1 0.699, dark_rim_excess −0.089, blob_shade_err 0.059 (thin
margin), pop max 3.17, all hard rules 0. Lapras re-checked: PASS (no shadow config, unchanged).
Still different: Showdown's bottom petal is darker (0.13 mean shade vs our 0.23; ours touches the
lower-right petal, so the piece check sees them as one).

**Lesson:** match where shades go, not just how many — check placement per piece.

### Glimmora round 3: the crown ("Showdown's central flower has real definition")

Cause, measured: I had switched the crown's inner lines off in round 1 (they showed up as "line
spam" against a reference that had lost them); the reference had lost them because snapping the
still to a 3-shade crown palette turned its slate-lilac separators into flat body colour; and the
crown had 3 tones against the still's 63. Crown edge share was 0.70 of Showdown's: a blob.

| Change | Why |
|---|---|
| crown palette 5 shades: `#495379` separator (core:0, line only: `first_shade` 1, `inner_line`, `dark_line_colours`), 3 lilacs, pale lilac | from the still's crown clusters |
| `make_reference.py`: `reference_hue_parts` {part: [hue lo, hi, (sat lo, hi)]} | the separator, the grey-teal spike and the petals' sheen are close in RGB, not in hue / saturation |
| `make_reference.py`: `reference_thin` {"core:0": "core:1"} | the still's soft dark bands snap 2–3 px wide; Showdown (and our rule) draw 1-px lines |
| spike palette from the spike itself (`#32434a #486674 #658b9e`) | the old one was dark crown shadow mislabelled as spike |
| `style.hires_lines` {parts, source: freestyle \| depth/fold at full res, cover} | sprite-resolution detection lost a third of the crown lines when the loop's crop box shifted sub-pixel; the mesh-traced lines pass (Freestyle) outlines every crown petal |
| `style.behind_shade` (option, not used: no visible gain) | shade beside a line on the deeper side |
| `compare.py` / `qa.py`: `<part>_edge_ratio` (`qa.structure_parts`) | how much of a part is drawn as edges vs Showdown; a blob scores low |

**Final QA: PASS** — crown edge ratio 1.18 (limit ≥ 1.0, was 0.70), crown colour mix 0.153 (≤ 0.17),
style 82.7, lines extra / missing 0 / 3, shadows (F1 0.715, piece error 0.052), all hard rules 0, pops
3.26. Lapras re-checked: PASS.
Still different: Showdown's crown separators read stronger because the faces beside them are the
bright lilacs; ours sit more often beside the darker body lilac. The teal star is less crisp.

**Lessons:** when a reference is built from a render, check what the snapping keeps before fitting
to it — every later fit inherits its losses. Detect thin-feature lines at full resolution (or from
the mesh), not from point samples at sprite size.

### Glimmora round 4: crown pose ("maybe it's too small?")

I first reported Showdown's crown as 52×39 px against our 33×40, "wide with long petals reaching
back". That was wrong: one stray petal pixel snapped to a crown colour stretched the bounding box.
Measured properly (2–98 % extent) both crowns are 28×33 px with the same area, and their
footprints overlap almost entirely (shape F1 0.981). A crown-weighted pose fit of the six crown
petal bones (`skirt_01`, new `A:x,y,z` any-axis rotation in `render_sprite.py`, `fit_weights`
{core: 0.5} and `--only` in `fit_pose.py`) moved them 1–7° for a score change of 1.150 → 1.152, left
the footprint unchanged (0.979), and nudged the crown's cast shadow enough to fail blob_shade_err
(0.062). Kept the rest pose; the parameters stay in the config at 0.

New check: `<part>_shape_f1` (qa.structure_parts) — the part's footprint vs Showdown's, F1 within
1 px; `core_shape_f1` ≥ 0.95. Box extents now use the 2nd–98th percentile.

**Lesson:** never trust a bounding box built from snapped colours — one stray pixel moves it.
Look at the footprint itself before concluding anything about size.

### Glimmora round 5: fuller crown ramp

From the still's crown clusters: a 6-tone lilac ramp (`#575c9f #6269b5 #6b70cf #7075d9 #6f89d5 #8390df`,
the bluer `#6f89d5` = light on the ridges) after the `#495379` separator, and the muted mauve back
bulb (`#756e97`, hue 0.695) as its own part `bulb` (`#5f5a85 #756e97 #8c86b0`, albedo `#a0a0d0`, material
group `core|teal|spike|bulb`, hue/sat range in `reference_hue_parts`) — it's a different surface, not
a step of the lilac ramp. Reference re-snapped (19 colours).

New check: `<part>_tones` — shades of a part in use (each ≥ 1 % of it); Showdown's crown uses all 7,
the bulb 2 → limits core ≥ 7, bulb ≥ 2.

Re-learning the matcap on the new crown shifted the petals' shading (it's learned over all parts):
shadow_f1 0.656 and piece error 0.068 failed. Kept the previous lighting and petal thresholds; only
the crown / bulb thresholds were fitted (`--auto`).

**Final QA: PASS** — core tones 7, core mix 0.12 (was 0.153), crown edge 1.31, crown shape 0.978,
style 81.6, all hard rules 0, pops 3.03. Thin margins: blob_shade_err 0.060 (limit 0.06), shadow_f1
0.684 (≥ 0.68). Lapras re-checked: PASS.

**Lesson:** a learned lighting model shared by all parts couples them: improving one part's
palette can move another part's shadows. Re-check every part's metrics after re-learning.

### Glimmora round 6: the animation (float, crown breathing, petal spin)

Ours (Showdown has no Mega Glimmora animation). 180 frames = 5.4 s:
* **float** 2 px, twice per loop — `style.pixel_bob`: a whole-pixel shift of the finished sprite (the
  3-D bob of round 1 popped at thin gaps; a whole-sprite shift adds no new shapes)
* **crown** opens 14° and closes once (`CROWN_OPEN`, skirt bones; frame 0 at rest = Showdown's still)
* **petal spin** 720° over frames 110–150, eased (`SPIN_DEG * smooth((t - SPIN_T0)/SPIN_LEN)`); peak
  27°/frame, under the 30° at which a ~60°-symmetric ring seems to turn backwards; a whole number
  of turns ends where it started

| Change | Why |
|---|---|
| pose expressions get `t`, `ts`, `pi`, `sin`, `cos`, `smooth`, `min`, `max` | timed events |
| `ts` = "slow time" (`slow_t`): loop position with `style.fast_frames` cut out | slow motions pause during the spin, so the frames around it join seamlessly (without it: a 13.2 pop right after the spin) |
| `style.fast_frames`: drawn per frame with the same rules (repair, seal, 1-px lines) but no time smoothing; the rest stabilised as a loop of its own | debouncing a spin would freeze or smear it |
| `smooth_silhouette` for fast frames | odd petal angles left spurs / notches (teeth 14.4 in spin frames → overall 5.8) |
| `framing(anchor=...)`: grid fixed by the slow frames, grown by whole sprite px (picked to land on whole render px) | the spin's in-between poses widened the box and shifted frame 0's sampling (shadow F1 0.683 → 0.661) |
| checks: `check_loop.unbob` undoes the float before time-based checks; blinks / flicker / pops skip the fast frames (every per-frame rule still applies to them) | the float is rigid motion, not flicker (it read as 3500 blinks); a spin changes every pixel by design |
| `make_gif --auto`: the shade fit treats the gate's shadow limits as constraints | it fitted the colour mix while pushing piece error over (0.062) |

**Final QA: PASS (20 checks)** — style 81.5, hard rules 0, blinks / flicker 0 / 0, pop max 3.28, teeth
5.77, shadows 0.681 / 0.059, crown edge 1.33, shape 0.977, tones 7. Thin margins: big_pops 22 (= limit),
blob_shade_err 0.059, shadow_f1 0.681. Lapras rebuilt from its frames: pixel-identical, PASS.

### Glimmora round 7: easing ("the floating is so hard and stiff, the spinning too")

Why it was stiff: the float was the whole sprite moving as one block in 1-px jumps (held 3–16 frames)
and it **froze** for the 40 spin frames; the spin ramped straight to 27°/frame and back to a dead stop
with no wind-up or follow-through, while everything else stood still.

Now: the float never stops (3 bobs per loop: its 60-frame period equals the spin window, so the
frames on either side of the spin still match); the spin is a wind-up back 20° (sin² ease), two
turns with smootherstep (peak 29°/frame), an overshoot of 16° that settles (sin²) — every phase
starts and ends at zero speed. The petal sway swings one way only (0 → −3°): past about +1° the
lower-right petal came within 1 px of the crown's spike and that gap popped (5.6).

Tried and dropped — petals trailing the float (follow-through): in 3-D sub-pixel steps the petal
edges re-rasterised (pops 4.9, 30 steps); 3.5 px of trail moved cast shadows across petals (pop 19);
whole-pixel steps along the camera's up (`LOCCAM`) jumped petals against the crown (9 failures). The
pixel-art rules (no anti-aliasing) leave no room for sub-pixel secondary motion here.

| Change | Why |
|---|---|
| pose helpers `smoother` (smootherstep), `bump` (sin²), `round`; axis `LOCCAM` | eased events |
| `pixel_bob` on real time (`slow_time` optional) | the float shouldn't pause during the spin |
| fast frames: repair + 1-px cleanup repeated until `hard_faults` is 0 | the last cleanup could reopen an outline pixel |
| `style.frame_anchor: "first"` — frame 0 keeps its own pixel grid (the one tune / fit / compare use), the box grows by whole sprite px | any motion change moved the box by a render px and resampled frame 0 (shadow F1 0.680 → 0.676) |
| `make_gif --auto` shade fit: shadow limits weighted 100 (as the tuner) | ×10 let it trade a small shadow violation for colour mix |

**Final QA: PASS (20)** — pop max 2.89, big pops 15, flicker / blinks 0 / 0, shadows 0.686 / 0.056,
crown edge 1.25, shape 0.983, tones 7, style 81.2. Lapras rebuilt from its frames: pixel-identical, PASS.

### Glimmora round 8: speed, a smooth float, crown breathing

**Speed** ("I don't want another 1-hour run"). Where the time went: one Blender process rendering
every frame in turn, and `rule_safe_debounce` re-checking the *whole frame's* hard rules for every
candidate pixel (a build hung > 8 min). Now: `render_parallel.py` (4 processes, interleaved frames),
`rule_safe_debounce` checks a 13×13 window around each pixel (verified pixel-identical output),
`clean_parts` keeps a candidate heap, and `preview_check.py` checks a motion on 5–6 frames before a
full run. A full attempt (render + build + QA) went from ~1 h to 30–110 s.

**Motion limits calibrated on Showdown** (`calibration/floating_carbink.json`). A floating Showdown
sprite is re-drawn every frame (~25 % of its pixels change per step); the absolute limits learned on
Lapras's near-still idle would fail Showdown's own Carbink 1000×. The same checks were ported to JS
and run on Showdown's GIF in the browser (pixels read in-page, never downloaded), and normalised so
any sprite size and loop length can share them: `blink_rate` / `dark_flicker_rate` per frame per solid
pixel, `pop_max_norm` = largest pop / √(solid px / 1000), `big_pops_share` = share of steps with a pop
≥ 2. The per-frame rules (1-px lines, closed outline, teeth) stay strict whatever the motion.

**Smooth float with desync** ("inching up pixel by pixel"). Split float: the whole-pixel part of the
bob is `pixel_bob` (a rigid shift: no new shapes), only the fraction is rendered in 3-D (`LOCCAM` on
the root bone), so edges re-rasterise by at most one pixel's worth. The crown leads and the petals
trail (`LAG_PH` 0.2 of a cycle, `RIPPLE` 2 % tilt); `FLOAT_PX` is chosen so frame 0 lands on a whole
pixel (frame 0 is the one compared with Showdown). **Crown breathing**: the crown petals open
`BREATH_OPEN` 15° and scale `BREATH_SCALE` 8 % on the bob's rhythm.

### Glimmora round 9: natural levitation, a menacing spin, a shake

User: "the levitate should be more natural (reference Pokémon that fly and levitate), the spin more
natural and menacing, maybe an occasional shake". Measured on Showdown's floaters in the browser
(centroid / principal-axis per frame, pixels read in-page): base **Glimmora** bobs 6.7 % of its height
over 90 frames and drifts 5.5 px sideways about a third of a cycle behind the bob, hanging at the
crest (~14 frames within 0.1 px) and turning quicker at the trough, rocking ~±4°; Bronzong 8.5 % / 79
frames, Claydol 7 % / 79, Carbink 14 % / 83, Cosmoem 13 % / 89 with a sideways orbit and ±20° rock,
Nihilego 7 % with a figure-eight drift. Ours was a pure vertical sine, 11.6 % every 60 frames, no
drift, no rock: too big, too fast, too mechanical.

Now (`glimmora-model/set_motion.py` writes it into all five Glimmora configs), 270 frames = 8.1 s:
* **float** 3 × 90 frames, 7 px (8.3 % measured), `wave(p, skew)`: crest broad, trough quick;
  **drift** 2.5 px a quarter cycle behind (egg-shaped orbit; 5.3 px measured); **pendulum rock**
  `TILT_DEG` 3° (leans out at the ends of the drift, `ROLLCAM` on the waist); petals trail by 2.5
  frames. Frame 0 is still the fitted rest pose on a whole pixel (crest, no drift, no tilt).
* **shake** frames 78–104 (slow frames, hanging at a crest): whole-pixel rattle ±2 px, 2 frames per
  swing, sin² envelope (`jitter`), crown and petals bristle.
* **spin** frames 150–239 (fast frames, exactly one float cycle): charge 20 frames (crown clenches,
  petals tuck and wind back 40°, body dips 2 px and trembles 1 px), snap release
  (`smoother(u^0.7)`: peak 24.6°/frame at frame 17 of 56, then a long coast), crown flared, petals
  flung out, body lifted 3 px and counter-rolled 4°, overshoot ~6° / recoil ~7° / settle
  (`damp`, eased in so it joins the coast without a speed jump).

| Change | Why |
|---|---|
| `motion.py`: shared helpers (`smooth`, `smoother`, `bump`, `damp`, `jitter`, `wave`) and `motion.functions` (named functions of t, callable from every pose expression) | one formula for the rendered sub-pixel part and the whole-pixel shift |
| `style.pixel_bob {"y": expr, "x": expr}` → `motion.offsets`: whole-pixel shift in both axes (old `{amplitude, cycles, phase}` form unchanged) | drift and shake are rigid shifts: no new shapes, nothing to pop |
| pose axes `LOCCAMX` (camera right), `ROLLCAM` (tilt about the view axis) | sub-pixel drift; in-picture rock |
| `check_loop.unbob` undoes x and y | the shake / drift are known shifts, not flicker |

**QA: all four PASS** — front: pop_max_norm 2.81 (limit 6.86), big_pops_share 0.30 (0.759), teeth
2.86, style 81.4, shadows 0.685 / 0.057, crown edge 1.20, shape 0.984. The 3° rock re-rasterises the
whole sprite every frame and still stays far under Carbink's limits.

## 7. Back views and shinies (all three Megas)

**Back views, Showdown back style**: seen from behind and above, the front's turn mirrored. Where
Showdown has the normal form's back sprite and the shapes are alike (Golisopod, Glimmora), the camera
is fitted silhouette-only to it (`fit_reference` + `fit_silhouette_only`); the sprite height follows
Showdown's own back / front ratio. Mega Dragalge's wings make its shape unlike the normal form's, so
its back camera is the front's turn mirrored behind (azimuth 270 − 22), looking down 18°.
`smooth_silhouette` is on for every view (back views showed 1-px jags).

**Shinies are recolours of the finished normal sprite** (`palette_swap.py`), the way Showdown's are:
identical shapes, lines and motion; only the palette changes. Re-rendering with the shiny textures
(the first approach) moved shade bands and failed pops where the normal passed (Golisopod back 3.79).
* `make_shiny.py --keep-steps`: hue/chroma from the shiny textures (per part, in Lab), but each shade's
  *brightness step* is kept from the normal ramp (Rec.601 luma, the measure the pop check uses),
  compressed below white instead of clipped. Scaling by the light ratio (old way) stretched
  Golisopod's armour steps from 0.15 to 0.20 and clipped the top to #ffffff.
* A part whose shiny colour differs must not share colours with one whose doesn't: two parts with one
  palette can't be told apart in the finished sprite (Dragalge's `iris` is a hair off `red`: the eyes
  stay red, the chest turns green). `palette_swap` refuses a non one-to-one map.
* One-part material groups count all their texels for that part (`make_shiny` fix: Dragalge's fin
  texels had diluted the accent purple's measured change).
* Glimmora's shinies were re-made the same way (both pass).
* Golisopod's shiny back was the one place a recolour scored worse than its normal (big-pop share
  0.82 vs 0.52): brighter armour has more contrast against the outline, so every line move weighs
  more. Showdown's own Golisopod shows the same effect (0.72 → 0.82 recoloured). Fixed by a normal
  build that passes with room (`steady_window` 2, height 91: shiny 0.67), not by loosening the limit.

## 8. Third Pokémon: Mega Golisopod (no reference)

Showdown has no Mega Golisopod sprite. Camera fitted silhouette-only to Showdown's normal Golisopod
(`reference/showdown_base_front.png`); palette from the Mega's own textures in Showdown's conventions
(4 shades per part, ramps brightened to Showdown's level, outline a near-black of the armour hue);
`match_shares.py` sets the shade thresholds to target shares (20 / 32 / 30 / 18 %). A first, murky
render was just the textures (grey on grey): brighter ramps + share matching fixed it.

Motion = base idle + a signature move (the user's choice), 120 frames: three 40-frame breaths
(spine `BREATH`, claw arms / forearms following a beat later, `FOLLOW` 1.5°, `ARM` 1.1°), and a claw
flex (frames 66–105: arms lift, pincers snap open and shut), drawn as `fast_frames`. The flex window
is exactly one breath long, so the slow frames still join seamlessly around it. Limits:
`calibration/idle_golisopod.json`; teeth 1.25 × Showdown's normal Golisopod (22 → 27.5).

Back: a 1-px purple spine tip flicked in and out over one breath step (pop 3.85 vs 3.75). Smaller
follow-through didn't move it (it is a threshold crossing, not speed); a different pixel grid did
(sprite height 91 + `steady_window` 2: pop 3.34, and its shiny recolour passes too).

## 9. Fourth Pokémon: Mega Dragalge

Showdown has only a placeholder (`sprites/ani/dragalge-mega.gif`: one still frame, a downscaled 3-D
render with ~200 colours, not pixel art). Used for: the silhouette (`reference/mega_still_sil.png`,
camera), and the part hues. It shows **olive horns** the composite textures don't have (the horns are
on the fins' flat purple texture): `kelp_mat.py` gives the horn-skinned fin faces their own
material (`MegaDragalge_parts.blend`, material `kelp_horns` → part `kelp`). Parts: skin (maroon),
kelp, fin (wings: stay purple in the shiny), purple (accents), red (chest), iris (eyes: stay red).

Camera: the silhouette fit scored only 0.53 (the placeholder's pose isn't the rest pose) and chose a
near side view that stacked both wings to one side; azimuths 10–90° were previewed and 68° matches
the placeholder's cape-like spread. Size: 5800 solid px at first — twice the normal form's 2895 —
so height 79 (~4050 px, 156 × 89).

Motion (160 frames, two 80-frame sways like Showdown's 79-frame normal Dragalge): body roll `SWAY` 3°,
head lagging against it, a ripple along each wing (`FIN` 1.2°, a lag per segment), wings held `REST`
8° up, tail and horn trail; signature **fin flare** (frames 97–144): head rears, wings sweep up 22°,
beat down once, settle. Problems found and fixed, each by the checks:
* **render clipped** — the flaring wing left the 460-px render and was cut straight. New hard check
  `render_clipped` in `make_gif` (any frame touching the render edge fails). Widening the render:
  scale `render.width` **and** `camera.ortho_scale` **and** FOV together (FOV alone only moves the
  perspective camera closer, it adds no margin).
* **legs in dashes** — the dangling feelers (its "legs") are thinner than a sprite pixel. New pose axis
  `SCALEW`: widen a bone chain without lengthening it. FBX bones run along X, not Blender's Y, and end
  in `_end` marker bones on another axis — the length axis is taken per bone from the direction to its
  real child (the first version stretched the legs off the render). Legs kept upright against the
  body roll and splayed 5°: an upright line shifts a whole column at once (pop 3.47), a slight slant
  steps a few pixels at a time.
* **hands sliding** — the arms (planted on the ground) hang off the spine, so the roll dragged them;
  each arm root counter-rotates.
* **wing tip vs hand** — a wing tip resting on a hand blade opened / closed a 1-px gap: wings held
  higher (`REST`).
* **hard faults left after cleanup** — `fix_faults`: greedy single (or paired) pixel changes at the
  fault, kept only if the frame's fault count drops; runs on any frame still failing after repair,
  slow frames included. Frame 96, where the flare's easing is still exactly 0, is drawn as a slow
  frame (a pinch where wing and body outlines merged had no small fix as a fast frame).
Limits: `calibration/sway_dragalge.json`; teeth 1.25 × Showdown's normal Dragalge (front 37 → 46,
back 47 → 58).

## 10. Final set (12 GIFs, each also ×4)

`final_sprites/mega_{glimmora,golisopod,dragalge}_{front,back,front_shiny,back_shiny}[_4x].gif`.
Verified together: every one passes QA re-run from scratch, every ×4 is an exact nearest-neighbour
enlargement, every shiny is an exact one-to-one recolour of its normal, no render touches its edge.

| Sprite | Size | Frames | Notes |
|---|---|---|---|
| Glimmora front / back | 96×119 / 106×121 | 270 | float + drift + rock + crown breathing + shake + charged petal spin |
| Golisopod front / back | 89×94 / 68×98 | 120 | breathing idle + claw flex |
| Dragalge front / back | 156×89 / 161×92 | 160 | underwater sway + fin flare |

## 11. Round 2 of the set: "looks kind of dirty, especially Golisopod and Dragalge"

**Why it wasn't caught.** Golisopod and Dragalge have no Showdown reference, so every check that
compares with one (style score, shade mix, line placement) was skipped; what remained were the
per-frame rules and motion. Nothing looked at whether the shading was *clean*.

**What "dirty" was, measured.** Not single-pixel specks (Showdown's sprites have more of those than
ours: 9–16 % of pixels are deliberate accents). Two things:
* **render noise in the shading**: each sprite pixel took its normal from one point of the render,
  so modelled detail (plate ridges, wing folds) flipped shade bands pixel by pixel — streaks on
  Dragalge's wings, mottled grey on Golisopod. Measured as `shade_slivers` (interior fill pixels
  with ≤ 1 same-colour neighbour): the builds called dirty 0.26–0.30, clean ones 0.06–0.13.
* **muddy tones**: Showdown's Golisopod puts 46 % of its pixels in the brightest band and 12 % in
  the middle greys; ours had 12 % and 49 %. Showdown's metal is a dark core plus light tones close
  to white (luma .37/.64/.87/.97); our ramp was evenly spaced (.39/.54/.69/.85).

**Fixes (style options, off unless set, so Lapras / Glimmora are unchanged — Lapras rebuilds
pixel-identical):**
| Option | What it does |
|---|---|
| `shade_blur` r | light averaged over a (2r+1)² window **within the same part** before banding (2; Golisopod back 3) |
| `min_region` n | shade islands under n px take the shade around them. n = 4: merging ≤ 3 px changes ≤ 3 × 0.6 brightness, below a big pop (2.0). 14 was tried: islands crossing 14 px popped whole (6.2) |
| `depth_jump` 3, `crease_cos` 0.5 | plate / feather lines, as Showdown's Golisopod draws every plate |
| `transport_lines`, `transport_shading` | lines and shading decided on frame 0 and carried with the body (more lines on brighter armour otherwise flickered: big-pop share 0.87) |
| Golisopod armour ramp | `#565d64 #939ca4 #cdd4da #eff3f6` (Showdown's metal spacing), shares 18/17/30/35 % |
| `match_tones.py` | for the back views: shade shares (peak shade + spread) fitted so frame 0's brightness mix matches the base form's Showdown back sprite (Showdown's backs sit mostly in one middle shade) |

**New checks (`qa.py`)**, which now fail every one of the old dirty builds:
* `tone_mix_l1` ≤ 0.35: brightness mix (5 luma bands) vs `qa.tone_ref`, the base form's Showdown
  sprite for the same view, all frames. Golisopod back: 0.45 — the Mega's palette gets no closer than
  0.37 to the base form's back. Normal sprites only: a shiny is a recolour whose brightness comes from
  the game's shiny textures (Showdown's own back / back-shiny Golisopod differ by 0.96).
* `shade_slivers` ≤ 0.15 (no-reference sprites; our limit, from the dirty / clean builds above —
  Showdown's hand-drawn detail scores higher but follows the forms; Glimmora, which has a reference,
  scores 0.27, the same as Showdown's Glimmora, and is held by its reference checks instead).
* `blotch_share` ≤ 0.011: small islands (≤ 12 px, corner-touching pixels joined) enclosed by one other
  colour — 2 × the median of 14 Showdown sprites (0.0052). The first version joined pixels by edges
  only and counted every step of a diagonal line as a fleck.
* `make_shiny.py` applies `qa.qa_shiny` limits where Showdown has a shiny of the same animation:
  Golisopod's shiny is its normal recoloured and scores big-pop share 0.821 vs 0.718
  (`calibration/idle_golisopod_shiny.json`).

Final: all 12 pass from scratch (Dragalge front without island merging or carried shading: the blur
alone passes; Golisopod back blur 3), ×4 exact, shinies exact recolours.

## 12. Golisopod's stance ("claws forward, like base Golisopod")

The Mega's big claw arms (`arm_01` → `arm_02` → `hand`; the pincers are `index` / `middle`) were in
the model's bind pose — a T-pose, straight out at shoulder height — and the motion only added
small swings on top, so the claws were held out level. Showdown's normal Golisopod (front and back)
hangs them at its sides, forearms down, claws forward and down at hip height, framing the torso.

Rest pose, ahead of the motion in `pose` (world-axis rotations, mirrored for the right arm):
shoulder down `SH_DOWN` and forward `SH_FWD`, elbow down `EL_DOWN` and forward `EL_FWD`, fitted with
the camera to the normal form's Showdown silhouette (`fit_pose.py --only`, silhouette 0.50 → 0.59;
22° / 8° / 19° / 25°, azimuth 60°). Swinging further forward hid the torso behind the arm's big
plate. The back camera refitted with the arms down: 201° / 16° (0.60). The signature became a claw
strike: the claws thrust forward `THRUST` 22° and up, the upper pincers snap. Lesson: check a rigged
model's bind pose before animating — game rips are usually T-posed, and a pose fitted only from small
offsets keeps the T.

All four Golisopod sprites rebuilt; all QA checks pass (front 95×97, back 83×99).

## 13. Inner lines that trace the armour (per Pokemon: seams)

"Notice how Showdown's Golisopod has inner outlines tracing the details on its head and armour."
Showdown outlines every plate and segment (a grid on the head plate, lobster-like bands on the arm
plates, each leg and hip plate). Ours found lines only at depth jumps and sharp folds, which
overlapping plates barely make.

Where the seams are: each armour piece is its own UV island, and the normal map carries the grooves.
`make_seams.py` paints them in texture space (island borders `--width` texels wide, plus texels where
the normal map tilts more than `--groove`), and the `seams` render pass is the colour pass with those
textures swapped for their seam maps — so lines sit on the surface and move with it exactly.
`style.seam_lines {parts, cover}` adds them to the drawn lines for the parts listed (a pixel is a line
when `cover` of it is seam; seams are 1–2 render px, ~5 render px per sprite px, so 0.12).

**This is a per-Pokemon choice, not a rule** (user: "sometimes seams matter more on some Pokemon,
sometimes they're less needed, like on Lapras"):
| Pokemon | Seam lines | Why |
|---|---|---|
| Golisopod | armour, cover 0.12 | Showdown traces every plate and segment |
| Dragalge | none | Showdown's Dragalge is soft and organic — shading and a few fin veins; its fins are one flat texture, and body seams fall on the outline of its thin limbs anyway |
| Lapras, Glimmora | none | few inner lines on Showdown's; Glimmora's crown lines come from Freestyle (`hires_lines`) |

More lines over near-white armour meant more line steps per frame: big-pop share 0.747 (limit 0.718)
at the old breath. The breath went from 1.2 / 1.5 / 1.1° to 0.7 / 0.9 / 0.7° (share 0.57); its bands
still move 0.2–0.6 px, against 0.3–0.8 on Showdown's Golisopod idle. All 12 sprites re-verified.

## 14. Artist rules as per-Pokemon settings ("make them configurable and scalable")

"Still feels messy compared to the base version." The render shows where light falls; Showdown's
artist shows what the shapes are. Four artist decisions are now settings. Each is off unless a
Pokemon's config turns it on (Lapras rebuilds pixel-identical), and each is generic: it names
parts, textures or numbers, never a Pokemon.

### Per-Pokemon options reference
| Setting | What it does | Golisopod | Others |
|---|---|---|---|
| `render.texture_passes {name: {maps, nearest}}` | renders maps painted in the model's texture layout (made by `make_seams.py`) as extra passes that stick to the surface; `nearest` for ids | `seams`, `islands` | — |
| `style.seam_lines {parts, cover, bridge}` | lines from the seams pass; `bridge` joins a seam split across two pixels | armour, 0.12, 0.04 | — |
| `style.plate_shading {parts, follow, edge {dark, width, dir}, cast}` | each plate (UV island) shaded as one unit: its mean light + `follow` × the 3-D light; `dark` darker along its `dir` edge; `cast: false` = no cast shadows on it | armour, 0.3, {0.35, 1, [1, 0]}, false | — |
| `palette.lines {part: "#hex"}` + `style.inner_line {part: "line:part"}` | a softer inner-line colour per part (in the palette, the 1-px checks via `style.dark_line_colours`, and recoloured with its part for shinies) | armour `#3d454b` | — |
| `style.min_line_px_part {part: n}` | removes inner-line pieces under n px in that part, even where they touch the outline | armour 4 | — |
| `style.part_tones {part: n}` | the part uses only n shades of its ramp | dark 2, purple 3 | — |
| `parts.min_region {part: px}` | pieces of a part under px pixels take the part around them (accent splashes, tiny spikes) | purple 6, dark 4 | — |
| `style.shade_blur`, `style.min_region` | see §11 | 2 / 3, 4 | Dragalge 2, 0 |
| camera `AZIMUTH` | Golisopod 60° → 80°: front-on like Showdown's, claws framing the body | 80° | — |

**When to use what**: armour or shell made of separate pieces (Golisopod, likely Scizor, Aegislash,
Corviknight) → seams + islands + `plate_shading`; soft or organic bodies (Dragalge, Lapras) → none of
it, `shade_blur` at most; small accent colours scattered by the render → `parts.min_region`.
New Pokemon: `make_seams.py MODEL_DIR TEXTURE --islands K` per texture (a different K per texture),
then list the maps under `render.texture_passes`.

### Fixes found on the way
* `render_parallel.py` reported nothing when Blender crashed: Blender prints tracebacks to stdout,
  which was discarded; both streams are now read, so a failed render fails loudly.
* `shade_slivers` decided what is a line by brightness (< .25); the softer armour line (.26) then
  counted every 1-px line as a sliver (0.173). It now uses the configured line colours (outline +
  `style.dark_line_colours`) and keeps the brightness rule only for Showdown sprites.

Golisopod front 108×98 (front-on), back 83×99; all 12 sprites re-verified (QA, ×4, exact shiny
recolours).

## 15. Speed (massive builds)

Rule: a speed change may not change a single pixel. `regress.py check` (build) and
`regress.py render-check` (every render pass) must say IDENTICAL for all four regression sprites
before it goes in; a Rust rule also passes `rust/check_kernels.py` on every call.

| Where | What | Settings |
|---|---|---|
| render | one Blender thread per process (more just contend: ~12% more CPU); shadows only in the shadow pass; Freestyle culling; rest pass written by the data render (AOV); workers kept up between sprites | `SPRITE_RENDER_JOBS` (4 suits 16 GB; more thrash), `SPRITE_RENDER_THREADS` (1), `SPRITE_RENDER_FORMAT=TGA` (raw passes: ~5% faster render, ~2x faster load, ~7x the disk) |
| build | per-frame steps on all cores; frames loaded and prepared by the workers; the per-pixel rules in Rust | `SPRITE_JOBS` (default: all cores; 1 = one process), `SPRITE_RUST=0` (Python only) |
| repeatable | a few tie-breaks follow Python's string hash order, random per run: the scripts pin `PYTHONHASHSEED` to 0 (`sprite_style.pin_hash_seed`), so a build is the same every time | |

Tried and dropped (pixels changed): fewer anti-aliasing samples for the lines pass, the shadow pass
or the lines pass folded into the data render, uncompressed PNG (no faster).

**The one deliberate change: traced lines instead of Freestyle** (`render.freestyle.engine`,
default `"trace"`). Freestyle cost ~280 ms per frame; `linetrace.py` draws the same kinds of edges
(border, silhouette / contour, crease past `crease_angle`, visible only, `thickness` px) in ~25 ms.
Glimmora's render: 54 s / 161 CPU-s -> 33 s / 98 CPU-s. Its sprite moves ~60 px per frame (2%),
all inner crown lines: QA still passes, style score 81.4 -> 80.8, core_edge_ratio 1.20 -> 1.41
(a few more crown lines than Freestyle drew). Blender's Line Art was tried first: half the lines
(IoU 0.5) for a 20% gain. Edge types the tracer doesn't draw (material_boundary, ridge_valley, ...)
make a config use Freestyle automatically; `"engine": "freestyle"` brings it back for any config.

**Render resolution** (`res_study.py`, not changed): rendering at 75% / 50% of the size saves
7-48% render time but changes the sprite (size shifts by a few px, 6-8% of pixels) and fails QA
for Lapras and Glimmora; Golisopod passes at 50% (-21%), Dragalge at 75% (-7%). A per-Pokemon
choice, made with a re-tune, not a global setting.
