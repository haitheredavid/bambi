from datetime import date
from pathlib import Path

import pytest

from bambi import session, slicer
from bambi.slicer import Filament


def test_create_fills_template(sessions_dir):
    s = session.create("Phone Stand!", base=sessions_dir, today=date(2026, 9, 26))
    assert s.name == "2026-09-26-phone-stand"
    assert s.config["name"] == "phone-stand"
    assert s.config["created"] == "2026-09-26"
    assert s.config["slice"]["machine"] == "p1s_0.4"
    assert s.exports.is_dir() and s.out.is_dir()
    assert s.status() == "new"


def test_create_refuses_duplicates(sessions_dir):
    session.create("cube", base=sessions_dir, today=date(2026, 9, 26))
    with pytest.raises(FileExistsError):
        session.create("cube", base=sessions_dir, today=date(2026, 9, 26))


def test_resolve_by_substring(sessions_dir):
    session.create("cube", base=sessions_dir, today=date(2026, 9, 26))
    session.create("cube-v2", base=sessions_dir, today=date(2026, 9, 26))
    assert (
        session.resolve("2026-09-26-cube", base=sessions_dir).name == "2026-09-26-cube"
    )
    assert session.resolve("v2", base=sessions_dir).name == "2026-09-26-cube-v2"
    with pytest.raises(LookupError, match="ambiguous"):
        session.resolve("cube", base=sessions_dir)
    with pytest.raises(LookupError, match="no session"):
        session.resolve("nope", base=sessions_dir)


def test_list_skips_template(sessions_dir):
    session.create("a", base=sessions_dir)
    assert [s.name.split("-", 3)[-1] for s in session.list_all(base=sessions_dir)] == [
        "a"
    ]


def _with_config(s, extra: str):
    toml = s.path / "session.toml"
    toml.write_text(toml.read_text() + extra)
    return s


def test_single_filament_default(sessions_dir):
    s = session.create("cube", base=sessions_dir)
    [f] = s.filaments()
    assert (f.profile, f.color, f.ams_slot) == ("pla_basic", None, 0)


def test_multicolor_filaments_and_objects(sessions_dir, tmp_path):
    s = _with_config(
        session.create("sign", base=sessions_dir),
        """
[[filaments]]
profile = "pla_basic"
color = "#FFFFFF"

[[filaments]]
profile = "pla_basic"
color = "#000000"
ams_slot = 3

[objects]
Logo = 2
""",
    )
    white, black = s.filaments()
    assert (white.color, white.ams_slot) == ("#FFFFFF", 0)
    assert (black.color, black.ams_slot) == ("#000000", 3)
    models = [tmp_path / "Base.stl", tmp_path / "Logo.stl"]
    assert s.object_filament_ids(models) == [1, 2]
    with pytest.raises(ValueError, match="Logo"):
        s.object_filament_ids(models[:1])


def test_write_filaments_replaces_block(sessions_dir):
    s = session.create("ams", base=sessions_dir, today=date(2026, 9, 27))
    toml = s.path / "session.toml"
    toml.write_text(
        toml.read_text()
        + '\n[[filaments]]\nprofile = "old"\n\n[[filaments]]\nprofile = "old2"\n'
        + "\n# keep me\n[objects]\nTop = 2\n"
    )
    new = [Filament("pla_basic", "#FFFFFF", 0), Filament("petg_hf", None, 3)]
    s.write_filaments(new, ["tray: PLA Basic (GFA00)"])
    text = toml.read_text()
    assert "old" not in text and "# keep me" in text
    assert "# tray: PLA Basic (GFA00)" in text
    cfg = s.config
    assert cfg["objects"] == {"Top": 2}
    assert cfg["slice"]["machine"] == "p1s_0.4"
    assert cfg["filaments"] == [
        {"profile": "pla_basic", "color": "#FFFFFF", "ams_slot": 0},
        {"profile": "petg_hf", "ams_slot": 3},
    ]


def test_write_filaments_appends(sessions_dir):
    s = session.create("ams2", base=sessions_dir, today=date(2026, 9, 27))
    s.write_filaments([Filament("pla_basic", "#000000", 1)])
    assert s.filaments() == [Filament("pla_basic", "#000000", 1)]
    s.write_filaments([Filament("petg_hf", "#FF0000", 2)])  # replaces, idempotent
    assert s.filaments() == [Filament("petg_hf", "#FF0000", 2)]


def test_profile_less_filament_needs_ams(sessions_dir, tmp_path):
    with pytest.raises(ValueError, match="--ams"):
        slicer.SliceJob(
            models=[Path("a.stl")],
            output=tmp_path / "x.gcode.3mf",
            filaments=[Filament(profile=None, ams_slot=2)],
        )


def test_render_options(sessions_dir):
    s = session.create("cube", base=sessions_dir, today=date(2026, 9, 26))
    assert s.render_options() == {"framing": "fit", "scene": None}  # template default
    toml = s.path / "session.toml"
    toml.write_text(
        toml.read_text().replace(
            '# framing = "fit"', 'framing = "wide"\nscene = "Scene"'
        )
    )
    assert s.render_options() == {"framing": "wide", "scene": "Scene"}
    toml.write_text(toml.read_text().replace('"wide"', '"close"'))
    with pytest.raises(ValueError, match="framing"):
        s.render_options()
