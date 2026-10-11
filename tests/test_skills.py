"""The skills must load in any Agent Skills harness (Claude Code, Codex, opencode)."""

import re
from importlib.resources import files
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = sorted(p.parent for p in (ROOT / "src/bambi/skills").glob("*/SKILL.md"))
DOCS = {p.name.removesuffix(".md") for p in files("bambi").joinpath("docs").iterdir()}
CLAUDE_ONLY = [
    "CLAUDE_PLUGIN_ROOT",
    "/bambi:",
    "mcp__",
    "EnterPlanMode",
    "ExitPlanMode",
]


def frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    assert m, "missing frontmatter"
    return dict(line.split(": ", 1) for line in m.group(1).splitlines())


def test_skills_found():
    assert len(SKILLS) >= 7


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_skill_is_portable(skill: Path):
    text = (skill / "SKILL.md").read_text()
    meta = frontmatter(text)
    assert meta["name"] == skill.name
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", meta["name"])
    assert 0 < len(meta["description"]) <= 1024
    for s in CLAUDE_ONLY:
        assert s not in text, f"Claude-only reference {s!r}"
    for topic in re.findall(r"`bambi docs ([\w-]+)`", text):
        assert topic in DOCS, f"unknown doc {topic}"
