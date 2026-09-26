"""Slice models with the Bambu Studio CLI into printer-ready .gcode.3mf files."""

import json
import subprocess
import tempfile
from dataclasses import dataclass
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


class SliceError(RuntimeError):
    pass


@dataclass
class SliceJob:
    models: list[Path]
    output: Path  # .gcode.3mf
    machine: str = "p1s_0.4"
    process: str = "0.20mm_standard"
    filament: str = "pla_basic"
    orient: bool = True
    arrange: bool = True
    plate: str = "Textured PEI Plate"

    def __post_init__(self) -> None:
        if self.plate not in PLATES:
            raise ValueError(
                f"unknown plate {self.plate!r}; choose one of: {', '.join(PLATES)}"
            )

    def process_config(self) -> dict:
        """The process profile with the build plate applied (the CLI reads curr_bed_type from it)."""
        data = json.loads(profiles.path_for("process", self.process).read_text())
        data["curr_bed_type"] = self.plate
        return data

    def command(self, process_file: Path, bin_path: Path | None = None) -> list[str]:
        machine = profiles.path_for("machine", self.machine)
        process = process_file
        filament = profiles.path_for("filament", self.filament)
        return [
            str(bin_path or get_settings().bambu_studio_bin),
            "--slice",
            "0",
            "--arrange",
            "1" if self.arrange else "0",
            "--orient",
            "1" if self.orient else "0",
            "--load-settings",
            f"{machine};{process}",
            "--load-filaments",
            str(filament),
            "--outputdir",
            str(self.output.parent),
            "--export-3mf",
            self.output.name,
            *map(str, self.models),
        ]


@dataclass
class SliceResult:
    output: Path
    seconds: float
    grams: float
    raw: dict

    @property
    def duration(self) -> str:
        h, m = divmod(round(self.seconds / 60), 60)
        return f"{h}h {m:02d}m" if h else f"{m}m"


def parse_result(output: Path, raw: dict) -> SliceResult:
    plates = raw.get("sliced_plates", [])
    return SliceResult(
        output=output,
        seconds=sum(p.get("total_predication", 0.0) for p in plates),
        grams=sum(
            f.get("total_used_g", 0.0) for p in plates for f in p.get("filaments", [])
        ),
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
        proc = subprocess.run(
            job.command(process_file), capture_output=True, text=True, check=False
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
