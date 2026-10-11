"""Printability checks on mesh objects (like Blender's 3D-Print Toolbox), written as JSON.

Usage: blender -b model.blend -P check_print.py -- --result r.json [--overhang 45]
"""

import argparse
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy

parser = argparse.ArgumentParser()
parser.add_argument("--result", required=True)
parser.add_argument(
    "--overhang", type=float, default=45.0, help="degrees from vertical"
)
opts = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])

# A downward-facing face is an overhang when its normal points more steeply down than this.
overhang_z = -math.cos(math.radians(opts.overhang))
depsgraph = bpy.context.evaluated_depsgraph_get()
report = {"unit_scale": bpy.context.scene.unit_settings.scale_length, "objects": []}

for obj in bpy.context.scene.objects:
    if obj.type != "MESH" or not obj.visible_get():
        continue
    evaluated = obj.evaluated_get(depsgraph)
    bm = bmesh.new()
    bm.from_mesh(evaluated.to_mesh())
    bm.transform(obj.matrix_world)
    bm.normal_update()
    evaluated.to_mesh_clear()

    xs, ys, zs = zip(*(v.co[:] for v in bm.verts)) if bm.verts else ((0,), (0,), (0,))
    total_area = sum(f.calc_area() for f in bm.faces) or 1.0
    min_z = min(zs)
    # Faces resting on the bed are supported, not overhangs.
    overhang_area = sum(
        f.calc_area()
        for f in bm.faces
        if f.normal.z < overhang_z and f.calc_center_median().z > min_z + 0.01
    )
    report["objects"].append(
        {
            "name": obj.name,
            "verts": len(bm.verts),
            "faces": len(bm.faces),
            "non_manifold_edges": sum(1 for e in bm.edges if not e.is_manifold),
            "loose_verts": sum(1 for v in bm.verts if not v.link_edges),
            "degenerate_faces": sum(1 for f in bm.faces if f.calc_area() < 1e-8),
            "bounds_min": [min(xs), min(ys), min_z],
            "size": [max(xs) - min(xs), max(ys) - min(ys), max(zs) - min_z],
            "volume": abs(bm.calc_volume(signed=True)),
            "overhang_fraction": overhang_area / total_area,
            "below_bed": min_z < -0.001,
        }
    )
    bm.free()

Path(opts.result).write_text(json.dumps(report, indent=2))
