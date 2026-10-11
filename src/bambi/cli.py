"""`bambi` command line."""

import json
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from bambi import blender, gallery, mesh, printability, profiles, session, slicer, spec
from bambi.config import ROOT, get_settings, rel

app = typer.Typer(no_args_is_help=True, help="Blender -> Bambu Studio -> P1S sandbox.")
printer_app = typer.Typer(
    no_args_is_help=True,
    help="Talk to the P1S over LAN (use `bambi studio` for cloud).",
)
blender_app = typer.Typer(no_args_is_help=True, help="Blender helpers.")
profiles_app = typer.Typer(no_args_is_help=True, help="Slicer profiles.")
app.add_typer(printer_app, name="printer")
app.add_typer(blender_app, name="blender")
app.add_typer(profiles_app, name="profiles")

console = Console()

SessionArg = Annotated[
    str,
    typer.Argument(
        help="Session folder name or unique part of it, or a path: a workspace with "
        "session.toml, a print pack, or a blender-sessions model folder (= its print/)."
    ),
]


def _session(ref: str) -> session.Session:
    try:
        return session.resolve(ref)
    except LookupError as e:
        console.print(f"[red]{escape(str(e))}[/red]")
        raise typer.Exit(1)


def _refuse_pack(s: session.Session, what: str) -> None:
    if s.is_pack:
        console.print(
            f"[red]{escape(s.name)} is a print pack: {what} belongs to the modelling repo. "
            "Change it there and re-pack (`blend print-pack`), or log a recommendation "
            "with `bambi log rec`.[/red]"
        )
        raise typer.Exit(1)


def _warn_stale(s: session.Session) -> None:
    """A pack re-packed since `bambi init` may have new parts or intent."""
    if not s.is_pack:
        return
    seen = s.config.get("source", {}).get("spec_hash")
    if seen and (now := s.spec_hash()) and now != seen:
        console.print(
            f"[yellow]the pack changed since `bambi init` (spec {seen} -> {now}); "
            "re-run `bambi init --force` if its intent (supports, filaments) changed[/yellow]"
        )


# --- sessions ---------------------------------------------------------------


@app.command()
def new(
    name: str,
    no_blend: Annotated[bool, typer.Option(help="Skip creating model.blend.")] = False,
) -> None:
    """Create sessions/YYYY-MM-DD-<name>/ from the template."""
    s = session.create(name)
    if not no_blend:
        try:
            blender.new_blend(s.blend)
        except blender.BlenderError as e:
            console.print(f"[yellow]couldn't create model.blend:[/yellow] {e}")
    console.print(f"[green]created[/green] {s.path}")


@app.command()
def init(
    directory: Annotated[
        Path,
        typer.Argument(help="Print pack folder (has manifest.json) or model folder."),
    ],
    pack: Annotated[
        str | None, typer.Option(help="Pack under a model's print/, e.g. coupon.")
    ] = None,
    process: Annotated[
        str, typer.Option(help="profiles/process/<name>")
    ] = "0.20mm_standard",
    force: Annotated[
        bool, typer.Option(help="Replace an existing session.toml.")
    ] = False,
) -> None:
    """Make a print pack sliceable: write its session.toml from the spec (manifest.json)."""
    if (directory / "model.toml").exists():
        directory = directory / "print" / (pack or "")
    elif pack:
        directory = directory / pack
    try:
        s = session.init_pack(directory, process=process, force=force)
    except FileExistsError as e:
        console.print(
            f"[yellow]{rel(Path(str(e)))} exists[/yellow] (--force to rewrite)"
        )
        raise typer.Exit(1)
    except LookupError as e:
        console.print(f"[red]{escape(str(e))}[/red]")
        raise typer.Exit(1)
    cfg = s.config
    sl = cfg["slice"]
    console.print(f"[green]wrote[/green] {rel(s.path / 'session.toml')}")
    console.print(
        f"  {s.name}: {len(s.export_files())} parts, {sl['filament']}, {sl['process']}, "
        f"supports {spec.support_policy(s.spec) or 'per profile'}"
        + (", assemble" if sl.get("assemble") else "")
    )
    gitignore = s.path / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("out/\n")


@app.command("ls")
def list_sessions() -> None:
    """List sessions and how far along each is."""
    table = Table("session", "status", "exports", "sliced")
    for s in session.list_all():
        table.add_row(
            s.name, s.status(), str(len(s.export_files())), str(len(s.sliced_files()))
        )
    console.print(table)


# --- pipeline ---------------------------------------------------------------


@app.command()
def export(
    ref: SessionArg,
    objects: Annotated[str, typer.Option(help="Comma-separated object names.")] = "",
    combined: Annotated[
        str, typer.Option(help="Write all objects into one STL with this name.")
    ] = "",
) -> None:
    """Export mesh objects from the session's model.blend to exports/*.stl."""
    s = _session(ref)
    _refuse_pack(s, "stl/")
    if not s.blend.exists():
        console.print(f"[red]{s.blend} does not exist[/red]")
        raise typer.Exit(1)
    args = ["--outdir", str(s.exports)]
    if objects:
        args += ["--objects", objects]
    if combined:
        args += ["--combined", combined]
    res = blender.run_script("export_stl.py", blend=s.blend, args=args)
    for path in res["written"]:
        console.print(f"[green]wrote[/green] {Path(path).relative_to(s.path)}")
    if res["missing"]:
        console.print(f"[yellow]not found:[/yellow] {', '.join(res['missing'])}")
    if not res["written"]:
        console.print("[yellow]no visible mesh objects to export[/yellow]")
        raise typer.Exit(1)


