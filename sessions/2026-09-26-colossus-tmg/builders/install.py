import bpy, bmesh, math
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
g = bpy.app.driver_namespace['cz2']
O, D = bpy.data.objects, bpy.data
vl = D.scenes['Scene'].view_layers[0]
lc = vl.layer_collection.children
lc['Work2'].exclude = False; lc['Assembly'].exclude = False


def bvh(o):
    bm = bmesh.new(); bm.from_mesh(o.data); bm.transform(o.matrix_world); return BVHTree.FromBMesh(bm), bm


def inside(t, p):
    n = 0; o = p.copy(); d = Vector((0.1234, 0.2345, 0.9643)).normalized()
    while True:
        hit = t.ray_cast(o, d)
        if hit[0] is None:
            return n % 2 == 1
        n += 1; o = hit[0] + d * 1e-4


# assembled copies: head/core in world coords, legs keep their leg-frame matrices
for n, src in (('Head_asm', 'HeadNew'), ('Core_asm', 'CoreNew')):
    O[n].data = O[src].data.copy(); O[n].data.name = n.replace('_asm', '_v4'); O[n].matrix_world = Matrix.Identity(4)
leg_me = O['LegFull'].data.copy(); leg_me.name = 'LegFull_v4'
for k in ('FL', 'FR', 'BL', 'BR'):
    O[f'Leg_{k}_asm'].data = leg_me

others = {n: bvh(O[n]) for n in ('Head_asm', 'Core_asm', 'Base_asm')}
for k in ('FL', 'FR', 'BL', 'BR'):
    t, bm = bvh(O[f'Leg_{k}_asm'])
    res = {n: sum(inside(tt, v.co) for v in bm.verts) for n, (tt, _) in others.items()}
    res.update({n + '-in-leg': sum(inside(t, v.co) for v in obm.verts) for n, (tt, obm) in others.items()})
    print(k, res)
th, hbm = others['Head_asm']; tc, cbm = others['Core_asm']
print('head-in-core', sum(inside(tc, v.co) for v in hbm.verts), 'core-in-head', sum(inside(th, v.co) for v in cbm.verts))


def mesh_from(src_me, name, M, mirror=False):
    me = D.meshes.get(name) or D.meshes.new(name)
    bm = bmesh.new(); bm.from_mesh(src_me); bm.transform(M)
    if mirror:
        bmesh.ops.scale(bm, vec=(1, -1, 1), verts=bm.verts); bmesh.ops.reverse_faces(bm, faces=bm.faces)
    zmin = min(v.co.z for v in bm.verts); bm.transform(Matrix.Translation((0, 0, -zmin)))
    bm.to_mesh(me); bm.free()
    if not me.materials:
        me.materials.append(None)
    return me


# head half (y >= 0) laid on its cut face
hh = O['HeadNew'].copy(); hh.data = O['HeadNew'].data.copy(); g['work']().objects.link(hh)
g['cut'](hh, [g['box']('keep', -80, 80, 0, 60, 60, 200)], op='INTERSECT')
bm = bmesh.new(); bm.from_mesh(hh.data)
bmesh.ops.triangulate(bm, faces=bm.faces, quad_method='BEAUTY', ngon_method='BEAUTY'); bm.to_mesh(hh.data); bm.free()
g['clean'](hh.data)
Rx = Matrix.Rotation(math.radians(90), 4, 'X')
head_a = mesh_from(hh.data, 'HeadHalf_A', Rx)
head_b = mesh_from(hh.data, 'HeadHalf_B', Rx, mirror=True)
D.objects.remove(hh)
core_p = mesh_from(O['CoreNew'].data, 'Core_print', Matrix.Rotation(math.pi, 4, 'X'))
leg_a = mesh_from(O['LegHalf'].data, 'LegHalf_A', Matrix.Identity(4))
leg_b = mesh_from(O['LegHalf'].data, 'LegHalf_B', Matrix.Identity(4), mirror=True)

plate = D.collections['Plate']
if 'Hull' in O:
    D.objects.remove(O['Hull'])
for name, me, loc in (('Head_L', head_a, (190, 110, 0)), ('Head_R', head_b, (190, -110, 0)), ('Core', core_p, (100, 110, 0))):
    o = O.get(name) or D.objects.new(name, me)
    if o.name not in plate.objects:
        plate.objects.link(o)
    o.data = me; o.matrix_world = Matrix.Translation(loc)
for k in ('FL', 'FR', 'BL', 'BR'):
    O[f'Leg_{k}_a'].data = leg_a; O[f'Leg_{k}_b'].data = leg_b
for me in list(D.meshes):
    if me.users == 0:
        D.meshes.remove(me)
for o in plate.objects:
    print(o.name, o.data.name, g['stats'](o))
lc['Work2'].exclude = True; lc['Assembly'].exclude = True; lc['Plate'].exclude = False
