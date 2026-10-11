"""examples/witch-frame-coupon: a real session, run through what works without Blender."""

from pathlib import Path

from bambi import mesh, printability, profiles, session

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "witch-frame-coupon"


def test_example_resolves_by_path():
    s = session.resolve(str(EXAMPLE))
    assert s.path == EXAMPLE
    assert not s.is_pack
    assert len(s.export_files()) >= 2


def test_example_profiles_are_bundled():
    s = session.resolve(str(EXAMPLE))
    assert profiles.path_for("process", s.config["slice"]["process"]).exists()
    for f in s.filaments():
        assert profiles.path_for("filament", f.profile).exists()


def test_example_parts_are_printable_meshes():
    for stl in session.resolve(str(EXAMPLE)).export_files():
        assert mesh.check(stl).watertight, stl.name
        part = printability.analyse(stl, h=0.16)
        assert all(0 < x <= 256 for x in part.size), stl.name
