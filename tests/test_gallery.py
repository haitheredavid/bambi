import zipfile
from datetime import date
from pathlib import Path

import pytest

from bambi import gallery, session

PNG = b"\x89PNG\r\n\x1a\nfake"


def make_3mf(path: Path, plates: dict[int, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("3D/3dmodel.model", "<model/>")
        for n, data in plates.items():
            z.writestr(f"Metadata/plate_{n}.png", data)
    return path


def test_extract_thumb(tmp_path):
    src = make_3mf(tmp_path / "a.gcode.3mf", {1: PNG, 2: b"other"})
    dest = tmp_path / "thumb.png"
    assert gallery.extract_thumb(src, dest) == dest
    assert dest.read_bytes() == PNG
    assert gallery.extract_thumb(src, dest, plate=2) and dest.read_bytes() == b"other"


def test_extract_thumb_missing(tmp_path):
    src = make_3mf(tmp_path / "a.gcode.3mf", {})
    assert gallery.extract_thumb(src, tmp_path / "thumb.png") is None
    (tmp_path / "junk.3mf").write_text("not a zip")
    assert gallery.extract_thumb(tmp_path / "junk.3mf", tmp_path / "t.png") is None
    assert not (tmp_path / "thumb.png").exists()


def test_backfill_only_when_missing(sessions_dir):
    s = session.create("cube", base=sessions_dir, today=date(2026, 9, 26))
    assert gallery.backfill(s) is None  # nothing sliced
    make_3mf(s.out / f"{s.name}.gcode.3mf", {1: PNG})
    assert gallery.backfill(s) == s.path / gallery.THUMB
    assert gallery.backfill(s) is None  # already there


def test_gallery_prefers_render_and_skips_imageless(sessions_dir):
    root = sessions_dir.parent
    a = session.create("cube", base=sessions_dir, today=date(2026, 9, 26))
    b = session.create("stand", base=sessions_dir, today=date(2026, 9, 27))
    c = session.create("nothing", base=sessions_dir, today=date(2026, 9, 27))
    (a.path / gallery.THUMB).write_bytes(PNG)
    (b.path / gallery.THUMB).write_bytes(PNG)
    (b.path / gallery.RENDER).write_bytes(PNG)
    (b.exports / "Stand.stl").write_bytes(b"solid")

    md = gallery.gallery_markdown(session.list_all(sessions_dir), root)
    assert c.name not in md
    assert f"sessions/{b.name}/render.png" in md
    assert f"sessions/{b.name}/thumb.png" not in md
    assert f'<a href="sessions/{b.name}/exports/Stand.stl">' in md
    assert md.index(b.name) < md.index(a.name)  # newest first


def test_gallery_empty(sessions_dir):
    assert "nothing" in gallery.gallery_markdown([], sessions_dir.parent)


def test_update_readme(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(f"# x\n\n{gallery.START}\nold\n{gallery.END}\n\nafter\n")
    assert gallery.update_readme(readme, "new")
    assert (
        readme.read_text() == f"# x\n\n{gallery.START}\nnew\n{gallery.END}\n\nafter\n"
    )
    assert not gallery.update_readme(readme, "new")


def test_update_readme_needs_markers(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("# x\n")
    with pytest.raises(LookupError):
        gallery.update_readme(readme, "new")
