"""AMS trays as the printer reports them, and matching them to session filaments."""

import json
from dataclasses import dataclass, replace

from bambulabs_api import AMSHub, FilamentTray

from bambi import profiles
from bambi.slicer import Filament

EXTERNAL = -1  # the external spool holder (vt_tray)


@dataclass
class Tray:
    slot: int  # 0-15 (AMS unit * 4 + tray), -1 = external spool
    filament_id: str  # Bambu material code, e.g. GFA00; "" when unknown
    type: str  # PLA, PETG, ...
    sub_brand: str  # e.g. "PLA Matte"; RFID spools only
    color: str  # "#RRGGBB"

    @property
    def label(self) -> str:
        return self.sub_brand or self.type or "unknown"


def _tray(slot: int, t: FilamentTray) -> Tray:
    return Tray(
        slot=slot,
        filament_id=t.tray_info_idx or "",
        type=t.tray_type or "",
        sub_brand=t.tray_sub_brands or "",
        color="#" + (t.tray_color or "000000")[:6].upper(),
    )


def trays_from(hub: AMSHub, external: FilamentTray | None = None) -> list[Tray]:
    """Loaded trays, AMS first (by slot), then the external spool."""
    trays = [
        _tray(int(ams_id) * 4 + int(tray_id), t)
        for ams_id, unit in hub.ams_hub.items()
        for tray_id, t in unit.filament_trays.items()
        if t.tray_type
    ]
    trays.sort(key=lambda t: t.slot)
    if external is not None and external.tray_type:
        trays.append(_tray(EXTERNAL, external))
    return trays


def filaments_from(trays: list[Tray], slots: list[int] | None = None) -> list[Filament]:
    """One filament per tray (all loaded AMS trays, or `slots` in that order)."""
    by_slot = {t.slot: t for t in trays}
    if slots is None:
        slots = [t.slot for t in trays if t.slot != EXTERNAL]
    if missing := [s for s in slots if s not in by_slot]:
        raise ValueError(f"no filament loaded in slot(s) {missing}")
    return [fill(Filament(profile=None, ams_slot=s), by_slot[s]) for s in slots]


def fill(f: Filament, tray: Tray) -> Filament:
    """Fill a filament's missing profile/colour from its tray."""
    profile = f.profile
    if profile is None:
        if not tray.filament_id:
            raise ValueError(
                f"slot {tray.slot} ({tray.label}) has no material code; "
                "set profile by hand"
            )
        profile = profiles.ensure_filament(tray.filament_id)
    return replace(f, profile=profile, color=f.color or tray.color)


def fill_all(filaments: list[Filament], trays: list[Tray]) -> list[Filament]:
    """Fill every filament that lacks a profile or colour from the tray at its ams_slot."""
    by_slot = {t.slot: t for t in trays}
    out = []
    for n, f in enumerate(filaments, start=1):
        if f.profile and f.color:
            out.append(f)
            continue
        if f.ams_slot not in by_slot:
            raise ValueError(f"filament {n}: AMS slot {f.ams_slot} is empty")
        out.append(fill(f, by_slot[f.ams_slot]))
    return out


def material(profile: str) -> tuple[str, str]:
    """(filament_id, filament_type) of a local filament profile."""
    data = json.loads(profiles.path_for("filament", profile).read_text())
    kind = data.get("filament_type", [""])
    return data.get("filament_id", ""), (kind[0] if isinstance(kind, list) else kind)


def check(filaments: list[Filament], trays: list[Tray]) -> tuple[list[str], list[str]]:
    """(errors, warnings) for printing `filaments` from what's loaded now."""
    by_slot = {t.slot: t for t in trays}
    errors, warnings = [], []
    for n, f in enumerate(filaments, start=1):
        where = "external spool" if f.ams_slot == EXTERNAL else f"AMS slot {f.ams_slot}"
        tray = by_slot.get(f.ams_slot)
        if tray is None:
            if f.ams_slot == EXTERNAL:
                continue  # the printer often doesn't report the external spool
            errors.append(f"filament {n}: {where} is empty")
            continue
        fid, want = material(f.profile) if f.profile else ("", "")
        same = fid and fid == tray.filament_id
        if not same and want and tray.type and want.upper() != tray.type.upper():
            errors.append(
                f"filament {n}: {f.profile} is {want} but {where} holds {tray.type}"
            )
        if f.color and f.color.upper() != tray.color:
            warnings.append(
                f"filament {n}: colour {f.color} but {where} is {tray.color} "
                f"({tray.label})"
            )
    return errors, warnings
