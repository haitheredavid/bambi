"""Slice models with the Bambu Studio CLI into printer-ready .gcode.3mf files."""

import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from bambi import profiles
from bambi.config import get_settings

# Values Bambu Studio accepts for curr_bed_type. The P1S ships with the Textured PEI plate.
PLATES = (
    "Textured PEI Plate",
    "Cool Plate",
    "Engineering Plate",
    "High Temp Plate",
    "Supertack Plate",
)


# The AMS holds up to 4 units x 4 trays.
MAX_FILAMENTS = 16


class SliceError(RuntimeError):
    pass


@dataclass
class Filament:
    profile: str | None = (
        "pla_basic"  # profiles/filament/<profile>.json; None = from AMS
    )
    color: str | None = None  # "#RRGGBB" preview colour; None keeps the profile's
    ams_slot: int = 0  # AMS tray 0-15 for LAN send, -1 = external spool


@dataclass
class SliceJob:
    models: list[Path]
    output: Path  # .gcode.3mf
    machine: str = "p1s_0.4"
    process: str = "0.20mm_standard"
    filaments: list[Filament] = field(default_factory=lambda: [Filament()])
    # 1-based filament number per entry in `models`; None puts everything on filament 1.
    object_filaments: list[int] | None = None
    orient: bool = True
    arrange: bool = True
    # Multi-colour only: load all models as parts of one object, keeping their relative
    # positions. Needed for inlays and details that don't touch the bed.
    assemble: bool = False
    # Process keys to override, e.g. {"wall_loops": 5}. Values are stringified like the profiles.
    overrides: dict = field(default_factory=dict)
    plate: str = "Textured PEI Plate"

    def __post_init__(self) -> None:
        if self.plate not in PLATES:
            raise ValueError(
                f"unknown plate {self.plate!r}; choose one of: {', '.join(PLATES)}"
            )
        if not 1 <= len(self.filaments) <= MAX_FILAMENTS:
            raise ValueError(f"need 1-{MAX_FILAMENTS} filaments")
        if unset := [n for n, f in enumerate(self.filaments, start=1) if not f.profile]:
            raise ValueError(
                f"filament(s) {unset} have no profile; slice with --ams or run "
                "`bambi printer ams <session> --write`"
            )
        ids = self.object_filaments
        if ids is not None:
            if len(ids) != len(self.models):
                raise ValueError(
                    f"{len(ids)} filament ids for {len(self.models)} models"
                )
            if bad := [i for i in ids if not 1 <= i <= len(self.filaments)]:
                raise ValueError(
                    f"filament ids {bad} out of range 1-{len(self.filaments)}"
                )

    @property
    def multicolor(self) -> bool:
        return len(self.filaments) > 1

    @property
    def filament_names(self) -> str:
        return " + ".join(f.profile or "?" for f in self.filaments)

    def process_config(self) -> dict:
        """The process profile with the build plate and overrides applied (the CLI reads curr_bed_type from it)."""
        data = json.loads(profiles.path_for("process", self.process).read_text())
        data["curr_bed_type"] = self.plate
        for key, value in self.overrides.items():
            if key not in data:
                raise ValueError(f"unknown process setting {key!r} in overrides")
            data[key] = str(value)
        return data

    def filament_configs(self) -> list[dict]:
        """Each filament profile with its preview colour applied."""
        configs = []
        for f in self.filaments:
            data = json.loads(profiles.path_for("filament", f.profile).read_text())
            if f.color:
                data["filament_colour"] = [f.color]
            configs.append(data)
        return configs

    def assemble_list(self) -> dict:
        """Multi-colour input for --load-assemble-list: one plate, each model on its filament.

        Bambu Studio 2.x ignores --load-filament-ids for plain model inputs, so multi-colour
        jobs load models this way instead. The CLI can't combine it with --orient/--arrange;
        need_arrange covers arranging, and models keep their Blender orientation.
        With `assemble`, a shared assemble_index merges the models into one object.
        """
        ids = self.object_filaments or [1] * len(self.models)
        return {
            "plates": [
                {
                    "plate_name": "",
                    "need_arrange": self.arrange,
                    "objects": [
                        {
                            "path": str(m),
                            "count": 1,
                            "filaments": [i],
                            **({"assemble_index": [1]} if self.assemble else {}),
                        }
                        for m, i in zip(self.models, ids)
                    ],
                }
            ]
        }

    def command(
        self,
        process_file: Path,
        filament_files: list[Path] | None = None,
        assemble_file: Path | None = None,
        bin_path: Path | None = None,
    ) -> list[str]:
        machine = profiles.path_for("machine", self.machine)
        process = process_file
        filaments = filament_files or [
            profiles.path_for("filament", f.profile) for f in self.filaments
        ]
        if self.multicolor:
            if assemble_file is None:
                raise ValueError("multi-colour jobs need an assemble list file")
            inputs = [
                "--load-assemble-list",
                str(assemble_file),
                "--allow-multicolor-oneplate",
            ]
            transforms = []
        else:
            inputs = list(map(str, self.models))
            transforms = [
                "--arrange",
                "1" if self.arrange else "0",
                "--orient",
                "1" if self.orient else "0",
            ]
        return [
            str(bin_path or get_settings().bambu_studio_bin),
            "--slice",
            "0",
            *transforms,
            "--load-settings",
            f"{machine};{process}",
            "--load-filaments",
            ";".join(map(str, filaments)),
            "--outputdir",
            str(self.output.parent),
            "--export-3mf",
            self.output.name,
            *inputs,
        ]