@app.command()
def check(
    ref: SessionArg,
    as_json: Annotated[
        bool, typer.Option("--json", help="Print the report as JSON only.")
    ] = False,
    layers: Annotated[
        bool, typer.Option(help="Layer analysis: ceilings, bridges, thin walls.")
    ] = True,
) -> None:
    """Printability checks: the Blender scene, then each exported part layer by layer.

    Fails (exit 1) on broken meshes and on 'block' findings: unsupported ceilings, ledges
    and islands the current supports setting won't print, and sub-0.4 mm features.
    """
    s = _session(ref)
    out = console if not as_json else Console(quiet=True)
    report, failed = _check(s, out, layers)
    if as_json:
        typer.echo(json.dumps(report, indent=2))
    if failed:
        raise typer.Exit(1)


def _check(s: session.Session, out: Console, layers: bool = True) -> tuple[dict, bool]:
    """Run every check, print tables to `out`, log the run; (report, failed)."""
    material = s.material()
    h, supports = s.layer_height(), s.supports_on()
    report: dict = {
        "workspace": str(s.path),
        "layer_height": h,
        "supports": supports,
        "material": material,
        "scene": [],
        "parts": [],
    }
    failed = False

    if s.blend.exists() and not s.is_pack:  # packs are baked; check the STLs
        res = blender.run_script("check_print.py", blend=s.blend)
        report["scene"] = res["objects"]
        table = Table(
            "object",
            "size mm",
            "non-manifold",
            "overhang",
            "below bed",
            title=s.blend.name,
        )
        for o in res["objects"]:
            bad = o["non_manifold_edges"] or o["below_bed"]
            failed |= bool(bad)
            table.add_row(
                o["name"],
                mesh.size_mm_str(tuple(o["size"])),
                str(o["non_manifold_edges"]),
                f"{o['overhang_fraction']:.0%}",
                "[red]yes[/red]" if o["below_bed"] else "no",
            )
        out.print(table)

    files = [f for f in s.export_files() if f.suffix.lower() == ".stl"]
    if files:
        table = Table(
            "part",
            "size",
            "watertight",
            "solid weight",
            "layers",
            "problems",
            title=f"{s.exports.name}/ at {h:g} mm layers, supports {'on' if supports else 'off'}",
        )
        details = []
        for f in files:
            r = mesh.check(f)
            failed |= bool(r.problems)
            part = {
                "name": f.stem,
                "size": [round(v, 2) for v in r.size_mm],
                "watertight": r.watertight,
                "volume_cm3": round(r.volume_cm3, 2),
                "problems": r.problems,
            }
            sev = "ok" if not r.problems else "block"
            if layers and r.watertight:
                pr = printability.analyse(f, h=h, supports=supports)
                part.update(pr.to_json())
                part["problems"] = r.problems + pr.notes
                sev = max(sev, pr.severity, key=printability.SEVERITY.index)
                details += [
                    (f.stem, x.severity, printability.describe(x))
                    for x in pr.unsupported + pr.thin
                ]
            part["severity"] = sev
            failed |= sev == "block"
            report["parts"].append(part)
            colour = {"ok": "green", "warn": "yellow", "block": "red"}[sev]
            table.add_row(
                f.stem,
                mesh.size_mm_str(r.size_mm),
                "yes" if r.watertight else "[red]no[/red]",
                f"≤{r.solid_weight_g(material):.0f} g",
                f"[{colour}]{sev}[/{colour}]",
                "; ".join(part["problems"]) or "-",
            )
        out.print(table)
        for name, sev, text in details:
            colour = {"warn": "yellow", "block": "red"}.get(sev, "dim")
            out.print(f"  [{colour}]{sev:5}[/{colour}] {escape(name)}: {escape(text)}")
        if s.config.get("slice", {}).get("assemble") and len(files) > 1:
            report["overlaps"] = printability.overlaps_between(files)
            for a, b, v in report["overlaps"]:
                out.print(f"  [yellow]warn [/yellow] {a} and {b} overlap by {v} cm³")

    counts = {
        k: sum(p.get("severity") == k for p in report["parts"])
        for k in printability.SEVERITY
    }
    report["severity"] = "block" if failed else ("warn" if counts["warn"] else "ok")
    s.out.mkdir(parents=True, exist_ok=True)
    (s.out / "check.json").write_text(json.dumps(report, indent=2) + "\n")
    log = s.results()
    log.add_run(
        "check",
        severity=report["severity"],
        summary=counts,
        layer_height=h,
        supports=supports,
        report=str((s.out / "check.json").relative_to(s.path)),
        spec_hash=s.spec_hash(),
    )
    log.save()
    return report, failed


