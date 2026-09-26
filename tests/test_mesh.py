import trimesh

from bambi import mesh


def test_cube_is_clean(tmp_path):
    path = tmp_path / "cube.stl"
    trimesh.creation.box((20, 20, 20)).export(path)
    r = mesh.check(path)
    assert r.watertight
    assert r.problems == []
    assert r.volume_cm3 == 8.0
    assert round(r.solid_weight_g("pla"), 2) == 9.92


def test_flags_metre_scale_and_oversize(tmp_path):
    tiny = tmp_path / "tiny.stl"
    trimesh.creation.box((0.02, 0.02, 0.02)).export(tiny)
    assert any("metres" in p for p in mesh.check(tiny).problems)

    huge = tmp_path / "huge.stl"
    trimesh.creation.box((300, 10, 10)).export(huge)
    assert any("too large" in p for p in mesh.check(huge).problems)


def test_open_mesh_not_watertight(tmp_path):
    box = trimesh.creation.box((10, 10, 10))
    box.update_faces([True] * 10 + [False] * 2)
    path = tmp_path / "open.stl"
    box.export(path)
    assert not mesh.check(path).watertight
