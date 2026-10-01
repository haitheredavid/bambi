# Parametric cat putty knife, one piece. Rebuilds Knife + Eyes in the open model.blend and saves.
#   Blender -b <session>/model.blend -P sessions/2026-09-30-cat-putty-knife/builders/knife.py -- --variant spine|slope [--no-eyes]
# --no-eyes: single colour, eye pockets stay as 1 mm engravings and no Eyes inlay object.
# spine: wide blade with a tang-like spine that fades from the handle into the blade (v2).
# slope: pizza-server wedge, top rises steadily from the edge into the handle (cat-putty-knife-slope).
# Frame: X = length (0 = working edge), Y = width, Z up, bottom flat on the bed. 1 unit = 1 mm.
import argparse
import itertools
import math
import sys

import bmesh
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--variant", choices=("spine", "slope"), default="spine")
ap.add_argument("--no-eyes", action="store_true")
ARGS = ap.parse_args(argv)
VARIANT = ARGS.variant

EDGE_W = 150.0  # working edge width
EDGE_T = 1.2  # working edge thickness
PLATE_T = 3.0  # blade thickness at the shoulder / handle side-wall height
HANDLE_W = 28.0
HANDLE_H = 16.0
CH = 0.4  # bottom chamfer (elephant's foot); none on the working edge
HANDLE_END = (
    230.0  # butt end of the handle; the cat face sits on its top, ears past the end
)
END_R = 6.0  # planform corner radius at the butt end


def sm(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def corner(x, w):
    # R3 rounded corners on the working edge
    r = 3.0
    return (
        min(w, EDGE_W / 2 - r + math.sqrt(max(r * r - (r - x) ** 2, 0))) if x < r else w
    )


HW = HANDLE_W / 2
if VARIANT == "spine":
    # Blade stays wide (bell-shaped planform) and flows tangentially into the handle at x=115.
    def W(x):
        return corner(x, HW + (EDGE_W / 2 - HW) * (1 - sm(x / 115)))

    def T(x):
        return EDGE_T + (PLATE_T - EDGE_T) * sm(x / 55)

    def H(x):  # centreline height: spine starts at x=20, full handle height at x=125
        return T(x) + (HANDLE_H - T(x)) * sm((x - 20) / 105)

    def S(x):  # spine half-width, merges with the handle at x=115
        return min(W(x), 8 + (HW - 8) * sm((x - 20) / 95))

    def K(x):  # 0 = soft cos² bump, 1 = rounded-box handle section
        return sm((x - 60) / 55)
else:
    # Pizza-server wedge: concave taper to the handle width, crown across the full width.
    L = 130.0

    def W(x):
        return corner(x, HW + (EDGE_W / 2 - HW) * (1 - min(x / L, 1)) ** 1.6)

    def T(x):
        return EDGE_T + (PLATE_T - EDGE_T) * sm(x / 60)

    def H(x):  # near-linear ramp that eases into the handle top
        s = min(x / L, 1)
        r = 0.5 * s + 0.5 * (s - math.sin(2 * math.pi * s) / (2 * math.pi))
        return T(x) + (HANDLE_H - T(x)) * r

    def S(x):
        return W(x)

    def K(x):
        return sm((x - 40) / 90)


N_TOP = 121


def section(x):
    w, t, h, s, k = W(x), T(x), H(x), S(x), K(x)
    d = x - (HANDLE_END - END_R)
    if d > 0:  # round the butt corners, shrinking the section in proportion
        r = min(w, HW - END_R + math.sqrt(max(END_R**2 - d * d, 0))) / w
        w, s = w * r, s * r
    top = []
    for i in range(N_TOP):
        u = 1 - 2 * i / (N_TOP - 1)  # +1 -> -1
        y = w * math.copysign(abs(u) ** 1.6, u)  # denser near the centre
        a = min(abs(y) / s, 1.0)
        f = (1 - k) * math.cos(math.pi * a / 2) ** 2 + k * (1 - a**3) ** (1 / 3)
        top.append((y, t + (h - t) * f))
    return [(-w + CH, 0.0), (w - CH, 0.0), (w, CH)] + top + [(-w, CH)]


def loft(name, xs, sec=None):
    bm = bmesh.new()
    rings = [[bm.verts.new((x, y, z)) for y, z in (sec or section)(x)] for x in xs]
    n = len(rings[0])
    for a, b in itertools.pairwise(rings):
        for j in range(n):
            bm.faces.new((a[j], a[(j + 1) % n], b[(j + 1) % n], b[j]))
    for r in (rings[0], rings[-1]):
        bm.faces.new(r)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return ob


def hull(name, pts):
    bm = bmesh.new()
    for p in {tuple(round(c, 4) for c in p) for p in pts}:
        bm.verts.new(p)
    r = bmesh.ops.convex_hull(bm, input=bm.verts)
    junk = {
        e
        for e in r["geom_interior"] + r["geom_unused"]
        if isinstance(e, bmesh.types.BMVert)
    }
    if junk:
        bmesh.ops.delete(bm, geom=list(junk), context="VERTS")
    bmesh.ops.dissolve_limit(
        bm, angle_limit=math.radians(0.5), verts=bm.verts[:], edges=bm.edges[:]
    )
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return ob


def circ(cx, cy, r, n=24):
    return [
        (cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n))
        for i in range(n)
    ]


