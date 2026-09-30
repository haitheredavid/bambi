"""Build the render studio: a P1S textured PEI plate on a cyclorama sweep, lit, with a camera.

Usage: blender -b --factory-startup -P build_studio.py -- --save assets/studio.blend --result r.json

Everything lives in scene `bambi_studio` (collection `studio`); render_studio.py appends that
scene and drops a session's models onto the plate. The plate is centred on the origin with
its top at z=0 (the bed). Printer front is -Y, so the default camera looks in from the
front-right, like standing at the P1S door. The angle lives in the scene's custom props
bambi_azimuth / bambi_elevation; tweak the look by opening the saved .blend by hand.
"""

import argparse
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

parser = argparse.ArgumentParser()
parser.add_argument("--save", required=True)
parser.add_argument("--result", required=True)
opts = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])

PLATE = 256.0  # P1S bed, mm
PLATE_R = 5.0  # corner radius
PLATE_T = 1.6  # spring steel + PEI
AZIMUTH, ELEVATION = -60.0, 25.0

for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

sc = bpy.context.scene
sc.name = "bambi_studio"
sc.unit_settings.system = "METRIC"
sc.unit_settings.scale_length = 0.001
sc.unit_settings.length_unit = "MILLIMETERS"
sc["bambi_azimuth"] = AZIMUTH
sc["bambi_elevation"] = ELEVATION

coll = bpy.data.collections.new("studio")
sc.collection.children.link(coll)


def srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb(hex_color: str) -> tuple[float, float, float, float]:
    h = hex_color.lstrip("#")
    return (*(srgb_to_linear(int(h[i : i + 2], 16) / 255) for i in (0, 2, 4)), 1.0)


def material(name: str, hex_color: str, roughness: float, metallic: float = 0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = rgb(hex_color)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    m.diffuse_color = rgb(hex_color)
    return m, bsdf


def link(name: str, data) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, data)
    coll.objects.link(obj)
    return obj


# --- plate: rounded slab, PEI top face, steel sides and bottom ---------------
pei, pei_bsdf = material("studio_pei", "#4E3F26", roughness=0.7)
nodes, links = pei.node_tree.nodes, pei.node_tree.links
coord = nodes.new("ShaderNodeTexCoord")
noise = nodes.new("ShaderNodeTexNoise")
noise.inputs["Scale"].default_value = 2.5  # object space is mm: ~0.4 mm grain
noise.inputs["Detail"].default_value = 8.0
bump = nodes.new("ShaderNodeBump")
bump.inputs["Strength"].default_value = 0.25
bump.inputs["Distance"].default_value = 0.05
ramp = nodes.new("ShaderNodeValToRGB")  # speckle: slightly lighter/darker grains
ramp.color_ramp.elements[0].color = rgb("#3F321D")
ramp.color_ramp.elements[1].color = rgb("#62502F")
links.new(coord.outputs["Object"], noise.inputs["Vector"])
links.new(noise.outputs["Fac"], bump.inputs["Height"])
links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
links.new(ramp.outputs["Color"], pei_bsdf.inputs["Base Color"])
links.new(bump.outputs["Normal"], pei_bsdf.inputs["Normal"])
steel, _ = material("studio_steel", "#8A8D91", roughness=0.35, metallic=1.0)

bm = bmesh.new()
half, seg = PLATE / 2, 8
ring = []
for cx, cy, a0 in (
    (half - PLATE_R, half - PLATE_R, 0),
    (-half + PLATE_R, half - PLATE_R, 90),
    (-half + PLATE_R, -half + PLATE_R, 180),
    (half - PLATE_R, -half + PLATE_R, 270),
):
    for i in range(seg + 1):
        a = math.radians(a0 + 90 * i / seg)
        ring.append(
            bm.verts.new((cx + PLATE_R * math.cos(a), cy + PLATE_R * math.sin(a), 0))
        )
