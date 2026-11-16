# Sprite-Drawer

Animated pixel sprites from 3D Pokémon models (palette colours, cel bands, inverted-hull lines).

- `sprites/<pokemon>/`: the finished GIFs
- `models/<pokemon>/`: the configs. The models themselves are local only.
- `pipeline/`: the scripts. Each one prints its usage at the top.

Needs Blender at `/Applications/Blender.app` and Python 3 with numpy and Pillow.

```bash
python3 pipeline/build.py [POKEMON]            # build into out/<pokemon>/ (all Pokémon if none named)
python3 pipeline/build.py --publish POKEMON    # copy the approved GIFs into sprites/
python3 pipeline/regress.py                    # pixel regression; the pre-push hook runs it
```

In a fresh clone, turn the hook on with `git config core.hooksPath .githooks`.

Fan project, not affiliated with Nintendo, Game Freak or The Pokémon Company.
