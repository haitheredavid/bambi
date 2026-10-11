"""Install the bundled skills into an agent harness that has no Claude plugin.

Claude Code gets them from the plugin (`bambi@bambi`); this is for Codex, opencode, or a Claude
setup without the plugin. Each installed skill carries a `.bambi-version` stamp so `bambi doctor`
can spot stale copies.
"""

import json
import shutil
from importlib.metadata import version
from pathlib import Path

from bambi.config import SOURCE

SKILLS = Path(__file__).parent / "skills"
STAMP = ".bambi-version"

# (user dir, project dir relative to the project root)
TARGETS: dict[str, tuple[Path, Path]] = {
    "claude": (Path.home() / ".claude" / "skills", Path(".claude/skills")),
    "codex": (Path.home() / ".codex" / "skills", Path(".agents/skills")),
    "opencode": (
        Path.home() / ".config" / "opencode" / "skills",
        Path(".opencode/skills"),
    ),
    "agents": (Path.home() / ".agents" / "skills", Path(".agents/skills")),
}
# opencode asks before running a command matching this (it has no hooks).
OPENCODE_ASK = "bambi printer send *--start*"


def names() -> list[str]:
    return sorted(p.parent.name for p in SKILLS.glob("*/SKILL.md"))


def bambi_version() -> str:
    return version("bambi")


def target_dir(target: str, project: Path | None = None) -> Path:
    user, proj = TARGETS[target]
    return project / proj if project else user


def install(target: str, project: Path | None = None, link: bool = False) -> list[Path]:
    """Copy (or symlink, for a dev checkout) each skill into the target's skills dir."""
    dest = target_dir(target, project)
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for name in names():
        to = dest / name
        _remove(to)
        if link:
            to.symlink_to(SKILLS / name, target_is_directory=True)
        else:
            shutil.copytree(
                SKILLS / name, to, ignore=shutil.ignore_patterns(".DS_Store")
            )
            (to / STAMP).write_text(bambi_version() + "\n")
        out.append(to)
    if target == "opencode":
        _opencode_permission(project)
    return out


def uninstall(target: str, project: Path | None = None) -> list[Path]:
    dest = target_dir(target, project)
    gone = []
    for name in names():
        to = dest / name
        if _ours(to):
            _remove(to)
            gone.append(to)
    return gone


def installed(target: str, project: Path | None = None) -> dict[str, str]:
    """Skill name -> installed version ('link' for symlinks), for bambi's skills present."""
    dest = target_dir(target, project)
    found = {}
    for name in names():
        to = dest / name
        if to.is_symlink():
            found[name] = "link"
        elif (to / STAMP).exists():
            found[name] = (to / STAMP).read_text().strip()
    return found


def is_checkout() -> bool:
    return SKILLS.resolve().is_relative_to(SOURCE.resolve())


def _ours(path: Path) -> bool:
    return path.is_symlink() or (path / STAMP).exists()


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        if not (path / STAMP).exists():
            raise FileExistsError(f"{path} exists and wasn't installed by bambi")
        shutil.rmtree(path)


def _opencode_permission(project: Path | None) -> Path:
    """Add the print-start rule to opencode.json(c)'s permission.bash, keeping the rest."""
    path = (
        project / "opencode.json"
        if project
        else Path.home() / ".config" / "opencode" / "opencode.json"
    )
    try:
        data = json.loads(path.read_text()) if path.exists() else {}
    except json.JSONDecodeError as e:
        # comments (jsonc) or broken: leave it to the user
        raise ValueError(
            f'{path}: add "permission": {{"bash": {{"{OPENCODE_ASK}": "ask"}}}} by hand'
        ) from e
    perm = data.setdefault("permission", {})
    bash = perm.get("bash")
    if isinstance(bash, str):  # "ask" / "allow" for everything: make it a map
        bash = {"*": bash}
    bash = bash or {}
    bash[OPENCODE_ASK] = "ask"
    perm["bash"] = bash
    data.setdefault("$schema", "https://opencode.ai/config.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    return path
