"""Session thumbnails and the README gallery.

thumb.png comes from the plate preview Bambu Studio embeds in every sliced .gcode.3mf;
render.png is an optional Blender studio shot (`bambi render`). Both live at the session
root so they're committed (out/ is gitignored). The README shows them as uniform
tiles (docs/gallery/<session>.png) so plate previews and renders sit together in a grid.
"""

import re
import zipfile
from html import escape
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

from bambi.session import Session

THUMB = "thumb.png"
RENDER = "render.png"
START = "<!-- gallery:start -->"
END = "<!-- gallery:end -->"
COLUMNS = 4
TILE = 480
BG_TOP, BG_BOTTOM = (28, 30, 35), (46, 48, 53)


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


def _label(s: Session) -> tuple[str, str]:
    """('colossus tmg', '2026-09-26') from '2026-09-26-colossus-tmg'."""
    if re.match(r"\d{4}-\d{2}-\d{2}-", s.name):
        return s.name[11:].replace("-", " "), s.name[:10]
    return s.name.replace("-", " "), ""


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/System/Library/Fonts/SFNSRounded.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def make_tile(src: Path, title: str, subtitle: str, size: int = TILE) -> Image.Image:
    """Square card: dark backdrop, the image fitted in, caption bar, rounded corners."""
    img = Image.open(src).convert("RGBA")
    tile = Image.new("RGBA", (size, size))
    draw = ImageDraw.Draw(tile)
    for y in range(size):  # vertical gradient, same palette as render_thumb.py
        k = y / (size - 1)
        c = tuple(round(a + (b - a) * k) for a, b in zip(BG_TOP, BG_BOTTOM))
        draw.line([(0, y), (size, y)], fill=(*c, 255))

    caption_h = size // 6
    if img.getextrema()[3][0] == 255:  # opaque (a render): cover the whole card
        fitted = ImageOps.fit(img, (size, size), Image.Resampling.LANCZOS)
        tile.alpha_composite(fitted)
    else:  # transparent plate preview: fit above the caption with some air
        box = size - caption_h - size // 10
        fitted = ImageOps.contain(img, (box, box), Image.Resampling.LANCZOS)
        x = (size - fitted.width) // 2
        y = (size - caption_h - fitted.height) // 2
        tile.alpha_composite(fitted, (x, y))

    shade = Image.new("RGBA", (size, caption_h), (12, 13, 16, 200))
    tile.alpha_composite(shade, (0, size - caption_h))
    pad = size // 22
    draw = ImageDraw.Draw(tile)
    draw.text(
        (pad, size - caption_h + pad * 0.7),
        title,
        font=_font(size // 17),
        fill=(240, 240, 242, 255),
    )
    draw.text(
        (pad, size - pad * 0.8),
        subtitle,
        font=_font(size // 26),
        fill=(150, 154, 162, 255),
        anchor="ls",
    )

    mask = Image.new("L", (size, size))
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=size // 18, fill=255
    )
    tile.putalpha(ImageChops.multiply(tile.getchannel("A"), mask))
    return tile


def _shown(sessions: list[Session]) -> list[Session]:
    return sorted(
        (s for s in sessions if session_image(s)), key=lambda s: s.name, reverse=True
    )


def write_tiles(sessions: list[Session], tiles: Path) -> list[Path]:
    """Render tiles/<session>.png for every session with an image; returns the changed ones."""
    tiles.mkdir(parents=True, exist_ok=True)
    changed = []
    for s in _shown(sessions):
        buf = BytesIO()
        img = session_image(s)
        assert img is not None
        make_tile(img, *_label(s)).save(buf, "PNG", optimize=True)
        dest = tiles / f"{s.name}.png"
        if not dest.exists() or dest.read_bytes() != buf.getvalue():
            dest.write_bytes(buf.getvalue())
            changed.append(dest)
    return changed


def gallery_markdown(sessions: list[Session], root: Path, tiles: Path) -> str:
    """A borderless grid of tile links, newest first. Paths are relative to root."""
    shown = _shown(sessions)
    if not shown:
        return "_nothing sliced yet_"

    def rel(p: Path) -> str:
        return p.relative_to(root).as_posix()

    links = []
    for s in shown:
        tip = escape(s.config.get("intent", "") or s.name, quote=True)
        img = (
            f'<img src="{rel(tiles / f"{s.name}.png")}" width="{100 // COLUMNS - 1}%" '
            f'alt="{escape(s.name, quote=True)}" title="{tip}">'
        )
        # clicking a tile opens the STL in GitHub's 3D viewer, else the notes
        stls = [p for p in s.export_files() if p.suffix.lower() == ".stl"]
        target = stls[0] if stls else s.path / "notes.md"
        links.append(f'<a href="{rel(target)}">{img}</a>')
    return '<p align="center">\n' + "\n".join(links) + "\n</p>"


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