top = bm.faces.new(ring)
ext = bmesh.ops.extrude_face_region(bm, geom=[top], use_keep_orig=True)
bmesh.ops.translate(
    bm,
    vec=(0, 0, -PLATE_T),
    verts=[g for g in ext["geom"] if isinstance(g, bmesh.types.BMVert)],
)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
bm.normal_update()
for f in bm.faces:  # PEI on the top face only
    f.material_index = 0 if f.normal.z > 0.9 else 1
plate_me = bpy.data.meshes.new("studio_plate")
bm.to_mesh(plate_me)
bm.free()
plate_me.materials.append(pei)
plate_me.materials.append(steel)
link("studio_plate", plate_me)

# --- cyclorama: floor under the plate curving up into a wall behind (+Y) ----
WIDTH, FRONT, CURVE_Y, R, HEIGHT = 2400.0, -1400.0, 300.0, 300.0, 1400.0
FLOOR_Z = -PLATE_T - 0.4
profile = [(FRONT, FLOOR_Z), (CURVE_Y, FLOOR_Z)]
for i in range(1, 24):
    a = math.radians(90 * i / 24)
    profile.append((CURVE_Y + R * math.sin(a), FLOOR_Z + R * (1 - math.cos(a))))
profile += [(CURVE_Y + R, FLOOR_Z + R), (CURVE_Y + R, FLOOR_Z + HEIGHT)]
verts = [(x, y, z) for y, z in profile for x in (-WIDTH / 2, WIDTH / 2)]
faces = [(2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2) for i in range(len(profile) - 1)]
cyc_me = bpy.data.meshes.new("studio_cyclorama")
cyc_me.from_pydata(verts, [], faces)
cyc_me.shade_smooth()
cyc_mat, _ = material("studio_backdrop", "#9EA0A4", roughness=0.9)
cyc_me.materials.append(cyc_mat)
link("studio_cyclorama", cyc_me)


# --- lights + camera ---------------------------------------------------------
def orbit(az: float, el: float, dist: float, center: Vector) -> Vector:
    a, e = math.radians(az), math.radians(el)
    return center + dist * Vector(
        (math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e))
    )


def aim(obj, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


target = Vector((0, 0, 30))
radius = PLATE / math.sqrt(2)  # plate half-diagonal: lights sized for the whole bed
for name, az, el, power, color, size in (
    ("studio_key", AZIMUTH + 40, 45, 1.0, (1, 0.93, 0.85), 1.2),
    ("studio_rim", AZIMUTH + 180, 35, 1.2, (0.7, 0.8, 1), 0.8),
    ("studio_fill", AZIMUTH - 70, 15, 0.35, (1, 1, 1), 2.0),
):
    light = bpy.data.lights.new(name, "AREA")
    dist = radius * 4
    light.energy = power * 11 * dist**2  # inverse-square: fixed irradiance on the bed
    light.color = color
    light.size = radius * size
    obj = link(name, light)
    obj.location = orbit(az, el, dist, target)
    aim(obj, target)

cam_data = bpy.data.cameras.new("studio_cam")
cam_data.lens = 50
cam_data.clip_start = 1
cam_data.clip_end = 20000
cam = link("studio_cam", cam_data)
cam.location = orbit(AZIMUTH, ELEVATION, 900, Vector((0, 0, 0)))
aim(cam, Vector((0, 0, 0)))
sc.camera = cam

world = bpy.data.worlds.new("studio_world")
world.use_nodes = True
bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
bg.inputs["Color"].default_value = rgb("#B4B6BA")
bg.inputs["Strength"].default_value = 0.25
sc.world = world

# --- render settings (render_studio.py renders with these) --------------------
engines = [i.identifier for i in sc.render.bl_rna.properties["engine"].enum_items]
for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", *engines):
    try:
        sc.render.engine = engine
        break
    except TypeError:
        continue
sc.render.resolution_x = sc.render.resolution_y = 1000
sc.render.resolution_percentage = 100
sc.render.film_transparent = False
sc.render.image_settings.file_format = "PNG"
try:
    sc.view_settings.view_transform = "AgX"
except TypeError:
    pass

Path(opts.save).parent.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(Path(opts.save).resolve()))
Path(opts.result).write_text(
    json.dumps({"saved": opts.save, "engine": sc.render.engine})
)
