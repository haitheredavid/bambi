"""Flatten Bambu Studio system profiles into standalone JSON the CLI can load.

System profiles chain via "inherits" (parent by name) and "include" (template fragments by
name). The slicer CLI wants a single fully-resolved file per machine/process/filament.
"""

import json
import re
from pathlib import Path

from bambi.config import get_settings

# local name -> (kind, Bambu Studio system profile name)
DEFAULTS: dict[str, tuple[str, str]] = {
    "p1s_0.4": ("machine", "Bambu Lab P1S 0.4 nozzle"),
    "0.20mm_standard": ("process", "0.20mm Standard @BBL X1C"),
    "0.16mm_optimal": ("process", "0.16mm Optimal @BBL X1C"),
    "0.12mm_fine": ("process", "0.12mm Fine @BBL X1C"),
    "0.28mm_extra_draft": ("process", "0.28mm Extra Draft @BBL X1C"),
    "pla_basic": ("filament", "Bambu PLA Basic @BBL P1S 0.4 nozzle"),
    "petg_hf": ("filament", "Bambu PETG HF @BBL P1S 0.4 nozzle"),
}

DROP_KEYS = {"inherits", "include"}

PRINTER = "Bambu Lab P1S 0.4 nozzle"


class ProfileIndex:
    def __init__(self, root: Path):
        self.root = root
        self._by_kind: dict[str, dict[str, Path]] = {}
        for kind in ("machine", "process", "filament"):
            index = {}
            for path in (root / kind).rglob("*.json"):
                try:
                    name = json.loads(path.read_text()).get("name")
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if name:
                    index[name] = path
            self._by_kind[kind] = index

    def names(self, kind: str) -> list[str]:
        return sorted(self._by_kind[kind])

    def flatten(self, kind: str, name: str) -> dict:
        path = self._by_kind[kind].get(name)
        if path is None:
            raise KeyError(f"no {kind} profile named {name!r} in {self.root}")
        own = json.loads(path.read_text())
        merged: dict = {}
        if parent := own.get("inherits"):
            merged.update(self.flatten(kind, parent))
        for fragment in own.get("include", []):
            merged.update(self.flatten(kind, fragment))
        merged.update({k: v for k, v in own.items() if k not in DROP_KEYS})
        return merged

    def find_filament(self, filament_id: str, printer: str = PRINTER) -> str | None:
        """System filament profile for a Bambu material code (AMS tray_info_idx)."""
        matches = []
        for name in self.names("filament"):
            try:
                data = self.flatten("filament", name)
            except KeyError:
                continue  # broken inherits chain
            if (
                data.get("instantiation") == "true"
                and data.get("filament_id") == filament_id
                and printer in data.get("compatible_printers", [])
            ):
                matches.append(name)
        # Prefer the printer-specific variant ("... @BBL P1S 0.4 nozzle").
        matches.sort(key=lambda n: "P1S 0.4" not in n)
        return matches[0] if matches else None


def local_name(system_name: str) -> str:
    """'Bambu PLA Matte @BBL P1S 0.4 nozzle' -> 'bambu_pla_matte'."""
    return re.sub(r"[^a-z0-9]+", "_", system_name.split("@")[0].lower()).strip("_")


def local_filament(filament_id: str, root: Path | None = None) -> str | None:
    """Local profiles/filament/<name> already made for this material code."""
    root = root or get_settings().profiles_dir
    for path in sorted((root / "filament").glob("*.json")):
        try:
            if json.loads(path.read_text()).get("filament_id") == filament_id:
                return path.stem
        except json.JSONDecodeError:
            continue
    return None


def ensure_filament(filament_id: str, index: "ProfileIndex | None" = None) -> str:
    """Local filament profile name for a material code, flattening it on first use."""
    if name := local_filament(filament_id):
        return name
    settings = get_settings()
    index = index or ProfileIndex(settings.bambu_system_profiles)
    system_name = index.find_filament(filament_id)
    if system_name is None:
        raise LookupError(
            f"no Bambu Studio filament profile with id {filament_id} for {PRINTER}"
        )
    name = local_name(system_name)
    data = index.flatten("filament", system_name)
    data["instantiation"] = "true"
    out = settings.profiles_dir / "filament" / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return name


def sync(dest: Path | None = None, overwrite: bool = False) -> list[Path]:
    """Write flattened copies of DEFAULTS into profiles/<kind>/<local>.json."""
    settings = get_settings()
    dest = dest or settings.profiles_dir
    index = ProfileIndex(settings.bambu_system_profiles)
    written = []
    for local, (kind, system_name) in DEFAULTS.items():
        out = dest / kind / f"{local}.json"
        if out.exists() and not overwrite:
            continue
        data = index.flatten(kind, system_name)
        data["instantiation"] = "true"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        written.append(out)
    return written


def path_for(kind: str, local: str) -> Path:
    path = get_settings().profiles_dir / kind / f"{local}.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing; run `bambi profiles sync`")
    return path