@app.command("slice")
def slice_cmd(
    ref: SessionArg,
    process: Annotated[str | None, typer.Option(help="profiles/process/<name>")] = None,
    filament: Annotated[
        str | None, typer.Option(help="profiles/filament/<name>")
    ] = None,
    machine: Annotated[str | None, typer.Option(help="profiles/machine/<name>")] = None,
    plate: Annotated[
        str | None, typer.Option(help=f"Build plate: {', '.join(slicer.PLATES)}")
    ] = None,
    ams: Annotated[
        bool,
        typer.Option(
            "--ams", help="Fill filaments missing profile/color from the live AMS."
        ),
    ] = False,
) -> None:
    """Slice exports/ into out/<session>.gcode.3mf with Bambu Studio."""
    s = _session(ref)
    _warn_stale(s)
    cfg = s.config.get("slice", {})
    models = [
        f for f in s.export_files() if f.suffix.lower() in {".stl", ".3mf", ".obj"}
    ]
    if not models:
        console.print(
            "[red]nothing to slice; "
            + ("re-run `blend print-pack`" if s.is_pack else "run `bambi export` first")
            + "[/red]"
        )
        raise typer.Exit(1)
    try:
        if filament:  # override forces a single-filament print
            filaments, ids = [slicer.Filament(filament)], None
        else:
            filaments = s.filaments()
            if ams:
                filaments = _ams_module().fill_all(filaments, _live_trays())
            ids = s.object_filament_ids(models) if len(filaments) > 1 else None
        job = slicer.SliceJob(
            models=models,
            output=s.out / f"{s.name}.gcode.3mf",
            machine=machine or cfg.get("machine", "p1s_0.4"),
            process=process or cfg.get("process", "0.20mm_standard"),
            filaments=filaments,
            object_filaments=ids,
            orient=cfg.get("orient", True),
            arrange=cfg.get("arrange", True),
            assemble=cfg.get("assemble", False),
            overrides=cfg.get("overrides", {}),
            plate=plate or cfg.get("plate", "Textured PEI Plate"),
        )
        res = slicer.run(job)
    except (slicer.SliceError, FileNotFoundError, LookupError, ValueError) as e:
        console.print(f"[red]{escape(str(e))}[/red]")
        raise typer.Exit(1)
    console.print(
        f"[green]sliced[/green] {res.output.relative_to(s.path)}: "
        f"{res.duration}, {res.grams:.1f} g "
        f"({job.process}, {job.filament_names}, {job.plate})"
    )
    if job.multicolor:
        for n, f in enumerate(job.filaments, start=1):
            used = [m.stem for m, i in zip(models, ids or []) if i == n]
            grams = (
                res.grams_per_filament[n - 1] if n <= len(res.grams_per_filament) else 0
            )
            console.print(
                f"  filament {n}: {f.profile} {f.color or ''} "
                f"-> AMS slot {f.ams_slot}, {grams:.1f} g: {', '.join(used) or '-'}"
            )
    if gallery.extract_thumb(res.output, s.path / gallery.THUMB):
        console.print(f"[dim]thumb -> {rel(s.path / gallery.THUMB)}[/dim]")
    log = s.results()
    run = log.add_run(
        "slice",
        file=str(res.output.relative_to(s.path)),
        machine=job.machine,
        process=job.process,
        filaments=[f.profile for f in job.filaments],
        plate=job.plate,
        overrides=job.overrides,
        seconds=round(res.seconds),
        grams=round(res.grams, 1),
        grams_per_filament=[round(g, 1) for g in res.grams_per_filament],
        filament_changes=slicer.filament_changes(res.output),
        spec_hash=s.spec_hash(),
    )
    log.save()
    if run["filament_changes"]:
        console.print(f"  {run['filament_changes']} filament changes")
    if s.in_repo():
        _update_gallery()


@app.command()
def build(
    ref: SessionArg,
    ams: Annotated[
        bool, typer.Option("--ams", help="Fill filaments from the live AMS.")
    ] = False,
    strict: Annotated[
        bool, typer.Option(help="Stop before slicing when checks fail.")
    ] = False,
) -> None:
    """export -> check -> slice (packs skip export: their STLs come from upstream)."""
    if not _session(ref).is_pack:
        export(ref)
    try:
        check(ref)
    except typer.Exit:
        if strict:
            console.print("[red]checks failed; not slicing (--strict)[/red]")
            raise
        console.print("[yellow]checks reported problems; slicing anyway[/yellow]")
    slice_cmd(ref, ams=ams)


@app.command()
def studio(ref: SessionArg) -> None:
    """Open the session's sliced .gcode.3mf in Bambu Studio to send via Bambu Cloud."""
    s = _session(ref)
    sliced = s.sliced_files()
    if not sliced:
        console.print("[red]nothing sliced; run `bambi slice` first[/red]")
        raise typer.Exit(1)
    try:
        slicer.open_in_studio(sliced[-1])
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        console.print(f"[red]{escape(str(e))}[/red]")
        raise typer.Exit(1)
    console.print(
        f"opened {sliced[-1].name} in Bambu Studio; use Print plate to send via cloud"
    )


# --- gallery ----------------------------------------------------------------

