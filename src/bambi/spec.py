"""Print specs: the manifest.json a modelling repo (blender-sessions) writes next to a print pack.

The spec carries intent (orientation, supports policy, colour method, joints, coupons), never
Bambu Studio keys; this module translates intent into slice settings. bambi only reads specs.
Schema: `bambi docs print-spec`. Version 0 (no "schema" key) is the original pack
manifest and still loads; its parts simply carry no intent.
"""

import hashlib
import json
from pathlib import Path

FILE = "manifest.json"
SCHEMA = "print-spec/1"

# Strongest wins when parts disagree: the CLI slices a plate with one process.
SUPPORT_POLICIES = ("none", "auto", "build-plate", "everywhere")
SUPPORT_OVERRIDES = {
    "none": {"enable_support": 0},
    "auto": {},  # keep the process profile's choice
    "build-plate": {
        "enable_support": 1,
        "support_type": "normal(auto)",
        "support_on_build_plate_only": 1,
    },
    "everywhere": {"enable_support": 1, "support_type": "tree(auto)"},
}
COLOUR_METHODS = ("single", "ams", "glue-in", "paint", "engrave")
# Preferred profile when several local profiles match a bare material name.
DEFAULT_PROFILE = {"pla": "pla_basic", "petg": "petg_hf"}
# Keys that change between packs of identical geometry; ignored by spec_hash.
VOLATILE = {"created", "feedback_applied", "feedback_declined", "source"}


def load(directory: Path) -> dict | None:
    path = directory / FILE
    return json.loads(path.read_text()) if path.exists() else None


def version(spec: dict) -> int:
    return int(str(spec.get("schema", "print-spec/0")).rsplit("/", 1)[-1])


def parts(spec: dict) -> list[dict]:
    return list(spec.get("parts", []))


def spec_hash(directory: Path, spec: dict) -> str:
    """Identity of a pack's geometry and intent: STL bytes plus the spec minus timestamps."""
    h = hashlib.sha256()
    body = {k: v for k, v in spec.items() if k not in VOLATILE}
    h.update(json.dumps(body, sort_keys=True).encode())
    for p in sorted(parts(spec), key=lambda p: p["name"]):
        stl = directory / p.get("stl", f"stl/{p['name']}.stl")
        if stl.exists():
            h.update(p["name"].encode())
            h.update(hashlib.sha256(stl.read_bytes()).digest())
    return h.hexdigest()[:16]


def support_policy(spec: dict) -> str | None:
    """The strongest supports policy any part asks for, or None if no part says."""
    asked = [
        (p.get("supports") or {}).get("policy")
        for p in parts(spec)
        if isinstance(p.get("supports"), dict)
    ]
    asked = [a for a in asked if a in SUPPORT_POLICIES]
    return max(asked, key=SUPPORT_POLICIES.index) if asked else None


def material_of(spec: dict) -> str:
    """'petg' from 'PETG (Insignia, black)' or the first filament's material."""
    if (fil := spec.get("filaments")) and (m := fil[0].get("material")):
        return m.lower()
    text = str(spec.get("material", "pla")).lower()
    for m in ("petg", "pla", "abs", "asa", "tpu"):
        if m in text:
            return m
    return "pla"


def match_profile(text: str, available: list[str]) -> str | None:
    """Best local filament profile for a free-text material ('PETG (Insignia, black)')."""
    words = set(
        text.lower().replace("(", " ").replace(")", " ").replace(",", " ").split()
    )
    scored = []
    for name in available:
        tokens = name.lower().split("_")
        hits = sum(t in words for t in tokens)
        if hits:
            scored.append((hits, -len(tokens), name))
    if not scored:
        return None
    scored.sort(reverse=True)
    best = [n for h, _, n in scored if h == scored[0][0]]
    if len(best) > 1:
        for m, preferred in DEFAULT_PROFILE.items():
            if m in words and preferred in best:
                return preferred
    return scored[0][2]


def filaments(spec: dict, available: list[str]) -> list[dict]:
    """[{profile, color, material}] in filament order; one entry for single-material specs."""
    entries = spec.get("filaments") or [
        {"id": 1, "material": spec.get("material", "PLA")}
    ]
    out = []
    for e in sorted(entries, key=lambda e: e.get("id", 0)):
        hint = e.get("profile_hint")
        profile = hint if hint in available else None
        if profile is None:
            text = " ".join(str(e.get(k, "")) for k in ("material", "role"))
            if e is entries[0] and not spec.get("filaments"):
                text = str(spec.get("material", "PLA"))
            profile = match_profile(text, available)
        out.append(
            {
                "profile": profile,
                "color": e.get("color"),
                "material": e.get("material") or material_of(spec),
            }
        )
    return out


def object_filaments(spec: dict) -> dict[str, int]:
    """STL stem -> filament number for parts that aren't on filament 1."""
    return {
        Path(p.get("stl", p["name"])).stem: int(p["filament"])
        for p in parts(spec)
        if int(p.get("filament", 1)) != 1
    }


def needs_assemble(spec: dict) -> bool:
    """Colour parts placed in another part (inlays) must be sliced as one object."""
    return any(
        (p.get("colour") or {}).get("method") == "ams"
        and (p.get("colour") or {}).get("into")
        for p in parts(spec)
    )


def coupon(spec: dict, coupon_id: str) -> dict:
    for c in spec.get("coupons", []):
        if c.get("id") == coupon_id:
            return c
    have = ", ".join(c.get("id", "?") for c in spec.get("coupons", [])) or "none"
    raise LookupError(f"no coupon {coupon_id!r} in the spec (have: {have})")


def closed(spec: dict) -> set[str]:
    return set(spec.get("feedback_applied", [])) | set(
        spec.get("feedback_declined", [])
    )
