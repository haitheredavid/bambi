"""Layer-based printability analysis of exported parts (host side, no Blender).

Each part is sliced into layers at the process layer height (manifold3d), and the layer
outlines (shapely) answer what the face-angle check in Blender can't:
- unsupported regions: flat ceilings and ledges (bridged or cantilevered), steep overhang
  bands, and islands that start in mid-air;
- thin walls and features below what the nozzle lays down;
- bed contact (adhesion) and overlapping shells.

Severity is relative to the slice: an unsupported region is fine when supports are on.
"""

import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import manifold3d as m3
import numpy as np
import trimesh
from shapely import MultiPolygon, Polygon, maximum_inscribed_circle, union_all
from shapely.geometry.base import BaseGeometry

OVERHANG_DEG = 45.0  # steeper than this from vertical needs support
MIN_AREA = (
    2.0  # mm²: smaller unsupported pieces are tessellation noise or self-supporting
)
CEILING_WIDTH = (
    1.0  # mm: unsupported pieces wider than this are ceilings, not slope steps
)
BRIDGE_MAX = 10.0  # mm: the P1S bridges this far cleanly
CANTILEVER_MAX = (
    1.0  # mm: a ledge anchored on one side sags past this (witch-frame 3.7 mm)
)
WALL_MIN = 0.8  # mm: 2 perimeters at 0.4
FEATURE_MIN = 0.4  # mm: one line; thinner may vanish
CONTACT_MIN = 60.0  # mm² on the first layer
ASPECT_MAX = 4.0  # height / sqrt(contact): taller than this tips or wobbles
SEVERITY = ("ok", "warn", "block")


@dataclass
class Region:
    kind: str  # ceiling | overhang | island
    z: tuple[float, float]
    area_mm2: float
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1
    anchored: str = ""  # bridge | cantilever | none (ceilings)
    span_mm: float = 0.0  # bridge span or cantilever reach
    severity: str = "warn"


@dataclass
class Thin:
    kind: str  # wall (<0.8) | feature (<0.4)
    z: tuple[float, float]
    area_mm2: float
    bbox: tuple[float, float, float, float]
    severity: str = "warn"


@dataclass
class PartReport:
    name: str
    size: tuple[float, float, float]
    bodies: int
    contact_mm2: float
    aspect: float
    unsupported: list[Region] = field(default_factory=list)
    thin: list[Thin] = field(default_factory=list)
    overlaps_cm3: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def severity(self) -> str:
        levels = [r.severity for r in self.unsupported] + [
            t.severity for t in self.thin
        ]
        if self.overlaps_cm3 > 0.001:
            levels.append("warn")
        if self.contact_mm2 < CONTACT_MIN or self.aspect > ASPECT_MAX:
            levels.append("warn")
        return max(levels, key=SEVERITY.index, default="ok")

    def to_json(self) -> dict:
        d = asdict(self)
        d["severity"] = self.severity
        return d


def to_manifold(mesh: trimesh.Trimesh) -> m3.Manifold:
    return m3.Manifold(
        m3.Mesh(
            vert_properties=np.asarray(mesh.vertices, dtype=np.float32),
            tri_verts=np.asarray(mesh.faces, dtype=np.uint32),
        )
    )


def _shape(cs: m3.CrossSection) -> BaseGeometry:
    """CrossSection -> shapely, with holes (even-odd over the contours)."""
    polys = [Polygon(c) for c in cs.to_polygons() if len(c) >= 3]
    shape: BaseGeometry = Polygon()
    for p in polys:
        shape = shape.symmetric_difference(p.buffer(0))
    return shape


def layers(mf: m3.Manifold, h: float) -> list[tuple[float, BaseGeometry]]:
    """Layer outlines at mid-layer heights (h/2, 3h/2, ...): never on a facet plane."""
    lo, hi = mf.bounding_box()[2], mf.bounding_box()[5]
    zs = np.arange(lo + h / 2, hi, h)
    return [(float(z), _shape(mf.slice(float(z)))) for z in zs]


def _pieces(g: BaseGeometry) -> list[Polygon]:
    if g.is_empty:
        return []
    if isinstance(g, Polygon):
        return [g]
    return [p for p in getattr(g, "geoms", []) if isinstance(p, Polygon) and p.area > 0]


def _width(p: Polygon) -> float:
    """Narrowest-direction width: the diameter of the largest circle that fits.

    For an L-shaped ledge that's the ledge depth, not its length along the wall.
    """
    if p.is_empty or p.area <= 0:
        return 0.0
    return 2 * maximum_inscribed_circle(p, tolerance=0.02).length


def _anchor(piece: Polygon, held: BaseGeometry) -> tuple[str, float]:
    """How a ceiling piece is held at its edges: by 2+ separate edges (bridge) or one."""
    edge = piece.exterior.intersection(held.buffer(0.05))
    held = [
        g for g in getattr(edge, "geoms", [edge]) if not g.is_empty and g.length > 0.3
    ]
    if not held:
        return "none", _width(piece)
    merged = union_all([g.buffer(0.2) for g in held])
    groups = len(getattr(merged, "geoms", [merged]))
    return ("bridge" if groups >= 2 else "cantilever"), _width(piece)