README = ROOT / "README.md"
TILES = ROOT / "docs" / "gallery"


def _update_gallery() -> None:
    sessions = session.list_all()
    for tile in gallery.write_tiles(sessions, TILES):
        console.print(f"[dim]tile -> {rel(tile)}[/dim]")
    md = gallery.gallery_markdown(sessions, ROOT, TILES)
    try:
        if gallery.update_readme(README, md):
            console.print("[dim]README gallery updated[/dim]")
    except LookupError as e:
        console.print(f"[yellow]{escape(str(e))}[/yellow]")


@app.command("gallery")
def gallery_cmd() -> None:
    """Backfill thumb.png from sliced 3mfs and rewrite the README gallery."""
    for s in session.list_all():
        if thumb := gallery.backfill(s):
            console.print(f"thumb -> {rel(thumb)}")
    _update_gallery()


def _render_colors(s: session.Session) -> list[str]:
    """--color args for render_studio.py: STL stem -> filament colour, '*' for unlisted."""
    cfg = s.config
    entries = cfg.get("filaments") or []
    colors = [e.get("color") for e in entries]
    args = []
    if colors and colors[0]:
        args += ["--color", f"*={colors[0]}"]
    for stem, n in cfg.get("objects", {}).items():
        if 0 < int(n) <= len(colors) and colors[int(n) - 1]:
            args += ["--color", f"{stem}={colors[int(n) - 1]}"]
    return args


@app.command()
def render(
    ref: SessionArg,
    framing: Annotated[
        str | None,
        typer.Option(
            help="fit: zoom to the models; wide: the whole plate "
            "(default: [render] framing, else fit)."
        ),
    ] = None,
    scene: Annotated[
        str | None,
        typer.Option(
            help="Scene to render (default: [render] scene, else the saved one)."
        ),
    ] = None,
) -> None:
    """Studio render of model.blend's visible meshes on the P1S plate to render.png."""
    s = _session(ref)
    if not s.blend.exists():
        console.print("[red]no model.blend[/red]")
        raise typer.Exit(1)
    try:
        opts = s.render_options()
    except ValueError as e:
        console.print(f"[red]{escape(str(e))}[/red]")
        raise typer.Exit(1)
    framing = framing or opts["framing"]
    if framing not in session.FRAMINGS:
        console.print(
            f"[red]--framing must be one of {', '.join(session.FRAMINGS)}[/red]"
        )
        raise typer.Exit(1)
    scene = scene or opts["scene"]
    studio_blend = get_settings().studio_blend
    out = s.path / gallery.RENDER
    try:
        if not studio_blend.exists():
            blender.build_studio(studio_blend)
            console.print(f"[dim]studio -> {rel(studio_blend)}[/dim]")
        res = blender.run_script(
            "render_studio.py",
            blend=s.blend,
            args=[
                "--studio",
                str(studio_blend),
                "--out",
                str(out),
                "--framing",
                framing,
                *(["--scene", scene] if scene else []),
                *_render_colors(s),
            ],
        )
    except blender.BlenderError as e:
        console.print(f"[red]{escape(str(e))}[/red]")
        raise typer.Exit(1)
    console.print(
        f"[green]rendered[/green] {rel(out)} ({res['objects']} objects, {framing})"
    )
    for w in res.get("warnings", []):
        console.print(f"[yellow]{escape(w)}[/yellow]")
    if s.in_repo():
        _update_gallery()


@app.command("render-scene")
def render_scene(
    overwrite: Annotated[
        bool, typer.Option(help="Replace it, discarding hand edits.")
    ] = False,
) -> None:
    """Build the studio .blend `bambi render` uses (P1S plate, cyclorama, lights, camera)."""
    path = get_settings().studio_blend
    if path.exists() and not overwrite:
        console.print(f"[yellow]{rel(path)} exists[/yellow] (--overwrite to rebuild)")
        raise typer.Exit(1)
    try:
        blender.build_studio(path)
    except blender.BlenderError as e:
        console.print(f"[red]{escape(str(e))}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]built[/green] {rel(path)}")


# --- blender ----------------------------------------------------------------


@blender_app.command("open")
def blender_open(ref: SessionArg) -> None:
    """Open the session's model.blend in the Blender GUI (MCP bridge auto-starts)."""
    s = _session(ref)
    if not s.blend.exists() and not s.is_pack:
        blender.new_blend(s.blend)
    blender.open_gui(s.blend)
    console.print(f"opened {s.blend}")


@blender_app.command("orient")
def blender_orient(
    ref: SessionArg,
    no_center: Annotated[bool, typer.Option(help="Only drop to z=0.")] = False,
) -> None:
    """Drop objects onto the bed and centre them; saves model.blend."""
    s = _session(ref)
    _refuse_pack(s, "part placement")
    args = ["--no-center"] if no_center else []
    res = blender.run_script("orient.py", blend=s.blend, args=args)
    for m in res["moved"]:
        console.print(
            f"moved {m['name']} by {', '.join(f'{v:.2f}' for v in m['offset'])}"
        )


# --- profiles ---------------------------------------------------------------


