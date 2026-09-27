# v4 head: ball head on the neck, leaf cowl on the front, concentric side emitters, 4 lance rods, looped rear fin.
# World coords, front = +x. Split on y=0 into two halves (install.py). Needs lib.py.
import bpy, bmesh, math
from mathutils import Vector
from mathutils.bvhtree import BVHTree
g = bpy.app.driver_namespace['cz2']

Z0 = 103.0
PROF = [(0, 6.5), (1.5, 9.5), (4, 14), (8, 18.5), (13, 22), (19, 24.5), (26, 25.8), (33, 25.8), (39, 24.6), (45, 22.2),
        (50, 19), (54, 15.2), (57, 11), (59.5, 6.5), (61, 2.5), (61.5, 0.6)]
TOP = PROF[-1][0]
SY, NSEG = 0.96, 64
A, B, M, GL = 'M_Armor', 'M_Body', 'M_Metal', 'M_Glow'
# side emitters: origin t, direction (y is mirrored), terraces (r, height over surface, mat), ball r, nozzle r/len, rod dir
DISCS = (dict(t=32, d=(-0.2, 1, 0.25), steps=((13, 1.0, A), (11.4, 2.0, B), (9, 3.0, A), (6, 3.8, B)), ball=4.0, noz=(2.2, 10),
              rim=(0.1, 0, 1), rod=(-0.3, 0.8, 0.55)),
         dict(t=22, d=(0.15, 1, -0.3), steps=((9.5, 1.0, A), (8, 2.0, B), (6, 2.8, A), (4, 3.4, B)), ball=3.0, noz=(1.7, 8.5),
              rim=(0.1, 0, -1), rod=(-0.15, 0.8, -0.55)))


def rr(t):
    """Catmull-Rom through PROF."""
    for i, ((t0, r0), (t1, r1)) in enumerate(zip(PROF, PROF[1:])):
        if t0 <= t <= t1:
            m0 = (r1 - PROF[i - 1][1]) / (t1 - PROF[i - 1][0]) if i else (r1 - r0) / (t1 - t0)
            m1 = (PROF[i + 2][1] - r0) / (PROF[i + 2][0] - t0) if i + 2 < len(PROF) else (r1 - r0) / (t1 - t0)
            h = t1 - t0; s = (t - t0) / h
            return ((2*s**3 - 3*s**2 + 1) * r0 + (s**3 - 2*s**2 + s) * h * m0
                    + (-2*s**3 + 3*s**2) * r1 + (s**3 - s**2) * h * m1)
    return PROF[-1][1]


TG = sorted({round(t, 2) for t in [x * 1.5 for x in range(41)] + [t for t, _ in PROF] if t <= TOP})


def cx(t):
    return 3 * (max(t, 0) / TOP) ** 1.5


def hp(t, th, dr=0.0):
    r = rr(t) + dr
    return Vector((cx(t) + r * math.cos(th), SY * r * math.sin(th), Z0 + t))


def ts(t0, t1, step=1.5):
    n = max(2, round((t1 - t0) / step)); return [t0 + (t1 - t0) * i / n for i in range(n + 1)]


def xr(t):
    return cx(t) - rr(t)


def head_plate(name, t0, t1, i0, i1, out=0.9, inn=3.0, m=A):
    rings = []
    for t in ts(t0, t1):
        arc = [hp(t, 2 * math.pi * i / NSEG, out) for i in range(i0, i1 + 1)]
        rings.append(arc + [hp(t, 2 * math.pi * i1 / NSEG, -inn), hp(t, 2 * math.pi * i0 / NSEG, -inn)])
    return g['rings_obj'](name, rings, m=m)


# ---- leaf cowl over the face ----
C0, C1, CW = 5.0, 58.0, math.radians(40)
U = [-1 + 2 * i / 14 for i in range(15)]


def cw(t, k=1.0):
    s = (t - C0) / (C1 - C0)
    w = CW * (0.45 + 0.55 * math.sin(math.pi / 2 * min(s / .32, 1))) * (1 - max(0, (s - .32) / .68)) ** 0.85
    return max(w * k, math.radians(1.2))


def cdr(t, u):
    s = (t - C0) / (C1 - C0); return 2.2 + 3.3 * math.sqrt(max(0, 1 - u * u)) + 3 * s ** 3 * (1 - u * u)


def cowl_pt(t, u, dr, k=1.0):
    return hp(t, u * cw(t, k), dr)


