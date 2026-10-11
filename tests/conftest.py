import shutil
from pathlib import Path

import pytest

from bambi.config import DATA

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sessions_dir(tmp_path: Path) -> Path:
    base = tmp_path / "sessions"
    shutil.copytree(DATA / "session_template", base / "_template")
    return base