@profiles_app.command("sync")
def profiles_sync(
    overwrite: Annotated[
        bool, typer.Option(help="Replace existing local profiles.")
    ] = False,
) -> None:
    """Flatten Bambu Studio's system profiles into profiles/."""
    written = profiles.sync(overwrite=overwrite)
    for p in written:
        console.print(f"[green]wrote[/green] {p}")
    if not written:
        console.print("all profiles present (use --overwrite to refresh)")


@profiles_app.command("ls")
def profiles_ls() -> None:
    """List local profiles."""
    root = profiles.get_settings().profiles_dir
    for kind in ("machine", "process", "filament"):
        names = sorted(p.stem for p in (root / kind).glob("*.json"))
        console.print(f"[bold]{kind}[/bold]: {', '.join(names) or '-'}")


@profiles_app.command("search")
def profiles_search(kind: str, text: str) -> None:
    """Search Bambu Studio system profile names (kind: machine|process|filament)."""
    index = profiles.ProfileIndex(profiles.get_settings().bambu_system_profiles)
    for name in index.names(kind):
        if text.lower() in name.lower():
            console.print(name)


# --- printer ----------------------------------------------------------------


def _ams_module():
    from bambi import ams  # imports bambulabs_api; keep it off the startup path

    return ams


def _live_trays() -> list:
    from bambi import printer

    try:
        with printer.connect() as p:
            return printer.trays(p)
    except (printer.PrinterConfigError, TimeoutError) as e:
        console.print(f"[red]{escape(str(e))}[/red]")
        raise typer.Exit(1)


def _slot(slot: int) -> str:
    return "external spool" if slot < 0 else f"AMS slot {slot}"


@printer_app.command("status")
def printer_status() -> None:
    """Read-only status snapshot from the printer."""
    from bambi import printer

    try:
        with printer.connect() as p:
            st = printer.status(p)
    except (printer.PrinterConfigError, TimeoutError) as e:
        console.print(f"[red]{escape(str(e))}[/red]")
        raise typer.Exit(1)
    ams = st.pop("ams")
    for k, v in st.items():
        console.print(f"[bold]{k}[/bold]: {v}")
    for t in ams:
        console.print(f"  {_slot(t.slot)}: {t.label} [{t.color}]■[/] {t.color}")


@printer_app.command("ams")
def printer_ams(
    ref: Annotated[
        str | None,
        typer.Argument(help="Session to write filaments into (with --write)."),
    ] = None,
    write: Annotated[
        bool, typer.Option(help="Write the trays as filaments in session.toml.")
    ] = False,
    slots: Annotated[
        str | None,
        typer.Option(
            help="Comma-separated slots to use, in filament order (e.g. 2,0)."
        ),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Replace existing filaments without asking."),
    ] = False,
) -> None:
    """Show what's loaded in the AMS; with --write, turn it into session filaments."""
    ams = _ams_module()
    if write and not ref:
        console.print("[red]--write needs a session[/red]")
        raise typer.Exit(1)
    s = _session(ref) if ref else None
    trays = _live_trays()
    table = Table("slot", "material", "type", "colour", "id", "profile")
    for t in trays:
        local = profiles.local_filament(t.filament_id) if t.filament_id else None
        table.add_row(
            _slot(t.slot),
            t.sub_brand or "-",
            t.type,
            f"[{t.color}]■[/] {t.color}",
            t.filament_id or "-",
            local or ("(new)" if t.filament_id else "unknown: set by hand"),
        )
    console.print(table if trays else "[yellow]no filament loaded[/yellow]")
    if not write or s is None:
        return
    try:
        chosen = [int(x) for x in slots.split(",")] if slots else None
        filaments = ams.filaments_from(trays, chosen)
    except (LookupError, ValueError) as e:
        console.print(f"[red]{escape(str(e))}[/red]")
        raise typer.Exit(1)
    if s.config.get("filaments") and not yes:
        typer.confirm(f"Replace [[filaments]] in {s.name}/session.toml?", abort=True)
    by_slot = {t.slot: t for t in trays}
    notes = [
        f"filament {n}: {by_slot[f.ams_slot].label} ({by_slot[f.ams_slot].filament_id})"
        for n, f in enumerate(filaments, start=1)
    ]
    s.write_filaments(filaments, notes)
    for n, f in enumerate(filaments, start=1):
        console.print(f"  filament {n}: {f.profile} {f.color} <- {_slot(f.ams_slot)}")
    console.print(
        f"[green]wrote[/green] {len(filaments)} filament(s) to {s.name}/session.toml; "
        "map objects to them in \\[objects]"
    )


