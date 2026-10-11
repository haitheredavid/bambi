from pathlib import Path

import pytest
import trimesh

from bambi import colour, orientation, printability

STL = Path(__file__).parent / "fixtures" / "coupon" / "stl"


def test_flat_ledge_blocks_without_supports():
    # The witch-frame coupon whose flat 3.7 mm glazing lip sagged in PETG.
    r = printability.analyse(STL / "Coupon_C10_Flat_A.stl", h=0.16)
    [ceiling] = [u for u in r.unsupported if u.kind == "ceiling"]
    assert ceiling.severity == "block"
    assert ceiling.anchored == "cantilever"
    assert 8.8 < ceiling.z[0] < 9.2
    assert 3.0 < ceiling.span_mm < 3.8
    assert r.severity == "block"


def test_supports_downgrade_the_ledge_to_a_warning():
    r = printability.analyse(STL / "Coupon_C10_Flat_A.stl", h=0.16, supports=True)
    assert r.severity == "warn"


def test_chamfered_lip_needs_nothing():
    r = printability.analyse(STL / "Coupon_C10_Chamfer_A.stl", h=0.16)
    assert r.unsupported == [] and r.severity == "ok"


def test_tenon_with_chamfered_edges_is_clean():
    assert (
        printability.analyse(STL / "Coupon_C10_Flat_Tenon.stl", h=0.16).severity == "ok"
    )


@pytest.mark.parametrize(
    ("width", "kind"), [(0.5, "wall"), (0.3, "feature"), (1.2, None)]
)
def test_thin_fin(width, kind):
    fin = trimesh.creation.box((20, width, 10))
    fin.apply_translation([0, 0, 5])
    r = printability.analyse(Path("fin.stl"), h=0.2, mesh=fin)
    assert {t.kind for t in r.thin} == ({kind} if kind else set())


def test_island_found():
    a = trimesh.creation.box((10, 10, 2))
    a.apply_translation([0, 0, 1])
    b = trimesh.creation.box((5, 5, 2))
    b.apply_translation([20, 0, 6])  # floats 5 mm above the bed
    r = printability.analyse(
        Path("two.stl"), h=0.2, mesh=trimesh.util.concatenate([a, b])
    )
    assert any(u.kind == "island" and u.severity == "block" for u in r.unsupported)


def test_bridge_vs_cantilever():
    # An arch: two pillars and a 6 mm span on top bridges; the ledge on one pillar doesn't.
    left = trimesh.creation.box((2, 10, 5))
    left.apply_translation([-4, 0, 2.5])
    right = left.copy()
    right.apply_translation([8, 0, 0])
    top = trimesh.creation.box((10, 10, 2))
    top.apply_translation([0, 0, 6])
    arch = trimesh.boolean.union([left, right, top], engine="manifold")
    r = printability.analyse(Path("arch.stl"), h=0.2, mesh=arch)
    [c] = [u for u in r.unsupported if u.kind == "ceiling"]
    assert c.anchored == "bridge" and c.severity == "warn"


def test_orientation_prefers_the_ledge_free_side():
    mesh = trimesh.load_mesh(STL / "Coupon_C10_Flat_A.stl")
    best = orientation.rank(mesh, h=0.16)[0]
    assert best.label != "as modelled"
    assert best.report.severity == "ok"


@pytest.mark.parametrize(
    ("sets", "swaps"),
    [
        ([{1}, {1}, {2}, {2}], 1),  # a colour band
        ([{1, 2}, {1, 2}, {1, 2}], 3),  # an inlay: 1 swap a layer, starting on the last
        ([{1}, {1, 2, 3}, {3}], 2),
        ([set(), {1}], 0),
    ],
)
def test_count_swaps(sets, swaps):
    assert colour.count_swaps(sets) == swaps


def test_colour_recommends_glue_in_for_tall_inlays():
    rows = colour.strategies([{1, 2}] * 200, colours=2)
    assert rows[0].name == "ams-inlay" and rows[0].swaps == 200
    assert colour.recommend(rows).startswith("glue-in")
