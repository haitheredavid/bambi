"""`bambi doctor`: is this machine ready for the whole Blender -> slice -> print loop?"""

import socket
from dataclasses import dataclass

from bambi import profiles, skills_install
from bambi.config import CONFIG_FILE, get_settings


@dataclass
class Check:
    name: str
    status: str  # ok | warn | fail
    detail: str


def run() -> list[Check]:
    s = get_settings()
    checks = [
        _exists("blender", s.blender_bin, "set BLENDER_BIN", fail=True),
        _exists("bambu studio", s.bambu_studio_bin, "set BAMBU_STUDIO_BIN", fail=True),
        Check(
            "workspace",
            "ok" if (s.home / "sessions").is_dir() else "warn",
            f"{s.home}"
            + (
                "" if (s.home / "sessions").is_dir() else "; run `bambi workspace init`"
            ),
        ),
        Check(
            "config",
            "ok" if CONFIG_FILE.exists() else "warn",
            str(CONFIG_FILE) if CONFIG_FILE.exists() else "none; BAMBI_HOME or default",
        ),
    ]
    missing = [
        f"{kind}/{name}"
        for kind, name in (("machine", "p1s_0.4"), ("process", "0.20mm_standard"))
        if name not in profiles.local_names(kind)
    ]
    checks.append(
        Check("profiles", "fail" if missing else "ok", ", ".join(missing) or "bundled")
    )
    lan = all((s.bambu_ip, s.bambu_access_code, s.bambu_serial))
    checks.append(
        Check(
            "printer (LAN)",
            "ok" if lan else "warn",
            "configured" if lan else "no .env; cloud via `bambi studio` still works",
        )
    )
    checks.append(
        Check(
            "blender mcp",
            "ok" if _port_open(9876) else "warn",
            ":9876 "
            + ("listening" if _port_open(9876) else "not up (`bambi blender open`)"),
        )
    )
    current = skills_install.bambi_version()
    for target in skills_install.TARGETS:
        found = skills_install.installed(target)
        if found:
            stale = set(found.values()) - {current, "link"}
            checks.append(
                Check(
                    f"skills ({target})",
                    "warn" if stale else "ok",
                    f"stale {', '.join(sorted(stale))}; "
                    f"`bambi skills install --target {target}`"
                    if stale
                    else f"{len(found)} at {current}",
                )
            )
    return checks


def _exists(name: str, path, hint: str, fail: bool = False) -> Check:
    if path.exists():
        return Check(name, "ok", str(path))
    return Check(name, "fail" if fail else "warn", f"{path} missing; {hint}")


def _port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0
