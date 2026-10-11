"""Print workspaces: the folder that holds sessions/, profile overrides and the gallery.

The template ships in the package with its dotfiles renamed (`gitignore` -> `.gitignore`) so
they don't act on the bambi repo itself.
"""

import shutil
from pathlib import Path

from bambi.config import CONFIG_FILE, DATA, configured_home

TEMPLATE = DATA / "workspace_template"
DOTTED = {"gitignore", "gitattributes", "env.example", "claude"}
SUBSTITUTE = {"README.md", "AGENTS.md"}


def init(dest: Path, name: str | None = None) -> list[Path]:
    """Copy the template into `dest`, never overwriting. Returns the files written."""
    name = name or dest.resolve().name
    written = []
    for src in sorted(TEMPLATE.rglob("*")):
        if src.is_dir() or src.name == ".DS_Store":
            continue
        parts = list(src.relative_to(TEMPLATE).parts)
        if parts[0] in DOTTED:
            parts[0] = "." + parts[0]
        out = dest.joinpath(*parts)
        if out.exists():
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        if src.name in SUBSTITUTE:
            out.write_text(src.read_text().replace("{{name}}", name))
        else:
            shutil.copyfile(src, out)
        written.append(out)
    return written


def set_default(dest: Path, config_file: Path = CONFIG_FILE) -> None:
    """Make `dest` the home bambi uses when BAMBI_HOME isn't set."""
    config_file.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        ln
        for ln in (config_file.read_text().splitlines() if config_file.exists() else [])
        if not ln.strip().startswith("home")
    ]
    path = str(dest.resolve()).replace("\\", "\\\\").replace('"', '\\"')
    config_file.write_text("\n".join([f'home = "{path}"', *lines]) + "\n")


def has_default() -> bool:
    return configured_home() is not None
