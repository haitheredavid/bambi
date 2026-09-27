"""Studio render of the visible mesh objects, for the session gallery.

Usage: blender -b model.blend -P render_thumb.py -- --out render.png [--color NAME=#RRGGBB ...] [--scene NAME] [--size 600] --result r.json
NAME is the exported STL stem (clean object name); `*` colours every object not listed.
Objects without a colour keep their own materials (grey if they have none). Never saves the .blend.
"""

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

parser = argparse.ArgumentParser()
parser.add_argument("--out", required=True)
parser.add_argument("--color", action="append", default=[])
parser.add_argument("--scene", default="")
parser.add_argument("--size", type=int, default=600)
parser.add_argument("--azimuth", type=float, default=-55.0)
parser.add_argument("--elevation", type=float, default=25.0)
parser.add_argument("--result", required=True)
opts = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])

src = bpy.data.scenes[opts.scene] if opts.scene else bpy.context.scene
layer = src.view_layers[0]
objects = [
    o for o in src.objects if o.type == "MESH" and o.visible_get(view_layer=layer)
]


def srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def material(name: str, hex_color: str, roughness: float = 0.55) -> bpy.types.Material:
    h = hex_color.lstrip("#")[:6]
    rgb = [srgb_to_linear(int(h[i : i + 2], 16) / 255) for i in (0, 2, 4)]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1)
    bsdf.inputs["Roughness"].default_value = roughness
    m.diffuse_color = (*rgb, 1)
    return m


colors = dict(c.split("=", 1) for c in opts.color)
grey = None
for o in objects:
    hex_color = colors.get(bpy.path.clean_name(o.name)) or colors.get("*")
    if hex_color:
        mat = material(f"thumb_{o.name}", hex_color)
    elif not any(s.material for s in o.material_slots):
        grey = grey or material("thumb_grey", "#B8B8B8")
        mat = grey
    else:
        continue
    o.data.materials.clear()
    o.data.materials.append(mat)

sc = bpy.data.scenes.new("bambi_thumb")
sc.unit_settings.system = "METRIC"
sc.unit_settings.scale_length = 0.001
for o in objects:
    sc.collection.objects.link(o)

# frame the union of world bounding boxes
layer.update()  # a non-active scene's transforms/bounds aren't evaluated on load
evaluated = [o.evaluated_get(layer.depsgraph) for o in objects]
corners = [o.matrix_world @ Vector(c) for o in evaluated for c in o.bound_box] or [
    Vector((0, 0, 0))
]
lo = Vector(tuple(min(c[i] for c in corners) for i in range(3)))
hi = Vector(tuple(max(c[i] for c in corners) for i in range(3)))
center = (lo + hi) / 2
radius = max((hi - lo).length / 2, 1.0)

engines = [i.identifier for i in sc.render.bl_rna.properties["engine"].enum_items]
for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", *engines):
    try:
        sc.render.engine = engine
        break
    except TypeError:
        continue
sc.render.resolution_x = sc.render.resolution_y = opts.size
sc.render.resolution_percentage = 100
sc.render.film_transparent = False
sc.render.image_settings.file_format = "PNG"
sc.render.filepath = str(Path(opts.out).resolve())
try:
    sc.view_settings.view_transform = "AgX"
except TypeError:
    pass

world = bpy.data.worlds.new("thumb_world")
world.use_nodes = True
bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
bg.inputs["Color"].default_value = (0.18, 0.19, 0.21, 1)
bg.inputs["Strength"].default_value = 0.6
sc.world = world

# floor just under the model
floor_me = bpy.data.meshes.new("thumb_floor")
s = radius * 20
floor_me.from_pydata(
    [(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)]
)
floor_me.materials.append(material("thumb_floor", "#2E3035", roughness=0.8))
floor = bpy.data.objects.new("thumb_floor", floor_me)
floor.location = (center.x, center.y, lo.z - 0.05)
sc.collection.objects.link(floor)


def aim(obj, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def orbit(az: float, el: float, dist: float) -> Vector:
    a, e = math.radians(az), math.radians(el)
    return (
        center
        + Vector((math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e)))
        * dist
    )


# key warm, rim cool, fill: scaled to the model so small and large parts light the same
for name, az, el, power, color, size in (
    ("thumb_key", opts.azimuth + 40, 45, 1.0, (1, 0.93, 0.85), 1.2),
    ("thumb_rim", opts.azimuth + 180, 35, 1.2, (0.7, 0.8, 1), 0.8),
    ("thumb_fill", opts.azimuth - 70, 15, 0.35, (1, 1, 1), 2.0),
):
    light = bpy.data.lights.new(name, "AREA")
    dist = radius * 4
    light.energy = power * 22 * dist**2  # inverse-square: same irradiance at any scale
    light.color = color
    light.size = radius * size
    lo_ = bpy.data.objects.new(name, light)
    lo_.location = orbit(az, el, dist)
    aim(lo_, center)
    sc.collection.objects.link(lo_)

cam_data = bpy.data.cameras.new("thumb_cam")
cam_data.lens = 50
cam_data.clip_start = radius * 0.01
cam_data.clip_end = radius * 100
tan_half = cam_data.sensor_width / (2 * cam_data.lens)  # square frame: same both ways
cam = bpy.data.objects.new("thumb_cam", cam_data)
sc.collection.objects.link(cam)

# Fit: project the bbox corners, then centre with lens shift and scale the distance
# until the model fills FILL of the frame. Perspective makes it nonlinear, so iterate.
FILL = 0.86
dist = radius / tan_half
for _ in range(8):
    cam.location = orbit(opts.azimuth, opts.elevation, dist)
    aim(cam, center)
    view = cam.matrix_basis.inverted()
    ndc = [
        (p.x / -p.z / tan_half, p.y / -p.z / tan_half)
        for p in (view @ c for c in corners)
    ]
    us, vs = [u for u, _ in ndc], [v for _, v in ndc]
    cam_data.shift_x = (min(us) + max(us)) / 4  # shift is in frame widths; ndc spans 2
    cam_data.shift_y = (min(vs) + max(vs)) / 4
    extent = max(max(us) - min(us), max(vs) - min(vs)) / 2
    dist *= extent / FILL
sc.camera = cam

Path(opts.out).parent.mkdir(parents=True, exist_ok=True)
bpy.ops.render.render(write_still=True, scene=sc.name)

Path(opts.result).write_text(
    json.dumps(
        {
            "out": sc.render.filepath,
            "objects": len(objects),
            "engine": sc.render.engine,
        },
        indent=2,
    )
)