@dataclass
class SliceResult:
    output: Path
    seconds: float
    grams: float
    grams_per_filament: list[float]
    raw: dict

    @property
    def duration(self) -> str:
        h, m = divmod(round(self.seconds / 60), 60)
        return f"{h}h {m:02d}m" if h else f"{m}m"


def parse_result(output: Path, raw: dict) -> SliceResult:
    plates = raw.get("sliced_plates", [])
    per: dict[int, float] = {}
    for p in plates:
        for n, f in enumerate(p.get("filaments", []), start=1):
            fid = f.get("id", n)  # 1-based filament number
            per[fid] = per.get(fid, 0.0) + f.get("total_used_g", 0.0)
    return SliceResult(
        output=output,
        seconds=sum(p.get("total_predication", 0.0) for p in plates),
        grams=sum(per.values()),
        grams_per_filament=[per.get(i, 0.0) for i in range(1, max(per, default=0) + 1)],
        raw=raw,
    )


def run(job: SliceJob) -> SliceResult:
    if not job.models:
        raise SliceError("nothing to slice")
    outdir = job.output.parent
    outdir.mkdir(parents=True, exist_ok=True)
    result_file = outdir / "result.json"
    result_file.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        process_file = Path(tmp) / f"{job.process}.json"
        process_file.write_text(json.dumps(job.process_config()))
        filament_files = []
        for n, data in enumerate(job.filament_configs(), start=1):
            path = Path(tmp) / f"filament{n}.json"
            path.write_text(json.dumps(data))
            filament_files.append(path)
        assemble_file = None
        if job.multicolor:
            assemble_file = Path(tmp) / "assemble.json"
            assemble_file.write_text(json.dumps(job.assemble_list()))
        proc = subprocess.run(
            job.command(process_file, filament_files, assemble_file),
            capture_output=True,
            text=True,
            check=False,
        )
    raw = json.loads(result_file.read_text()) if result_file.exists() else {}
    # The CLI also drops loose plate_N.gcode files next to the 3mf; the 3mf already contains them.
    for stray in outdir.glob("plate_*.gcode"):
        stray.unlink()

    if (
        proc.returncode != 0
        or raw.get("return_code", -1) != 0
        or not job.output.exists()
    ):
        # Skip the auto-orient cost table; keep the lines that explain the failure.
        noise = ("orientation:", "best:")
        lines = [
            ln
            for ln in (proc.stdout + proc.stderr).splitlines()
            if ln.strip() and not ln.lstrip().startswith(noise)
        ]
        tail = "\n".join(lines[-8:])
        msg = raw.get("error_string") or f"exit {proc.returncode}"
        raise SliceError(f"slicing failed: {msg}\n{tail}")
    return parse_result(job.output, raw)


def studio_app(bin_path: Path | None = None) -> Path:
    # .../BambuStudio.app/Contents/MacOS/BambuStudio -> .../BambuStudio.app
    return (bin_path or get_settings().bambu_studio_bin).parents[2]


def open_in_studio(file: Path) -> None:
    """Open a sliced .gcode.3mf in the Bambu Studio GUI (reuses a running instance).

    From there Print plate sends it via Bambu Cloud, so this works outside LAN mode.
    """
    app = studio_app()
    if not app.exists():
        raise FileNotFoundError(f"Bambu Studio not found at {app}")
    subprocess.run(["open", "-a", str(app), str(file)], check=True)
