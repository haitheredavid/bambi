"""Studio render of the visible mesh objects on the P1S plate, for the session gallery.

Usage: blender -b model.blend -P render_studio.py -- --studio assets/studio.blend --out render.png
       [--framing fit|wide] [--color NAME=#RRGGBB ...] [--scene NAME] [--size 600]
       [--azimuth DEG --elevation DEG] --result r.json

Appends the `bambi_studio` scene from studio.blend (build_studio.py), centres the models on
its plate (XY only; they already sit on the bed) and renders with its camera at the studio's
fixed angle. `fit` zooms to the models; `wide` frames the whole plate.
NAME is the exported STL stem (clean object name); `*` colours every object not listed.
Objects without a colour keep their own materials (grey if they have none). Never saves the .blend.
"""

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

parser = argparse.ArgumentParser()
parser.add_argument("--studio", required=True)
parser.add_argument("--out", required=True)
parser.add_argument("--framing", choices=("fit", "wide"), default="fit")
parser.add_argument("--color", action="append", default=[])
parser.add_argument("--scene", default="")
parser.add_argument("--size", type=int, default=600)
parser.add_argument("--azimuth", type=float)
parser.add_argument("--elevation", type=float)
parser.add_argument("--result", required=True)
opts = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])

STUDIO_SCENE, PLATE = "bambi_studio", 256.0

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

with bpy.data.libraries.load(opts.studio, link=False) as (lib, data):
    if STUDIO_SCENE not in lib.scenes:
        raise SystemExit(f"{opts.studio} has no scene {STUDIO_SCENE!r}")
    data.scenes = [STUDIO_SCENE]
sc = data.scenes[0]
for o in objects:
    sc.collection.objects.link(o)
cam = sc.camera
studio_layer = sc.view_layers[0]


def world_points(objs) -> np.ndarray:
    """Evaluated vertices in world space, (N, 3). Framing on real geometry, not bboxes,
    keeps sparse layouts (a kit of parts) from leaving the frame half empty."""
    studio_layer.update()  # a non-active scene's transforms aren't evaluated on load
    dg = studio_layer.depsgraph
    chunks = [np.zeros((0, 3))]
    for o in objs:
        e = o.evaluated_get(dg)
        co = np.empty(len(e.data.vertices) * 3)
        e.data.vertices.foreach_get("co", co)
        m = np.array(e.matrix_world)
        chunks.append(co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3])
    return np.concatenate(chunks)


# centre the models on the plate in XY; Z stays (they already sit on the bed)
pts = world_points(objects)
if len(pts):
    mid = (pts.min(0) + pts.max(0)) / 2
    shift = Matrix.Translation((-mid[0], -mid[1], 0))
    for o in objects:
        if o.parent not in objects:  # children follow their parent
            o.matrix_world = shift @ o.matrix_world
    pts = world_points(objects)
else:
    pts = np.zeros((1, 3))
size = pts.max(0) - pts.min(0)
warnings = []
if max(size[0], size[1]) > PLATE:
    warnings.append(
        f"models span {size[0]:.0f} x {size[1]:.0f} mm, wider than the plate"
    )

half = PLATE / 2
plate_corners = np.array(
    [(x, y, z) for x in (-half, half) for y in (-half, half) for z in (-1.6, 0)]
)
if opts.framing == "wide":
    frame, fill = np.concatenate([plate_corners, pts]), 0.92
else:
    frame, fill = pts, 0.86
center = Vector((frame.min(0) + frame.max(0)) / 2)
radius = max(float(np.linalg.norm(frame.max(0) - frame.min(0))) / 2, 1.0)

azimuth = opts.azimuth if opts.azimuth is not None else sc.get("bambi_azimuth", -60.0)
elevation = (
    opts.elevation if opts.elevation is not None else sc.get("bambi_elevation", 25.0)
)


def orbit(az: float, el: float, dist: float) -> Vector:
    a, e = math.radians(az), math.radians(el)
    return center + dist * Vector(
        (math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e))
    )


cam_data = cam.data
cam_data.clip_start = radius * 0.01
cam_data.clip_end = radius * 1000
tan_half = cam_data.sensor_width / (2 * cam_data.lens)  # square frame: same both ways

# Fit: project the frame points, then centre with lens shift and scale the distance
# until they fill FILL of the frame. Perspective makes it nonlinear, so iterate.
dist = radius / tan_half
for _ in range(8):
    cam.location = orbit(azimuth, elevation, dist)
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    view = np.array(cam.matrix_basis.inverted())
    p = frame @ view[:3, :3].T + view[:3, 3]
    us, vs = p[:, 0] / -p[:, 2] / tan_half, p[:, 1] / -p[:, 2] / tan_half
    cam_data.shift_x = (
        us.min() + us.max()
    ) / 4  # shift is in frame widths; ndc spans 2
    cam_data.shift_y = (vs.min() + vs.max()) / 4
    extent = max(us.max() - us.min(), vs.max() - vs.min()) / 2
    dist *= float(extent) / fill

sc.render.resolution_x = sc.render.resolution_y = opts.size
sc.render.filepath = str(Path(opts.out).resolve())
Path(opts.out).parent.mkdir(parents=True, exist_ok=True)
bpy.ops.render.render(write_still=True, scene=sc.name)

Path(opts.result).write_text(
    json.dumps(
        {
            "out": sc.render.filepath,
            "objects": len(objects),
            "engine": sc.render.engine,
            "framing": opts.framing,
            "size_mm": [round(float(v), 1) for v in size],
            "warnings": warnings,
        },
        indent=2,
    )
)
