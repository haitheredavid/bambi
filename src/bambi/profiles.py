"""Flatten Bambu Studio system profiles into standalone JSON the CLI can load.

System profiles chain via "inherits" (parent by name) and "include" (template fragments by
name). The slicer CLI wants a single fully-resolved file per machine/process/filament.
"""

import json
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