def unsupported(
    stack: list[tuple[float, BaseGeometry]], h: float, supports: bool = False
) -> list[Region]:
    """Regions of each layer that the layer below can't hold up."""
    # A hair over 45° of reach: exact 45° chamfers land on the limit and flicker.
    reach = h * math.tan(math.radians(OVERHANG_DEG)) * 1.1
    found: list[Region] = []
    bands: dict[int, Region] = {}  # open overhang band, keyed by its first layer
    for i in range(1, len(stack)):
        z, cur = stack[i]
        below = stack[i - 1][1]
        if cur.is_empty:
            continue
        held = below.buffer(reach, join_style="mitre")
        band_area, band_box = 0.0, None
        for comp in _pieces(cur):
            if not comp.intersects(below):
                if comp.area >= MIN_AREA:
                    sev = "warn" if supports else "block"
                    found.append(_region("island", z, h, comp, sev=sev))
                continue
            for p in _pieces(comp.difference(held)):
                if p.area < 0.05:
                    continue
                w = _width(p)
                if w >= CEILING_WIDTH and p.area >= MIN_AREA:
                    anchored, span = _anchor(p, held)
                    bad = (anchored == "bridge" and span > BRIDGE_MAX) or (
                        anchored != "bridge" and span > CANTILEVER_MAX
                    )
                    r = _region(
                        "ceiling",
                        z,
                        h,
                        p,
                        sev="block" if bad and not supports else "warn",
                    )
                    r.anchored, r.span_mm = anchored, round(span, 2)
                    found.append(r)
                else:
                    band_area += p.area
                    b = p.bounds
                    band_box = b if band_box is None else _union_box(band_box, b)
        # Thin slope steps accumulate into an overhang band across consecutive layers.
        key = next(iter(bands), None)
        if band_area > 0:
            if key is None:
                bands[i] = Region(
                    "overhang", (z - h / 2, z + h / 2), band_area, band_box
                )
            else:
                r = bands[key]
                r.z = (r.z[0], z + h / 2)
                r.area_mm2 += band_area
                r.bbox = _union_box(r.bbox, band_box)
        elif key is not None:
            found.append(bands.pop(key))
    found.extend(bands.values())
    out = []
    for r in found:
        if r.kind == "overhang":
            if r.area_mm2 < MIN_AREA * 5:
                continue
            r.severity = "warn"
        r.area_mm2 = round(r.area_mm2, 1)
        r.z = (round(r.z[0], 2), round(r.z[1], 2))
        r.bbox = tuple(round(v, 1) for v in r.bbox)
        out.append(r)
    return _merge_ceilings(out)


def _region(kind: str, z: float, h: float, p: Polygon, sev: str) -> Region:
    return Region(kind, (z - h / 2, z + h / 2), p.area, p.bounds, severity=sev)


