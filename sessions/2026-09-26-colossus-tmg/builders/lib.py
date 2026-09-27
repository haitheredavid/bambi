# Mesh helpers shared by the builders; exec over MCP first, they live in driver_namespace['cz2'].
import bpy, bmesh, math
from mathutils import Vector

g = bpy.app.driver_namespace.setdefault('cz2', {})
DIAG = {'FL': 45, 'FR': -45, 'BL': 135, 'BR': -135}


def work():
    c = bpy.data.collections.get('Work2')
    if not c:
        c = bpy.data.collections.new('Work2'); bpy.data.scenes['Scene'].collection.children.link(c)
    return c


def mat(name):
    """material slot tag; the render scene gives these real shaders (see render.py)."""
    return bpy.data.materials.get(name) or bpy.data.materials.new(name)


def mesh_obj(name, bm, m=None):
    me = bpy.data.meshes.new(name); bm.normal_update(); bm.to_mesh(me); bm.free()
    me.materials.append(mat(m or g.get('MAT', 'M_Body')))
    o = bpy.data.objects.new(name, me); work().objects.link(o); return o


def rings_obj(name, rings, cap=True, m=None):
    """rings: list of lists of Vector (same count); lofted + capped."""
    bm = bmesh.new(); R = [[bm.verts.new(p) for p in r] for r in rings]; n = len(R[0])
    for a, b in zip(R, R[1:]):
        for i in range(n):
            bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
    if cap:
        bm.faces.new(list(reversed(R[0]))); bm.faces.new(R[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return mesh_obj(name, bm, m)


def oct_sec(w, t, k=0.3):
    a, b = w / 2, t / 2; ca, cb = a * (1 - 2 * k) if k else a, b * (1 - 2 * k) if k else b
    return [(a, -cb), (a, cb), (ca, b), (-ca, b), (-a, cb), (-a, -cb), (-ca, -b), (ca, -b)]


def leg_prism(name, P0, P1, w0, w1, t0, t1, k=0.3, off0=0.0, off1=0.0, m=None):
    """octagonal prism in leg print frame between XY points P0->P1, symmetric in Z."""
    P0, P1 = Vector((*P0, 0)), Vector((*P1, 0)); ax = (P1 - P0).normalized(); pe = Vector((-ax.y, ax.x, 0)); Z = Vector((0, 0, 1))
    rings = [[P + pe * (a + off) + Z * b for a, b in oct_sec(w, t, k)] for P, w, t, off in ((P0, w0, t0, off0), (P1, w1, t1, off1))]
    return rings_obj(name, rings, m=m)


def zcyl(name, c, r, hz, ch=0.8, seg=24, z0=0.0, m=None):
    rings = [[Vector((c[0] + rr * math.cos(2 * math.pi * i / seg), c[1] + rr * math.sin(2 * math.pi * i / seg), z0 + z)) for i in range(seg)]
             for z, rr in ((-hz, r - ch), (-hz + ch, r), (hz - ch, r), (hz, r - ch))]
    return rings_obj(name, rings, m=m)


def frame(P0, P1):
    ax = (Vector(P1) - Vector(P0)).normalized(); u = ax.orthogonal().normalized(); return ax, u, ax.cross(u)


def axcyl(name, P0, P1, r, seg=16, r1=None, m=None):
    """cylinder (or cone when r1 given) from P0 to P1."""
    P0, P1 = Vector(P0), Vector(P1); _, u, v = frame(P0, P1)
    return rings_obj(name, [[P + (u * math.cos(2 * math.pi * i / seg) + v * math.sin(2 * math.pi * i / seg)) * rad for i in range(seg)]
                            for P, rad in ((P0, r), (P1, r if r1 is None else r1))], m=m)


def sphere(name, c, r, seg=20, m=None):
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2, radius=r)
    bmesh.ops.translate(bm, vec=Vector(c), verts=bm.verts); return mesh_obj(name, bm, m)


def box(name, x0, x1, y0, y1, z0, z1, m=None):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1)
    for v in bm.verts:
        v.co = Vector((x0 if v.co.x < 0 else x1, y0 if v.co.y < 0 else y1, z0 if v.co.z < 0 else z1))
    return mesh_obj(name, bm, m)


def apply(o):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg); old = o.data
    o.modifiers.clear(); o.data = me
    if old.users == 0:
        bpy.data.meshes.remove(old)


def clean(me, d=1e-3):
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=d)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=d)
    bnd = [e for e in bm.edges if e.is_boundary]
    if bnd:
        bmesh.ops.holes_fill(bm, edges=bnd, sides=0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()


def _bool(o, op):
    m = o.modifiers.new('B', 'BOOLEAN'); m.operation = op; m.solver = 'EXACT'; m.material_mode = 'TRANSFER'; return m


def union_all(name, objs):
    base = objs[0]; tmp = bpy.data.collections.new('_ops')
    for o in objs[1:]:
        for c in o.users_collection:
            c.objects.unlink(o)
        tmp.objects.link(o)
    m = _bool(base, 'UNION'); m.operand_type = 'COLLECTION'; m.collection = tmp
    apply(base)
    for o in list(tmp.objects):
        bpy.data.objects.remove(o)
    bpy.data.collections.remove(tmp); base.name = name; clean(base.data); return base


def cut(base, cutters, op='DIFFERENCE'):
    for c in cutters:
        m = _bool(base, op); m.object = c
        apply(base); bpy.data.objects.remove(c); clean(base.data)
    return base


def tri(o):
    bm = bmesh.new(); bm.from_mesh(o.data)
    bmesh.ops.triangulate(bm, faces=bm.faces, quad_method='BEAUTY', ngon_method='BEAUTY'); bm.to_mesh(o.data); bm.free()
    clean(o.data); return o


def stats(o):
    bm = bmesh.new(); bm.from_mesh(o.data)
    nm = sum(1 for e in bm.edges if not e.is_manifold); vol = bm.calc_volume(); bm.free()
    vs = [o.matrix_world @ v.co for v in o.data.vertices]
    mn = [round(min(v[i] for v in vs), 2) for i in range(3)]; mx = [round(max(v[i] for v in vs), 2) for i in range(3)]
    return dict(nm=nm, v=len(vs), vol=round(vol), min=mn, max=mx)


def lframe(a_deg):
    a = math.radians(a_deg); d = Vector((math.cos(a), math.sin(a), 0)); n = Vector((math.sin(a), -math.cos(a), 0))
    return lambda u, z, nn: d * u + Vector((0, 0, z)) + n * nn


def to_leg_frame(c, a):
    """remap an object built as (u, n, z) into leg frame a; negate n to keep it right-handed."""
    L = lframe(a)
    for v in c.data.vertices:
        u, nn, z = v.co.x, v.co.y, v.co.z; v.co = L(u, z, -nn)
    c.data.update(); return c


g.update(DIAG=DIAG, work=work, mat=mat, mesh_obj=mesh_obj, rings_obj=rings_obj, oct_sec=oct_sec, leg_prism=leg_prism, zcyl=zcyl,
         frame=frame, axcyl=axcyl, sphere=sphere, box=box, apply=apply, clean=clean, union_all=union_all, cut=cut, tri=tri,
         stats=stats, lframe=lframe, to_leg_frame=to_leg_frame)
print('lib ok')
