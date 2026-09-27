import json

import pytest
from bambulabs_api import AMS, AMSHub, FilamentTray

from bambi import ams, profiles
from bambi.config import get_settings
from bambi.slicer import Filament


def _tray(idx: str, kind: str, sub: str, color: str) -> FilamentTray:
    return FilamentTray.from_dict(
        {
            "k": 0.02, "n": 1, "tag_uid": "", "tray_id_name": "",
            "tray_info_idx": idx, "tray_type": kind, "tray_sub_brands": sub,
            "tray_color": color, "tray_weight": "1000", "tray_diameter": "1.75",
            "tray_temp": "", "tray_time": "", "bed_temp_type": "", "bed_temp": "",
            "nozzle_temp_max": 230, "nozzle_temp_min": 190, "xcam_info": "",
            "tray_uuid": "",
        }
    )  # fmt: skip


@pytest.fixture
def hub() -> AMSHub:
    unit = AMS(humidity=4, temperature=25.0)
    unit.set_filament_tray(_tray("GFA00", "PLA", "PLA Basic", "FFFFFFFF"), 0)
    unit.set_filament_tray(_tray("GFG02", "PETG", "PETG HF", "000000FF"), 2)
    unit.set_filament_tray(_tray("GFS02", "PLA-S", "Support for PLA", "FFFFFFFF"), 3)
    h = AMSHub()
    h[0] = unit
    return h


@pytest.fixture
def profiles_dir(tmp_path, monkeypatch):
    root = tmp_path / "profiles"
    (root / "filament").mkdir(parents=True)
    for name in ("pla_basic", "petg_hf"):
        src = get_settings().profiles_dir / "filament" / f"{name}.json"
        (root / "filament" / src.name).write_text(src.read_text())
    (root / "filament" / "support.json").write_text(
        json.dumps({"filament_id": "GFS02", "filament_type": ["PLA"]})
    )
    monkeypatch.setenv("PROFILES_DIR", str(root))
    get_settings.cache_clear()
    yield root
    get_settings.cache_clear()


def test_trays_from_hub(hub):
    external = _tray("GFL99", "PLA", "", "FF0000FF")
    trays = ams.trays_from(hub, external)
    assert [(t.slot, t.filament_id, t.color) for t in trays] == [
        (0, "GFA00", "#FFFFFF"),
        (2, "GFG02", "#000000"),
        (3, "GFS02", "#FFFFFF"),
        (-1, "GFL99", "#FF0000"),
    ]
    assert trays[1].label == "PETG HF"
    assert trays[3].label == "PLA"


def test_filaments_from_trays(hub, profiles_dir):
    trays = ams.trays_from(hub)
    fs = ams.filaments_from(trays)
    assert [(f.profile, f.color, f.ams_slot) for f in fs] == [
        ("pla_basic", "#FFFFFF", 0),
        ("petg_hf", "#000000", 2),
        ("support", "#FFFFFF", 3),
    ]
    assert [f.ams_slot for f in ams.filaments_from(trays, [2, 0])] == [2, 0]
    with pytest.raises(ValueError, match="slot"):
        ams.filaments_from(trays, [1])


def test_fill_all(hub, profiles_dir):
    trays = ams.trays_from(hub)
    fs = ams.fill_all(
        [Filament(profile=None, ams_slot=2), Filament("pla_basic", "#123456", 0)],
        trays,
    )
    assert (fs[0].profile, fs[0].color) == ("petg_hf", "#000000")
    assert (fs[1].profile, fs[1].color) == ("pla_basic", "#123456")
    with pytest.raises(ValueError, match="slot 1 is empty"):
        ams.fill_all([Filament(profile=None, ams_slot=1)], trays)


def test_check(hub, profiles_dir):
    trays = ams.trays_from(hub)
    errors, warnings = ams.check(
        [
            Filament("pla_basic", "#FFFFFF", 0),  # ok
            Filament("pla_basic", "#FF0000", 2),  # PETG loaded; colour differs
            Filament("pla_basic", None, 1),  # empty
            Filament("pla_basic", None, -1),  # external not reported: skip
            Filament("support", None, 3),  # PLA profile, PLA-S tray, same id
            Filament("pla_basic", None, 3),  # PLA on a support tray
        ],
        trays,
    )
    assert errors == [
        "filament 2: pla_basic is PLA but AMS slot 2 holds PETG",
        "filament 3: AMS slot 1 is empty",
        "filament 6: pla_basic is PLA but AMS slot 3 holds PLA-S",
    ]
    assert warnings == [
        "filament 2: colour #FF0000 but AMS slot 2 is #000000 (PETG HF)"
    ]


def test_ensure_filament_flattens_system_profile(tmp_path, profiles_dir):
    system = tmp_path / "system" / "filament"
    system.mkdir(parents=True)
    base = {"name": "Bambu PLA Matte @base", "filament_id": "GFA01",
            "filament_type": ["PLA"], "instantiation": "false"}  # fmt: skip
    child = {"name": "Bambu PLA Matte @BBL P1S 0.4 nozzle",
             "inherits": "Bambu PLA Matte @base", "instantiation": "true",
             "compatible_printers": [profiles.PRINTER]}  # fmt: skip
    (system / "base.json").write_text(json.dumps(base))
    (system / "child.json").write_text(json.dumps(child))
    index = profiles.ProfileIndex(tmp_path / "system")

    assert profiles.ensure_filament("GFA00", index) == "pla_basic"  # already local
    assert profiles.ensure_filament("GFA01", index) == "bambu_pla_matte"
    made = json.loads((profiles_dir / "filament" / "bambu_pla_matte.json").read_text())
    assert made["filament_id"] == "GFA01" and "inherits" not in made
    assert profiles.local_filament("GFA01") == "bambu_pla_matte"
    with pytest.raises(LookupError):
        profiles.ensure_filament("GFZ99", index)
