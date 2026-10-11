"""PreToolUse guard: starting a physical print always goes through the user.

Any Bash command that would run `bambi printer send ... --start` (directly, via `just print`,
or `uv run bambi`) gets permissionDecision "ask", whatever the permission mode or allowlist.
"""

import json
import re
import sys

START = re.compile(r"\bprinter\s+send\b[^|;&]*--start|\bjust\s+print(\s|$)")

try:
    event = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(0)
command = (event.get("tool_input") or {}).get("command", "")
if START.search(command):
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": "This starts a physical print on the P1S. "
                "Confirm the plate is clear and the right filament is loaded.",
            }
        },
        sys.stdout,
    )
