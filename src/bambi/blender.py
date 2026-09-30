"""Run scripts from blender_scripts/ inside headless Blender and collect their JSON results."""

import json
import subprocess
import tempfile
from pathlib import Path

from bambi.config import get_settings


class BlenderError(RuntimeError):
    pass


def run_script(
    script: str,
    blend: Path | None = None,
    args: list[str] | None = None,
    factory_startup: bool = False,
) -> dict:
    """Run blender_scripts/<script> headless. The script must write JSON to the --result path."""
    settings = get_settings()
    script_path = settings.blender_scripts_dir / script
    with tempfile.TemporaryDirectory() as tmp:
        result = Path(tmp) / "result.json"
        cmd = [str(settings.blender_bin), "-b"]
        if factory_startup:
            cmd.append("--factory-startup")
        if blend is not None:
            cmd.append(str(blend))
        cmd += ["-P", str(script_path), "--", "--result", str(result), *(args or [])]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0 or not result.exists():
            tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-25:])
            raise BlenderError(f"{script} failed (exit {proc.returncode}):\n{tail}")
        return json.loads(result.read_text())


def new_blend(path: Path) -> None:
    """Create an empty .blend set up for printing (mm units)."""
    run_script("setup_scene.py", args=["--save", str(path)], factory_startup=True)


def build_studio(path: Path) -> None:
    """Create the render studio .blend (plate, cyclorama, lights, camera)."""
    run_script("build_studio.py", args=["--save", str(path)], factory_startup=True)


def open_gui(blend: Path) -> subprocess.Popen:
    """Open a .blend in the Blender GUI. The blender-mcp add-on auto-starts its bridge on load."""
    return subprocess.Popen(
        [str(get_settings().blender_bin), str(blend)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
