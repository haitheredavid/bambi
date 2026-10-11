"""Copy the version from pyproject.toml (`uv version`) into the plugin and npm manifests."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = [ROOT / ".claude-plugin" / "plugin.json", ROOT / "npm" / "package.json"]


def main() -> int:
    version = subprocess.run(
        ["uv", "version", "--short"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    check = "--check" in sys.argv
    stale = []
    for path in MANIFESTS:
        data = json.loads(path.read_text())
        if data["version"] == version:
            continue
        stale.append(path.relative_to(ROOT))
        if not check:
            data["version"] = version
            path.write_text(json.dumps(data, indent=2) + "\n")
    if check and stale:
        print(
            f"not at {version}: {', '.join(map(str, stale))}; run `just sync-version`"
        )
        return 1
    print(version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
