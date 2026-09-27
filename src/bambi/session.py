"""Worksessions: dated folders under sessions/ holding a model and its outputs."""

import re
import shutil
import tomllib
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from bambi.config import get_settings
from bambi.slicer import Filament

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

    def filaments(self) -> list[Filament]:
        """[[filaments]] in order (filament 1, 2, ...), else the single [slice] filament."""
        cfg = self.config
        entries = cfg.get("filaments")
        if not entries:
            return [
                Filament(
                    profile=cfg.get("slice", {}).get("filament", "pla_basic"),
                    ams_slot=cfg.get("print", {}).get("ams_slot", 0),
                )
            ]
        return [
            Filament(
                profile=e.get("profile"),  # None: fill from the AMS
                color=e.get("color"),
                ams_slot=e.get("ams_slot", n - 1),
            )
            for n, e in enumerate(entries, start=1)
        ]

    def object_filament_ids(self, models: list[Path]) -> list[int]:
        """1-based filament number per model, from [objects] (file stem -> number)."""
        mapping = self.config.get("objects", {})
        stems = {m.stem for m in models}
        if unknown := sorted(set(mapping) - stems):
            raise ValueError(
                f"[objects] names not in exports/: {', '.join(unknown)} "
                f"(have: {', '.join(sorted(stems)) or '-'})"
            )
        return [int(mapping.get(m.stem, 1)) for m in models]

    def write_filaments(
        self, filaments: list[Filament], notes: list[str] | None = None
    ) -> None:
        """Replace the [[filaments]] tables in session.toml, keeping everything else.

        notes[i] becomes a trailing comment on filament i+1's header (e.g. the tray it came from).
        """
        toml = self.path / "session.toml"
        lines = toml.read_text().splitlines()
        block = []
        for n, f in enumerate(filaments):
            note = notes[n] if notes and n < len(notes) else f"filament {n + 1}"
            block += [f"{'[[filaments]]':<30}# {note}", f'profile = "{f.profile}"']
            if f.color:
                block.append(f'color = "{f.color}"')
            block += [f"ams_slot = {f.ams_slot}", ""]

        def header(line: str) -> str | None:
            s = line.strip()
            return s.split("#")[0].strip() if s.startswith("[") else None

        kept, insert_at, i = [], None, 0
        while i < len(lines):
            if header(lines[i]) == "[[filaments]]":
                insert_at = len(kept) if insert_at is None else insert_at
                j = i + 1
                while j < len(lines) and header(lines[j]) is None:
                    j += 1
                # Trailing comments/blank lines belong to whatever comes next.
                while j > i + 1 and (
                    not lines[j - 1].strip() or lines[j - 1].lstrip().startswith("#")
                ):
                    j -= 1
                i = j
                continue
            kept.append(lines[i])
            i += 1
        if insert_at is None:
            objects = [n for n, ln in enumerate(kept) if header(ln) == "[objects]"]
            insert_at = objects[0] if objects else len(kept)
            if insert_at == len(kept) and kept and kept[-1].strip():
                block.insert(0, "")
        kept[insert_at:insert_at] = block
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(kept).rstrip("\n") + "\n")
        tomllib.loads(text)  # never leave a broken session.toml behind
        toml.write_text(text)

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
