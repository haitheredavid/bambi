import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from bambi import results, session, slicer, spec

FIXTURE = Path(__file__).parent / "fixtures" / "coupon"
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def model(tmp_path: Path) -> Path:
    """A blender-sessions style model folder with a coupon pack."""
    m = tmp_path / "models" / "witch-frame"
    (m / "print").mkdir(parents=True)
    (m / "model.toml").write_text('name = "witch-frame"\n')
    shutil.copytree(FIXTURE, m / "print" / "coupon")
    return m


def test_init_pack_translates_intent(model):
    s = session.init_pack(model / "print" / "coupon")
    cfg = s.config
    assert s.is_pack and s.name == "witch-frame-coupon"
    assert cfg["slice"]["filament"] == "insignia_petg"  # from "PETG (Insignia, black)"
    assert cfg["slice"]["orient"] is False
    assert cfg["slice"]["overrides"]["support_on_build_plate_only"] == 1
    assert cfg["source"]["spec_hash"] == s.spec_hash()
    assert s.blend.name == "parts.blend" and s.exports.name == "stl"
    assert len(s.export_files()) == 3
    with pytest.raises(FileExistsError):
        session.init_pack(model / "print" / "coupon")


def test_resolve_model_folder_and_pack(model):
    with pytest.raises(LookupError, match="bambi init"):
        session.resolve(str(model / "print" / "coupon"))
    session.init_pack(model / "print" / "coupon")
    assert session.resolve(str(model), pack="coupon").name == "witch-frame-coupon"
    assert session.resolve(str(model / "print" / "coupon")).kind == "pack"
    with pytest.raises(LookupError, match="print-pack"):
        session.resolve(str(model))  # no main pack yet


def test_spec_hash_ignores_timestamps_but_not_geometry(model):
    d = model / "print" / "coupon"
    sp = spec.load(d)
    before = spec.spec_hash(d, sp)
    assert (
        spec.spec_hash(d, sp | {"created": "later", "feedback_applied": ["x"]})
        == before
    )
    stl = d / "stl" / "Coupon_C10_Flat_A.stl"
    stl.write_bytes(stl.read_bytes() + b"\0")
    assert spec.spec_hash(d, sp) != before


@pytest.mark.parametrize(
    ("text", "profile"),
    [
        ("PETG (Insignia, black)", "insignia_petg"),
        ("PETG", "petg_hf"),
        ("PLA", "pla_basic"),
        ("Bambu PLA Silk", "bambu_pla_silk"),
        ("TPU", None),
    ],
)
def test_match_profile(text, profile):
    available = [
        "bambu_pla_silk",
        "bambu_support_for_pla",
        "insignia_petg",
        "petg_hf",
        "pla_basic",
    ]
    assert spec.match_profile(text, available) == profile


def test_support_policy_strongest_wins():
    sp = {
        "parts": [
            {"supports": {"policy": "none"}},
            {"supports": {"policy": "build-plate"}},
        ]
    }
    assert spec.support_policy(sp) == "build-plate"
    assert spec.support_policy({"parts": [{}]}) is None


def test_results_log_and_pending(tmp_path):
    log = results.Results.load(tmp_path, model="m", pack="coupon")
    run = log.add_run("fit", coupon="tenon-E", value=0.1)
    rec = log.add_recommendation(
        "builders/joinery.py:TENON_CLEAR", 0.1, "pick", source=run["id"]
    )
    assert rec["id"].startswith("rec-coupon-")  # pack-scoped: ids meet upstream
    log.save()
    again = results.Results.load(tmp_path)
    assert [r["id"] for r in again.pending(set())] == [rec["id"]]
    assert again.pending({rec["id"]}) == []
    with pytest.raises(ValueError):
        log.add_run("bake")


def test_filament_changes_counts_ams_loads(tmp_path):
    threemf = tmp_path / "x.gcode.3mf"
    gcode = "M620 S0A\nT0\n; layer\nM620 S1A\nT1\nM620 S0A\nT0\n"
    with zipfile.ZipFile(threemf, "w") as z:
        z.writestr("Metadata/plate_1.gcode", gcode)
        z.writestr("Metadata/plate_2.gcode", "M620 S0A\n")
    assert slicer.filament_changes(threemf) == 2


@pytest.mark.parametrize(
    ("command", "asks"),
    [
        ("bambi printer send models/x --start -y", True),
        ("uv run bambi printer send coupon --plate 2 --start", True),
        ("just print coupon", True),
        ("just print-pack witch-frame", False),
        ("bambi printer send coupon", False),
        ("bambi check x", False),
    ],
)
def test_send_guard_hook(command, asks):
    hook = ROOT / "hooks" / "guard_send.py"
    out = subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps({"tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert ('"ask"' in out) == asks
