import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sessions_dir(tmp_path: Path) -> Path:
    base = tmp_path / "sessions"
    shutil.copytree(ROOT / "sessions" / "_template", base / "_template")
    return base
