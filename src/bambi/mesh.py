"""Host-side mesh checks with trimesh (no Blender needed)."""

from dataclasses import dataclass, field
from pathlib import Path

import trimesh

# P1S build volume in mm.
BED = (256.0, 256.0, 256.0)

# g/cm^3 — rough densities for a solid-part weight upper bound.
DENSITY = {"pla": 1.24, "petg": 1.27, "abs": 1.04, "asa": 1.07, "tpu": 1.21}


@dataclass
class MeshReport:
    path: Path
    watertight: bool
    size_mm: tuple[float, float, float]
    volume_cm3: float
    triangles: int
    problems: list[str] = field(default_factory=list)

    def solid_weight_g(self, material: str = "pla") -> float:
        return self.volume_cm3 * DENSITY.get(material.lower(), 1.24)


def check(path: Path) -> MeshReport:
    mesh = trimesh.load_mesh(path, force="mesh")
    size = tuple(float(x) for x in mesh.extents)
    report = MeshReport(
        path=path,
        watertight=bool(mesh.is_watertight),
        size_mm=size,
        volume_cm3=float(abs(mesh.volume)) / 1000.0 if mesh.is_volume else 0.0,
        triangles=len(mesh.faces),
    )
    if not mesh.is_watertight:
        report.problems.append("not watertight (holes or non-manifold edges)")
    if not mesh.is_winding_consistent:
        report.problems.append("inconsistent face winding (flipped normals)")
    if any(s > b for s, b in zip(sorted(size), sorted(BED))):
        report.problems.append(
            f"too large for the {BED[0]:.0f}mm bed: {size_mm_str(size)}"
        )
    if max(size) < 1.0:
        report.problems.append(
            f"tiny ({size_mm_str(size)}), probably modelled in metres; sessions expect 1 unit = 1 mm"
        )
    return report


def size_mm_str(size: tuple[float, float, float]) -> str:
    return " x ".join(f"{s:.1f}" for s in size) + " mm"