def cowl(name, t0, t1, k=1.0, lift=0.0, m=A):
    rings = []
    for t in ts(t0, t1, 1.0):
        rings.append([cowl_pt(t, u, cdr(t, u * k) + lift, k) for u in U] + [cowl_pt(t, u, -3, k) for u in reversed(U)])
    return g['rings_obj'](name, rings, m=m)


def groove(name, pts, nrm, w=0.9, d=0.7, m=GL):
    """V-groove cutter along a path; nrm(p) = outward normal at p."""
    rings = []
    for i, p in enumerate(pts):
        tan = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized(); n = nrm(p); s = tan.cross(n).normalized()
        rings.append([p + n * 1.5 + s * w, p + n * 1.5 - s * w, p - n * d])
    return g['rings_obj'](name, rings, m=m)


def tube(name, P0, P1, r0, r1, m=GL):
    o = g['axcyl'](name, P0, P1, r1, seg=48, m=m)
    return g['cut'](o, [g['axcyl'](name + 'i', P0 - (P1 - P0), P1 + (P1 - P0), r0, seg=48)])


def blade(name, pts, half, m=A):
    return g['rings_obj'](name, [[Vector((x, dy, Z0 + t)) for x, t in pts] for dy in (-half, half)], m=m)


def bez(p0, p1, p2, n=14):
    return [tuple((1 - u)**2 * a + 2 * (1 - u) * u * b + u**2 * c for a, b, c in zip(p0, p1, p2)) for u in (i / n for i in range(n + 1))]


def band(ctrl, w0, w1, side=0):
    """(x, t) outline of a curved strip along a quadratic bezier, width w0 -> w1 (side=1: grows to the +normal only)."""
    c = bez(*ctrl); n = len(c) - 1; L, R = [], []
    for i, p in enumerate(c):
        q0, q1 = c[max(i - 1, 0)], c[min(i + 1, n)]; tx, tt = q1[0] - q0[0], q1[1] - q0[1]; ln = math.hypot(tx, tt)
        nx, nt = -tt / ln, tx / ln; w = w0 + (w1 - w0) * i / n
        a = w if side else w / 2; b = 0 if side else w / 2
        L.append((p[0] + nx * a, p[1] + nt * a)); R.append((p[0] - nx * b, p[1] - nt * b))
    return L + R[::-1]


