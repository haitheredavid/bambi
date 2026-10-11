"""Print workspaces: a folder with a session.toml, a model, its exports and outputs.

Two kinds:
- "session": dated folders under sessions/ (bambi models these itself in model.blend).
- "pack": a print pack another repo wrote (blender-sessions `models/<m>/print[/<pack>]/`):
  parts.blend + stl/ + manifest.json, owned upstream. `bambi init` adds a session.toml with
  [paths] pointing at them; bambi never rewrites the pack's own files.
"""

import json
import re
import shutil
import tomllib
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from bambi import profiles, spec
from bambi.config import get_settings
from bambi.results import Results
from bambi.slicer import Filament

TEMPLATE = "_template"
FRAMINGS = ("fit", "wide")  # `bambi render`: zoom to the models, or the whole plate


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        raise ValueError(f"invalid session name: {name!r}")
    return slug


@dataclass
class Session:
    path: Path

    @property
    def config(self) -> dict:
        return tomllib.loads((self.path / "session.toml").read_text())

    @property
    def paths(self) -> dict:
        return self.config.get("paths", {})

    @property
    def kind(self) -> str:
        return self.paths.get("kind", "session")

    @property
    def is_pack(self) -> bool:
        return self.kind == "pack"

    @property
    def name(self) -> str:
        """Folder name for sessions; session.toml `name` for packs (their folder is print/)."""
        return (
            self.config.get("name", self.path.name) if self.is_pack else self.path.name
        )

    @property
    def blend(self) -> Path:
        return self.path / self.paths.get("blend", "model.blend")

    @property
    def exports(self) -> Path:
        return self.path / self.paths.get("exports", "exports")

    @property
    def out(self) -> Path:
        return self.path / self.paths.get("out", "out")

    @property
    def spec(self) -> dict | None:
        return spec.load(self.path)

    def spec_hash(self) -> str | None:
        return spec.spec_hash(self.path, s) if (s := self.spec) else None

    def results(self) -> Results:
        source = self.config.get("source", {}) if self.is_pack else {}
        return Results.load(
            self.path,
            model=source.get("model", self.name),
            pack=source.get("pack", ""),
        )

    def process_settings(self) -> dict:
        """The [slice] process profile with [slice.overrides] applied (string values)."""
        sl = self.config.get("slice", {})
        data = json.loads(
            profiles.path_for(
                "process", sl.get("process", "0.20mm_standard")
            ).read_text()
        )
        data.update({k: str(v) for k, v in sl.get("overrides", {}).items()})
        return data

    def layer_height(self) -> float:
        try:
            return float(self.process_settings().get("layer_height", 0.2))
        except (FileNotFoundError, ValueError):
            return 0.2

    def supports_on(self) -> bool:
        try:
            return str(self.process_settings().get("enable_support", "0")) in (
                "1",
                "true",
            )
        except FileNotFoundError:
            return False

    def in_repo(self) -> bool:
        """Under bambi's own sessions/ (these feed the README gallery)."""
        return self.path.resolve().is_relative_to(get_settings().sessions_dir.resolve())

    def material(self) -> str:
        """'petg' etc. for weight estimates: filament 1's profile, else the spec."""
        profile = self.filaments()[0].profile or ""
        for m in ("petg", "pla", "abs", "asa", "tpu"):
            if m in profile:
                return m
        return spec.material_of(self.spec) if self.spec else "pla"

    def render_options(self) -> dict:
        """[render] framing (fit|wide) and scene for `bambi render`, with defaults."""
        cfg = self.config.get("render", {})
        framing = cfg.get("framing", "fit")
        if framing not in FRAMINGS:
            raise ValueError(
                f"[render] framing must be one of {', '.join(FRAMINGS)}, not {framing!r}"
            )
        return {"framing": framing, "scene": cfg.get("scene")}

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
    # A workspace may keep its own sessions/_template; otherwise use the bundled one.
    template = base / TEMPLATE
    if not template.is_dir():
        template = get_settings().session_template
    shutil.copytree(template, dest, ignore=shutil.ignore_patterns(".DS_Store"))
    toml = dest / "session.toml"
    toml.write_text(
        toml.read_text().replace("{{name}}", slug).replace("{{date}}", dest.name[:10])
    )
    return Session(dest)


def list_all(base: Path | None = None) -> list[Session]:
    base = sessions_dir(base)
    if not base.is_dir():
        return []
    return [
        Session(p)
        for p in sorted(base.iterdir())
        if p.is_dir() and p.name != TEMPLATE and (p / "session.toml").exists()
    ]


def resolve(ref: str, base: Path | None = None, pack: str | None = None) -> Session:
    """Find a workspace by path, or a session by exact folder name or unique substring.

    Paths: a folder with session.toml; a blender-sessions model folder (models/<m>/, with
    model.toml) means its print/ pack, or print/<pack> with `pack`.
    """
    path = Path(ref).expanduser()
    looks_like_path = "/" in ref or ref.startswith((".", "~"))
    if looks_like_path or (path.is_dir() and _is_workspace(path)):
        return _workspace(path, pack)
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


