"""Settings loaded from environment / .env.

Code and bundled data (profiles, session template, docs) ship in the package. Print work lives
in a separate *workspace*, the `home`: sessions/, profile overrides, the render studio, the
gallery. home = BAMBI_HOME, else `home` in ~/.config/bambi/config.toml, else a source checkout
that still has sessions/ (legacy layout), else ~/bambi. `bambi workspace init` makes one.
"""

import os
import tomllib
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SOURCE = Path(__file__).resolve().parents[2]
CONFIG_DIR = Path.home() / ".config" / "bambi"


DATA = Path(str(files("bambi") / "data"))
CONFIG_FILE = CONFIG_DIR / "config.toml"


def is_checkout(path: Path = SOURCE) -> bool:
    return (path / "pyproject.toml").exists() and (path / "sessions").is_dir()


def configured_home() -> Path | None:
    try:
        home = tomllib.loads(CONFIG_FILE.read_text()).get("home")
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        return None
    return Path(home).expanduser() if home else None


def find_home() -> Path:
    if env := os.environ.get("BAMBI_HOME"):
        return Path(env).expanduser()
    if home := configured_home():
        return home
    if is_checkout():
        return SOURCE
    return Path.home() / "bambi"


# Kept for callers that print paths relative to the data home.
ROOT = find_home()


def _env_files() -> tuple[Path, ...]:
    # Never the cwd .env: bambi runs from other repos (blender-sessions) with their own secrets.
    return tuple(p for p in (CONFIG_DIR / ".env", ROOT / ".env") if p.exists())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_env_files(), extra="ignore")

    bambu_ip: str | None = None
    bambu_access_code: str | None = None
    bambu_serial: str | None = None

    blender_bin: Path = Path("/Applications/Blender.app/Contents/MacOS/Blender")
    bambu_studio_bin: Path = Path(
        "/Applications/BambuStudio.app/Contents/MacOS/BambuStudio"
    )

    home: Path = Field(default=ROOT, validation_alias="BAMBI_HOME")  # not $HOME
    sessions_dir: Path = ROOT / "sessions"
    profiles_dir: Path = ROOT / "profiles"
    blender_scripts_dir: Path = Path(str(files("bambi") / "blender_scripts"))
    bundled_profiles_dir: Path = DATA / "profiles"
    session_template: Path = DATA / "session_template"
    studio_blend: Path = ROOT / "assets" / "studio.blend"

    @property
    def bambu_system_profiles(self) -> Path:
        # .../BambuStudio.app/Contents/MacOS/BambuStudio -> .../Contents/Resources/profiles/BBL
        return self.bambu_studio_bin.parents[1] / "Resources" / "profiles" / "BBL"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def rel(path: Path) -> Path:
    """`path` relative to the data home or cwd when it's under one, for display."""
    for base in (Path.cwd(), ROOT):
        try:
            return path.resolve().relative_to(base.resolve())
        except ValueError:
            continue
    return path
