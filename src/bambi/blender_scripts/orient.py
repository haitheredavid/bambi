"""Drop objects onto the bed (lowest point at z=0) and centre them on the origin, then save.

Usage: blender -b model.blend -P orient.py -- --result r.json [--objects A,B] [--no-center]
       [--rotate X,Y,Z]   (degrees, XYZ Euler, applied in world space before dropping)
"""

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Euler, Vector

parser = argparse.ArgumentParser()
parser.add_argument("--result", required=True)
parser.add_argument("--objects", default="")
parser.add_argument("--no-center", action="store_true")
parser.add_argument("--rotate", default="")
opts = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])

wanted = {n.strip() for n in opts.objects.split(",") if n.strip()}
moved = []
for obj in bpy.context.scene.objects:
    if obj.type != "MESH" or (wanted and obj.name not in wanted):
        continue
    if opts.rotate:
        rx, ry, rz = (math.radians(float(v)) for v in opts.rotate.split(","))
        obj.matrix_world = (
            Euler((rx, ry, rz), "XYZ").to_matrix().to_4x4() @ obj.matrix_world
        )
        bpy.context.view_layer.update()
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    lo = Vector(
        (
            min(c.x for c in corners),
            min(c.y for c in corners),
            min(c.z for c in corners),
        )
    )
    hi = Vector(
        (
            max(c.x for c in corners),
            max(c.y for c in corners),
            max(c.z for c in corners),
        )
    )
    offset = Vector((0.0, 0.0, -lo.z))
    if not opts.no_center:
        center = (lo + hi) / 2
        offset.x, offset.y = -center.x, -center.y
    obj.location += offset
    moved.append({"name": obj.name, "offset": list(offset)})

bpy.ops.wm.save_mainfile()
Path(opts.result).write_text(json.dumps({"moved": moved}, indent=2))