def prism(name, outline, z0, z1, ch=CH, top_ch=0.0):
    # convex outline with a bottom chamfer and optional top chamfer
    c = Vector(
        (
            sum(p[0] for p in outline) / len(outline),
            sum(p[1] for p in outline) / len(outline),
        )
    )

    def inset(d):
        return [
            tuple(c + (Vector(p) - c) * (1 - d / (Vector(p) - c).length))
            for p in outline
        ]

    pts = [(x, y, z0) for x, y in inset(ch)] + [(x, y, z0 + ch) for x, y in outline]
    pts += [(x, y, z1 - top_ch) for x, y in outline] + [
        (x, y, z1) for x, y in inset(top_ch)
    ]
    return hull(name, pts)


def extrude(name, pts2d, z0, z1):
    bm = bmesh.new()
    f = bm.faces.new([bm.verts.new((x, y, z0)) for x, y in pts2d])
    r = bmesh.ops.extrude_face_region(bm, geom=[f])
    for v in r["geom"]:
        if isinstance(v, bmesh.types.BMVert):
            v.co.z = z1
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return ob


def boolean(target, others, op):
    for o in others:
        m = target.modifiers.new(o.name, "BOOLEAN")
        m.operation, m.solver, m.object = op, "EXACT", o
        with bpy.context.temp_override(object=target, active_object=target):
            bpy.ops.object.modifier_apply(modifier=m.name)
        bpy.data.objects.remove(o)


for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
for m in list(bpy.data.meshes):
    if m.users == 0:
        bpy.data.meshes.remove(m)

xs = (
    [i * 0.25 for i in range(12)]
    + [3 + i for i in range(int(HANDLE_END - END_R - 3))]
    + [HANDLE_END - END_R + i * 0.25 for i in range(int(END_R * 4) + 1)]
)
knife = loft("Knife", xs)

# Triangular ears grow out of the butt end, trimmed to the handle's cross-section
# so they continue its form (no wider, no taller).
ears = []
for sgn in (-1, 1):
    out = [
        (HANDLE_END - 5, sgn * 1.0),
        (HANDLE_END - 5, sgn * 13.6),
        *circ(HANDLE_END + 10, sgn * 10.5, 1.8, 16),
    ]
    ears.append(prism(f"Ear{sgn}", out, 0, HANDLE_H + 1, CH, 0.0))
boolean(ears[0], ears[1:], "UNION")
grip = section(150)  # full handle cross-section, run straight past the end
envelope = loft("Envelope", [HANDLE_END - 8, HANDLE_END + 15], lambda x: grip)
boolean(ears[0], [envelope], "INTERSECT")
boolean(knife, [ears[0]], "UNION")

# Face on the handle top: eye pockets (engraved, or inlaid) + engraved nose.
EX, EY, RX, RY = HANDLE_END - 13, 5.5, 2.2, 3.2
# pocket floor; the crown curves, so depth is ~1.8 centre, ~0.8 edge
EYE_Z = HANDLE_H - 1.8
ell = lambda cx, cy: [
    (cx + RX * math.cos(2 * math.pi * i / 32), cy + RY * math.sin(2 * math.pi * i / 32))
    for i in range(32)
]
if not ARGS.no_eyes:
    shell = knife.copy()
    shell.data = knife.data.copy()
    bpy.context.collection.objects.link(shell)
cuts = [extrude(f"EyeCut{s}", ell(EX, s * EY), EYE_Z, HANDLE_H + 1) for s in (-1, 1)]
nx = HANDLE_END - 22
cuts.append(
    extrude(
        "NoseCut",
        [(nx, 0), (nx + 3, -2.5), (nx + 3, 2.5)],
        HANDLE_H - 0.6,
        HANDLE_H + 1,
    )
)
boolean(knife, cuts, "DIFFERENCE")

parts = [(knife, (1.0, 0.25, 0.02, 1))]
if not ARGS.no_eyes:
    # inlay fills the pockets flush with the curved crown
    eyes = extrude("Eyes", ell(EX, EY), EYE_Z, HANDLE_H + 1)
    other = extrude("EyeR", ell(EX, -EY), EYE_Z, HANDLE_H + 1)
    boolean(eyes, [other], "UNION")
    boolean(eyes, [shell], "INTERSECT")
    parts.append((eyes, (0.0, 0.06, 0.5, 1)))

for ob, col in parts:
    mat = bpy.data.materials.get(ob.name + "_mat") or bpy.data.materials.new(
        ob.name + "_mat"
    )
    mat.diffuse_color = col
    ob.data.materials.clear()
    ob.data.materials.append(mat)

for ob, _ in parts:
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bad = sum(not e.is_manifold for e in bm.edges)
    bm.free()
    print(
        f"[knife:{VARIANT}] {ob.name} dims={[round(d, 2) for d in ob.dimensions]} nonmanifold={bad}"
    )
bpy.ops.wm.save_mainfile()
