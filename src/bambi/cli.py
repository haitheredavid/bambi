"""`bambi` command line."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from bambi import blender, mesh, profiles, session, slicer

app = typer.Typer(no_args_is_help=True, help="Blender -> Bambu Studio -> P1S sandbox.")
printer_app = typer.Typer(no_args_is_help=True, help="Talk to the P1S over LAN.")
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
        console.print(f"[red]{e}[/red]")
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
    job = slicer.SliceJob(
        models=models,
        output=s.out / f"{s.name}.gcode.3mf",
        machine=machine or cfg.get("machine", "p1s_0.4"),
        process=process or cfg.get("process", "0.20mm_standard"),
        filament=filament or cfg.get("filament", "pla_basic"),
        orient=cfg.get("orient", True),
        arrange=cfg.get("arrange", True),
    )
    try:
        res = slicer.run(job)
    except (slicer.SliceError, FileNotFoundError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print(
        f"[green]sliced[/green] {res.output.relative_to(s.path)}: "
        f"{res.duration}, {res.grams:.1f} g ({job.process}, {job.filament})"
    )


@app.command()
def build(ref: SessionArg) -> None:
    """export -> check -> slice."""
    export(ref)
    try:
        check(ref)
    except typer.Exit:
        console.print("[yellow]checks reported problems; slicing anyway[/yellow]")
    slice_cmd(ref)


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


@printer_app.command("status")
def printer_status() -> None:
    """Read-only status snapshot from the printer."""
    from bambi import printer

    try:
        with printer.connect() as p:
            st = printer.status(p)
    except (printer.PrinterConfigError, TimeoutError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    ams = st.pop("ams")
    for k, v in st.items():
        console.print(f"[bold]{k}[/bold]: {v}")
    for t in ams:
        console.print(
            f"  AMS slot {t['slot']}: {t['type'] or 'empty'} #{t['color'] or ''}"
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
) -> None:
    """Upload the session's sliced .gcode.3mf, optionally starting the print."""
    from bambi import printer

    s = _session(ref)
    sliced = s.sliced_files()
    if not sliced:
        console.print("[red]nothing sliced; run `bambi slice` first[/red]")
        raise typer.Exit(1)
    file = sliced[-1]
    slot = (
        ams_slot
        if ams_slot is not None
        else s.config.get("print", {}).get("ams_slot", 0)
    )
    if start and not yes:
        where = "external spool" if slot < 0 else f"AMS slot {slot}"
        typer.confirm(f"Start printing {file.name} from {where}?", abort=True)
    try:
        with printer.connect() as p:
            printer.send(p, file, start=start, ams_slot=slot)
    except (printer.PrinterConfigError, TimeoutError, RuntimeError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print(
        f"[green]uploaded[/green] {file.name}" + (" and started" if start else "")
    )
