"""Create an empty print-ready .blend: millimetre units, 1 Blender unit = 1 mm.

Usage: blender -b --factory-startup -P setup_scene.py -- --save path/to/model.blend --result r.json
"""

import argparse
import json
import sys
from pathlib import Path

import bpy

parser = argparse.ArgumentParser()
parser.add_argument("--save", required=True)
parser.add_argument("--result", required=True)
opts = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])

# Start from an empty scene.
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

scene = bpy.context.scene
scene.unit_settings.system = "METRIC"
scene.unit_settings.scale_length = 0.001
scene.unit_settings.length_unit = "MILLIMETERS"

# Make the viewport grid and clipping sensible at mm scale.
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type == "VIEW_3D":
            for space in area.spaces:
                if space.type == "VIEW_3D":
                    space.overlay.grid_scale = 0.001
                    space.clip_start = 0.1
                    space.clip_end = 100000
                    # Frame roughly a P1S plate's worth of space instead of Blender's metre-scale default.
                    space.region_3d.view_location = (0, 0, 20)
                    space.region_3d.view_distance = 300

bpy.ops.wm.save_as_mainfile(filepath=opts.save)
Path(opts.result).write_text(json.dumps({"saved": opts.save}))
