"""Readiness triage: what a workspace still needs before it's worth slicing and printing.

One row per need in the taxonomy (`bambi docs readiness-taxonomy`), each with a
status and the skill or command that resolves it. `bambi plan` prints these; the
/bambi:print router skill reads them as JSON.
"""

from dataclasses import asdict, dataclass

import trimesh

from bambi import colour, orientation, printability, spec
from bambi.session import Session

STATUS = ("ok", "info", "todo", "warn", "block")
# Bambu rejects these filament/plate pairs (or they release mid-print).
BAD_PLATES = {"petg": {"Cool Plate"}, "abs": {"Cool Plate"}, "asa": {"Cool Plate"}}
ORIENT_PARTS = 6  # rank orientations for at most this many blocked parts


@dataclass
class Need:
    key: str  # taxonomy letter
    need: str
    status: str
    detail: str
    next: str = ""


def plan(s: Session, report: dict, orient: bool = True) -> list[Need]:
    parts = report.get("parts", [])
    sp = s.spec
    rows: list[Need] = []

    # A. validity
    broken = [
        f"{p['name']}: {'; '.join(x for x in p['problems'] if 'too large' not in x)}"
        for p in parts
        if any("too large" not in x for x in p["problems"])
        and not p.get("watertight", True)
    ]
    broken += [
        f"{o['name']}: {o['non_manifold_edges']} non-manifold edges"
        for o in report.get("scene", [])
        if o["non_manifold_edges"]
    ]
    broken += [f"{a} + {b} overlap {v} cm³" for a, b, v in report.get("overlaps", [])]
    rows.append(
        Need(
            "A",
            "valid meshes",
            "block" if broken else ("ok" if parts else "todo"),
            "; ".join(broken)
            or (f"{len(parts)} parts watertight" if parts else "no parts"),
            "fix in the model (offset boolean cutters 0.3-0.5 mm, BEAUTY triangulation)"
            if broken
            else ("" if parts else "bambi export"),
        )
    )

    # B. fit
    big = [p["name"] for p in parts if any("too large" in x for x in p["problems"])]
    rows.append(
        Need(
            "B",
            "fits the bed",
            "block" if big else "ok",
            f"too large: {', '.join(big)}" if big else "every part fits 256³",
            "/bambi:print-fit (split + joinery)" if big else "",
        )
    )

    # C + D. orientation and support
    blocked = [
        p
        for p in parts
        if any(r["severity"] == "block" for r in p.get("unsupported", []))
    ]
    supported = report.get("supports")
    loose = [
        f"{p['name']}: {printability.describe(_region(r))}"
        for p in parts
        for r in p.get("unsupported", [])
        if r["severity"] == "block" or (supported and r["kind"] != "overhang")
    ]
    if blocked:
        rows.append(
            Need(
                "D",
                "supported",
                "block",
                "; ".join(loose[:4])
                + (f" (+{len(loose) - 4})" if len(loose) > 4 else ""),
                "/bambi:print-orient: rotate, turn supports on, or fix the model "
                "(45° chamfer under ledges, gable roofs, teardrop holes)",
            )
        )
    else:
        rows.append(
            Need(
                "D",
                "supported",
                "warn" if supported and loose else "ok",
                f"supports on for: {'; '.join(loose[:3])}"
                if supported and loose
                else "nothing needs support"
                if not supported
                else "supports on; no unsupported regions found",
                "check the support scars land on hidden faces"
                if supported and loose
                else "",
            )
        )
    better = _orientation_hints(s, blocked) if orient and blocked else []
    rows.append(
        Need(
            "C",
            "orientation",
            "warn" if better else "info",
            "; ".join(better)
            if better
            else "as modelled"
            + (
                " (spec: " + _orientation_why(sp) + ")"
                if sp and _orientation_why(sp)
                else ""
            ),
            "/bambi:print-orient (weigh strength and the show face first)"
            if better
            else "",
        )
    )

    # E. resolution
    thin_rows = [
        (p["name"], t)
        for p in parts
        for t in p.get("thin", [])
        if t["severity"] != "ok"
    ]
    worst = max((t["severity"] for _, t in thin_rows), key=STATUS.index, default="ok")
    rows.append(
        Need(
            "E",
            "printable detail",
            worst,
            "; ".join(
                f"{n}: {printability.describe(_thin(t))}" for n, t in thin_rows[:3]
            )
            or "walls ≥ 0.8 mm, features ≥ 0.4 mm",
            "thicken walls/features in the model, or accept (tapers print rounded)"
            if thin_rows
            else "",
        )
    )

    # F. adhesion
    weak = [
        f"{p['name']} ({p['contact_mm2']} mm², h/√A {p['aspect']})"
        for p in parts
        if p.get("contact_mm2", 1e9) < printability.CONTACT_MIN
        or p.get("aspect", 0) > printability.ASPECT_MAX
    ]
    rows.append(
        Need(
            "F",
            "bed adhesion",
            "warn" if weak else "ok",
            "small or tall footprint: " + ", ".join(weak) if weak else "footprints OK",
            'brim ([slice.overrides] brim_type = "outer_only") or reorient; chamfer bottom edges 0.4-0.6'
            if weak
            else "",
        )
    )

    # G. assembly
    rows.append(_assembly(s, sp, len(parts)))

    # H. colour
    rows.append(_colour(s))

    # I. material and process
    rows.append(_material(s, sp))

    # J. provenance
    rows.append(_provenance(s, sp))
    return sorted(rows, key=lambda r: r.key)