@printer_app.command("send")
def printer_send(
    ref: SessionArg,
    start: Annotated[bool, typer.Option(help="Start printing after upload.")] = False,
    ams_slot: Annotated[
        int | None, typer.Option(help="AMS tray 0-15, -1 = external spool.")
    ] = None,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Skip the start confirmation.")
    ] = False,
    force: Annotated[
        bool, typer.Option(help="Send even if the AMS trays don't match.")
    ] = False,
    plate: Annotated[
        int, typer.Option(help="Plate to print, for slices with several plates.")
    ] = 1,
) -> None:
    """Upload the session's sliced .gcode.3mf, optionally starting the print."""
    from bambi import printer

    s = _session(ref)
    sliced = s.sliced_files()
    if not sliced:
        console.print("[red]nothing sliced; run `bambi slice` first[/red]")
        raise typer.Exit(1)
    file = sliced[-1]
    plates = printer.plates(file)
    if plate not in plates:
        console.print(
            f"[red]{file.name} has no plate {plate} "
            f"(plates: {', '.join(map(str, plates))})[/red]"
        )
        raise typer.Exit(1)
    filaments = s.filaments()
    if ams_slot is not None:
        if len(filaments) > 1:
            console.print(
                "[red]--ams-slot is single-filament only; "
                "set ams_slot per \\[\\[filaments]] in session.toml[/red]"
            )
            raise typer.Exit(1)
        filaments[0].ams_slot = ams_slot
    mapping = [f.ams_slot for f in filaments]
    if len(mapping) > 1 and min(mapping) < 0:
        console.print(
            "[red]multi-color prints need every filament on an AMS slot[/red]"
        )
        raise typer.Exit(1)
    ams = _ams_module()
    try:
        with printer.connect() as p:
            errors, warnings = ams.check(filaments, printer.trays(p))
            for w in warnings:
                console.print(f"[yellow]{escape(w)}[/yellow]")
            for e in errors:
                console.print(f"[red]{escape(str(e))}[/red]")
            if errors and not force:
                console.print("[red]fix the trays or pass --force[/red]")
                raise typer.Exit(1)
            if start and not yes:
                where = "; ".join(
                    f"{f.profile or '?'} {f.color or ''} from {_slot(f.ams_slot)}"
                    for f in filaments
                )
                of = f" plate {plate}/{len(plates)}" if len(plates) > 1 else ""
                typer.confirm(f"Start printing {file.name}{of}: {where}?", abort=True)
            printer.send(p, file, start=start, ams_mapping=mapping, plate=plate)
    except (printer.PrinterConfigError, TimeoutError, RuntimeError) as e:
        console.print(f"[red]{escape(str(e))}[/red]")
        raise typer.Exit(1)
    console.print(
        f"[green]uploaded[/green] {file.name}"
        + (f" and started plate {plate}" if start else "")
    )
    log = s.results()
    last = log.last("slice")
    log.add_run(
        "print",
        state="started" if start else "uploaded",
        file=str(file.relative_to(s.path)),
        plate=plate,
        slice=last["id"] if last else None,
        ams_mapping=mapping,
    )
    log.save()
    if start and len(plates) > 1 and plate < len(plates):
        console.print(f"next: bambi printer send {s.name} --start --plate {plate + 1}")


# --- readiness ----------------------------------------------------------------

STATUS_STYLE = {
    "ok": "green",
    "info": "dim",
    "todo": "cyan",
    "warn": "yellow",
    "block": "red",
}


@app.command()
def plan(
    ref: SessionArg,
    as_json: Annotated[
        bool, typer.Option("--json", help="Print the readiness rows as JSON only.")
    ] = False,
    orient: Annotated[
        bool, typer.Option(help="Rank orientations for parts that need support.")
    ] = True,
) -> None:
    """Readiness triage: what the workspace needs before slicing, and what resolves it."""
    from bambi import readiness

    s = _session(ref)
    report, _ = _check(s, Console(quiet=True))
    rows = readiness.plan(s, report, orient=orient)
    if as_json:
        typer.echo(
            json.dumps(
                {
                    "workspace": str(s.path),
                    "name": s.name,
                    "kind": s.kind,
                    "ready": readiness.ready(rows),
                    "needs": readiness.to_json(rows),
                    "check": report,
                },
                indent=2,
            )
        )
        return
    table = Table("", "need", "status", "detail", "next", title=f"{s.name} ({s.kind})")
    for r in rows:
        st = STATUS_STYLE[r.status]
        table.add_row(
            r.key, r.need, f"[{st}]{r.status}[/{st}]", escape(r.detail), escape(r.next)
        )
    console.print(table)
    if readiness.ready(rows):
        console.print(
            "[green]ready to slice[/green]: bambi build --strict "
            + escape(str(rel(s.path)))
        )
    else:
        console.print("[red]not ready[/red]: resolve the block rows first")