def _is_workspace(path: Path) -> bool:
    return any((path / f).exists() for f in ("session.toml", "model.toml", spec.FILE))


def _workspace(path: Path, pack: str | None) -> Session:
    path = path.resolve()  # Bambu Studio and Blender need absolute paths
    if not path.is_dir():
        raise LookupError(f"no such folder: {path}")
    if (path / "model.toml").exists():  # a blender-sessions model
        model, path = path, path / "print" / (pack or "")
        if not (path / spec.FILE).exists() and not (path / "session.toml").exists():
            packs = sorted(
                p.parent.name for p in (model / "print").glob("*/" + spec.FILE)
            )
            raise LookupError(
                f"no print pack at {path}; run `blend print-pack` first"
                + (
                    f" (other packs: {', '.join(str(model / 'print' / p) for p in packs)})"
                    if packs
                    else ""
                )
            )
    elif pack:
        path = path / pack
    if (path / "session.toml").exists():
        return Session(path)
    if (path / spec.FILE).exists():
        raise LookupError(
            f"{path} is a print pack without a session; run `bambi init {path}`"
        )
    raise LookupError(f"{path} has no session.toml")


PACK_TOML = """name = "{name}"
created = "{created}"
intent = {intent}

[paths]                       # a print pack: the files below belong to the modelling repo
kind = "pack"
blend = "parts.blend"
exports = "stl"
out = "out"                   # bambi's: sliced files (gitignore it upstream)

[source]                      # what `bambi init` read; `bambi status` compares the live spec
repo = "{repo}"
model = "{model}"
pack = "{pack}"
spec_created = "{spec_created}"
spec_hash = "{spec_hash}"

[slice]
machine = "p1s_0.4"           # profiles/machine/<name>.json
process = "{process}"
filament = "{filament}"
plate = "Textured PEI Plate"  # or Cool Plate, Engineering Plate, High Temp Plate, Supertack Plate
orient = false                # packs arrive in print orientation; Bambu's auto-orient fights it
arrange = true
{assemble}{overrides}
[print]
ams_slot = 0                  # AMS tray (0-15), or -1 for external spool
{filaments}"""


def init_pack(
    directory: Path, process: str = "0.20mm_standard", force: bool = False
) -> Session:
    """Write session.toml into a print pack from its spec (manifest.json)."""
    directory = directory.resolve()
    toml = directory / "session.toml"
    if toml.exists() and not force:
        raise FileExistsError(toml)
    sp = spec.load(directory)
    if sp is None:
        raise LookupError(f"no {spec.FILE} in {directory}")
    available = profiles.local_names("filament")
    fils = spec.filaments(sp, available)
    if missing := [n for n, f in enumerate(fils, start=1) if not f["profile"]]:
        raise LookupError(
            f"no local filament profile matches filament(s) {missing} "
            f"({', '.join(fils[n - 1]['material'] for n in missing)}); "
            f"have {', '.join(available)}"
        )
    policy = spec.support_policy(sp)
    overrides = spec.SUPPORT_OVERRIDES.get(policy or "auto", {})
    over = ""
    if overrides:
        over = (
            f"\n[slice.overrides]             # supports = {policy!r} from the spec\n"
            + "".join(f"{k} = {json.dumps(v)}\n" for k, v in overrides.items())
        )
    fil_block = ""
    if len(fils) > 1:
        fil_block = "\n" + "".join(
            f"[[filaments]]                 # filament {n}: {f['material']}\n"
            f'profile = "{f["profile"]}"\n'
            + (f'color = "{f["color"]}"\n' if f.get("color") else "")
            + f"ams_slot = {n - 1}\n\n"
            for n, f in enumerate(fils, start=1)
        )
        if objs := spec.object_filaments(sp):
            fil_block += "[objects]\n" + "".join(
                f"{k} = {v}\n" for k, v in objs.items()
            )
    model = sp.get("model", directory.parent.name)
    pack = sp.get("pack") or ("print" if directory.name == "print" else directory.name)
    text = PACK_TOML.format(
        name=f"{model}-{pack}" if pack != "print" else model,
        created=datetime.now().astimezone().date().isoformat(),
        intent=json.dumps(sp.get("intent") or f"print pack of {model}"),
        repo=(sp.get("source") or {}).get("repo", ""),
        model=model,
        pack=pack,
        spec_created=sp.get("created", ""),
        spec_hash=spec.spec_hash(directory, sp),
        process=process,
        filament=fils[0]["profile"],
        assemble="assemble = true              # colour parts sit inside others\n"
        if spec.needs_assemble(sp)
        else "",
        overrides=over,
        filaments=fil_block,
    )
    tomllib.loads(text)
    toml.write_text(text)
    return Session(directory)