def build_head():
    RO, AX, SP = g['rings_obj'], g['axcyl'], g['sphere']
    g['MAT'] = B
    TH = [2 * math.pi * i / NSEG for i in range(NSEG)]
    body = RO('head_body', [[hp(t, th) for th in TH] for t in TG])
    bm = bmesh.new(); bm.from_mesh(body.data); tree = BVHTree.FromBMesh(bm); bm.free()
    P, C = [body], []
    P += [cowl('cowl', C0, C1), cowl('cowl_leaf', 14, 50, k=0.5, lift=0.9)]
    for s in (1, -1):
        P += [head_plate(f'cheek{s}', 8, 52, 7 * s if s > 0 else -11, 11 if s > 0 else -7),
              head_plate(f'crown{s}', 50, 57, 3 * s if s > 0 else -12, 12 if s > 0 else -3, m=B)]
    P += [head_plate('back0', 6, 15, 24, 40), head_plate('back1', 17, 28, 25, 39)]
    # chin gun: housing, twin barrels, whiskers, hook
    gx = cowl_pt(C0 + 1.5, 0, 0).x + 1
    P.append(SP('gun', (gx, 0, Z0 + 5), 3.6, m=M))
    bd = Vector((1, 0, -0.3)).normalized()
    for s in (1, -1):
        b0 = Vector((gx + 1, 1.9 * s, Z0 + 4.5))
        P.append(AX(f'barrel{s}', b0, b0 + bd * 6.5, 1.3, m=M))
        C.append(AX(f'bore{s}', b0 + bd * 3, b0 + bd * 7, 0.6, seg=12, m=GL))
        w0 = Vector((gx, 2.2 * s, Z0 + 4.5)); wd = Vector((0.35, s, -0.5)).normalized()
        P.append(AX(f'whisker{s}', w0, w0 + wd * 12, 0.9, r1=0.35, seg=10, m=M))
        # ears on the crown
        e0 = hp(55, math.radians(30) * s, -2); ed = Vector((0.15, 0.35 * s, 1)).normalized()
        P.append(AX(f'ear{s}', e0, e0 + ed * 8, 3.2, r1=0.3, seg=4, m=A))
    h0 = Vector((gx - 6, 0, Z0 + 2)); P.append(AX('chin_hook', h0, h0 + Vector((0.45, 0, -1)).normalized() * 9, 1.8, r1=0.3, seg=8, m=A))
    # side emitters + lance rods
    for s in (1, -1):
        for j, D in enumerate(DISCS):
            o = Vector((cx(D['t']), 0, Z0 + D['t'])); dv = Vector((D['d'][0], s * D['d'][1], D['d'][2])).normalized()
            hit = tree.ray_cast(o, dv)[3]
            for k, (r, h, m) in enumerate(D['steps']):
                P.append(AX(f'disc{s}{j}{k}', o + dv * (hit - 5), o + dv * (hit + h), r, seg=48 if r > 5 else 24, m=m))
            top = D['steps'][-1][1]
            P.append(SP(f'dome{s}{j}', o + dv * (hit + top), D['ball'], m=M))
            nr, nl = D['noz']
            P.append(AX(f'noz{s}{j}', o + dv * (hit + top), o + dv * (hit + nl), nr, m=M))
            P.append(AX(f'nozc{s}{j}', o + dv * (hit + nl - 1.4), o + dv * (hit + nl + 0.3), nr + 0.6, m=M))
            C.append(AX(f'nbore{s}{j}', o + dv * (hit + nl - 3), o + dv * (hit + nl + 1), nr * 0.5, seg=12, m=GL))
            r2 = D['steps'][2][0]
            C.append(tube(f'ring{s}{j}', o + dv * (hit + 2.5), o + dv * (hit + 3.5), r2 - 1.6, r2 - 1.0))
            rim = Vector(D['rim']); rim = (rim - dv * rim.dot(dv)).normalized()
            R0 = D['steps'][0][0]
            bc = o + dv * (hit + 1.5) + rim * (R0 - 1.0)
            rd = Vector((D['rod'][0], s * D['rod'][1], D['rod'][2])).normalized()
            P += [SP(f'rball{s}{j}', bc, 2.8, m=M), AX(f'rod{s}{j}0', bc, bc + rd * 8, 1.6, m=A),
                  AX(f'rodc{s}{j}', bc + rd * 7.5, bc + rd * 9, 2.1, m=M), AX(f'rod{s}{j}1', bc + rd * 8.5, bc + rd * 15, 1.3, m=A),
                  AX(f'rodt{s}{j}', bc + rd * 14.5, bc + rd * 18, 1.3, r1=0.4, m=A)]
    # rear fin: a curved stem from the back up to a hooked tip, and a crescent flag from the tip back to the crown
    P.append(blade('fin_stem', band(((-21, 27), (-43, 38), (-45, 67)), 3.6, 0.8), 1.6))
    P.append(blade('fin_flag', band(((-45, 67), (-27, 57), (-2, 57.5)), 0.8, 4.0, side=1), 1.4))
    head = g['union_all']('HeadNew', P)
    # blue energy lines: cowl centre + leaf outline, collar ring; split pins + neck dowels
    ctr = [cowl_pt(t, 0, cdr(t, 0) + 0.9, 0.5) for t in ts(16, 48, 1.0)]
    C.append(groove('cgroove', ctr, lambda p: Vector((1, 0, 0))))
    for s in (1, -1):
        pts = [cowl_pt(t, 0.72 * s, cdr(t, 0.72) + 0.2) for t in ts(9, 44, 1.0)]
        C.append(groove(f'lgroove{s}', pts, lambda p: Vector((p.x - cx(p.z - Z0), p.y, 0)).normalized(), w=0.6, d=0.6))
    for i, (x, t) in enumerate(((2, 12), (-10, 30), (10, 30), (0, 48))):
        C.append(AX(f'hpin{i}', (x, -4, Z0 + t), (x, 4, Z0 + t), 1.05))
    for i, x in enumerate((-3, 3)):
        C.append(AX(f'npin{i}', (x, 0, Z0 - 5), (x, 0, Z0 + 5), 1.05))
    g['cut'](head, C)
    return g['tri'](head)


g.update(build_head=build_head, rr=rr, cx=cx, hp=hp, HEAD_Z0=Z0)
if __name__ == 'head':
    for n in ('HeadNew', 'head_body'):
        if n in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[n])
    h = build_head()
    print(g['stats'](h))