@app.command()
def orient(
    ref: SessionArg,
    part: Annotated[
        list[str] | None, typer.Option(help="Part (STL stem); repeat. Default: all.")
    ] = None,
    top: Annotated[int, typer.Option(help="Candidates to analyse in full.")] = 4,
    apply: Annotated[
        int | None,
        typer.Option(
            help="Rotate the part in model.blend to this rank (sessions only)."
        ),
    ] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Rank print orientations per part: support area, height, bed contact."""
    import trimesh

    from bambi import orientation

    s = _session(ref)
    files = [f for f in s.export_files() if f.suffix.lower() == ".stl"]
    if part:
        files = [f for f in files if f.stem in part]
        if missing := set(part) - {f.stem for f in files}:
            console.print(
                f"[red]no exported part(s): {', '.join(sorted(missing))}[/red]"
            )
            raise typer.Exit(1)
    h = s.layer_height()
    result = {}
    for f in files:
        ranked = orientation.rank(
            trimesh.load_mesh(f, force="mesh"), h=h, full=top, name=f.stem
        )
        result[f.stem] = [c.to_json() for c in ranked]
        if as_json:
            continue
        table = Table(
            "#",
            "orientation",
            "rotate°",
            "height",
            "contact mm²",
            "support mm²",
            "layers",
            title=f.stem,
        )
        for n, c in enumerate(ranked, start=1):
            d = c.to_json()
            st = STATUS_STYLE.get(d["severity"] or "ok", "dim")
            table.add_row(
                str(n),
                d["label"],
                str(d["rotate_deg"]),
                f"{d['height']:g}",
                f"{d['contact_mm2']:.0f}",
                f"{d['support_mm2']:.0f}",
                f"[{st}]{d['severity']}[/{st}] " + escape("; ".join(d["findings"][:2])),
            )
        console.print(table)
    if as_json:
        typer.echo(json.dumps(result, indent=2))
    if apply is None:
        if not as_json and s.is_pack:
            console.print(
                "[dim]packs keep upstream orientation: propose a change with "
                '`bambi log rec <ws> --target "model.toml:[[print.part]] match=<part> rotate" '
                "--value '[x, y, z]' --reason ...`[/dim]"
            )
        return
    _refuse_pack(s, "part orientation")
    if len(files) != 1:
        console.print("[red]--apply needs exactly one --part[/red]")
        raise typer.Exit(1)
    choice = result[files[0].stem][apply - 1]
    rot = ",".join(str(v) for v in choice["rotate_deg"])
    res = blender.run_script(
        "orient.py",
        blend=s.blend,
        args=["--objects", files[0].stem, "--rotate", rot, "--no-center"],
    )
    console.print(
        f"[green]rotated[/green] {files[0].stem} by {choice['rotate_deg']} and dropped it on the bed"
    )
    for m in res["moved"]:
        console.print(f"  {m['name']}")
    console.print("re-export: bambi build --strict " + escape(s.name))


@app.command("colour")
def colour_cmd(
    ref: SessionArg,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Colour strategies for this workspace: AMS swaps vs glue-in, paint, engrave."""
    from bambi import colour

    s = _session(ref)
    models = [f for f in s.export_files() if f.suffix.lower() == ".stl"]
    fils = s.filaments()
    try:
        ids = s.object_filament_ids(models) if len(fils) > 1 else [1] * len(models)
    except ValueError as e:
        console.print(f"[red]{escape(str(e))}[/red]")
        raise typer.Exit(1)
    sets = colour.layer_sets(list(zip(models, ids)), s.layer_height())
    rows = colour.strategies(sets, len(set(ids)))
    advice = colour.recommend(rows)
    last = s.results().last("slice")
    if as_json:
        typer.echo(
            json.dumps(
                {
                    "filaments": len(fils),
                    "strategies": [r.to_json() for r in rows],
                    "recommend": advice,
                    "sliced_filament_changes": last.get("filament_changes")
                    if last
                    else None,
                },
                indent=2,
            )
        )
        return
    table = Table(
        "strategy", "swaps", "+time", "+purge", "model changes", "note", title=s.name
    )
    for r in rows:
        table.add_row(
            r.name,
            str(r.swaps),
            f"{r.extra_minutes:.0f} min",
            f"{r.extra_grams:.1f} g",
            escape(r.parts_change),
            escape(r.note),
        )
    console.print(table)
    console.print(f"recommend: {escape(advice)}")
    if last and last.get("filament_changes") is not None and len(fils) > 1:
        console.print(
            f"[dim]last slice counted {last['filament_changes']} filament changes[/dim]"
        )


# --- results log --------------------------------------------------------------

log_app = typer.Typer(
    no_args_is_help=True,
    help="Record what happened (prints, coupon fits) and recommend changes upstream.",
)
app.add_typer(log_app, name="log")


def _parse_value(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


@log_app.command("print")
def log_print(
    ref: SessionArg,
    outcome: Annotated[str, typer.Option(help="ok | failed | partial")],
    part: Annotated[str | None, typer.Option(help="Part that failed.")] = None,
    kind: Annotated[
        str | None,
        typer.Option(
            help="sag | warp | adhesion | stringing | fit | layer-shift | snap | spaghetti | other"
        ),
    ] = None,
    z: Annotated[float | None, typer.Option(help="Height of the failure, mm.")] = None,
    note: Annotated[str, typer.Option(help="What you saw.")] = "",
    rec: Annotated[
        list[str] | None,
        typer.Option(
            help='Recommendation "<target>=<value>", split at the last "=" (repeatable). '
            "Use `bambi log rec` when the value itself holds '='."
        ),
    ] = None,
    reason: Annotated[str, typer.Option(help="Why, for --rec.")] = "",
) -> None:
    """Log a print's outcome (and failures) against the last slice."""
    from bambi import results

    s = _session(ref)
    if outcome not in results.OUTCOMES:
        console.print(
            f"[red]--outcome must be one of {', '.join(results.OUTCOMES)}[/red]"
        )
        raise typer.Exit(1)
    if kind and kind not in results.FAILURES:
        console.print(f"[red]--kind must be one of {', '.join(results.FAILURES)}[/red]")
        raise typer.Exit(1)
    log = s.results()
    last = log.last("slice")
    failures = (
        [
            {
                k: v
                for k, v in {
                    "part": part,
                    "kind": kind,
                    "z_mm": z,
                    "note": note,
                }.items()
                if v is not None and v != ""
            }
        ]
        if (part or kind)
        else []
    )
    run = log.add_run(
        "print",
        slice=last["id"] if last else None,
        outcome=outcome,
        failures=failures,
        note=note,
    )
    console.print(f"[green]logged[/green] {run['id']}: {outcome}")
    for r in rec or []:
        target, _, value = r.rpartition("=")  # targets can hold "=" (match=Piece_*)
        made = log.add_recommendation(
            target.strip(),
            _parse_value(value.strip()),
            reason or note,
            source=run["id"],
        )
        console.print(
            f"[green]recommend[/green] {made['id']}: {escape(made['target'])} = {made['value']!r}"
        )
    log.save()


@log_app.command("fit")
def log_fit(
    ref: SessionArg,
    coupon: Annotated[str, typer.Option(help="Coupon id from the spec, or a label.")],
    value: Annotated[str, typer.Option(help="The value that won, e.g. 0.10.")],
    note: Annotated[str, typer.Option()] = "",
    param: Annotated[
        str | None, typer.Option(help="Model parameter it sets (default: the spec's).")
    ] = None,
) -> None:
    """Log a coupon pick; recommends the winning value for the coupon's parameter."""
    s = _session(ref)
    sp = s.spec
    if param is None and sp:
        try:
            param = spec.coupon(sp, coupon).get("param")
        except LookupError as e:
            console.print(f"[yellow]{escape(str(e))}[/yellow]")
    log = s.results()
    material = s.material()
    run = log.add_run(
        "fit",
        coupon=coupon,
        param=param,
        value=_parse_value(value),
        material=material,
        note=note,
    )
    console.print(f"[green]logged[/green] {run['id']}: {coupon} = {value} ({material})")
    if param:
        made = log.add_recommendation(
            param,
            _parse_value(value),
            f"coupon {coupon} pick ({material.upper()}). {note}".strip(),
            source=run["id"],
        )
        console.print(
            f"[green]recommend[/green] {made['id']}: {escape(param)} = {value}"
        )
    log.save()


@log_app.command("rec")
def log_rec(
    ref: SessionArg,
    target: Annotated[
        str,
        typer.Option(
            help="model.toml key or builder param, e.g. builders/joinery.py:TENON_CLEAR"
        ),
    ],
    value: Annotated[str, typer.Option(help="JSON or text value.")],
    reason: Annotated[str, typer.Option()],
    alt: Annotated[str, typer.Option(help="An alternative fix.")] = "",
    source: Annotated[str, typer.Option("--from", help="Run id this came from.")] = "",
) -> None:
    """Recommend a change to the model upstream."""
    s = _session(ref)
    log = s.results()
    made = log.add_recommendation(
        target, _parse_value(value), reason, source=source, alt=alt
    )
    log.save()
    console.print(
        f"[green]recommend[/green] {made['id']}: {escape(target)} = {made['value']!r}"
    )


def _run_facts(r: dict) -> str:
    if r["kind"] == "slice":
        text = f"{round(r['seconds'] / 60)} min, {r['grams']} g, {r['process']}"
        if r.get("filament_changes"):
            text += f", {r['filament_changes']} swaps"
        if r.get("overrides"):
            text += f", overrides {r['overrides']}"
        return text
    if r["kind"] == "check":
        return f"{r['severity']} {r.get('summary', {})}"
    if r["kind"] == "print":
        text = r.get("outcome") or r.get("state", "")
        for f in r.get("failures", []):
            text += f"; {f.get('part', '')} {f.get('kind', '')} z{f.get('z_mm', '')}"
        return text + (f" ({r['note']})" if r.get("note") else "")
    return f"{r['coupon']} = {r['value']} ({r.get('material', '')})"


@log_app.command("show")
def log_show(
    ref: SessionArg,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Runs and recommendations, with which recommendations the model has closed."""
    s = _session(ref)
    log = s.results()
    closed = spec.closed(s.spec) if s.spec else set()
    if as_json:
        data = dict(log.data)
        data["recommendations"] = [
            r | {"status": "closed" if r["id"] in closed else "pending"}
            for r in log.recommendations
        ]
        typer.echo(json.dumps(data, indent=2))
        return
    table = Table("run", "kind", "when", "facts", title=f"{s.name}: runs")
    for r in log.runs:
        facts = _run_facts(r)
        table.add_row(
            r["id"], r["kind"], r["at"][:16].replace("T", " "), escape(str(facts))
        )
    console.print(table)
    if log.recommendations:
        table = Table(
            "rec", "status", "target", "value", "reason", title="recommendations"
        )
        for r in log.recommendations:
            st = "closed" if r["id"] in closed else "[yellow]pending[/yellow]"
            table.add_row(
                r["id"],
                st,
                escape(r["target"]),
                escape(repr(r["value"])),
                escape(r["reason"]),
            )
        console.print(table)
