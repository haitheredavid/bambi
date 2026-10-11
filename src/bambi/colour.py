"""Colour strategy: what a multi-colour part costs as AMS swaps vs the alternatives.

Every layer that holds more than one filament costs a filament change per extra colour (P1S:
cut, retract, purge into the poop chute). On a tall part with inlays that adds up fast:
anubis-head's inlays meant about 690 swaps, 18h30 and 361 g, against 3h06 and 113.5 g as
glue-in trim. The per-swap constants below come from that pair.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh

from bambi import printability

SWAP_SECONDS = 80.0  # (18h30 - 3h06) / 690
SWAP_GRAMS = 0.36  # (361 - 113.5) / 690
GLUE_POCKET_MM = 1.2  # glue-in: pocket depth in the body
GLUE_INSET_MM = 0.25  # glue-in: inlay piece shrunk this much per side
INLAY_SWAP_LIMIT = 60  # above this, AMS inlays usually lose to glue-in


@dataclass
class Strategy:
    name: str
    swaps: int
    extra_minutes: float
    extra_grams: float
    parts_change: str
    note: str

    def to_json(self) -> dict:
        return self.__dict__ | {
            "extra_minutes": round(self.extra_minutes),
            "extra_grams": round(self.extra_grams, 1),
        }


def layer_sets(parts: list[tuple[Path, int]], h: float) -> list[set[int]]:
    """Filament numbers present in each layer, for parts placed as they'll print."""
    mfs = []
    top = 0.0
    for path, fil in parts:
        mesh = trimesh.load_mesh(path, force="mesh")
        mfs.append((printability.to_manifold(mesh), fil))
        top = max(top, float(mesh.bounds[1][2]))
    heights = np.arange(h / 2, top, h)
    sets: list[set[int]] = [set() for _ in heights]
    for mf, fil in mfs:
        lo, hi = mf.bounding_box()[2], mf.bounding_box()[5]
        for i, z in enumerate(heights):
            if lo <= z <= hi and mf.slice(float(z)).area() > 0.01:
                sets[i].add(fil)
    return sets


def count_swaps(sets: list[set[int]]) -> int:
    """Filament changes if each layer starts with the filament the last one ended on."""
    swaps, last = 0, None
    for s in sets:
        if not s:
            continue
        if last is None:
            swaps += len(s) - 1
            last = max(s)
        elif last in s:
            swaps += len(s) - 1
            last = max(s - {last}) if len(s) > 1 else last
        else:
            swaps += len(s)
            last = max(s)
    return swaps


def strategies(sets: list[set[int]], colours: int) -> list[Strategy]:
    swaps = count_swaps(sets)
    mixed = sum(1 for s in sets if len(s) > 1)
    banded = mixed == 0
    rows = [
        Strategy(
            "ams-bands" if banded else "ams-inlay",
            swaps,
            swaps * SWAP_SECONDS / 60,
            swaps * SWAP_GRAMS,
            "none",
            "colour changes at layer boundaries only: cheap"
            if banded
            else f"{mixed} layers mix colours; floating inlays need [slice] assemble",
        ),
        Strategy(
            "glue-in",
            0,
            0.0,
            0.0,
            f"pockets {GLUE_POCKET_MM} mm deep in the body; trim pieces inset "
            f"{GLUE_INSET_MM} mm/side, printed flat in their own colour",
            "one print per colour, then glue (CA for PLA, epoxy for PETG)",
        ),
        Strategy(
            "paint",
            0,
            0.0,
            0.0,
            "none (single colour); optionally 0.4-0.6 mm recessed outlines as paint guides",
            "slowest by hand, any number of colours",
        ),
        Strategy(
            "engrave",
            0,
            0.0,
            0.0,
            "detail cut 0.6 mm+ into the surface, single colour",
            "reads by shadow only; fine for text and logos",
        ),
    ]
    if colours <= 1:
        return rows[2:]
    return rows


def recommend(rows: list[Strategy]) -> str:
    ams = next((r for r in rows if r.name.startswith("ams")), None)
    if ams is None:
        return "single colour: nothing to choose"
    if ams.name == "ams-bands" or ams.swaps <= 15:
        return f"{ams.name}: only {ams.swaps} swaps"
    if ams.swaps > INLAY_SWAP_LIMIT:
        return (
            f"glue-in: AMS would add {ams.swaps} swaps "
            f"(~{ams.extra_minutes / 60:.1f} h, ~{ams.extra_grams:.0f} g purge)"
        )
    return f"either: {ams.swaps} swaps (~{ams.extra_minutes:.0f} min) is tolerable for inlays"
