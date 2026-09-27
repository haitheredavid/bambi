# v4 core (hub, flared collar, ribbed neck, belly spike) and leg (hip claw, kite knee shield, curved shin, pointed foot).
# Leg frame (u, Y = z - 4, Z = thickness). Needs lib.py.
import bpy, math
from mathutils import Vector
g = bpy.app.driver_namespace['cz2']

HIP, KNEE, FOOT = (16, 70), (44, 88), (50, 12)
HUB_Z = HIP[1] + 4  # world z of the hip axis
NECK_TOP = 103.0     # head bottom (head.py Z0)
A, B, M, GL = 'M_Armor', 'M_Body', 'M_Metal', 'M_Glow'


def circ(r, z, n=32):
    return [Vector((r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n), z)) for k in range(n)]


def build_core():
    """world coords; prints upside down on the neck's top face."""
    RO = g['rings_obj']; g['MAT'] = B
    oct8 = lambda a, z: [Vector((a / math.cos(math.pi / 8) * math.cos(math.pi / 8 + k * math.pi / 4),
                                 a / math.cos(math.pi / 8) * math.sin(math.pi / 8 + k * math.pi / 4), z)) for k in range(8)]
    zb, zt = HUB_Z - 6, HUB_Z + 6
    hub = RO('hub', [oct8(8.5, zb - 1.5), oct8(10, zb), oct8(10, zt)], m=M)
    sq = lambda h, z: [Vector((h * math.cos(k * math.pi / 2), h * math.sin(k * math.pi / 2), z)) for k in range(4)]
    spike = RO('spike', [sq(8, zb - 1), sq(0.6, zb - 15)], m=A)
    collar = RO('collar', [circ(12, zt - 0.5, 48), circ(12, zt + 1.2, 48), circ(6.3, zt + 6.9, 48)], m=A)
    prof = [(zt + 6, 5.4)]; z = zt + 6.5; n = 7; pitch = (NECK_TOP - 2.5 - z) / n
    for i in range(n):
        b = z + i * pitch
        prof += [(b, 5.4), (b + .75, 6.2), (b + pitch - .75, 6.2), (b + pitch, 5.4)]
    prof += [(NECK_TOP - 1.5, 6.8), (NECK_TOP, 6.8)]
    neck = RO('neck', [circ(r, z) for z, r in prof])
    core = g['union_all']('CoreNew', [hub, spike, collar, neck])
    C = [g['to_leg_frame'](g['box'](f'sock{k}', HIP[0] - 11.3, HIP[0] - 5.5, -3.3, 3.3, HUB_Z - 2.3, HUB_Z + 2.3), a)
         for k, a in g['DIAG'].items()]
    C += [g['axcyl'](f'npin{i}', (x, 0, NECK_TOP - 5), (x, 0, NECK_TOP + 5), 1.05) for i, x in enumerate((-3, 3))]
    # glowing ring on the collar slope
    o = g['axcyl']('cring', (0, 0, zt + 2.2), (0, 0, zt + 3.6), 11.5, seg=48, m=GL)
    C.append(g['cut'](o, [g['axcyl']('cring_i', (0, 0, zt), (0, 0, zt + 6), 10.3, seg=48)]))
    g['cut'](core, C)
    return g['tri'](core)