def ready(rows: list[Need]) -> bool:
    return not any(r.status == "block" for r in rows)


def to_json(rows: list[Need]) -> list[dict]:
    return [asdict(r) for r in rows]


def _region(d: dict) -> printability.Region:
    return printability.Region(
        kind=d["kind"],
        z=tuple(d["z"]),
        area_mm2=d["area_mm2"],
        bbox=tuple(d["bbox"]),
        anchored=d.get("anchored", ""),
        span_mm=d.get("span_mm", 0.0),
        severity=d["severity"],
    )


def _thin(d: dict) -> printability.Thin:
    return printability.Thin(d["kind"], tuple(d["z"]), d["area_mm2"], tuple(d["bbox"]))


def _orientation_why(sp: dict | None) -> str:
    if not sp:
        return ""
    whys = {(p.get("orientation") or {}).get("why") for p in spec.parts(sp)} - {
        None,
        "",
    }
    return "; ".join(sorted(whys)) or str(sp.get("orientation", ""))


def _orientation_hints(s: Session, blocked: list[dict]) -> list[str]:
    hints = []
    h = s.layer_height()
    for p in blocked[:ORIENT_PARTS]:
        path = s.exports / f"{p['name']}.stl"
        if not path.exists():
            continue
        ranked = orientation.rank(
            trimesh.load_mesh(path, force="mesh"), h=h, name=p["name"]
        )
        best = ranked[0]
        if (
            best.label != "as modelled"
            and best.report
            and best.report.severity != "block"
        ):
            hints.append(
                f"{p['name']}: {best.label} (rotate {best.rotate_deg}) needs no support"
            )
    return hints


def _assembly(s: Session, sp: dict | None, count: int) -> Need:
    if not sp or spec.version(sp) < 1:
        return Need(
            "G",
            "assembly",
            "info",
            f"{count} parts; no joint/coupon intent in a spec"
            if count > 1
            else "single part",
        )
    log = s.results()
    picked = {r.get("coupon") for r in log.runs if r["kind"] == "fit"}
    untested = [c["id"] for c in sp.get("coupons", []) if c["id"] not in picked]
    joints = [j for p in spec.parts(sp) for j in p.get("joints", [])]
    loose = [
        j.get("id", j.get("kind", "?")) for j in joints if j.get("clearance_mm") is None
    ]
    if untested:
        return Need(
            "G",
            "assembly",
            "todo",
            f"coupon(s) not yet fitted: {', '.join(untested)}",
            "print the coupon pack, then `bambi log fit --coupon <id> --value <v>`",
        )
    return Need(
        "G",
        "assembly",
        "warn" if loose else "ok",
        f"{len(joints)} joints"
        + (f"; no clearance set on {', '.join(loose)}" if loose else "")
        + (
            f"; coupons fitted: {', '.join(sorted(picked - {None}))}"
            if picked - {None}
            else ""
        ),
        "/bambi:print-fit" if loose else "",
    )


