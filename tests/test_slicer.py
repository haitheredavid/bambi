import json
from pathlib import Path

import pytest

from bambi import profiles, slicer
from bambi.config import get_settings


def test_command_uses_local_profiles(tmp_path):
    job = slicer.SliceJob(
        models=[Path("a.stl"), Path("b.stl")], output=tmp_path / "x.gcode.3mf"
    )
    process = tmp_path / "process.json"
    cmd = job.command(process, bin_path=Path("/bin/BambuStudio"))
    root = get_settings().profiles_dir
    assert cmd[0] == "/bin/BambuStudio"
    assert cmd[cmd.index("--load-settings") + 1] == (
        f"{root / 'machine/p1s_0.4.json'};{process}"
    )
    assert cmd[cmd.index("--load-filaments") + 1] == str(
        root / "filament/pla_basic.json"
    )
    assert cmd[cmd.index("--outputdir") + 1] == str(tmp_path)
    assert cmd[cmd.index("--export-3mf") + 1] == "x.gcode.3mf"
    assert cmd[-2:] == ["a.stl", "b.stl"]
    assert "--load-assemble-list" not in cmd


def test_multicolor_command(tmp_path):
    job = slicer.SliceJob(
        models=[Path("a.stl"), Path("b.stl"), Path("c.stl")],
        output=tmp_path / "x.gcode.3mf",
        filaments=[slicer.Filament("pla_basic"), slicer.Filament("petg_hf")],
        object_filaments=[1, 2, 1],
    )
    [plate] = job.assemble_list()["plates"]
    assert plate["need_arrange"] is True
    assert [(o["path"], o["filaments"]) for o in plate["objects"]] == [
        ("a.stl", [1]),
        ("b.stl", [2]),
        ("c.stl", [1]),
    ]
    with pytest.raises(ValueError, match="assemble list"):
        job.command(tmp_path / "process.json")
    files = [tmp_path / "f1.json", tmp_path / "f2.json"]
    asm = tmp_path / "assemble.json"
    cmd = job.command(tmp_path / "process.json", files, asm)
    assert cmd[cmd.index("--load-filaments") + 1] == f"{files[0]};{files[1]}"
    assert cmd[cmd.index("--load-assemble-list") + 1] == str(asm)
    assert "--allow-multicolor-oneplate" in cmd
    # The CLI rejects model files and transforms alongside an assemble list.
    assert "a.stl" not in cmd and "--orient" not in cmd and "--arrange" not in cmd

    assert all("assemble_index" not in o for o in plate["objects"])


def test_multicolor_assemble_merges_objects(tmp_path):
    job = slicer.SliceJob(
        models=[Path("body.stl"), Path("inlay.stl")],
        output=tmp_path / "x.gcode.3mf",
        filaments=[slicer.Filament("pla_basic"), slicer.Filament("petg_hf")],
        object_filaments=[1, 2],
        assemble=True,
    )
    [plate] = job.assemble_list()["plates"]
    assert [o["assemble_index"] for o in plate["objects"]] == [[1], [1]]


def test_filament_ids_validated(tmp_path):
    out = tmp_path / "x.gcode.3mf"
    two = [slicer.Filament(), slicer.Filament()]
    with pytest.raises(ValueError, match="out of range"):
        slicer.SliceJob(
            models=[Path("a.stl")], output=out, filaments=two, object_filaments=[3]
        )
    with pytest.raises(ValueError, match="2 filament ids for 1 models"):
        slicer.SliceJob(
            models=[Path("a.stl")], output=out, filaments=two, object_filaments=[1, 2]
        )
    with pytest.raises(ValueError, match="filaments"):
        slicer.SliceJob(models=[], output=out, filaments=[])


def test_filament_colour_override(tmp_path):
    job = slicer.SliceJob(
        models=[],
        output=tmp_path / "x.gcode.3mf",
        filaments=[slicer.Filament(), slicer.Filament(color="#FF0000")],
    )
    plain, red = job.filament_configs()
    assert red["filament_colour"] == ["#FF0000"]
    assert plain.get("filament_colour") != ["#FF0000"]


def test_missing_profile_is_clear(tmp_path):
    job = slicer.SliceJob(
        models=[],
        output=tmp_path / "x.gcode.3mf",
        filaments=[slicer.Filament("unobtainium")],
    )
    with pytest.raises(FileNotFoundError, match="profiles sync"):
        job.command(tmp_path / "process.json")


def test_plate_is_applied_to_process(tmp_path):
    out = tmp_path / "x.gcode.3mf"
    default = slicer.SliceJob(models=[], output=out)
    assert default.process_config()["curr_bed_type"] == "Textured PEI Plate"
    cool = slicer.SliceJob(models=[], output=out, plate="Cool Plate")
    assert cool.process_config()["curr_bed_type"] == "Cool Plate"
    with pytest.raises(ValueError, match="unknown plate"):
        slicer.SliceJob(models=[], output=out, plate="Glass")


def test_process_overrides(tmp_path):
    out = tmp_path / "x.gcode.3mf"
    job = slicer.SliceJob(
        models=[],
        output=out,
        overrides={"wall_loops": 5, "sparse_infill_density": "40%"},
    )
    data = job.process_config()
    assert data["wall_loops"] == "5"
    assert data["sparse_infill_density"] == "40%"
    with pytest.raises(ValueError, match="unknown process setting"):
        slicer.SliceJob(
            models=[], output=out, overrides={"wal_loops": 5}
        ).process_config()


def test_parse_result_sums_plates(tmp_path):
    raw = {
        "sliced_plates": [
            {"total_predication": 600.0, "filaments": [{"total_used_g": 3.5}]},
            {
                "total_predication": 3000.0,
                "filaments": [{"total_used_g": 1.0}, {"total_used_g": 2.0}],
            },
        ]
    }
    r = slicer.parse_result(tmp_path / "x.gcode.3mf", raw)
    assert r.seconds == 3600.0
    assert r.grams == 6.5
    assert r.grams_per_filament == [4.5, 2.0]
    assert r.duration == "1h 00m"


def test_flatten_resolves_inherits_and_include(tmp_path):
    (tmp_path / "machine").mkdir()
    for kind in ("process", "filament"):
        (tmp_path / kind).mkdir()
    files = {
        "base": {"name": "base", "a": 1, "b": 1},
        "frag": {"name": "frag", "b": 2, "c": 2},
        "leaf": {"name": "leaf", "inherits": "base", "include": ["frag"], "c": 3},
    }
    for stem, data in files.items():
        (tmp_path / "machine" / f"{stem}.json").write_text(json.dumps(data))
    flat = profiles.ProfileIndex(tmp_path).flatten("machine", "leaf")
    assert flat == {"name": "leaf", "a": 1, "b": 2, "c": 3}


def test_studio_app_from_bin():
    bin_path = Path("/Applications/BambuStudio.app/Contents/MacOS/BambuStudio")
    assert slicer.studio_app(bin_path) == Path("/Applications/BambuStudio.app")
