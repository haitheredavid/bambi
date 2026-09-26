"""Worksessions: dated folders under sessions/ holding a model and its outputs."""

import re
import shutil
import tomllib
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from bambi.config import get_settings

TEMPLATE = "_template"


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        raise ValueError(f"invalid session name: {name!r}")
    return slug


@dataclass
class Session:
    path: Path

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def blend(self) -> Path:
        return self.path / "model.blend"

    @property
    def exports(self) -> Path:
        return self.path / "exports"

    @property
    def out(self) -> Path:
        return self.path / "out"

    @property
    def config(self) -> dict:
        return tomllib.loads((self.path / "session.toml").read_text())

    def export_files(self) -> list[Path]:
        return sorted(
            p
            for p in self.exports.glob("*")
            if p.suffix.lower() in {".stl", ".3mf", ".obj"}
        )

    def sliced_files(self) -> list[Path]:
        return sorted(self.out.glob("*.gcode.3mf"))

    def status(self) -> str:
        if self.sliced_files():
            return "sliced"
        if self.export_files():
            return "exported"
        if self.blend.exists():
            return "modeling"
        return "new"


def sessions_dir(base: Path | None = None) -> Path:
    return base or get_settings().sessions_dir


def create(name: str, base: Path | None = None, today: date | None = None) -> Session:
    base = sessions_dir(base)
    slug = slugify(name)
    dest = base / f"{(today or datetime.now().astimezone().date()).isoformat()}-{slug}"
    if dest.exists():
        raise FileExistsError(dest)
    shutil.copytree(base / TEMPLATE, dest, ignore=shutil.ignore_patterns(".DS_Store"))
    toml = dest / "session.toml"
    toml.write_text(
        toml.read_text().replace("{{name}}", slug).replace("{{date}}", dest.name[:10])
    )
    return Session(dest)


def list_all(base: Path | None = None) -> list[Session]:
    base = sessions_dir(base)
    return [
        Session(p)
        for p in sorted(base.iterdir())
        if p.is_dir() and p.name != TEMPLATE and (p / "session.toml").exists()
    ]


def resolve(ref: str, base: Path | None = None) -> Session:
    """Find a session by exact folder name, or by unique substring (e.g. 'phone-stand')."""
    all_sessions = list_all(base)
    exact = [s for s in all_sessions if s.name == ref]
    if exact:
        return exact[0]
    matches = [s for s in all_sessions if ref in s.name]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise LookupError(f"no session matches {ref!r}")
    raise LookupError(f"{ref!r} is ambiguous: {', '.join(s.name for s in matches)}")