def _union_box(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _merge_ceilings(regions: list[Region]) -> list[Region]:
    """Ceiling pieces at one level, or in consecutive layers over the same spot (a shallow
    slope steps out more than a perimeter per layer), merge into one region."""
    out: list[Region] = []
    for r in sorted(regions, key=lambda r: (r.kind != "ceiling", r.z)):
        prev = next(
            (
                p
                for p in reversed(out)
                if p.kind == r.kind == "ceiling"
                and r.z[0] <= p.z[1] + 1e-6
                and _boxes_touch(p.bbox, r.bbox)
            ),
            None,
        )
        if prev is None:
            out.append(r)
            continue
        prev.z = (prev.z[0], max(prev.z[1], r.z[1]))
        prev.area_mm2 = round(prev.area_mm2 + r.area_mm2, 1)
        prev.bbox = _union_box(prev.bbox, r.bbox)
        prev.span_mm = max(prev.span_mm, r.span_mm)
        worse = SEVERITY.index(r.severity) > SEVERITY.index(prev.severity)
        if worse:
            prev.severity, prev.anchored = r.severity, r.anchored
    return out


def _boxes_touch(a, b, pad: float = 0.5) -> bool:
    return not (
        a[2] + pad < b[0] or b[2] + pad < a[0] or a[3] + pad < b[1] or b[3] + pad < a[1]
    )


def thin(stack: list[tuple[float, BaseGeometry]], h: float) -> list[Thin]:
    """Parts of each layer narrower than a wall (0.8) or a feature (0.4), as z bands."""
    found: list[Thin] = []
    for kind, w, sev in (("wall", WALL_MIN, "warn"), ("feature", FEATURE_MIN, "block")):
        band: Thin | None = None
        for z, g in stack:
            if g.is_empty:
                continue
            opened = g.buffer(-w / 2, join_style="mitre").buffer(
                w / 2, join_style="mitre"
            )
            narrow = g.difference(opened.buffer(0.01))
            area = sum(p.area for p in _pieces(narrow) if p.area > 0.02)
            if area > 0.2:
                if band is None:
                    band = Thin(kind, (z - h / 2, z + h / 2), area, narrow.bounds, sev)
                else:
                    band.z = (band.z[0], z + h / 2)
                    band.area_mm2 += area
                    band.bbox = _union_box(band.bbox, narrow.bounds)
            elif band is not None:
                found.append(band)
                band = None
        if band is not None:
            found.append(band)
    top = stack[-1][0] + h / 2 if stack else 0.0
    out = []
    for t in found:
        layers_spanned = (t.z[1] - t.z[0]) / h
        if t.area_mm2 < 1.0 or layers_spanned < 2:
            continue
        # A ridge or edge tapering to the top always thins out in its last layers; it prints
        # rounded, which is cosmetic. Small slivers are the same.
        if t.kind == "feature" and (
            t.area_mm2 < 5.0 or (top - t.z[1] < h and layers_spanned * h < 3)
        ):
            t.severity = "warn"
        t.area_mm2 = round(t.area_mm2, 1)
        t.z = (round(t.z[0], 2), round(t.z[1], 2))
        t.bbox = tuple(round(v, 1) for v in t.bbox)
        out.append(t)
    # A feature band is also a wall band; report the stricter one only where they overlap.
    features = [t for t in out if t.kind == "feature"]
    return [
        t
        for t in out
        if t.kind == "feature"
        or not any(f.z[0] <= t.z[0] and f.z[1] >= t.z[1] for f in features)
    ]


def analyse(
    path: Path,
    h: float = 0.2,
    supports: bool = False,
    mesh: trimesh.Trimesh | None = None,
) -> PartReport:
    mesh = mesh if mesh is not None else trimesh.load_mesh(path, force="mesh")
    mf = to_manifold(mesh)
    size = tuple(round(float(x), 2) for x in mesh.extents)
    bodies = mf.decompose()
    overlap = 0.0
    if len(bodies) > 1:
        for a in range(len(bodies)):
            for b in range(a + 1, len(bodies)):
                overlap += (bodies[a] ^ bodies[b]).volume()
    stack = layers(mf, h)
    first = stack[0][1] if stack else Polygon()
    contact = float(first.area)
    aspect = size[2] / math.sqrt(contact) if contact > 0 else float("inf")
    report = PartReport(
        name=path.stem,
        size=size,
        bodies=len(bodies),
        contact_mm2=round(contact, 1),
        aspect=round(aspect, 2),
        unsupported=unsupported(stack, h, supports=supports),
        thin=thin(stack, h),
        overlaps_cm3=round(overlap / 1000, 4),
    )
    if mf.status() != m3.Error.NoError:
        report.notes.append(f"manifold3d: {mf.status().name}; layer results may be off")
    if contact < CONTACT_MIN:
        report.notes.append(f"small bed contact ({contact:.0f} mm²): brim or reorient")
    elif aspect > ASPECT_MAX:
        report.notes.append(f"tall for its footprint (h/√contact {aspect:.1f}): brim")
    if report.overlaps_cm3 > 0.001:
        report.notes.append(
            f"{len(bodies)} overlapping shells ({report.overlaps_cm3} cm³ shared): union them"
        )
    return report


def overlaps_between(paths: list[Path]) -> list[tuple[str, str, float]]:
    """Pairwise intersection volume (cm³) of parts placed together (assemble mode)."""
    mfs = [(p.stem, to_manifold(trimesh.load_mesh(p, force="mesh"))) for p in paths]
    out = []
    for i in range(len(mfs)):
        for j in range(i + 1, len(mfs)):
            v = (mfs[i][1] ^ mfs[j][1]).volume() / 1000
            if v > 0.001:
                out.append((mfs[i][0], mfs[j][0], round(v, 4)))
    return out


def describe(r: Region | Thin) -> str:
    z = f"z {r.z[0]:g}-{r.z[1]:g}" if r.z[1] - r.z[0] > 0.3 else f"z {r.z[0]:g}"
    if isinstance(r, Thin):
        limit = WALL_MIN if r.kind == "wall" else FEATURE_MIN
        return f"{r.kind} < {limit} mm at {z} ({r.area_mm2} mm²)"
    if r.kind == "ceiling":
        how = {
            "bridge": f"bridge {r.span_mm} mm",
            "cantilever": f"ledge {r.span_mm} mm",
            "none": "floating",
        }[r.anchored]
        what = "flat ceiling" if r.z[1] - r.z[0] <= 0.3 else "shallow overhang"
        return f"{what} at {z}: {r.area_mm2} mm², {how}"
    if r.kind == "island":
        return f"island starts in mid-air at {z} ({r.area_mm2} mm²)"
    return f"overhang > {OVERHANG_DEG:g}° at {z} ({r.area_mm2} mm²)"


__all__ = [
    "MultiPolygon",
    "PartReport",
    "Region",
    "Thin",
    "analyse",
    "describe",
    "layers",
    "overlaps_between",
    "thin",
    "unsupported",
]
