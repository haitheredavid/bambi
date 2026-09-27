"""`bambi` command line."""

import subprocess
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from bambi import blender, gallery, mesh, profiles, session, slicer
from bambi.config import ROOT

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
    str, typer.Argument(help="Session folder name or unique part of it.")
]


def _session(ref: str) -> session.Session:
    try:
        return session.resolve(ref)
    except LookupError as e:
        console.print(f"[red]{escape(str(e))}[/red]")
        raise typer.Exit(1)


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
def check(ref: SessionArg) -> None:
    """Printability checks: Blender (source scene) and trimesh (exported files)."""
    s = _session(ref)
    material = s.config.get("slice", {}).get("filament", "pla").split("_")[0]
    failed = False

    if s.blend.exists():
        res = blender.run_script("check_print.py", blend=s.blend)
        table = Table(
            "object",
            "size mm",
            "non-manifold",
            "overhang",
            "below bed",
            title="model.blend",
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
        console.print(table)

    files = s.export_files()
    if files:
        table = Table(
            "file", "size", "watertight", "solid weight", "problems", title="exports/"
        )
        for f in files:
            r = mesh.check(f)
            failed |= bool(r.problems)
            table.add_row(
                f.name,
                mesh.size_mm_str(r.size_mm),
                "yes" if r.watertight else "[red]no[/red]",
                f"≤{r.solid_weight_g(material):.0f} g",
                "; ".join(r.problems) or "-",
            )
        console.print(table)
    if failed:
        raise typer.Exit(1)


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
    cfg = s.config.get("slice", {})
    models = [
        f for f in s.export_files() if f.suffix.lower() in {".stl", ".3mf", ".obj"}
    ]
    if not models:
        console.print("[red]no exports; run `bambi export` first[/red]")
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
        console.print(f"[dim]thumb -> {s.path.relative_to(ROOT) / gallery.THUMB}[/dim]")
    _update_gallery()


@app.command()
def build(
    ref: SessionArg,
    ams: Annotated[
        bool, typer.Option("--ams", help="Fill filaments from the live AMS.")
    ] = False,
) -> None:
    """export -> check -> slice."""
    export(ref)
    try:
        check(ref)
    except typer.Exit:
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


def _update_gallery() -> None:
    md = gallery.gallery_markdown(session.list_all(), ROOT)
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
            console.print(f"thumb -> {thumb.relative_to(ROOT)}")
    _update_gallery()


def _render_colors(s: session.Session) -> list[str]:
    """--color args for render_thumb.py: STL stem -> filament colour, '*' for unlisted."""
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
    scene: Annotated[
        str | None, typer.Option(help="Scene to render (default: the saved one).")
    ] = None,
) -> None:
    """Studio render of model.blend's visible meshes to render.png (headless)."""
    s = _session(ref)
    if not s.blend.exists():
        console.print("[red]no model.blend[/red]")
        raise typer.Exit(1)
    out = s.path / gallery.RENDER
    try:
        res = blender.run_script(
            "render_thumb.py",
            blend=s.blend,
            args=[
                "--out",
                str(out),
                *(["--scene", scene] if scene else []),
                *_render_colors(s),
            ],
        )
    except blender.BlenderError as e:
        console.print(f"[red]{escape(str(e))}[/red]")
        raise typer.Exit(1)
    console.print(
        f"[green]rendered[/green] {out.relative_to(ROOT)} ({res['objects']} objects)"
    )
    _update_gallery()


# --- blender ----------------------------------------------------------------


@blender_app.command("open")
def blender_open(ref: SessionArg) -> None:
    """Open the session's model.blend in the Blender GUI (MCP bridge auto-starts)."""
    s = _session(ref)
    if not s.blend.exists():
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
) -> None:
    """Upload the session's sliced .gcode.3mf, optionally starting the print."""
    from bambi import printer

    s = _session(ref)
    sliced = s.sliced_files()
    if not sliced:
        console.print("[red]nothing sliced; run `bambi slice` first[/red]")
        raise typer.Exit(1)
    file = sliced[-1]
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
                typer.confirm(f"Start printing {file.name}: {where}?", abort=True)
            printer.send(p, file, start=start, ams_mapping=mapping)
    except (printer.PrinterConfigError, TimeoutError, RuntimeError) as e:
        console.print(f"[red]{escape(str(e))}[/red]")
        raise typer.Exit(1)
    console.print(
        f"[green]uploaded[/green] {file.name}" + (" and started" if start else "")
    )
