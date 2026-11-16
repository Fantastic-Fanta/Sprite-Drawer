"""Hides the drill-form model: the pack ships Excadrill's drill form as two loose, unrigged objects
beside the Pokemon (pm0530_51_00_drill_mesh, the drill, and pm0530_51_00_body_b_mesh, its handle).
The sprite is only the Pokemon (user, 2026-11-15). Run on MegaExcadrill_idle.blend and save."""
import bpy
for n in ("pm0530_51_00_drill_mesh", "pm0530_51_00_body_b_mesh"):
    o = bpy.data.objects[n]
    o.hide_render = True
    o.hide_viewport = True
    print("HIDDEN", n)
bpy.ops.wm.save_mainfile()
