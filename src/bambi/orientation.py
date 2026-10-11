"""Rank print orientations for a part (host side).

Candidates: as-is, the six axis-aligned rotations, and each large planar face direction laid
on the bed. A cheap face-normal proxy ranks them all; the best few get the full layer analysis
(printability.analyse), and the final order weighs:
the bed-projected area that would need support (minus bridges the printer spans), then
print height (time), then too little bed contact.

Bambu's own auto-orient is off for designed parts (it stood the half-step on end); this exists
so the choice is explicit and explained, not to be applied blindly. Strength (layer lines
across the load) and the cosmetic face are the user's call and aren't scored.
"""

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import trimesh
from trimesh import transformations as tf

from bambi import printability

DOWN = np.array([0.0, 0.0, -1.0])


@dataclass
class Candidate:
    label: str
    matrix: np.ndarray = field(repr=False)
    proxy: float = 0.0
    height: float = 0.0
    contact_mm2: float = 0.0
    overhang_mm2: float = 0.0
    support_mm2: float = (
        0.0  # bed-projected area of everything that faces down in mid-air
    )
    report: printability.PartReport | None = None
    score: float = 0.0

    @property
    def rotate_deg(self) -> list[float]:
        """Blender XYZ Euler in degrees (static xyz)."""
        return [
            round(math.degrees(a), 1) + 0.0
            for a in tf.euler_from_matrix(self.matrix, "sxyz")
        ]

    def to_json(self) -> dict:
        r = self.report
        return {
            "label": self.label,
            "rotate_deg": self.rotate_deg,
            "score": round(self.score, 1),
            "height": round(self.height, 2),
            "contact_mm2": round(self.contact_mm2, 1),
            "overhang_mm2": round(self.overhang_mm2, 1),
            "support_mm2": round(self.support_mm2, 1),
            "severity": r.severity if r else None,
            "findings": [
                printability.describe(x) for x in (r.unsupported if r else [])
            ],
        }


def _axis_rotations() -> list[tuple[str, np.ndarray]]:
    rx = lambda d: tf.rotation_matrix(math.radians(d), [1, 0, 0])
    ry = lambda d: tf.rotation_matrix(math.radians(d), [0, 1, 0])
    return [
        ("as modelled", np.eye(4)),
        ("flipped (top down)", rx(180)),
        ("on +Y face", rx(-90)),
        ("on -Y face", rx(90)),
        ("on +X face", ry(90)),
        ("on -X face", ry(-90)),
    ]


def _face_directions(mesh: trimesh.Trimesh, count: int = 8) -> list[np.ndarray]:
    """Normals of the largest planar areas (face normals grouped to ~1°, by total area)."""
    keys = np.round(mesh.face_normals * 60).astype(int)
    groups: dict[tuple, list] = {}
    for k, n, a in zip(map(tuple, keys), mesh.face_normals, mesh.area_faces):
        g = groups.setdefault(k, [np.zeros(3), 0.0])
        g[0] += n * a
        g[1] += a
    ranked = sorted(groups.values(), key=lambda g: -g[1])[:count]
    return [g[0] / np.linalg.norm(g[0]) for g in ranked if np.linalg.norm(g[0]) > 0]


def candidates(mesh: trimesh.Trimesh) -> list[Candidate]:
    out = [Candidate(label, m) for label, m in _axis_rotations()]
    for n in _face_directions(mesh):
        m = trimesh.geometry.align_vectors(n, DOWN)
        out.append(Candidate(f"face {np.round(n, 2).tolist()} down", m))
    seen, unique = [], []
    for c in out:
        down = c.matrix[:3, :3].T @ DOWN  # the model direction that ends up on the bed
        if any(np.allclose(down, d, atol=0.02) for d in seen):
            continue
        seen.append(down)
        unique.append(c)
    return unique


def _proxy(mesh: trimesh.Trimesh, c: Candidate) -> None:
    normals = mesh.face_normals @ c.matrix[:3, :3].T
    centers = trimesh.transform_points(mesh.triangles_center, c.matrix)
    zmin = trimesh.transform_points(mesh.vertices, c.matrix)[:, 2].min()
    zmax = trimesh.transform_points(mesh.vertices, c.matrix)[:, 2].max()
    on_bed = centers[:, 2] < zmin + 0.05
    limit = -math.cos(math.radians(printability.OVERHANG_DEG))
    over = (normals[:, 2] < limit) & ~on_bed
    c.height = float(zmax - zmin)
    c.contact_mm2 = float(mesh.area_faces[on_bed & (normals[:, 2] < -0.99)].sum())
    c.overhang_mm2 = float(mesh.area_faces[over].sum())
    # What support would have to hold up: downward faces projected onto the bed.
    c.support_mm2 = float((mesh.area_faces[over] * -normals[over, 2]).sum())
    c.proxy = c.support_mm2 + 2.0 * c.height + _contact_penalty(c.contact_mm2)


def _contact_penalty(contact: float) -> float:
    return (1000.0 if contact < printability.CONTACT_MIN else 0.0) - 0.05 * min(
        contact, 2000.0
    )


def rank(
    mesh: trimesh.Trimesh, h: float = 0.2, full: int = 4, name: str = "part"
) -> list[Candidate]:
    cands = candidates(mesh)
    for c in cands:
        _proxy(mesh, c)
    cands.sort(key=lambda c: c.proxy)
    current = next(c for c in cands if c.label == "as modelled")
    detailed = cands[:full] + ([current] if current not in cands[:full] else [])
    for c in detailed:
        m = mesh.copy()
        m.apply_transform(c.matrix)
        m.apply_translation([0, 0, -m.bounds[0][2]])
        c.report = printability.analyse(Path(f"{name}.stl"), h=h, mesh=m)
        # Bridges the printer handles need no support: take them back out of the estimate.
        bridged = sum(
            r.area_mm2
            for r in c.report.unsupported
            if r.kind == "ceiling" and r.anchored == "bridge" and r.severity != "block"
        )
        c.score = (
            max(c.support_mm2 - bridged, 0.0)
            + 2.0 * c.height
            + _contact_penalty(c.report.contact_mm2)
        )
    detailed.sort(key=lambda c: c.score)
    return detailed
