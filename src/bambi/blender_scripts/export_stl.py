"""Export mesh objects to STL (1 Blender unit = 1 mm in the file).

Usage: blender -b model.blend -P export_stl.py -- --outdir exports [--objects A,B] [--combined NAME] --result r.json
Default: one STL per visible mesh object. --combined writes all of them into a single file.
"""

import argparse
import json
import sys
from pathlib import Path

import bpy

parser = argparse.ArgumentParser()
parser.add_argument("--outdir", required=True)
parser.add_argument("--objects", default="")
parser.add_argument("--combined", default="")
parser.add_argument("--scale", type=float, default=1.0)
parser.add_argument("--result", required=True)
opts = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])

outdir = Path(opts.outdir)
outdir.mkdir(parents=True, exist_ok=True)

wanted = {n.strip() for n in opts.objects.split(",") if n.strip()}
objects = [
    o
    for o in bpy.context.scene.objects
    if o.type == "MESH" and o.visible_get() and (not wanted or o.name in wanted)
]
missing = wanted - {o.name for o in objects}

common = {
    "ascii_format": False,
    "export_selected_objects": True,
    "global_scale": opts.scale,
    "use_scene_unit": False,  # write raw Blender units; sessions use 1 BU = 1 mm
    "apply_modifiers": True,
    "forward_axis": "Y",
    "up_axis": "Z",
}


def select_only(objs):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    if objs:
        bpy.context.view_layer.objects.active = objs[0]


written = []
if objects:
    if opts.combined:
        path = outdir / f"{opts.combined}.stl"
        select_only(objects)
        bpy.ops.wm.stl_export(filepath=str(path), **common)
        written.append(str(path))
    else:
        for obj in objects:
            path = outdir / f"{bpy.path.clean_name(obj.name)}.stl"
            select_only([obj])
            bpy.ops.wm.stl_export(filepath=str(path), **common)
            written.append(str(path))

Path(opts.result).write_text(
    json.dumps(
        {
            "written": written,
            "missing": sorted(missing),
            "unit_scale": bpy.context.scene.unit_settings.scale_length,
        },
        indent=2,
    )
)
