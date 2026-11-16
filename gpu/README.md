# GPU renderer prototype (Rust + wgpu)

This prototype replaces Blender's per-frame **rendering** (the four Workbench/EEVEE passes) with a custom
Metal renderer. Blender still loads and poses the model, and `pipeline/` is untouched: the existing
`sprite_style.sprites()` + `save_gif()` build the GIF from the TGAs this renderer writes.
Test case: Mega Dragalge front, 160 frames, 1600×1600, M1 Pro.

```
python3 gpu/run.py /Users/manta/SpriteDrawer/models/mega-dragalge/mega_dragalge_front.json OUT_DIR
```

| file | what |
|---|---|
| `bake.py` | Runs inside Blender. Execs `pipeline/render_sprite.py` with no frames (setup only), then per frame: `pose_at`, evaluated body mesh (hull off) and body + shell (hull on, `cap_spikes` as configured). Dumps positions, corner normals, UVs, triangles, materials, textures and the camera. |
| `run_bake.py` | Runs `bake.py` in 4 Blenders at once (frames k::4, like the render pool), through `pipeline/blender.py`'s slots. |
| `renderer/` | `sprite_gpu BAKE OUT [--no-write]`: draws color_/id_/data_/hull_ for every frame and writes them as RLE TGA. |
| `run.py` | End to end, timed: bake → GPU → sprite step → GIF. |
| `old_pipeline.py` | The current route (RenderPool without cache, then the sprite step), timed. |
| `compare_gifs.py`, `compare_passes.py`, `classify_diffs.py`, `side_by_side.py`, `sprites_from.py` | Measuring tools. |
| `report/` | Side-by-side PNG and the prototype's GIFs. |

## Timing (Mega Dragalge front, 160 frames, 4 Blender workers both ways)

| stage | current (Blender renders) | prototype |
|---|---|---|
| Blender: open, set up, pose | inside the render (≈17 s per worker is posing) | **19.5–19.8 s** (bake; posing ≈ 16.7 s of it) |
| rendering the 4 passes | 46.4 / 53.2 s total incl. posing (two runs) | **2.9 s** (2.0 s GPU + readback, the rest TGA writes) |
| sprite step (`sprite_style.sprites`) | 4.6 s | 4.7 s (unchanged code) |
| GIF write | 2.5 s | 2.5 s |
| **total** | **≈ 54–60 s** | **≈ 30 s** |

* Render stage: 46–53 s → 22.5 s (≈ 2.2×). The GPU work itself is 2 s for 640 passes (≈ 3 ms per pass, 8× AA included).
  Almost all that's left is **posing in Blender**: `pose_at` takes 0.3 s a frame, because each of the config's 422
  pose entries calls `view_layer.update()`. Skipping mesh evaluation while posing changed nothing (it's the
  depsgraph and Python), so posing is the next thing to speed up. The current route pays the same posing cost inside its render.
* The bake writes 1 MB of static data + 0.6 MB per frame, against ~40 MB of TGAs per frame from Blender.
* Not done (optional step 4): porting the sprite step to Rust. Sprite step + GIF is 7.2 s, about a quarter of the new
  total. In Rust, in memory and without TGA round-trips, it should take about 1 s, which would bring the total to ≈ 23 s,
  with ≈ 20 s of that posing.
* Caveat: `blender.py` keeps its slot locks next to the checkout, so this worktree's slots are separate from
  the main checkout's. During these runs only this session's Blenders were running, so the numbers are not contended.

## How close the pixels are

Against the published `sprites/mega-dragalge/mega_dragalge_front.gif` (a fresh Blender build reproduces it exactly):

* **All 160 frames differ, by 14.6 px per frame on average (max 27) out of ~12,400 sprite pixels (0.12%).**
* By kind (all 2,335 differing pixels over the loop): **99% are one shade step at a cel-band border**,
  13 are outline pixels, 10 are other colour changes, 2 are silhouette pixels. Canvas size and framing are identical.
  See `report/side_by_side.png`: the differences are isolated single pixels, scattered.

Why, pass by pass (frame 1, render pixels):

| pass | match | cause of what's left |
|---|---|---|
| hull_ | 2 px xor of ~19,900 | rasterisation ties on the shell edge |
| id_ | exact colours; 139 edge px | same; Blender's 8-bit dither reproduced |
| color_ | alpha box identical, alpha ±1, RGB p99 ±1 | sampler/rounding detail inside texture texels |
| data_ (normals) | ±1 level on ~10% of pixels | float differences in EEVEE's normal path; this is what flips band borders |

Sprite-level attribution (one GPU pass swapped into Blender's frames): data_ alone → 12.9 px/frame,
color_ alone → 1.7, id_ and hull_ → < 0.1.

Getting there took reproducing Blender exactly where it matters, ported from Blender's source:
* **Workbench TAA**: `BLI_jitter_init` (its drand48 RNG and 24 relaxation rounds), the centre/wrap/reorder of
  `TaaSamples`, the projection shift of offset/2 px, Blackman-Harris weights of width 2.0 on the full offset, and
  log2-space accumulation. A generic 8× AA was 584 px/frame off, because a 1-px change in frame 0's alpha
  box rescales the whole sprite.
* **8-bit dither**: `dither_random_value` (iqint3 hash, triangle pdf, ×0.0033) on every pass.
* **10-bit packed normals** (`GPU_PackedNormal`, when High Quality Normals is off): halved the data_ mismatch.

The remaining data_ ±1 is the floor I reached in this prototype. Every sub-pixel offset I tried made it worse, and half-float
storage made no difference.

## Limits of the prototype

* Tested only on Mega Dragalge front. The back view, other models, `motion.clip` models, ortho cameras, multiple texture UV
  layers, texture alpha (ignored by the renderer; that matched Blender here, though the textures have transparent areas), mipmaps and anisotropic filtering
  (not used; minification is small at 1600 px) have not been checked.
* Texture choice per material copies Workbench (active image node, else the first one). Material without image → flat colour.
* The GPU passes go through TGA files only so the unchanged `sprite_style` can read them.