def build_leg():
    LP, ZC, AX, BOX, RO = g['leg_prism'], g['zcyl'], g['axcyl'], g['box'], g['rings_obj']
    g['MAT'] = B
    V = lambda x, y: Vector((x, y)); lerp = lambda a, b, s: a + (b - a) * s
    H, K, J = V(*HIP), V(*KNEE), V(*FOOT)
    Mid = lerp(K, J, .52) + V(3.2, 0)  # shin bows outward
    axT = (K - H).normalized(); peT = Vector((-axT.y, axT.x))
    P = [ZC('knuckle', H, 5.5, 5.0, 1.0, m=M), ZC('knuckle_cap', H, 3.0, 5.7, 0.6, m=A),
         BOX('hip_tab', H.x - 11, H.x - 3, H.y - 2, H.y + 2, -3, 3, m=M)]
    # hooked hip claw hanging under the knuckle
    P += [LP('hip_claw', H + V(3, -3), H + V(7.5, -12), 5.0, 2.2, 4.0, 2.4, m=A), LP('hip_claw2', H + V(7.5, -12), H + V(6, -19), 2.2, 0.6, 2.4, 0.8, m=A)]
    P += [LP('thigh', H, K, 8.5, 7.0, 8.0, 7.0)]
    P += [LP('thigh_armor', lerp(H, K, .28), lerp(H, K, .76), 8.5 - 1.5 * .28 + 1.6, 8.5 - 1.5 * .76 + 1.6, 8.0 - .28 + 1.6, 8.0 - .76 + 1.6, m=A)]
    p0, p1 = H + axT * 5 - peT * 5.2, H + axT * 22 - peT * 5.2
    P += [AX('piston_cyl', (*p0, 0), (*lerp(p0, p1, .55), 0), 1.9, m=M), AX('piston_rod', (*lerp(p0, p1, .5), 0), (*p1, 0), 1.2, m=M)]
    P += [LP('lug0', H + axT * 5, p0, 3, 3, 3.2, 3.2, m=M), LP('lug1', H + axT * 22, p1, 3, 3, 3.2, 3.2, m=M)]
    P += [ZC('knee', K, 6.5, 5.5, 1.2, m=M), ZC('knee_cap', K, 3.5, 6.2, 0.6, m=A)]
    P += [LP('knee_back', K, K + V(-9, 4), 5, 1.5, 4.5, 2.0)]
    # kite shield on the outside of the knee, point up, raised boss
    kite = lambda x, lo, w, hi, s=1.0: [Vector((x, K.y + dy * s, z * s)) for dy, z in ((lo, 0), (1, w), (hi, 0), (1, -w))]
    P += [RO('shield', [kite(K.x + 3.8, -12, 8.5, 18), kite(K.x + 6.6, -12, 8.5, 18)], m=A)]
    P += [RO('shield_boss', [kite(K.x + 6.2, -7, 4.6, 11), kite(K.x + 7.6, -7, 4.6, 11)], m=A)]
    # curved shin: knee -> bowed mid joint -> foot
    P += [LP('shin_up', K, Mid, 7.2, 6.2, 7.0, 6.4), LP('shin_lo', Mid, J, 6.2, 4.2, 6.4, 4.6)]
    P += [ZC('shin_joint', Mid, 4.0, 4.2, 0.8, m=M), ZC('shin_joint_cap', Mid, 2.2, 4.8, 0.5, m=A)]
    # greave: armour plate over the upper shin's inner (front) face, tapering to the mid joint
    P += [LP('greave', lerp(K, Mid, .1), lerp(Mid, J, .08), 5.0, 2.4, 8.4, 6.4, k=0.35, off0=-2.2, off1=-1.8, m=A)]
    P += [LP('shin_blade', lerp(K, Mid, .2), lerp(Mid, J, .6), 2.4, 1.0, 2.6, 1.4, k=0.25, off0=3.6 + 0.9, off1=2.8 + 0.4, m=A)]
    # pointed foot tapering into the base socket tab
    P += [LP('foot', J + V(0, 2), V(50, 0.3), 4.4, 5.0, 4.8, 6.0), BOX('foot_tab', 47.5, 52.5, -2.5, 0.8, -3, 3)]
    leg = g['union_all']('LegFull', P)
    # glow slot in the shield boss
    C = [RO('sglow', [kite(K.x + 7.0, -4.5, 2.2, 7.5), kite(K.x + 8.0, -4.5, 2.2, 7.5)], m=GL)]
    pins = [(lerp(H, K, .5), 3.0), (K, 3.0), (lerp(K, Mid, .62), 2.8), (Mid, 3.0), (lerp(Mid, J, .45), 2.5), (J + V(0, 4), 1.9)]
    C += [AX(f'pin{i}', (p.x, p.y, -d), (p.x, p.y, d), 1.05) for i, (p, d) in enumerate(pins)]
    g['cut'](leg, C)
    g['tri'](leg)
    half = leg.copy(); half.data = leg.data.copy(); g['work']().objects.link(half)
    g['cut'](half, [BOX('keep', -10, 80, -10, 180, 0, 20)], op='INTERSECT'); half.name = 'LegHalf'
    return leg, g['tri'](half)


g.update(build_core=build_core, build_leg3=build_leg, HUB_Z=HUB_Z)
if __name__ == 'core_leg':
    for n in ('CoreNew', 'LegFull', 'LegHalf'):
        if n in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[n])
    c = build_core(); leg, half = build_leg()
    print('core', g['stats'](c)); print('leg', g['stats'](leg)); print('half', g['stats'](half))
