"""Settings loaded from environment / .env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    bambu_ip: str | None = None
    bambu_access_code: str | None = None
    bambu_serial: str | None = None

    blender_bin: Path = Path("/Applications/Blender.app/Contents/MacOS/Blender")
    bambu_studio_bin: Path = Path(
        "/Applications/BambuStudio.app/Contents/MacOS/BambuStudio"
    )

    sessions_dir: Path = ROOT / "sessions"
    profiles_dir: Path = ROOT / "profiles"
    blender_scripts_dir: Path = ROOT / "blender_scripts"

    @property
    def bambu_system_profiles(self) -> Path:
        # .../BambuStudio.app/Contents/MacOS/BambuStudio -> .../Contents/Resources/profiles/BBL
        return self.bambu_studio_bin.parents[1] / "Resources" / "profiles" / "BBL"


@lru_cache
def get_settings() -> Settings:
    return Settings()