def _colour(s: Session) -> Need:
    fils = s.filaments()
    if len(fils) <= 1:
        return Need("H", "colour", "ok", "single colour")
    models = [f for f in s.export_files() if f.suffix.lower() == ".stl"]
    try:
        ids = s.object_filament_ids(models)
    except ValueError as e:
        return Need("H", "colour", "block", str(e), "/bambi:print-colour")
    if len(set(ids)) < 2:
        return Need(
            "H",
            "colour",
            "block",
            f"{len(fils)} filaments but every part is on filament 1",
            "map parts to filaments in [objects] (/bambi:print-colour)",
        )
    sets = colour.layer_sets(list(zip(models, ids)), s.layer_height())
    rows = colour.strategies(sets, len(fils))
    ams = rows[0]
    floating = [
        m.stem for m in models if trimesh.load_mesh(m, force="mesh").bounds[0][2] > 0.05
    ]
    status = "warn" if ams.swaps > colour.INLAY_SWAP_LIMIT else "ok"
    detail = f"{ams.name}: ~{ams.swaps} swaps (+{ams.extra_minutes:.0f} min, +{ams.extra_grams:.0f} g)"
    if floating and not s.config.get("slice", {}).get("assemble"):
        status = "block"
        detail += f"; {', '.join(floating)} off the bed need [slice] assemble = true"
    return Need(
        "H", "colour", status, detail, colour.recommend(rows) if status != "ok" else ""
    )


def _material(s: Session, sp: dict | None) -> Need:
    cfg = s.config.get("slice", {})
    plate = cfg.get("plate", "Textured PEI Plate")
    material = s.material()
    problems = []
    if plate in BAD_PLATES.get(material, set()):
        problems.append(
            f"{material.upper()} on the {plate}: use Textured PEI or Engineering"
        )
    if sp:
        want = spec.material_of(sp)
        if want != material:
            problems.append(
                f"spec asks for {want.upper()}, session slices {material.upper()}"
            )
    try:
        s.process_settings()
    except FileNotFoundError as e:
        problems.append(str(e))
    return Need(
        "I",
        "material + process",
        "block" if problems else "ok",
        "; ".join(problems)
        or f"{material.upper()}, {cfg.get('process', '0.20mm_standard')}, {plate}",
        "fix [slice] in session.toml" if problems else "",
    )


def _provenance(s: Session, sp: dict | None) -> Need:
    log = s.results()
    notes, status, nxt = [], "ok", ""
    closed = spec.closed(sp) if sp else set()
    pending = log.pending(closed)
    if pending:
        status = "warn"
        notes.append(f"{len(pending)} recommendation(s) not applied upstream")
        nxt = "/bambi:print-log (modelling side: blend print-results, apply, re-pack)"
    if s.is_pack and sp:
        seen = s.config.get("source", {}).get("spec_hash")
        now = s.spec_hash()
        if seen and now != seen:
            status = "warn"
            notes.append(
                "re-packed since `bambi init` (re-init if supports/filaments changed)"
            )
    last = log.last("slice")
    if last is None:
        notes.append("not sliced yet")
        status = max(status, "todo", key=STATUS.index)
    elif sp and last.get("spec_hash") and last["spec_hash"] != s.spec_hash():
        status = "warn"
        notes.append(f"last slice ({last['id']}) predates the current pack")
    elif last:
        notes.append(
            f"last slice {last['id']}: {round(last['seconds'] / 60)} min, {last['grams']} g"
        )
    if closed:
        notes.append(
            f"{len(closed & {r['id'] for r in log.recommendations})} recommendation(s) closed"
        )
    return Need("J", "provenance", status, "; ".join(notes), nxt)
