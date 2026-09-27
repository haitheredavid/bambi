"""Session thumbnails and the README gallery.

thumb.png comes from the plate preview Bambu Studio embeds in every sliced .gcode.3mf;
render.png is an optional Blender studio shot (`bambi render`). Both live at the session
root so they're committed (out/ is gitignored).
"""

import re
import zipfile
from html import escape
from pathlib import Path

from bambi.session import Session

THUMB = "thumb.png"
RENDER = "render.png"
START = "<!-- gallery:start -->"
END = "<!-- gallery:end -->"
COLUMNS = 3


def extract_thumb(threemf: Path, dest: Path, plate: int = 1) -> Path | None:
    """Copy Metadata/plate_<plate>.png out of a sliced 3mf. None if it has no preview."""
    try:
        with zipfile.ZipFile(threemf) as z:
            data = z.read(f"Metadata/plate_{plate}.png")
    except (KeyError, zipfile.BadZipFile):
        return None
    dest.write_bytes(data)
    return dest


def backfill(s: Session) -> Path | None:
    """Write thumb.png from the newest sliced 3mf if the session doesn't have one yet."""
    thumb = s.path / THUMB
    if thumb.exists() or not (sliced := s.sliced_files()):
        return None
    return extract_thumb(sliced[-1], thumb)


def session_image(s: Session) -> Path | None:
    for name in (RENDER, THUMB):
        if (p := s.path / name).exists():
            return p
    return None


def _cell(s: Session, root: Path) -> str:
    img = session_image(s)
    assert img is not None

    def rel(p: Path) -> str:
        return p.relative_to(root).as_posix()

    stls = [p for p in s.export_files() if p.suffix.lower() == ".stl"]
    image = f'<img src="{rel(img)}" width="240" alt="{escape(s.name)}">'
    if stls:  # GitHub shows a tracked STL in its 3D viewer
        image = f'<a href="{rel(stls[0])}">{image}</a>'
    notes = s.path / "notes.md"
    title = s.name
    title = f'<a href="{rel(notes)}">{title}</a>' if notes.exists() else title
    intent = s.config.get("intent", "")
    lines = [
        '<td align="center" valign="top" width="33%">',
        image,
        f"<br><b>{title}</b>",
    ]
    if intent:
        lines.append(f"<br><sub>{escape(intent)}</sub>")
    return "\n".join(lines) + "\n</td>"


def gallery_markdown(sessions: list[Session], root: Path) -> str:
    """HTML table of sessions with an image, newest first. Paths are relative to root."""
    shown = sorted(
        (s for s in sessions if session_image(s)), key=lambda s: s.name, reverse=True
    )
    if not shown:
        return "_nothing sliced yet_"
    rows = [shown[i : i + COLUMNS] for i in range(0, len(shown), COLUMNS)]
    body = "\n".join(
        "<tr>\n" + "\n".join(_cell(s, root) for s in row) + "\n</tr>" for row in rows
    )
    return f"<table>\n{body}\n</table>"


def update_readme(readme: Path, md: str) -> bool:
    """Replace the text between the gallery markers. True if the file changed."""
    text = readme.read_text()
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
    if not pattern.search(text):
        raise LookupError(f"{readme.name} has no {START} ... {END} block")
    new = pattern.sub(lambda _: f"{START}\n{md}\n{END}", text, count=1)
    if new == text:
        return False
    readme.write_text(new)
    return True
