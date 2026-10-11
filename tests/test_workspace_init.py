import tomllib

from bambi import workspace


def test_init_scaffolds_and_keeps_existing(tmp_path):
    dest = tmp_path / "prints"
    (dest).mkdir()
    (dest / "README.md").write_text("mine\n")
    written = {p.relative_to(dest).as_posix() for p in workspace.init(dest)}
    assert {
        ".gitignore",
        ".gitattributes",
        ".env.example",
        ".claude/settings.json",
    } <= written
    assert "README.md" not in written
    assert (dest / "README.md").read_text() == "mine\n"
    assert "# prints" in (dest / "AGENTS.md").read_text()
    assert (dest / "sessions").is_dir()
    assert workspace.init(dest) == []


def test_set_default_replaces_home(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('home = "/old"\nother = 1\n')
    workspace.set_default(tmp_path / "ws", cfg)
    data = tomllib.loads(cfg.read_text())
    assert data == {"home": str((tmp_path / "ws").resolve()), "other": 1}
